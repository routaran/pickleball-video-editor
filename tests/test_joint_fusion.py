"""Tests for the audio+visual learned combiner (ml.motion.joint_fusion)."""

from __future__ import annotations

import numpy as np
import pytest

from ml.config import InferenceConfig
from ml.motion.joint_fusion import (
    COMBINER_FEATURE_NAMES,
    JointCombiner,
    combiner_feature_matrix,
    predict_joint_intervals,
)
from ml.motion.visual_features import VISUAL_FEATURE_KEYS


def _visual(q, fill=1.0):
    return {k: np.full(q, fill, dtype=np.float64) for k in VISUAL_FEATURE_KEYS}


def test_feature_matrix_order_and_invalid_zeroing():
    q = 5
    p = np.linspace(0.1, 0.9, q)
    vis = _visual(q, fill=3.0)
    valid = np.array([True, True, False, True, False])
    X = combiner_feature_matrix(p, vis, valid)
    assert X.shape == (q, len(COMBINER_FEATURE_NAMES))
    # col 0 is p_audio (never zeroed)
    assert np.allclose(X[:, 0], p)
    # visual cols zeroed where invalid
    assert np.allclose(X[~valid, 1:1 + len(VISUAL_FEATURE_KEYS)], 0.0)
    assert np.allclose(X[valid, 1], 3.0)
    # trailing valid flag
    assert np.allclose(X[:, -1], valid.astype(float))


def test_combiner_predict_matches_manual_sigmoid():
    names = COMBINER_FEATURE_NAMES
    d = len(names)
    comb = JointCombiner(
        mean=np.zeros(d), scale=np.ones(d),
        coef=np.r_[2.0, np.zeros(d - 1)], intercept=-1.0,
    )
    X = np.zeros((3, d)); X[:, 0] = [0.0, 0.5, 1.0]
    expect = 1.0 / (1.0 + np.exp(-(2.0 * X[:, 0] - 1.0)))
    assert np.allclose(comb.predict_proba(X), expect)


def test_combiner_fit_and_save_load_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    d = len(COMBINER_FEATURE_NAMES)
    X = rng.normal(size=(400, d))
    # label depends on p_audio (col 0) + one visual col -> learnable
    y = ((X[:, 0] + X[:, 1]) > 0).astype(float)
    comb = JointCombiner.fit(X, y)
    p1 = comb.predict_proba(X)
    assert p1.shape == (400,)
    assert ((p1 > 0.5) == (y > 0.5)).mean() > 0.8  # fits the signal

    path = tmp_path / "c.json"
    comb.save(path)
    comb2 = JointCombiner.load(path)
    assert np.allclose(comb.predict_proba(X), comb2.predict_proba(X))
    assert comb2.feature_names == COMBINER_FEATURE_NAMES


def test_predict_joint_falls_back_to_audio_only(monkeypatch, tmp_path):
    """With no motion cache and no combiner, predict_joint == audio-only."""
    import ml.motion.predict_fused as pf
    from ml.predict import predictions_to_rallies

    times = np.arange(0.0, 40.0, 0.25)
    # two clear rally blocks
    probs = np.zeros(times.size)
    probs[(times >= 5) & (times <= 12)] = 0.9
    probs[(times >= 20) & (times <= 30)] = 0.9
    monkeypatch.setattr(pf, "audio_window_probs", lambda *a, **k: (probs, times))

    out = predict_joint_intervals(
        "/no/such/video_zzz.mp4", feature_path=None,
        combiner_path=tmp_path / "missing.json",
    )
    inf = InferenceConfig()
    expect = [(r["start_seconds"], r["end_seconds"])
              for r in predictions_to_rallies(probs, times, inf)]
    assert out == expect
    assert len(out) == 2  # the two blocks survive min-duration


def test_predict_joint_uses_combiner_when_available(monkeypatch, tmp_path):
    """End-to-end with a synthetic cache + a combiner that trusts p_audio."""
    import ml.motion.predict_fused as pf
    from ml.motion.features import save_feature_series

    times = np.arange(0.0, 30.0, 0.25)
    probs = np.zeros(times.size)
    probs[(times >= 4) & (times <= 14)] = 0.8
    monkeypatch.setattr(pf, "audio_window_probs", lambda *a, **k: (probs, times))

    # Synthetic 10fps raw cache spanning the audio grid (identity homography).
    ft = np.arange(0.0, 30.0, 0.1)
    fx = np.full(ft.size, 0.5, dtype=np.float32)
    fy = np.full(ft.size, 0.5, dtype=np.float32)
    raw = {
        "schema_version": np.asarray(2, dtype=np.int64),
        "foot_x": fx, "foot_y": fy,
        "frame_offsets": np.arange(ft.size + 1, dtype=np.int64),
        "track_id": np.ones(ft.size, dtype=np.int64),
        "scaled_corners": np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32),
        "extract_size": np.asarray([1, 1], dtype=np.int64),
        "t": ft, "fps_out": np.asarray(10.0, dtype=np.float64),
        "video_path": np.asarray("synthetic"),
    }
    npz = tmp_path / "vid.npz"
    save_feature_series(npz, raw)

    d = len(COMBINER_FEATURE_NAMES)
    comb = JointCombiner(mean=np.zeros(d), scale=np.ones(d),
                         coef=np.r_[5.0, np.zeros(d - 1)], intercept=-2.0)
    out = predict_joint_intervals("/no/such/vid.mp4", feature_path=npz, combiner=comb)
    assert isinstance(out, list) and len(out) == 1
    s, e = out[0]
    assert 3.0 <= s <= 6.0 and 12.0 <= e <= 15.0  # ~recovers the audio block
