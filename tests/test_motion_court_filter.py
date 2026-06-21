"""Tests for ml.motion.court_filter.CourtModel.

Covers court-polygon membership (including dilation and adjacent-court
rejection) and the normalised court-plane projection (corner mapping + net
split at y = 0.5).
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.motion.court_filter import CourtModel, foot_point

# A simple axis-aligned rectangle in pixel space, in team/perimeter order
# (TL, TR, BR, BL) as compute_homography expects.
CORNERS = [(100, 100), (300, 100), (300, 200), (100, 200)]


def test_foot_point_is_bottom_centre():
    assert foot_point((10, 20, 30, 80)) == (20.0, 80.0)


def test_on_court_inside_and_outside():
    court = CourtModel(CORNERS, dilation=0.0)
    assert court.on_court(200, 150) is True  # centre
    assert court.on_court(0, 0) is False  # far outside (adjacent court / stands)
    assert court.on_court(500, 150) is False


def test_dilation_admits_just_off_court():
    # Centroid is (200, 150); a 12% dilation moves the left edge from x=100 to
    # x = 200 - 100*1.12 = 88, so x=92 is in but x=80 is out.
    court = CourtModel(CORNERS, dilation=0.12)
    assert court.on_court(92, 150) is True
    assert court.on_court(80, 150) is False


def test_filter_on_court_keeps_only_inside():
    court = CourtModel(CORNERS, dilation=0.0)
    feet = [(200, 150), (0, 0), (250, 180)]
    assert court.filter_on_court(feet) == [(200, 150), (250, 180)]


def test_to_court_plane_maps_first_corner_to_origin():
    court = CourtModel(CORNERS, dilation=0.0)
    out = court.to_court_plane([CORNERS[0]])
    assert out.shape == (1, 2)
    np.testing.assert_allclose(out[0], [0.0, 0.0], atol=1e-4)


def test_to_court_plane_net_split():
    # Team 1 baseline (top edge, corners 0-1) -> y≈0 (near half, < 0.5);
    # Team 2 baseline (bottom edge, corners 2-3) -> y≈1 (far half, > 0.5).
    court = CourtModel(CORNERS, dilation=0.0)
    near = court.to_court_plane([(200, 105)])  # just below top edge
    far = court.to_court_plane([(200, 195)])  # just above bottom edge
    assert near[0, 1] < 0.5
    assert far[0, 1] > 0.5


def test_to_court_plane_empty():
    court = CourtModel(CORNERS, dilation=0.0)
    out = court.to_court_plane([])
    assert out.shape == (0, 2)


def test_rejects_wrong_corner_count():
    with pytest.raises(ValueError):
        CourtModel([(0, 0), (1, 1), (2, 2)])
