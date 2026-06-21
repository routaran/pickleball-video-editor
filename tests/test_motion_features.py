"""Tests for ml.motion.features (per-frame feature computation + resampling)."""

from __future__ import annotations

import numpy as np

from ml.motion.features import (
    FEATURE_KEYS,
    compute_frame_features,
    load_feature_series,
    resample_features,
    save_feature_series,
)


def _pts(coords):
    return np.array(coords, dtype=np.float64).reshape(-1, 2)


def test_empty_frame_yields_zeros_and_resets_displacement():
    times = np.array([0.0, 1.0])
    # frame0 empty; frame1 has players — displacement[1] must be 0 because the
    # previous (empty) frame provides no centroid reference.
    points = [_pts([]), _pts([[0.2, 0.2], [0.8, 0.8]])]
    feat = compute_frame_features(times, points)
    assert feat["n_detections"][0] == 0
    assert feat["displacement"][1] == 0.0
    assert feat["n_detections"][1] == 2


def test_cross_net_symmetry_balanced_vs_one_sided():
    times = np.arange(2.0)
    balanced = _pts([[0.3, 0.2], [0.7, 0.2], [0.3, 0.8], [0.7, 0.8]])  # 2 near, 2 far
    one_sided = _pts([[0.3, 0.1], [0.7, 0.1], [0.4, 0.2], [0.6, 0.2]])  # all near
    feat = compute_frame_features(times, [balanced, one_sided])
    assert feat["cross_net_symmetry"][0] == 1.0
    assert feat["cross_net_symmetry"][1] == 0.0
    assert feat["n_detections"][0] == 4


def test_spatial_std_higher_when_spread():
    times = np.arange(2.0)
    clustered = _pts([[0.50, 0.50], [0.51, 0.50]])
    spread = _pts([[0.1, 0.1], [0.9, 0.9]])
    feat = compute_frame_features(times, [clustered, spread])
    assert feat["spatial_std"][1] > feat["spatial_std"][0]


def test_displacement_tracks_centroid_motion():
    times = np.arange(3.0)
    # Constant single point at (0.2,0.2) then moved to (0.5,0.6).
    p0 = _pts([[0.2, 0.2]])
    p1 = _pts([[0.2, 0.2]])
    p2 = _pts([[0.5, 0.6]])
    feat = compute_frame_features(times, [p0, p1, p2])
    assert feat["displacement"][1] == 0.0  # no motion frame0->1
    expected = float(np.hypot(0.5 - 0.2, 0.6 - 0.2))
    assert feat["displacement"][2] == np.float64(expected)


def test_resample_windowed_mean_and_validity():
    times = np.array([0.0, 1.0, 2.0, 3.0])
    points = [
        _pts([]),
        _pts([[0.3, 0.2], [0.7, 0.8]]),
        _pts([[0.3, 0.2], [0.7, 0.8]]),
        _pts([]),
    ]
    feat = compute_frame_features(times, points)
    # Query at t=1 with a 0.6s half-window captures only frame t=1 -> n=2.
    resampled, valid = resample_features(feat, np.array([1.0, 10.0]), half_window_s=0.6)
    assert valid[0] is np.True_
    assert resampled["n_detections"][0] == 2
    # Query far outside the series is invalid.
    assert valid[1] is np.False_
    for key in FEATURE_KEYS:
        assert resampled[key][1] == 0.0


def test_save_load_roundtrip(tmp_path):
    times = np.arange(3.0)
    points = [_pts([[0.2, 0.2]]), _pts([[0.5, 0.5]]), _pts([])]
    feat = compute_frame_features(times, points)
    out = tmp_path / "vid.npz"
    save_feature_series(out, feat, fps_out=5.0, video_path="/x/vid.mp4")
    loaded = load_feature_series(out)
    for key in ("t", *FEATURE_KEYS):
        np.testing.assert_allclose(loaded[key], feat[key])
