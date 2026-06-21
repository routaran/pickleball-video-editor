"""Tests for ml.motion.court_apply (cheap-path court filter + projection).

Exercises the Change-0 split: a raw foot-point cache + a court dilation knob ->
on-court, court-plane points (carrying track ids) -> per-frame features (with
per-track displacement).  Uses cv2 via CourtModel (opencv-python-headless).
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.motion.court_apply import DEFAULT_DILATION, apply_court, features_from_raw

# Axis-aligned rectangle in pixel space, in team/perimeter order (TL, TR, BR, BL).
CORNERS = [(100, 100), (300, 100), (300, 200), (100, 200)]


def _raw(foot_xy, track_ids, frame_offsets, t, corners=CORNERS):
    foot = np.asarray(foot_xy, dtype=np.float32).reshape(-1, 2)
    return {
        "foot_x": foot[:, 0].copy(),
        "foot_y": foot[:, 1].copy(),
        "frame_offsets": np.asarray(frame_offsets, dtype=np.int64),
        "track_id": np.asarray(track_ids, dtype=np.int64),
        "scaled_corners": np.asarray(corners, dtype=np.float32),
        "t": np.asarray(t, dtype=np.float64),
    }


def test_apply_court_filters_and_projects():
    # One detection at court centre (kept), one far outside (rejected).
    raw = _raw(
        foot_xy=[[200, 150], [0, 0]],
        track_ids=[5, 6],
        frame_offsets=[0, 2],
        t=[0.0],
    )
    court_pts, kept_ids = apply_court(raw, dilation=0.0)
    assert len(court_pts) == 1
    assert court_pts[0].shape == (1, 2)
    # Centre of the rectangle maps to ~the centre of the normalised court plane
    # (small offset from canonical-pixel quantisation).
    np.testing.assert_allclose(court_pts[0][0], [0.5, 0.5], atol=1e-2)
    np.testing.assert_array_equal(kept_ids[0], [5])


def test_apply_court_empty_frame_yields_empty_arrays():
    raw = _raw(foot_xy=[], track_ids=[], frame_offsets=[0, 0], t=[0.0])
    court_pts, kept_ids = apply_court(raw, dilation=0.0)
    assert court_pts[0].shape == (0, 2)
    assert kept_ids[0].shape == (0,)


def test_dilation_admits_just_off_court_points():
    # Centroid (200,150); a point at x=92 is outside the bare court but inside a
    # 12% dilation (left edge moves 100 -> 88).  So dilation flips it to on-court.
    raw = _raw(foot_xy=[[92, 150]], track_ids=[1], frame_offsets=[0, 1], t=[0.0])

    tight, _ = apply_court(raw, dilation=0.0)
    assert tight[0].shape == (0, 2)  # rejected without dilation

    wide, wide_ids = apply_court(raw, dilation=DEFAULT_DILATION)
    assert wide[0].shape == (1, 2)  # admitted with the default dilation
    np.testing.assert_array_equal(wide_ids[0], [1])


def test_features_from_raw_per_track_displacement():
    # Same track (id 5) moves +10px in x (court width 200px -> +0.05 normalised)
    # between two frames; per-track displacement should report that motion.
    raw = _raw(
        foot_xy=[[200, 150], [210, 150]],
        track_ids=[5, 5],
        frame_offsets=[0, 1, 2],
        t=[0.0, 0.2],
    )
    feat = features_from_raw(raw, dilation=0.0)
    np.testing.assert_array_equal(feat["n_detections"], [1, 1])
    assert feat["displacement"][0] == 0.0
    assert feat["displacement"][1] == pytest.approx(0.05, abs=1e-3)
