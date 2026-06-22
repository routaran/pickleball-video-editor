"""Assemble per-window (audio + visual + label) rows for joint rally fusion.

For one labelled video this builds, on the audio model's window grid, a table of:

* ``p_audio``        — the Stage-1 audio rally probability (smoothed),
* the robust visual features (:data:`ml.motion.visual_features.VISUAL_FEATURE_KEYS`),
* ``valid``          — whether the visual estimate is trustworthy in that window,
* ``label``          — the ground-truth rally label (center-in-interval, the same
                       definition the audio model was trained on), and
* ``t``, ``group``, ``video`` — provenance for grouped cross-validation.

These rows feed the nested grouped-CV harness, the tuned visual veto, and (if it
graduates) the learned fusion head.  The audio half reuses
:func:`ml.motion.predict_fused.audio_window_probs`; labels reuse
:func:`ml.dataset.build_labels_from_rallies` for exact parity with audio training.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ml.config import AudioConfig, InferenceConfig, PathConfig
from ml.motion.court_apply import DEFAULT_DILATION
from ml.motion.features import load_feature_series
from ml.motion.visual_features import VISUAL_FEATURE_KEYS, robust_visual_features

__all__ = [
    "motion_cache_path",
    "group_id_for",
    "labels_at_times",
    "build_window_table",
]


def motion_cache_path(video_path: str | Path, cache_dir: Path | None = None) -> Path:
    """Path to the cached ``.npz`` motion series for ``video_path``."""
    cache_dir = cache_dir or (PathConfig().cache_dir / "motion")
    return Path(cache_dir) / f"{Path(video_path).stem}.npz"


def group_id_for(video_path: str | Path) -> str:
    """Grouped-CV key: the ``YYYYMMDD`` recording-date prefix.

    Games filmed the same evening share a venue, camera placement and lighting,
    so the date prefix is the largest defensible grouping unit available from the
    filename — it prevents same-session leakage across CV folds.  Refined in the
    Phase-0 hygiene step if a finer session/camera signal is found.
    """
    return Path(video_path).stem.split("_")[0]


def labels_at_times(
    rallies: list[dict[str, Any]],
    fps: float,
    total_duration: float,
    center_times: np.ndarray,
    audio_config: AudioConfig,
) -> np.ndarray:
    """Binary rally labels at ``center_times`` (center-in-interval, raw timestamps)."""
    from ml.dataset import build_labels_from_rallies  # noqa: PLC0415

    labels = build_labels_from_rallies(rallies, fps, total_duration, audio_config)
    if labels.size == 0:
        return np.zeros(center_times.shape[0], dtype=np.float64)
    idx = np.clip(
        (center_times * audio_config.sample_rate).astype(int), 0, labels.size - 1
    )
    return labels[idx].astype(np.float64)


def build_window_table(
    training_json: str | Path,
    *,
    model_path: Path | None = None,
    inference_config: InferenceConfig | None = None,
    cache_dir: Path | None = None,
    dilation: float = DEFAULT_DILATION,
    half_window_s: float = 1.0,
    device: Any = None,
) -> dict[str, np.ndarray] | None:
    """Build the per-window table for one labelled video.

    Returns ``None`` when the video, its court corners, or its motion cache are
    missing (caller treats those as the audio-only stratum).  Otherwise returns a
    dict of equal-length ``(Q,)`` arrays: ``t``, ``p_audio``, ``label``,
    ``valid``, every key in :data:`VISUAL_FEATURE_KEYS`, plus scalar metadata
    ``video`` (stem) and ``group``.
    """
    from ml.motion.predict_fused import audio_window_probs  # noqa: PLC0415 — pulls torch

    training_json = Path(training_json)
    with training_json.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("generated_by") == "auto_edit":
        return None
    video_block = data.get("video") or {}
    video_path = Path(video_block.get("path", ""))
    corners = video_block.get("court_corners") or []
    if len(corners) != 4 or not video_path.exists():
        return None

    npz_path = motion_cache_path(video_path, cache_dir)
    if not npz_path.exists():
        return None

    inference_config = inference_config or InferenceConfig()
    audio_config = AudioConfig()

    probs, center_times = audio_window_probs(
        video_path, model_path=model_path,
        inference_config=inference_config, device=device,
    )
    if center_times.size == 0:
        return None

    raw = load_feature_series(npz_path)
    total_duration = float(video_block.get("duration_seconds") or 0.0)
    if total_duration <= 0.0:
        total_duration = float(center_times[-1] + 2.0)
    labels = labels_at_times(
        data.get("rallies", []), float(video_block.get("fps", 60.0)),
        total_duration, center_times, audio_config,
    )
    feats, valid = robust_visual_features(
        raw, center_times, dilation=dilation, half_window_s=half_window_s
    )

    table: dict[str, np.ndarray] = {
        "t": np.asarray(center_times, dtype=np.float64),
        "p_audio": np.asarray(probs, dtype=np.float64),
        "label": labels,
        "valid": valid,
    }
    for key in VISUAL_FEATURE_KEYS:
        table[key] = feats[key]
    table["video"] = np.asarray(video_path.stem)
    table["group"] = np.asarray(group_id_for(video_path))
    return table
