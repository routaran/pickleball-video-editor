"""Audio + visual learned fusion: the validated rally producer.

The audio CNN proposes a per-window rally probability; this module adds robust
on-court **visual** features (occupancy / formation / motion in m/s, plus a
reliability flag) and a small **logistic combiner** learns to weigh them.  Under
leave-one-session-out grouped CV the combiner lifts interval F1 from ~0.60 to
~0.74 (precision 0.51→0.67, recall 0.72→0.83), improving every session, while
cutting over-segmentation by ~60% — see ``ml/tools/evaluate_joint.py``.

The combiner is intentionally tiny (standardiser + logistic over ``p_audio`` +
14 visual features): with only ~56 videos a linear model generalises where a
deep net would overfit, and the speed features turned out to be *anti*-signal
(pickleball is slow net play; high average speed means players walking *between*
points), so occupancy/formation carries the lift.

:func:`predict_joint` returns ``predict_video``-shaped dicts so it drops straight
into ``ml/auto_edit.py``; with no court corners / motion cache it degrades to the
exact audio-only result.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ml.config import InferenceConfig, PathConfig
from ml.motion.court_apply import DEFAULT_DILATION
from ml.motion.features import flatten_detections, load_feature_series
from ml.motion.visual_features import VISUAL_FEATURE_KEYS, robust_visual_features

__all__ = [
    "COMBINER_FEATURE_NAMES",
    "combiner_feature_matrix",
    "JointCombiner",
    "default_combiner_path",
    "predict_joint_intervals",
    "predict_joint",
]

# Feature order is part of the persisted contract: p_audio, the visual features,
# then the validity flag.  Visual columns are zero-imputed where invalid so the
# combiner can lean on `valid` to discount them.
COMBINER_FEATURE_NAMES = ("p_audio", *VISUAL_FEATURE_KEYS, "valid")


def default_combiner_path() -> Path:
    """Default persisted-combiner path: ``ml/checkpoints/joint_combiner.json``."""
    return PathConfig().checkpoints_dir / "joint_combiner.json"


def combiner_feature_matrix(
    p_audio: np.ndarray,
    visual: dict[str, np.ndarray],
    valid: np.ndarray,
) -> np.ndarray:
    """Assemble the ``(Q, D)`` combiner feature matrix in :data:`COMBINER_FEATURE_NAMES` order.

    Visual columns are zeroed where ``valid`` is False (the model uses the
    trailing ``valid`` flag to discount those windows).
    """
    valid = np.asarray(valid, dtype=bool).reshape(-1)
    cols = [np.asarray(p_audio, dtype=np.float64).reshape(-1)]
    for k in VISUAL_FEATURE_KEYS:
        col = np.asarray(visual[k], dtype=np.float64).reshape(-1).copy()
        col[~valid] = 0.0
        cols.append(col)
    cols.append(valid.astype(np.float64))
    return np.column_stack(cols)


class JointCombiner:
    """A persisted standardiser + logistic combiner over the joint feature vector."""

    def __init__(
        self,
        mean: np.ndarray,
        scale: np.ndarray,
        coef: np.ndarray,
        intercept: float,
        feature_names: tuple[str, ...] = COMBINER_FEATURE_NAMES,
    ) -> None:
        self.mean = np.asarray(mean, dtype=np.float64)
        self.scale = np.asarray(scale, dtype=np.float64)
        self.coef = np.asarray(coef, dtype=np.float64)
        self.intercept = float(intercept)
        self.feature_names = tuple(feature_names)

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray) -> "JointCombiner":
        """Fit the standardiser + class-balanced logistic regression."""
        from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
        from sklearn.preprocessing import StandardScaler  # noqa: PLC0415

        sc = StandardScaler().fit(X)
        clf = LogisticRegression(max_iter=2000, class_weight="balanced")
        clf.fit(sc.transform(X), y)
        return cls(sc.mean_, sc.scale_, clf.coef_[0], float(clf.intercept_[0]))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Per-window rally probability for an already-ordered feature matrix."""
        z = (np.asarray(X, dtype=np.float64) - self.mean) / self.scale
        logits = z @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-logits))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "feature_names": list(self.feature_names),
                    "mean": self.mean.tolist(),
                    "scale": self.scale.tolist(),
                    "coef": self.coef.tolist(),
                    "intercept": self.intercept,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "JointCombiner":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            mean=d["mean"], scale=d["scale"], coef=d["coef"],
            intercept=d["intercept"],
            feature_names=tuple(d.get("feature_names", COMBINER_FEATURE_NAMES)),
        )


