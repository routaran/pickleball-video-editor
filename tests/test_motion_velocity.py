"""Tests for robust visual motion features (ml.motion.visual_features).

The crux test is `test_speed_discriminates_rally_walk_jitter`: the whole
audio+visual approach rests on player *speed* separating a real rally (fast,
sustained movement) from a dead-ball return (players walking) and from a static
player whose foot-point merely jitters after the homography.  If that separation
doesn't hold in metres/second, nothing downstream will work.
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pytest

from ml.motion.visual_features import (
    COURT_LENGTH_M,
    COURT_WIDTH_M,
    VISUAL_FEATURE_KEYS,
    _metric_path,
    _per_frame_occupancy,
    _smooth,
    _track_speed_samples,
    robust_visual_features,
)

FPS = 10.0


def _single_track(ys, xs):
    """Build (court_points, ids, times) for one track from x/y normalised paths."""
    f = len(ys)
    court_points = [np.array([[xs[i], ys[i]]], dtype=np.float64) for i in range(f)]
    ids = [np.array([1], dtype=np.int64) for _ in range(f)]
    times = np.arange(f, dtype=np.float64) / FPS
    return court_points, ids, times


def test_metric_path_scaling():
    pts = np.array([[0.0, 0.0], [1.0, 1.0], [0.5, 0.5]])
    m = _metric_path(pts)
    assert np.allclose(m[1], [COURT_WIDTH_M, COURT_LENGTH_M])
    assert np.allclose(m[2], [COURT_WIDTH_M / 2, COURT_LENGTH_M / 2])


def test_smooth_reduces_jitter():
    rng = np.random.default_rng(0)
    base = np.tile([5.0, 5.0], (30, 1))
    noisy = base + rng.normal(0, 0.2, size=base.shape)
    sm = _smooth(noisy, 3)
    assert sm.shape == noisy.shape
    # Smoothed path is closer to the constant base than the noisy one.
    assert np.std(sm[:, 0]) < np.std(noisy[:, 0])


def test_speed_discriminates_rally_walk_jitter():
    f = 40  # 4 s at 10 fps
    t = np.arange(f) / FPS

    # Rally: player sprints back and forth ~1.34 m amplitude, 1.5 s period.
    rally_y = 0.5 + 0.1 * np.sin(2 * np.pi * t / 1.5)
    rc, ri, _ = _single_track(rally_y, np.full(f, 0.5))
    _, rally_v = _track_speed_samples(rc, ri, t, FPS)

    # Walk: steady ~0.4 m/s drift along the court length.
    walk_y = 0.3 + (0.4 / COURT_LENGTH_M) * t
    wc, wi, _ = _single_track(walk_y, np.full(f, 0.5))
    _, walk_v = _track_speed_samples(wc, wi, t, FPS)

    # Jitter: static player, foot-point noise ~10 cm.
    rng = np.random.default_rng(7)
    jit_y = 0.5 + rng.normal(0, 0.01, f)
    jit_x = 0.5 + rng.normal(0, 0.01, f)
    jc, ji, _ = _single_track(jit_y, jit_x)
    _, jit_v = _track_speed_samples(jc, ji, t, FPS)

    rally_med = float(np.median(rally_v))
    walk_med = float(np.median(walk_v))
    jit_med = float(np.median(jit_v))

    # The whole approach: rally is clearly faster than walking or jitter.
    assert rally_med > 2.0, f"rally median speed {rally_med:.2f} should exceed 2 m/s"
    assert walk_med < 1.0, f"walk median speed {walk_med:.2f} should be under 1 m/s"
    assert jit_med < 1.5, f"jitter median speed {jit_med:.2f} should be small"
    assert rally_med > 2 * walk_med
    assert rally_med > 2 * jit_med
    # Capped, never NaN.
    assert np.all(np.isfinite(rally_v)) and rally_v.max() <= 12.0


def test_short_tracklet_yields_no_speed():
    # Two-frame track is below _MIN_TRACK_FRAMES -> no speed samples.
    court_points = [np.array([[0.5, 0.5]]), np.array([[0.5, 0.6]])]
    ids = [np.array([1]), np.array([1])]
    times = np.array([0.0, 0.1])
    s_t, s_v = _track_speed_samples(court_points, ids, times, FPS)
    assert s_t.size == 0 and s_v.size == 0


def test_untracked_detections_excluded_from_speed():
    f = 20
    t = np.arange(f) / FPS
    court_points = [np.array([[0.5, 0.5 + 0.05 * i / f]]) for i in range(f)]
    ids = [np.array([-1]) for _ in range(f)]  # all untracked
    s_t, _ = _track_speed_samples(court_points, ids, t, FPS)
    assert s_t.size == 0


def test_occupancy_symmetry_two_and_two():
    # 2 near (y<0.5) + 2 far (y>0.5) -> full symmetry, both halves, n_det 4.
    pts = [np.array([[0.3, 0.2], [0.7, 0.3], [0.3, 0.8], [0.7, 0.7]])]
    ids = [np.array([1, 2, 3, 4])]
    occ = _per_frame_occupancy(pts, ids)
    assert occ["n_det"][0] == 4
    assert occ["sym"][0] == pytest.approx(1.0)
    assert bool(occ["both"][0]) is True
    assert occ["n_trk"][0] == 4


def _synthetic_raw(court_points, ids, times, fps=FPS):
    """Pack per-frame court-plane points into a raw cache whose homography is the
    identity over [0,1]^2 (axis-aligned full-frame corners), so apply_court is a
    no-op projection and we can drive robust_visual_features end-to-end."""
    # extract_size 1x1 with corners at the unit square -> homography maps the unit
    # square to the canonical plane; on_court keeps everything (dilated unit quad).
    foot_x, foot_y, tid, offsets, t_list = [], [], [], [0], []
    for pts, idrow, tt in zip(court_points, ids, times):
        pts = np.asarray(pts).reshape(-1, 2)
        foot_x.extend(pts[:, 0].tolist())
        foot_y.extend(pts[:, 1].tolist())
        tid.extend(np.asarray(idrow).reshape(-1).tolist())
        offsets.append(offsets[-1] + pts.shape[0])
        t_list.append(float(tt))
    return {
        "foot_x": np.asarray(foot_x, dtype=np.float32),
        "foot_y": np.asarray(foot_y, dtype=np.float32),
        "track_id": np.asarray(tid, dtype=np.int64),
        "frame_offsets": np.asarray(offsets, dtype=np.int64),
        "scaled_corners": np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32),
        "extract_size": np.asarray([1, 1], dtype=np.int64),
        "t": np.asarray(t_list, dtype=np.float64),
        "fps_out": np.asarray(fps, dtype=np.float64),
        "video_path": np.asarray("synthetic"),
    }


def test_robust_features_invalid_when_window_thin():
    f = 40
    t = np.arange(f) / FPS
    court_points, ids, _ = _single_track(0.5 + 0.1 * np.sin(t), np.full(f, 0.5))
    raw = _synthetic_raw(court_points, ids, t)
    # Query far past the end of the video -> no frames -> invalid.
    feats, valid = robust_visual_features(raw, np.array([100.0]))
    assert valid[0] == np.False_ or valid[0] is False or valid[0] == False  # noqa: E712
    assert all(k in feats for k in VISUAL_FEATURE_KEYS)


def test_robust_features_rally_window_is_fast_and_valid():
    f = 60
    t = np.arange(f) / FPS
    rally_y = 0.5 + 0.1 * np.sin(2 * np.pi * t / 1.5)
    court_points, ids, _ = _single_track(rally_y, np.full(f, 0.5))
    raw = _synthetic_raw(court_points, ids, t)
    feats, valid = robust_visual_features(raw, np.array([3.0]), half_window_s=1.0)
    assert bool(valid[0]) is True
    assert feats["speed_med"][0] > 2.0
    assert feats["frac_moving"][0] > 0.5
    assert feats["n_speed_samples"][0] > 0


@pytest.mark.parametrize("npz_path", sorted(glob.glob("ml/cache/motion/*.npz"))[:1])
def test_real_npz_smoke(npz_path):
    """Smoke test against a real 10fps extraction: shapes, finiteness, ranges."""
    from ml.motion.features import load_feature_series

    raw = load_feature_series(npz_path)
    t = np.asarray(raw["t"], dtype=np.float64)
    if t.size < 50:
        pytest.skip("cache too short")
    grid = np.arange(t.min() + 1.0, t.max() - 1.0, 1.0)
    feats, valid = robust_visual_features(raw, grid)
    for k in VISUAL_FEATURE_KEYS:
        assert feats[k].shape == grid.shape
        assert np.all(np.isfinite(feats[k]))
    assert valid.mean() > 0.5  # most interior windows have coverage
    assert feats["speed_med"].max() <= 12.0
    assert feats["speed_med"].min() >= 0.0
