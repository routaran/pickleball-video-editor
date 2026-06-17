"""Winner prediction inference for rally video clips.

For each rally interval, extracts the final clip_duration_s seconds of video,
warps to a canonical court view, and runs WinnerClassifier to produce a
(winning_team, confidence) prediction.

winning_team: 0 = server wins, 1 = receiver wins
confidence:   calibrated softmax max probability in [0.5, 1.0].
              Confidences are temperature-scaled using the scalar ``T`` stored
              in the checkpoint (fitted on the validation set during training).
              When the checkpoint has no ``"temperature"`` key, T defaults to
              1.0 (no-op).  The low-confidence flag threshold in
              WinnerModelConfig.confidence_threshold is therefore applied to
              calibrated probabilities.

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

from ml.config import WinnerModelConfig, load_winner_config_from_checkpoint
from ml.video_features import (
    compute_homography,
    extract_clip,
    get_video_frame_size,
    resolve_extract_geometry,
    warp_clip_to_canonical,
)
from ml.winner_model import WinnerClassifier


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
        config: WinnerModelConfig instance.  When None, the config is loaded
            from the checkpoint's v2.0 metadata so inference uses the exact
            clip geometry the model was trained with; legacy checkpoints
            without that metadata fall back to defaults with a one-time
            warning.

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

    # Load checkpoint once for model weights, calibration temperature, and
    # (when the caller did not pass an explicit config) the clip geometry the
    # model was trained with.  A single torch.load avoids reading the file
    # multiple times.  map_location="cpu" here keeps the load device-agnostic;
    # the model is moved to the resolved device below.
    checkpoint: dict = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=True,
    )

    # Resolve config: derive it from the checkpoint metadata when the caller
    # passes None so inference reproduces the training-time geometry (including
    # effective_clip_duration_s) instead of source defaults.  Legacy
    # checkpoints without a v2.0 config block fall back to defaults with a
    # single warning inside the shared loader.
    if config is None:
        config = load_winner_config_from_checkpoint(
            checkpoint, checkpoint_path=checkpoint_path
        )

    resolved_device = config.device
    if config.device.startswith("cuda") and not torch.cuda.is_available():
        warnings.warn(
            f"CUDA was requested (device='{config.device}') but is not available. "
            "Falling back to CPU for winner prediction.",
            stacklevel=2,
        )
        resolved_device = "cpu"

    canonical_size: tuple[int, int] = (config.canonical_width, config.canonical_height)
    extract_size, scaled_corners = resolve_extract_geometry(
        get_video_frame_size(video_path),
        corners,
        canonical_size,
        config.clip_extract_max_dim,
    )

    # Compute homography once — it is the same for every rally in this video.
    homography = compute_homography(scaled_corners, canonical_size)
    logger.debug(
        "Homography computed for canonical size %dx%d",
        config.canonical_width,
        config.canonical_height,
    )

    device = torch.device(resolved_device)

    # Temperature scalar fitted on the validation set during training.
    # Defaults to 1.0 (no-op) for checkpoints produced before temperature
    # scaling was introduced.
    temperature: float = float(checkpoint.get("temperature", 1.0))
    logger.debug(
        "WinnerClassifier temperature=%.4f from checkpoint %s",
        temperature,
        checkpoint_path,
    )

    # Build and initialise the model from the loaded checkpoint dict.
    model = WinnerClassifier()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    model.to(device)
    logger.debug("WinnerClassifier loaded from %s on %s", checkpoint_path, resolved_device)

    results: list[tuple[int, float]] = []

    # Cache/policy tag describing the clip-window + padding policy the model was
    # trained under (Phase 4).  Passed to extract_clip so the prediction-time
    # raw-frame cache never collides with clips produced under a different
    # policy, mirroring the training dataset's cache key.
    policy_tag = f"{config.clip_window_policy}+{config.padding_policy}"

    for idx, (start_s, end_s) in enumerate(rally_intervals):
        # Use the effective (ablation-aware) clip duration so prediction
        # extracts the SAME window length the model was trained on.  Reading
        # config.clip_duration_s here would ignore any clip_duration_override_s
        # recorded in the checkpoint and silently mismatch training geometry.
        #
        # Phase-4 clamp_to_rally_start_v1: never start the clip before the
        # rally's own start (start_s), so a long window on a short rally cannot
        # pull in frames from the previous point.  The result is floored at 0.0
        # for a valid seek offset.
        desired_start = end_s - config.effective_clip_duration_s
        clip_start = max(0.0, start_s, desired_start)
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
            extract_size,
            policy_tag,
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

        # Forward pass: (1, 2) logits → temperature-scaled softmax probabilities.
        # Dividing by T before softmax gives calibrated confidence values when
        # T > 1 (overconfident model) and leaves predictions unchanged (argmax
        # is scale-invariant).
        logits = model(clip_tensor)                          # (1, 2)
        probs = F.softmax(logits / temperature, dim=1)      # (1, 2) calibrated

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
