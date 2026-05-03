"""Winner prediction inference for rally video clips.

For each rally interval, extracts the final clip_duration_s seconds of video,
warps to a canonical court view, and runs WinnerClassifier to produce a
(winning_team, confidence) prediction.

winning_team: 0 = server wins, 1 = receiver wins
confidence:   softmax max probability (no temperature scaling in v1)

Public API
----------
predict_winners(video_path, corners, rally_intervals, checkpoint_path, config)
    -> list[tuple[int, float]]
"""

import logging
import warnings
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ml.config import WinnerModelConfig
from ml.video_features import compute_homography, extract_clip, warp_clip_to_canonical
from ml.winner_model import WinnerClassifier, load_winner_classifier


__all__ = ["predict_winners"]

logger = logging.getLogger(__name__)


@torch.no_grad()
def predict_winners(
    video_path: Path,
    corners: list[tuple[int, int]],
    rally_intervals: list[tuple[float, float]],
    checkpoint_path: Path,
    config: WinnerModelConfig | None = None,
) -> list[tuple[int, float]]:
    """For each rally interval, predict which team won and return confidence.

    Extracts the last clip_duration_s seconds of each rally, warps each frame
    to a canonical court view using the supplied corner coordinates, then runs
    WinnerClassifier to produce per-rally predictions.

    Args:
        video_path: Absolute path to the source video file.
        corners: Four (x, y) pixel coordinates in the original video frame,
            ordered top-left, top-right, bottom-right, bottom-left.
        rally_intervals: Sequence of (start_s, end_s) tuples defining each
            rally's time range in seconds.
        checkpoint_path: Path to the WinnerClassifier ``.pt`` checkpoint.
        config: WinnerModelConfig instance; uses defaults when None.

    Returns:
        A list of (winning_team, confidence) tuples in the same order as
        rally_intervals.  winning_team is 0 (server wins) or 1 (receiver
        wins).  confidence is the softmax max probability in [0.5, 1.0].

    Raises:
        FileNotFoundError: If checkpoint_path does not exist.
        ValueError: If corners does not contain exactly 4 points.
    """
    if not rally_intervals:
        return []

    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Winner classifier checkpoint not found: {checkpoint_path}\n"
            f"Train the model first or provide a valid checkpoint path."
        )

    # Resolve config and device.
    if config is None:
        config = WinnerModelConfig()

    resolved_device = config.device
    if config.device.startswith("cuda") and not torch.cuda.is_available():
        warnings.warn(
            f"CUDA was requested (device='{config.device}') but is not available. "
            "Falling back to CPU for winner prediction.",
            stacklevel=2,
        )
        resolved_device = "cpu"

    canonical_size: tuple[int, int] = (config.canonical_width, config.canonical_height)

    # Compute homography once — it is the same for every rally in this video.
    homography = compute_homography(corners, canonical_size)
    logger.debug(
        "Homography computed for canonical size %dx%d",
        config.canonical_width,
        config.canonical_height,
    )

    # Load model to the resolved device.
    # load_winner_classifier already handles the CUDA fallback internally,
    # but we pass the already-resolved device to keep behavior consistent.
    model: WinnerClassifier = load_winner_classifier(checkpoint_path, resolved_device)
    device = torch.device(resolved_device)
    logger.debug("WinnerClassifier loaded from %s on %s", checkpoint_path, resolved_device)

    results: list[tuple[int, float]] = []

    for idx, (start_s, end_s) in enumerate(rally_intervals):
        clip_start = max(0.0, end_s - config.clip_duration_s)
        clip_end = end_s

        logger.debug(
            "Rally %d/%d: extracting %.2f–%.2f s",
            idx + 1,
            len(rally_intervals),
            clip_start,
            clip_end,
        )

        # Extract raw frames: (T, H, W, 3) uint8.
        frames: np.ndarray = extract_clip(
            video_path,
            clip_start,
            clip_end,
            config.fps_out,
            canonical_size,
        )

        # Warp to canonical court view: (T, canonical_height, canonical_width, 3) uint8.
        warped: np.ndarray = warp_clip_to_canonical(frames, homography, canonical_size)

        # Build tensor: uint8 (T, H, W, 3) → float32 [0, 1] (T, H, W, 3)
        #   → permute to (T, 3, H, W) → unsqueeze batch → (1, T, 3, H, W).
        clip_tensor = (
            torch.from_numpy(warped)
            .float()
            .div(255.0)
            .permute(0, 3, 1, 2)
            .unsqueeze(0)
            .to(device)
        )  # shape: (1, T, 3, H, W)

        # Forward pass: (1, 2) logits → softmax probabilities.
        logits = model(clip_tensor)                          # (1, 2)
        probs = F.softmax(logits, dim=1)                    # (1, 2)

        confidence_tensor = probs.max(dim=1).values         # (1,)
        team_tensor = probs.argmax(dim=1)                   # (1,)

        winning_team: int = int(team_tensor.item())
        confidence: float = float(confidence_tensor.item())

        logger.debug(
            "Rally %d prediction: team=%d  confidence=%.4f",
            idx + 1,
            winning_team,
            confidence,
        )

        results.append((winning_team, confidence))

    return results