def _resolve_raw(
    video_path: Path,
    corners: list[tuple[int, int]] | None,
    feature_path: str | Path | None,
    detector,
    detect_fps: float,
) -> dict[str, np.ndarray] | None:
    """Load the cached raw-detection series (preferred) or compute it on demand."""
    if feature_path is None:
        cand = PathConfig().cache_dir / "motion" / f"{video_path.stem}.npz"
        if cand.exists():
            feature_path = cand
    if feature_path is not None and Path(feature_path).exists():
        return load_feature_series(feature_path)
    if detector is not None and corners is not None and len(corners) == 4:
        vd = detector.detect_video(video_path, corners, fps_out=detect_fps)
        return flatten_detections(
            vd.frames, scaled_corners=vd.scaled_corners,
            extract_size=vd.extract_size, fps_out=detect_fps, video_path=video_path,
        )
    return None


def predict_joint_intervals(
    video_path: str | Path,
    *,
    corners: list[tuple[int, int]] | None = None,
    feature_path: str | Path | None = None,
    model_path: Path | None = None,
    inference_config: InferenceConfig | None = None,
    combiner: JointCombiner | None = None,
    combiner_path: str | Path | None = None,
    dilation: float = DEFAULT_DILATION,
    half_window_s: float = 1.0,
    detector=None,
    detect_fps: float = 10.0,
    device=None,
) -> list[tuple[float, float]]:
    """Predict rally intervals with the audio+visual learned combiner.

    Degrades to audio-only (identical to :func:`ml.predict.predict_video`) when no
    motion features are available or the combiner cannot be loaded.
    """
    from ml.motion.predict_fused import audio_window_probs  # noqa: PLC0415 — pulls torch
    from ml.predict import predictions_to_rallies, smooth_predictions  # noqa: PLC0415

    video_path = Path(video_path)
    inference_config = inference_config or InferenceConfig()

    probs, center_times = audio_window_probs(
        video_path, model_path=model_path,
        inference_config=inference_config, device=device,
    )
    if center_times.size == 0:
        return []

    def _audio_only() -> list[tuple[float, float]]:
        rallies = predictions_to_rallies(probs, center_times, inference_config)
        return [(r["start_seconds"], r["end_seconds"]) for r in rallies]

    raw = _resolve_raw(video_path, corners, feature_path, detector, detect_fps)
    if raw is None:
        return _audio_only()

    if combiner is None:
        path = combiner_path or default_combiner_path()
        if not Path(path).exists():
            return _audio_only()
        combiner = JointCombiner.load(path)

    visual, valid = robust_visual_features(
        raw, center_times, dilation=dilation, half_window_s=half_window_s
    )
    p_joint = combiner.predict_proba(combiner_feature_matrix(probs, visual, valid))
    p_joint = smooth_predictions(p_joint, inference_config.smooth_kernel)
    rallies = predictions_to_rallies(p_joint, center_times, inference_config)
    return [(r["start_seconds"], r["end_seconds"]) for r in rallies]


def predict_joint(video_path: str | Path, **kwargs) -> list[dict[str, float]]:
    """Like :func:`predict_joint_intervals` but returns ``predict_video``-shaped dicts."""
    intervals = predict_joint_intervals(video_path, **kwargs)
    return [
        {
            "start_seconds": round(s, 3),
            "end_seconds": round(e, 3),
            "duration_seconds": round(e - s, 3),
        }
        for (s, e) in intervals
    ]
