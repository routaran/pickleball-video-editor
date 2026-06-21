"""End-to-end fused rally prediction: audio windows corrected by motion.

This mirrors :func:`ml.predict.predict_video`'s contract but inserts the motion
veto/sustain between the audio model's per-window probabilities and the
segment-forming step, so the output drops into the same downstream consumers
(``ml/auto_edit.py``) and the same evaluation harness.

Audio feature extraction reuses :mod:`ml.predict` and :mod:`ml.dataset`
unchanged.  Motion features are loaded from the cache written by
``ml/tools/extract_motion_features.py`` (preferred) or computed on demand when a
detector is supplied.  When neither motion features nor corners are available
the result is identical to audio-only prediction (graceful degradation).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np

from ml.config import InferenceConfig, PathConfig
from ml.motion.court_apply import DEFAULT_DILATION, features_from_raw, load_features
from ml.motion.features import flatten_detections, resample_features
from ml.motion.fusion import FusionConfig, fuse_binary

__all__ = [
    "audio_window_probs",
    "fuse_to_intervals",
    "predict_fused_intervals",
    "predict_fused",
]


def fuse_to_intervals(
    probs: np.ndarray,
    center_times: np.ndarray,
    features: dict[str, np.ndarray] | None,
    inference_config: InferenceConfig,
    fusion_config: FusionConfig | None = None,
    half_window_s: float = 0.5,
) -> list[tuple[float, float]]:
    """Turn audio window probs + motion features into corrected rally intervals.

    The single shared fusion path used by both prediction and evaluation.  When
    ``features`` is ``None`` (or there are no audio windows) this is exactly the
    audio-only result, so callers get graceful degradation for free.
    """
    from ml.predict import predictions_to_rallies  # noqa: PLC0415 — pulls torch via ml.predict

    if features is None or len(center_times) == 0:
        rallies = predictions_to_rallies(probs, center_times, inference_config)
        return [(r["start_seconds"], r["end_seconds"]) for r in rallies]

    feats, valid = resample_features(features, center_times, half_window_s)
    audio_binary = probs >= inference_config.threshold
    fused = fuse_binary(audio_binary, feats, valid, fusion_config)

    # Re-use the existing segment-former on the corrected binary stream.  A
    # threshold of 0.5 simply recovers the 0/1 stream; merge-gap and min-rally
    # are preserved from the caller's config.
    seg_config = dataclasses.replace(inference_config, threshold=0.5)
    rallies = predictions_to_rallies(fused.astype(np.float64), center_times, seg_config)
    return [(r["start_seconds"], r["end_seconds"]) for r in rallies]


def audio_window_probs(
    video_path: str | Path,
    model_path: Path | None = None,
    inference_config: InferenceConfig | None = None,
    device=None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(smoothed_probs, center_times)`` from the Stage-1 audio model.

    This is the front half of :func:`ml.predict.predict_video`, exposed so the
    motion fusion can operate on the per-window probability stream before it is
    collapsed into intervals.
    """
    import torch  # noqa: PLC0415 — heavy optional dep, lazy

    from ml.dataset import compute_mel_spectrogram, extract_audio  # noqa: PLC0415
    from ml.predict import load_model, predict_raw, smooth_predictions  # noqa: PLC0415

    paths = PathConfig()
    model_path = model_path or paths.best_model_path
    inference_config = inference_config or InferenceConfig()
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    video_path = Path(video_path)

    model, audio_cfg = load_model(model_path, device)

    cache_dir = paths.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav_path = cache_dir / f"{video_path.stem}_predict.wav"

    extract_audio(video_path, wav_path, audio_cfg.sample_rate)
    spectrogram = compute_mel_spectrogram(wav_path, audio_cfg)

    probs, center_times = predict_raw(
        model, spectrogram, audio_cfg, inference_config, device
    )
    probs = smooth_predictions(probs, inference_config.smooth_kernel)
    return probs, center_times


def _resolve_feature_series(
    video_path: Path,
    corners: list[tuple[int, int]] | None,
    feature_path: str | Path | None,
    detector,
    detect_fps: float,
    dilation: float = DEFAULT_DILATION,
) -> dict[str, np.ndarray] | None:
    """Load cached raw detections (or compute them) and build the feature series.

    The court filter + projection + feature compute (with the ``dilation`` knob)
    run here, in the cheap path — see :mod:`ml.motion.court_apply`.
    """
    if feature_path is not None and Path(feature_path).exists():
        return load_features(feature_path, dilation)

    if detector is not None and corners is not None and len(corners) == 4:
        vd = detector.detect_video(video_path, corners, fps_out=detect_fps)
        raw = flatten_detections(
            vd.frames,
            scaled_corners=vd.scaled_corners,
            extract_size=vd.extract_size,
            fps_out=detect_fps,
            video_path=video_path,
        )
        return features_from_raw(raw, dilation)

    return None


def predict_fused_intervals(
    video_path: str | Path,
    *,
    corners: list[tuple[int, int]] | None = None,
    feature_path: str | Path | None = None,
    model_path: Path | None = None,
    inference_config: InferenceConfig | None = None,
    fusion_config: FusionConfig | None = None,
    half_window_s: float = 0.5,
    detector=None,
    detect_fps: float = 5.0,
    dilation: float = DEFAULT_DILATION,
    device=None,
) -> list[tuple[float, float]]:
    """Predict rally intervals with motion fusion applied.

    Args:
        video_path: Source video path.
        corners: Four native-pixel court corners; required only when computing
            motion features on demand (ignored when ``feature_path`` is given).
        feature_path: Path to a cached ``.npz`` raw-detection series (preferred).
        model_path: Audio model checkpoint (default checkpoint when ``None``).
        inference_config: Audio post-processing config (defaults when ``None``).
        fusion_config: Veto/sustain thresholds (defaults when ``None``).
        half_window_s: Half-width for resampling motion onto audio windows.
        detector: Optional :class:`ml.motion.detector.MotionDetector` used to
            compute features when no cache is supplied.
        detect_fps: Detection sample rate when computing on demand.
        dilation: Court-polygon dilation applied in the cheap path.
        device: Torch device for the audio model.

    Returns:
        List of ``(start_s, end_s)`` rally intervals.  Identical to audio-only
        prediction when no motion features are available.
    """
    video_path = Path(video_path)
    inference_config = inference_config or InferenceConfig()

    probs, center_times = audio_window_probs(
        video_path, model_path=model_path, inference_config=inference_config, device=device
    )

    features = _resolve_feature_series(
        video_path, corners, feature_path, detector, detect_fps, dilation
    )

    return fuse_to_intervals(
        probs, center_times, features, inference_config, fusion_config, half_window_s
    )


def predict_fused(
    video_path: str | Path, **kwargs
) -> list[dict[str, float]]:
    """Like :func:`predict_fused_intervals` but returns ``predict_video``-shaped dicts.

    Provided so callers (e.g. ``ml/auto_edit.py``) can swap in fusion with no
    change to the consuming code: each dict has ``start_seconds``,
    ``end_seconds`` and ``duration_seconds``.
    """
    intervals = predict_fused_intervals(video_path, **kwargs)
    return [
        {
            "start_seconds": round(s, 3),
            "end_seconds": round(e, 3),
            "duration_seconds": round(e - s, 3),
        }
        for (s, e) in intervals
    ]
