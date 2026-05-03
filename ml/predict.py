"""Inference pipeline for rally detection on new videos.

Usage:
    python -m ml.predict --video /path/to/new_game.mp4

Runs the trained model on a new video and outputs detected rally
boundaries as JSON timestamps.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torchaudio

from ml.config import AudioConfig, InferenceConfig, PathConfig
from ml.dataset import extract_audio, compute_mel_spectrogram
from ml.model import RallyDetector


def load_model(
    checkpoint_path: Path,
    device: torch.device,
) -> tuple[RallyDetector, AudioConfig]:
    """Load trained model from checkpoint.

    Args:
        checkpoint_path: Path to .pt checkpoint file
        device: Target device

    Returns:
        Tuple of (model, audio_config used during training)
    """
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)

    # Reconstruct audio config from checkpoint
    saved_cfg = checkpoint.get("audio_config", {})
    audio_cfg = AudioConfig(
        sample_rate=saved_cfg.get("sample_rate", 22050),
        n_mels=saved_cfg.get("n_mels", 128),
        n_fft=saved_cfg.get("n_fft", 2048),
        hop_length=saved_cfg.get("hop_length", 512),
        window_seconds=saved_cfg.get("window_seconds", 2.0),
    )

    model = RallyDetector(audio_cfg)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    return model, audio_cfg


@torch.no_grad()
def predict_raw(
    model: RallyDetector,
    spectrogram: torch.Tensor,
    audio_config: AudioConfig,
    inference_config: InferenceConfig,
    device: torch.device,
    batch_size: int = 256,
) -> np.ndarray:
    """Run sliding window inference and return per-window probabilities.

    Args:
        model: Trained RallyDetector
        spectrogram: Full mel spectrogram, shape (n_mels, time_frames)
        audio_config: Audio config matching the model
        inference_config: Inference parameters
        device: Compute device
        batch_size: Inference batch size

    Returns:
        1D array of probabilities, one per window position.
        Also returns the corresponding center times in seconds.
    """
    window_frames = audio_config.window_mel_frames
    hop_frames = max(1, int(
        inference_config.hop_seconds * audio_config.sample_rate / audio_config.hop_length
    ))

    n_total_frames = spectrogram.shape[1]
    starts = list(range(0, n_total_frames - window_frames + 1, hop_frames))

    if not starts:
        return np.array([]), np.array([])

    # Batch inference
    all_probs = []
    for batch_start in range(0, len(starts), batch_size):
        batch_starts = starts[batch_start:batch_start + batch_size]
        windows = torch.stack([
            spectrogram[:, s:s + window_frames].unsqueeze(0)
            for s in batch_starts
        ])  # (B, 1, n_mels, window_frames)
        windows = windows.to(device)

        logits = model(windows).squeeze(1)
        probs = torch.sigmoid(logits).cpu().numpy()
        all_probs.append(probs)

    probs = np.concatenate(all_probs)

    # Compute center time for each window
    center_times = np.array([
        (s + window_frames // 2) * audio_config.hop_length / audio_config.sample_rate
        for s in starts
    ])

    return probs, center_times


def smooth_predictions(probs: np.ndarray, kernel_size: int) -> np.ndarray:
    """Apply median filter to smooth noisy predictions.

    Args:
        probs: Raw per-window probabilities
        kernel_size: Median filter kernel size (must be odd)

    Returns:
        Smoothed probabilities
    """
    if kernel_size <= 1 or len(probs) < kernel_size:
        return probs

    # Ensure odd kernel
    if kernel_size % 2 == 0:
        kernel_size += 1

    pad = kernel_size // 2
    padded = np.pad(probs, pad, mode="edge")
    smoothed = np.array([
        np.median(padded[i:i + kernel_size])
        for i in range(len(probs))
    ])
    return smoothed


def predictions_to_rallies(
    probs: np.ndarray,
    center_times: np.ndarray,
    config: InferenceConfig,
) -> list[dict[str, float]]:
    """Convert per-window predictions to rally boundary timestamps.

    Applies thresholding, merges nearby segments, and filters short rallies.

    Args:
        probs: Smoothed per-window probabilities
        center_times: Center time of each window in seconds
        config: Inference/post-processing configuration

    Returns:
        List of dicts with "start_seconds" and "end_seconds" keys
    """
    if len(probs) == 0:
        return []

    # Threshold to binary
    binary = (probs >= config.threshold).astype(int)

    # Find contiguous regions of 1s
    segments = []
    in_segment = False
    seg_start = 0.0

    for i, val in enumerate(binary):
        if val == 1 and not in_segment:
            in_segment = True
            seg_start = center_times[i]
        elif val == 0 and in_segment:
            in_segment = False
            segments.append((seg_start, center_times[i - 1]))

    # Close any open segment
    if in_segment:
        segments.append((seg_start, center_times[-1]))

    if not segments:
        return []

    # Merge segments closer than merge_gap_seconds
    merged = [segments[0]]
    for start, end in segments[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= config.merge_gap_seconds:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    # Filter by minimum duration
    rallies = []
    for start, end in merged:
        duration = end - start
        if duration >= config.min_rally_seconds:
            rallies.append({
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(duration, 3),
            })

    return rallies


def predict_video(
    video_path: str | Path,
    model_path: Path | None = None,
    inference_config: InferenceConfig | None = None,
    device: torch.device | None = None,
) -> list[dict[str, float]]:
    """End-to-end prediction: video file → rally timestamps.

    Args:
        video_path: Path to video file
        model_path: Path to model checkpoint (uses default if None)
        inference_config: Inference config (uses defaults if None)
        device: Compute device (auto-detect if None)

    Returns:
        List of rally boundary dicts with start/end times
    """
    paths = PathConfig()
    model_path = model_path or paths.best_model_path
    inference_config = inference_config or InferenceConfig()
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")

    video_path = Path(video_path)

    # Load model
    model, audio_cfg = load_model(model_path, device)

    # Extract and process audio
    cache_dir = paths.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav_path = cache_dir / f"{video_path.stem}_predict.wav"

    extract_audio(video_path, wav_path, audio_cfg.sample_rate)
    spectrogram = compute_mel_spectrogram(wav_path, audio_cfg)

    # Run inference
    probs, center_times = predict_raw(
        model, spectrogram, audio_cfg, inference_config, device
    )

    # Post-process
    probs = smooth_predictions(probs, inference_config.smooth_kernel)
    rallies = predictions_to_rallies(probs, center_times, inference_config)

    return rallies


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect rallies in a pickleball video")
    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="Path to video file",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to model checkpoint (default: ml/checkpoints/best_model.pt)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Detection threshold (default: 0.5)",
    )
    parser.add_argument(
        "--min-rally",
        type=float,
        default=None,
        help="Minimum rally duration in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: print to stdout)",
    )
    args = parser.parse_args()

    inf_cfg = InferenceConfig()
    if args.threshold is not None:
        inf_cfg.threshold = args.threshold
    if args.min_rally is not None:
        inf_cfg.min_rally_seconds = args.min_rally

    model_path = Path(args.model) if args.model else None

    print(f"Processing: {args.video}")
    rallies = predict_video(args.video, model_path=model_path, inference_config=inf_cfg)
    print(f"Detected {len(rallies)} rallies")

    output = {
        "video": args.video,
        "rallies": rallies,
        "rally_count": len(rallies),
    }

    json_str = json.dumps(output, indent=2)

    if args.output:
        Path(args.output).write_text(json_str + "\n", encoding="utf-8")
        print(f"Saved to: {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
