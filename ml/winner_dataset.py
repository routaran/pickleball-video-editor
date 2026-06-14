"""Dataset pipeline for rally winner classification training.

Handles:
1. Discovery and filtering of schema-1.1 .training.json label files
2. Clip extraction via ml.video_features (decord / torchvision, disk-cached)
3. Per-frame court homography warp to canonical 256x128 view
4. Video-wise 80/20 train/val split (no data leakage within a single video)
5. Augmentation for the train split: horizontal/vertical flips, color jitter,
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
    get_video_frame_size,
    resolve_extract_geometry,
    warp_clip_to_canonical,
)


__all__ = [
    "WinnerDataset",
    "load_winner_dataset",
]

# Forward-declare for type hints without a circular import at the module level.
# The actual import is deferred inside the classmethod to keep this module
# torch-importable without ml.examples dragging in unexpected dependencies.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ml.examples import RallyExample

logger = logging.getLogger(__name__)

# Maximum temporal jitter expressed in seconds.  During training __getitem__
# applies jitter as a frame-index offset into a fixed extended window rather
# than by shifting the extraction timestamps, so the disk-cache key for
# extract_clip is deterministic — exactly ONE .npy file per rally per run.
_TEMPORAL_JITTER_S: float = 0.2


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


def _vertical_flip_frames(frames_hwc: np.ndarray) -> np.ndarray:
    """Flip every frame in the clip vertically (top-bottom mirror).

    Args:
        frames_hwc: Shape (T, H, W, 3) uint8.

    Returns:
        Mirrored array with the same shape.
    """
    # np.flip on axis=1 (height) is zero-copy; ascontiguousarray makes it safe
    # to pass to downstream code that expects C-contiguous memory.
    return np.ascontiguousarray(np.flip(frames_hwc, axis=1))


# ---------------------------------------------------------------------------
# Core per-sample fetch
# ---------------------------------------------------------------------------

def _fetch_clip_tensor(
    record: _RallyRecord,
    config: WinnerModelConfig,
) -> np.ndarray:
    """Extract, warp, and return one EXTENDED clip as (T_ext, H, W, 3) uint8.

    Extracts a FIXED extended window per rally so that ``extract_clip``'s disk
    cache yields exactly ONE cache entry per rally, regardless of whether
    augmentation is active.  Temporal jitter is applied by the caller
    (``__getitem__``) as a frame-index offset into this returned array rather
    than by shifting the extraction window — keeping the ``hash_clip_key`` used
    by ``extract_clip`` stable across all augmented calls for a given rally.

    Extended window definition::

        J        = max(1, round(_TEMPORAL_JITTER_S * config.fps_out))
        pad_s    = J / config.fps_out
        start_s  = max(0, end_seconds - effective_clip_duration - pad_s)
        end_s    = end_seconds + pad_s

    The returned array nominally contains ``T + 2*J`` frames, where
    ``T = round(effective_clip_duration * fps_out)``.  When the rally is near
    the start of the video, video-start clamping may shorten the array; the
    caller handles this gracefully via the short-video fallback in
    ``__getitem__``.

    Previously cached non-extended clips (produced by the previous
    random-jitter-at-extraction approach) become orphaned cache entries; they
    are harmless and will be evicted naturally if/when the cache is pruned.

    Args:
        record: Rally metadata including video path, timestamps, and corners.
        config: WinnerModelConfig specifying fps_out, clip_duration_s, etc.

    Returns:
        Numpy array of shape (T_ext, H_canon, W_canon, 3), dtype uint8.
        T_ext equals T + 2*J in the unclamped case, potentially shorter when
        the rally falls near the start of the video.
    """
    canonical_size = (config.canonical_width, config.canonical_height)
    effective_duration = config.effective_clip_duration_s
    J = max(1, round(_TEMPORAL_JITTER_S * config.fps_out))
    pad_s = J / config.fps_out

    start_s = max(0.0, record.end_seconds - effective_duration - pad_s)
    end_s = record.end_seconds + pad_s

    extract_size, scaled_corners = resolve_extract_geometry(
        get_video_frame_size(record.video_path),
        record.corners,
        canonical_size,
        config.clip_extract_max_dim,
    )

    frames = extract_clip(
        record.video_path,
        start_s,
        end_s,
        config.fps_out,
        extract_size,
    )
    homography = compute_homography(scaled_corners, canonical_size)
    warped = warp_clip_to_canonical(frames, homography, canonical_size)
    return warped  # (T_ext, H_canon, W_canon, 3) uint8


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
    # Temporal jitter magnitude is defined at module level as _TEMPORAL_JITTER_S

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

    # ------------------------------------------------------------------
    # Alternate constructors: build from pre-parsed RallyExample records
    # ------------------------------------------------------------------

    @classmethod
    def _from_rally_examples_no_split(
        cls,
        records: "list[RallyExample]",
        config: "WinnerModelConfig",
        split: str = "train",
        augment: bool = True,
    ) -> "WinnerDataset":
        """Build a :class:`WinnerDataset` from an explicit RallyExample list.

        Unlike :meth:`from_rally_examples`, this constructor does not re-run the
        video-wise split or apply RallyExample-level filtering. The provided
        records are treated as the exact evaluation/training set.

        Args:
            records: RallyExample instances to include.
            config: WinnerModelConfig — fps_out, clip_duration_s, etc.
            split: ``"train"`` or ``"val"``.
            augment: Whether to apply data augmentation (only for train split).

        Returns:
            A WinnerDataset exposing ``records`` directly.
        """
        if split not in ("train", "val"):
            raise ValueError(f"split must be 'train' or 'val', got {split!r}")

        # Create a bare instance, bypassing __init__.
        instance = cls.__new__(cls)
        instance._config = config
        instance._split = split
        instance._do_augment = augment and split == "train"

        instance._records = [
            _RallyRecord(
                video_path=Path(ex.video_path),
                end_seconds=float(ex.raw_end),
                corners=list(ex.court_corners),
                winning_team=int(ex.winning_team),
            )
            for ex in records
        ]

        if not instance._records:
            logger.info(
                "WinnerDataset.from_rally_examples_no_split: no records provided; "
                "returning empty dataset."
            )

        return instance

    @classmethod
    def from_rally_examples(
        cls,
        records: "list[RallyExample]",
        config: "WinnerModelConfig",
        split: str = "train",
        val_fraction: float = 0.2,
        augment: bool = True,
    ) -> "WinnerDataset":
        """Build a WinnerDataset from a list of RallyExample objects.

        This is an alternate constructor that bypasses JSON-file scanning.
        It reuses the identical per-rally eligibility rules, video-wise
        train/val split logic, and internal _RallyRecord machinery as the
        default __init__, so the two construction paths produce the same
        sample list for the same underlying data.

        Eligibility mirrors WinnerDataset.__init__ exactly:
        - Skip rallies where ``is_post_game`` is True.
        - Skip rallies where ``winning_team`` is None (not applicable to
          RallyExample which always stores an int, but the guard is kept for
          consistency).
        - Skip rallies where ``raw_end`` is 0.0 and ``raw_start`` is 0.0
          simultaneously (placeholder produced when raw block was absent in
          the original JSON; mirrors the ``raw is None`` check).

        Video existence is NOT checked here because callers that build
        RallyExample lists from an index may work with videos that are
        present on a remote mount or are used for metadata-only tests.
        Callers that need existence checking should filter before passing.

        Args:
            records: List of RallyExample instances to build the dataset from.
                     May include post-game or missing-label records; those are
                     silently filtered out (same as the JSON path).
            config: WinnerModelConfig — fps_out, clip_duration_s, canonical size.
            split: ``"train"`` or ``"val"``.
            val_fraction: Fraction of videos (by count) reserved for validation.
            augment: Whether to apply data augmentation (only relevant for
                     the train split).

        Returns:
            A WinnerDataset whose ``_records`` list is built from the provided
            RallyExample objects rather than from JSON files on disk.
        """
        # Deferred import so that ml.examples stays torch-free at import time.
        from ml.examples import RallyExample as _RE  # noqa: F401 (used for isinstance guard only)

        if split not in ("train", "val"):
            raise ValueError(f"split must be 'train' or 'val', got {split!r}")

        # Create a bare instance, bypassing __init__
        instance = cls.__new__(cls)
        instance._config = config
        instance._split = split
        instance._do_augment = augment and split == "train"

        rallies_by_video: dict[str, list[_RallyRecord]] = {}
        n_skipped_rally = 0

        for ex in records:
            # --- per-rally eligibility (mirrors WinnerDataset.__init__) ---
            if ex.is_post_game:
                n_skipped_rally += 1
                continue

            # winning_team on RallyExample is always int (coerced in from_rally_dict)
            # but guard against any hand-constructed examples with None-like values.
            if ex.winning_team is None:  # type: ignore[comparison-overlap]
                n_skipped_rally += 1
                continue

            # Mirror the ``raw is None`` check: if both timestamps are 0.0 the
            # rally came from a missing raw block and is not usable.
            if ex.raw_end == 0.0 and ex.raw_start == 0.0:
                n_skipped_rally += 1
                continue

            video_key = str(ex.video_path)
            if video_key not in rallies_by_video:
                rallies_by_video[video_key] = []

            # court_corners on RallyExample is tuple[tuple[int,int],...];
            # _RallyRecord expects list[tuple[int,int]].
            corners: list[tuple[int, int]] = list(ex.court_corners)

            rallies_by_video[video_key].append(
                _RallyRecord(
                    video_path=ex.video_path,
                    end_seconds=ex.raw_end,
                    corners=corners,
                    winning_team=int(ex.winning_team),
                )
            )

        if n_skipped_rally > 0:
            logger.info(
                "WinnerDataset.from_rally_examples: skipped %d rally record(s) "
                "(post_game or winning_team=None or missing raw timestamps)",
                n_skipped_rally,
            )

        # Drop videos with zero usable rallies (mirrors __init__ behaviour)
        n_empty_videos = sum(1 for v in rallies_by_video.values() if not v)
        if n_empty_videos > 0:
            logger.info(
                "WinnerDataset.from_rally_examples: skipped %d video(s) with "
                "no labeled non-postgame rallies",
                n_empty_videos,
            )
        rallies_by_video = {k: v for k, v in rallies_by_video.items() if v}

        # Video-wise train/val split — identical logic to __init__
        all_video_keys = sorted(rallies_by_video.keys())
        n_videos = len(all_video_keys)

        if n_videos == 0:
            logger.warning(
                "WinnerDataset.from_rally_examples: no eligible videos found."
            )
            instance._records = []
            return instance

        n_val = max(1, math.floor(n_videos * val_fraction)) if n_videos >= 2 else 0
        n_train = n_videos - n_val

        train_keys = set(all_video_keys[:n_train])
        val_keys = set(all_video_keys[n_train:])

        selected_keys = train_keys if split == "train" else val_keys

        instance._records = []
        for key in sorted(selected_keys):
            instance._records.extend(rallies_by_video[key])

        logger.info(
            "WinnerDataset.from_rally_examples [%s]: %d rallies across %d "
            "video(s) (train=%d / val=%d videos total)",
            split,
            len(instance._records),
            len(selected_keys),
            n_train,
            n_val,
        )

        return instance

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        """Return a single (clip_tensor, winning_team) pair.

        Augmentation (training split only when ``augment=True``):
        - 50% chance to apply a flip augmentation, split evenly between
          horizontal (label preserved) and vertical (label swapped).
        - Color jitter (brightness, contrast, saturation ±0.2).
        - Temporal jitter: a frame-index offset of ``random.randint(-J, +J)``
          is applied to the base slice of the pre-cached extended clip, where
          ``J = max(1, round(_TEMPORAL_JITTER_S * fps_out))``.

        The temporal jitter is deliberately implemented as a frame-index offset
        rather than a floating-point time shift.  ``_fetch_clip_tensor`` always
        extracts the same deterministic extended window (one per rally), so
        ``extract_clip``'s ``hash_clip_key`` is stable across all augmented
        calls — producing exactly one .npy cache entry per rally rather than
        one per augmented call.

        Args:
            idx: Index into this split's rally list.

        Returns:
            Tuple of:
            - clip_tensor: ``(T, 3, H, W)`` float32 in ``[0, 1]``.
            - winning_team: ``0`` or ``1``.
        """
        record = self._records[idx]
        winning_team = record.winning_team

        # _fetch_clip_tensor returns a FIXED extended window — cache-stable.
        frames_ext = _fetch_clip_tensor(record, self._config)
        # frames_ext: (T_ext, H, W, 3) uint8

        # Slice a T-frame window from the extended array.
        T = round(self._config.effective_clip_duration_s * self._config.fps_out)
        J = max(1, round(_TEMPORAL_JITTER_S * self._config.fps_out))
        arr_len = len(frames_ext)

        if arr_len <= T:
            # Short video near the start of the file — return all frames as-is.
            # This preserves existing behavior for clips shorter than T frames.
            frames = frames_ext
        else:
            # Nominal clip ends J frames before the array end.
            # base_start is the start index of the offset=0 (centered) slice.
            # Clamped to 0 in case video-start clamping shortened the array.
            base_start = max(0, arr_len - J - T)

            if self._do_augment:
                offset_frames = random.randint(-J, J)
                start = base_start + offset_frames
                # Shift inward rather than shrinking: preserve slice length = T.
                start = max(0, min(start, arr_len - T))
            else:
                start = base_start

            frames = frames_ext[start : start + T]

        if self._do_augment:
            # Flip branch: 50% overall (horizontal or vertical) and
            # deterministic label semantics:
            # - Horizontal mirror: preserves label
            # - Vertical mirror: swaps label
            flip_random = random.random()
            if flip_random < 0.25:
                frames = _horizontal_flip_frames(frames)
            elif flip_random < 0.5:
                frames = _vertical_flip_frames(frames)
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
