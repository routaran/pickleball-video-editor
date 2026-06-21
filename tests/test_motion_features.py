"""Tests for ml.motion.features (per-frame feature computation, raw cache I/O)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from ml.motion.features import (
    FEATURE_KEYS,
    RAW_SCHEMA_VERSION,
    compute_frame_features,
    flatten_detections,
    load_feature_series,
    resample_features,
    save_feature_series,
)


def _pts(coords):
    return np.array(coords, dtype=np.float64).reshape(-1, 2)


def _ids(values):
    return np.array(values, dtype=np.int64).reshape(-1)


@dataclass
class _Frame:
    """Minimal stand-in for detector.FrameDetections for flatten/save tests."""

    time_s: float
    foot_points: np.ndarray
    track_ids: np.ndarray


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


def test_per_track_displacement_uses_matched_ids():
    times = np.arange(3.0)
    # Track 7 moves +0.05 in x between frames 1 and 2; a *new* track 9 appears in
    # frame 2 and must not contribute (no prior position to compare against).
    pts = [_pts([[0.20, 0.20]]), _pts([[0.20, 0.20]]),
           _pts([[0.25, 0.20], [0.90, 0.90]])]
    ids = [_ids([7]), _ids([7]), _ids([7, 9])]
    feat = compute_frame_features(times, pts, track_ids_per_frame=ids)
    assert feat["displacement"][0] == 0.0  # first frame has no reference
    assert feat["displacement"][1] == 0.0  # track 7 did not move
    assert feat["displacement"][2] == pytest.approx(0.05)  # only track 7 counts


def test_per_track_displacement_ignores_id_switch():
    # An id switch between frames (1 -> 2) means no track is common, so the
    # per-track displacement is 0 even though *something* moved a long way.
    times = np.arange(2.0)
    pts = [_pts([[0.2, 0.2]]), _pts([[0.9, 0.9]])]
    ids = [_ids([1]), _ids([2])]
    feat = compute_frame_features(times, pts, track_ids_per_frame=ids)
    assert feat["displacement"][1] == 0.0


def test_per_track_displacement_skips_untracked():
    # An untracked detection (id -1) is excluded from the per-track signal.
    times = np.arange(2.0)
    pts = [_pts([[0.2, 0.2]]), _pts([[0.5, 0.5]])]
    ids = [_ids([-1]), _ids([-1])]
    feat = compute_frame_features(times, pts, track_ids_per_frame=ids)
    assert feat["displacement"][1] == 0.0


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


def test_flatten_detections_ragged_offsets():
    frames = [
        _Frame(0.0, _pts([[10, 20]]), _ids([1])),
        _Frame(0.2, _pts([]), _ids([])),  # empty frame
        _Frame(0.4, _pts([[30, 40], [50, 60]]), _ids([1, 2])),
    ]
    raw = flatten_detections(
        frames,
        scaled_corners=[[0, 0], [100, 0], [100, 50], [0, 50]],
        extract_size=(100, 50),
        fps_out=5.0,
        video_path="/x/vid.mp4",
    )
    np.testing.assert_array_equal(raw["frame_offsets"], [0, 1, 1, 3])
    np.testing.assert_allclose(raw["foot_x"], [10, 30, 50])
    np.testing.assert_allclose(raw["foot_y"], [20, 40, 60])
    np.testing.assert_array_equal(raw["track_id"], [1, 1, 2])
    np.testing.assert_allclose(raw["t"], [0.0, 0.2, 0.4])
    assert raw["scaled_corners"].shape == (4, 2)
    assert int(raw["schema_version"]) == RAW_SCHEMA_VERSION


def test_save_load_raw_roundtrip(tmp_path):
    frames = [
        _Frame(0.0, _pts([[10, 20]]), _ids([1])),
        _Frame(0.2, _pts([]), _ids([])),
        _Frame(0.4, _pts([[30, 40], [50, 60]]), _ids([1, 2])),
    ]
    raw = flatten_detections(
        frames,
        scaled_corners=[[0, 0], [100, 0], [100, 50], [0, 50]],
        extract_size=(100, 50),
        fps_out=5.0,
        video_path="/x/vid.mp4",
    )
    out = tmp_path / "vid.npz"
    save_feature_series(out, raw)
    loaded = load_feature_series(out)
    for key in ("foot_x", "foot_y", "frame_offsets", "track_id", "t"):
        np.testing.assert_allclose(loaded[key], raw[key])
    np.testing.assert_allclose(loaded["scaled_corners"], raw["scaled_corners"])
    assert int(loaded["schema_version"]) == RAW_SCHEMA_VERSION
    assert str(loaded["video_path"]) == "/x/vid.mp4"


def test_load_rejects_legacy_schema(tmp_path):
    # A v1-style cache (no schema_version) must raise, never be misread.
    out = tmp_path / "legacy.npz"
    np.savez(out, t=np.arange(3.0), n_detections=np.zeros(3), displacement=np.zeros(3))
    with pytest.raises(ValueError, match="re-extract|schema_version"):
        load_feature_series(out)
