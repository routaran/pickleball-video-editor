"""Dataset pipeline for rally winner classification training.

Handles:
1. Discovery and filtering of schema-1.1 .training.json label files
2. Clip extraction via ml.video_features (decord / torchvision, disk-cached)
3. Per-frame court homography warp to canonical 256x128 view
4. Video-wise 80/20 train/val split (no data leakage within a single video)
5. Augmentation for the train split: horizontal flip + label swap, color jitter,
   temporal jitter

Public API
----------
WinnerDataset  -- PyTorch Dataset yielding (clip_tensor, winning_team) pairs
load_winner_dataset  -- factory that scans a root directory and returns a split
"""

import json
import logging
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchvision.transforms.functional as TF
from torch.utils.data import Dataset

from ml.config import WinnerModelConfig
from ml.video_features import (
    compute_homography,
    extract_clip,
    warp_clip_to_canonical,
)


__all__ = [
    "WinnerDataset",
    "load_winner_dataset",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _parse_version(version_str: str) -> tuple[int, ...]:
    """Convert a dotted version string like '1.1' to a comparable tuple.

    Args:
        version_str: Version string in 'MAJOR.MINOR[.PATCH]' format.

    Returns:
        Tuple of integers, e.g. (1, 1).
    """
    parts = version_str.strip().split(".")
    result: list[int] = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            break
    return tuple(result)


def _is_usable_training_file(data: dict[str, Any]) -> bool:
    """Return True if this training JSON is eligible for winner-classifier training.

    Eligibility criteria (all must hold):
    - schema_version >= 1.1
    - court_corners is present and non-null (stored at video.court_corners)
    - generated_by is not "auto_edit"

    Args:
        data: Parsed training JSON dictionary.

    Returns:
        True if the file should be included; False otherwise.
    """
    schema_str = data.get("schema_version", "0")
    if _parse_version(schema_str) < (1, 1):
        return False

    # court_corners lives under the video block in schema 1.1
    video_block = data.get("video", {})
    corners = video_block.get("court_corners")
    if not corners:
        return False

    if data.get("generated_by") == "auto_edit":
        return False

    return True


# ---------------------------------------------------------------------------
# Rally record
# ---------------------------------------------------------------------------

class _RallyRecord:
    """Lightweight container for a single rally's clip metadata.

    Attributes:
        video_path: Absolute path to the source video file.
        end_seconds: Rally end timestamp in seconds (clip anchor).
        corners: Four (x, y) court-corner pixel coordinates.
        winning_team: Ground-truth label (0 or 1).
    """

    __slots__ = ("video_path", "end_seconds", "corners", "winning_team")

    def __init__(
        self,
        video_path: Path,
        end_seconds: float,
        corners: list[tuple[int, int]],
        winning_team: int,
    ) -> None:
        self.video_path = video_path
        self.end_seconds = end_seconds
        self.corners = corners
        self.winning_team = winning_team


# ---------------------------------------------------------------------------
# Augmentation helpers
# ---------------------------------------------------------------------------

def _apply_color_jitter(
    frames_hwc: np.ndarray,
    brightness: float,
    contrast: float,
    saturation: float,
) -> np.ndarray:
    """Apply identical random color jitter to all frames in a clip.

    Converts numpy (T, H, W, 3) uint8 → torch, applies jitter per-frame
    with the same random factors, returns numpy uint8.

    Args:
        frames_hwc: Clip array with shape (T, H, W, 3), dtype uint8.
        brightness: Maximum absolute brightness delta (e.g. 0.2).
        contrast: Maximum absolute contrast delta.
        saturation: Maximum absolute saturation delta.

    Returns:
        Augmented clip with the same shape and dtype.
    """
    # Sample random factors once so all frames are shifted identically.
    brightness_factor = 1.0 + random.uniform(-brightness, brightness)
    contrast_factor = 1.0 + random.uniform(-contrast, contrast)
    saturation_factor = 1.0 + random.uniform(-saturation, saturation)

    # Clamp factors to valid range [0, +inf) — TF accepts values >= 0.
    brightness_factor = max(0.0, brightness_factor)
    contrast_factor = max(0.0, contrast_factor)
    saturation_factor = max(0.0, saturation_factor)

    result = np.empty_like(frames_hwc)
    for t, frame in enumerate(frames_hwc):
        # Convert (H, W, 3) uint8 → (3, H, W) uint8 tensor
        tensor = torch.from_numpy(frame).permute(2, 0, 1)  # (3, H, W)
        tensor = TF.adjust_brightness(tensor, brightness_factor)
        tensor = TF.adjust_contrast(tensor, contrast_factor)
        tensor = TF.adjust_saturation(tensor, saturation_factor)
        result[t] = tensor.permute(1, 2, 0).numpy()

    return result


def _horizontal_flip_frames(frames_hwc: np.ndarray) -> np.ndarray:
    """Flip every frame in the clip horizontally (left-right mirror).

    Args:
        frames_hwc: Shape (T, H, W, 3) uint8.

    Returns:
        Mirrored array with the same shape.
    """
    # np.flip on axis=2 (width) is zero-copy; ascontiguousarray makes it safe
    # to pass to downstream code that expects C-contiguous memory.
    return np.ascontiguousarray(np.flip(frames_hwc, axis=2))


# ---------------------------------------------------------------------------
# Core per-sample fetch
# ---------------------------------------------------------------------------

def _fetch_clip_tensor(
    record: _RallyRecord,
    config: WinnerModelConfig,
    temporal_jitter_s: float = 0.0,
) -> np.ndarray:
    """Extract, warp, and return one clip as (T, H, W, 3) uint8.

    The clip window is ``[end - duration + jitter, end + jitter]`` clamped
    to ``[0, video_end]``.  The warp uses the four corners stored in *record*
    to produce a perspective-corrected canonical view.

    Args:
        record: Rally metadata including video path, timestamps, corners.
        config: WinnerModelConfig specifying fps_out, clip_duration_s, etc.
        temporal_jitter_s: Shift (seconds) to apply to the clip start.
                           Positive shifts the window later; negative earlier.

    Returns:
        Numpy array of shape (T, H_canon, W_canon, 3), dtype uint8.
    """
    canonical_size = (config.canonical_width, config.canonical_height)

    raw_start = record.end_seconds - config.clip_duration_s + temporal_jitter_s
    start_s = max(0.0, raw_start)
    end_s = record.end_seconds + temporal_jitter_s
    # Ensure end_s is always after start_s (temporal jitter can shift both together)
    end_s = max(end_s, start_s + 0.1)

    frames = extract_clip(
        record.video_path,
        start_s,
        end_s,
        config.fps_out,
        canonical_size,
    )

    homography = compute_homography(record.corners, canonical_size)
    warped = warp_clip_to_canonical(frames, homography, canonical_size)
    return warped  # (T, H_canon, W_canon, 3) uint8


def _to_float_tensor(frames_hwc: np.ndarray) -> torch.Tensor:
    """Convert (T, H, W, 3) uint8 numpy array to (T, 3, H, W) float32 tensor in [0, 1].

    Args:
        frames_hwc: Source array, dtype uint8, values 0–255.

    Returns:
        Float32 tensor normalized to [0, 1] with shape (T, 3, H, W).
    """
    # (T, H, W, 3) → (T, 3, H, W), divide by 255
    tensor = torch.from_numpy(frames_hwc).permute(0, 3, 1, 2).float()
    tensor = tensor.div(255.0)
    return tensor


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class WinnerDataset(Dataset):
    """PyTorch Dataset yielding (clip_tensor, winning_team) pairs.

    Each item is a short video clip at the end of a pickleball rally, warped
    to a canonical top-down court view, together with the ground-truth label
    indicating which team won that rally.

    Clip tensor shape: ``(T, 3, H, W)`` float32, values in ``[0, 1]``.
    Label: integer 0 (team 0 won) or 1 (team 1 won).

    Args:
        training_json_paths: Paths to eligible .training.json files.
        config: WinnerModelConfig — fps_out, clip_duration_s, canonical size.
        split: Which subset to expose, ``"train"`` or ``"val"``.
        val_fraction: Fraction of videos to reserve for validation.
        augment: Whether to apply data augmentation (only relevant for train).
    """

    # Color jitter deltas (fixed; adjustable here if needed)
    _JITTER_BRIGHTNESS: float = 0.2
    _JITTER_CONTRAST: float = 0.2
    _JITTER_SATURATION: float = 0.2
    _TEMPORAL_JITTER_S: float = 0.2

    def __init__(
        self,
        training_json_paths: list[Path],
        config: WinnerModelConfig,
        split: str = "train",
        val_fraction: float = 0.2,
        augment: bool = True,
    ) -> None:
        if split not in ("train", "val"):
            raise ValueError(f"split must be 'train' or 'val', got {split!r}")

        self._config = config
        self._split = split
        self._do_augment = augment and split == "train"

        # Collect all eligible rallies grouped by video path
        rallies_by_video: dict[str, list[_RallyRecord]] = {}
        n_skipped_filter = 0
        n_skipped_rally = 0

        for json_path in training_json_paths:
            data = _load_json_safe(json_path)
            if data is None:
                continue

            if not _is_usable_training_file(data):
                logger.debug("Skipping %s (failed eligibility check)", json_path)
                n_skipped_filter += 1
                continue

            video_block = data["video"]
            video_path = Path(video_block["path"])

            if not video_path.exists():
                logger.warning("Video not found, skipping: %s", video_path)
                continue

            raw_corners: list[list[int]] = video_block["court_corners"]
            corners: list[tuple[int, int]] = [
                (int(c[0]), int(c[1])) for c in raw_corners
            ]

            video_key = str(video_path)
            if video_key not in rallies_by_video:
                rallies_by_video[video_key] = []

            for rally in data.get("rallies", []):
                if rally.get("is_post_game", False):
                    n_skipped_rally += 1
                    continue

                winning_team = rally.get("winning_team")
                if winning_team is None:
                    n_skipped_rally += 1
                    continue

                raw = rally.get("raw")
                if raw is None:
                    n_skipped_rally += 1
                    continue

                end_seconds = float(raw["end_seconds"])

                rallies_by_video[video_key].append(
                    _RallyRecord(
                        video_path=video_path,
                        end_seconds=end_seconds,
                        corners=corners,
                        winning_team=int(winning_team),
                    )
                )

        if n_skipped_filter > 0:
            logger.info(
                "Skipped %d training file(s) that failed eligibility filter",
                n_skipped_filter,
            )
        if n_skipped_rally > 0:
            logger.info(
                "Skipped %d rally record(s) (post_game or winning_team=None)",
                n_skipped_rally,
            )

        # Drop videos that registered but produced zero usable rallies — the
        # split is denominated by *contributing* videos, otherwise the val
        # bucket can land entirely on empty videos and produce 0 records.
        n_empty_videos = sum(1 for v in rallies_by_video.values() if not v)
        if n_empty_videos > 0:
            logger.info(
                "Skipped %d video(s) with no labeled non-postgame rallies",
                n_empty_videos,
            )
        rallies_by_video = {k: v for k, v in rallies_by_video.items() if v}

        # Video-wise train/val split: sort for determinism, last N → val
        all_video_keys = sorted(rallies_by_video.keys())
        n_videos = len(all_video_keys)

        if n_videos == 0:
            logger.warning("WinnerDataset: no eligible videos found.")
            self._records: list[_RallyRecord] = []
            return

        n_val = max(1, math.floor(n_videos * val_fraction)) if n_videos >= 2 else 0
        n_train = n_videos - n_val

        train_keys = set(all_video_keys[:n_train])
        val_keys = set(all_video_keys[n_train:])

        selected_keys = train_keys if split == "train" else val_keys

        self._records = []
        for key in sorted(selected_keys):
            self._records.extend(rallies_by_video[key])

        logger.info(
            "WinnerDataset [%s]: %d rallies across %d video(s) "
            "(train=%d / val=%d videos total)",
            split,
            len(self._records),
            len(selected_keys),
            n_train,
            n_val,
        )

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        """Return a single (clip_tensor, winning_team) pair.

        Augmentation (training split only when ``augment=True``):
        - With 50% probability: horizontal flip all frames and swap label.
        - Color jitter (brightness, contrast, saturation ±0.2).
        - Temporal jitter: clip start shifted by U(-0.2, +0.2) seconds.

        Args:
            idx: Index into this split's rally list.

        Returns:
            Tuple of:
            - clip_tensor: ``(T, 3, H, W)`` float32 in ``[0, 1]``.
            - winning_team: ``0`` or ``1``.
        """
        record = self._records[idx]
        winning_team = record.winning_team

        # Temporal jitter: applied at extraction time (shifts the clip window)
        temporal_jitter_s = 0.0
        if self._do_augment:
            temporal_jitter_s = random.uniform(
                -self._TEMPORAL_JITTER_S,
                +self._TEMPORAL_JITTER_S,
            )

        frames = _fetch_clip_tensor(record, self._config, temporal_jitter_s)
        # frames: (T, H, W, 3) uint8

        if self._do_augment:
            # Horizontal flip (50% probability) + swap label
            if random.random() < 0.5:
                frames = _horizontal_flip_frames(frames)
                winning_team = 1 - winning_team

            # Color jitter (applied after potential flip — order does not matter)
            frames = _apply_color_jitter(
                frames,
                brightness=self._JITTER_BRIGHTNESS,
                contrast=self._JITTER_CONTRAST,
                saturation=self._JITTER_SATURATION,
            )

        clip_tensor = _to_float_tensor(frames)
        return clip_tensor, winning_team


# ---------------------------------------------------------------------------
# Utility: safe JSON loader
# ---------------------------------------------------------------------------

def _load_json_safe(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None on parse errors.

    Args:
        path: Path to a JSON file.

    Returns:
        Parsed dictionary or None if the file is unreadable / malformed.
    """
    if not path.exists():
        logger.warning("Training file not found: %s", path)
        return None

    with path.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning("Malformed JSON in %s: %s", path, exc)
            return None


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def load_winner_dataset(
    root_dir: Path,
    config: WinnerModelConfig,
    split: str = "train",
    val_fraction: float = 0.2,
) -> "WinnerDataset":
    """Scan *root_dir* recursively and return a split-specific WinnerDataset.

    Only .training.json files that satisfy all three eligibility criteria are
    included:
    - ``schema_version >= "1.1"``
    - ``video.court_corners`` present and non-null
    - ``generated_by != "auto_edit"``

    The train split gets augmentation enabled; the val split does not.

    Args:
        root_dir: Directory to search recursively for ``.training.json`` files.
        config: WinnerModelConfig supplying fps_out, clip_duration_s, etc.
        split: ``"train"`` or ``"val"``.
        val_fraction: Fraction of videos (by count) reserved for validation.

    Returns:
        Configured WinnerDataset for the requested split.
    """
    json_paths = sorted(root_dir.rglob("*.training.json"))
    logger.info(
        "load_winner_dataset: found %d .training.json file(s) under %s",
        len(json_paths),
        root_dir,
    )
    return WinnerDataset(
        training_json_paths=json_paths,
        config=config,
        split=split,
        val_fraction=val_fraction,
        augment=(split == "train"),
    )
