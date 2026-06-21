"""Cheap-path court application: raw foot-points -> on-court motion features.

This is the second half of the split introduced by Change 0 of
``DILATION_TRACKING_SPEC.md``.  The GPU detector caches the *raw* foot-points (in
extracted-frame pixel space) plus per-detection track ids; this module — which
lives in the cheap, ultralytics-free path (only ``cv2`` via
:class:`~ml.motion.court_filter.CourtModel`) — takes that raw cache and a court
**dilation**, then:

1. rebuilds the :class:`CourtModel` from the cached corners at the requested
   dilation,
2. filters each frame's raw foot-points to the dilated court polygon,
3. projects the survivors onto the normalised court plane, carrying their track
   ids, and
4. computes the per-frame motion features (with **per-track** displacement, since
   ids are now available).

Because dilation is applied *here*, it is a cheap-path knob: tuning it re-runs
only this step (and the fusion downstream), never the GPU detector.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ml.motion.court_filter import CourtModel
from ml.motion.features import compute_frame_features, load_feature_series

__all__ = ["DEFAULT_DILATION", "apply_court", "features_from_raw", "load_features"]

# Matches CourtModel's own default; the cheap-path tuning knob for Change 1.
DEFAULT_DILATION = 0.12


def _frames_from_raw(
    raw: dict[str, np.ndarray],
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Un-flatten the ragged raw cache into per-frame ``(feet, track_ids)`` lists."""
    foot_x = np.asarray(raw["foot_x"], dtype=np.float64).reshape(-1)
    foot_y = np.asarray(raw["foot_y"], dtype=np.float64).reshape(-1)
    track_id = np.asarray(raw["track_id"], dtype=np.int64).reshape(-1)
    offsets = np.asarray(raw["frame_offsets"], dtype=np.int64).reshape(-1)

    feet_per_frame: list[np.ndarray] = []
    ids_per_frame: list[np.ndarray] = []
    for i in range(len(offsets) - 1):
        a, b = int(offsets[i]), int(offsets[i + 1])
        if b > a:
            feet_per_frame.append(np.stack([foot_x[a:b], foot_y[a:b]], axis=1))
        else:
            feet_per_frame.append(np.empty((0, 2), dtype=np.float64))
        ids_per_frame.append(track_id[a:b])
    return feet_per_frame, ids_per_frame


def apply_court(
    raw: dict[str, np.ndarray], dilation: float = DEFAULT_DILATION
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Filter + project the raw foot-points to the court at a given dilation.

    Args:
        raw: A raw-detection cache dict (see
            :func:`ml.motion.features.load_feature_series`).
        dilation: Court-polygon dilation fraction (Change 1 tuning knob).

    Returns:
        ``(court_points_per_frame, track_ids_per_frame)``: length-``F`` lists of
        ``(k_i, 2)`` normalised court-plane points and aligned ``(k_i,)`` track
        ids, restricted to the on-court detections.
    """
    feet_per_frame, ids_per_frame = _frames_from_raw(raw)
    corners = np.asarray(raw["scaled_corners"], dtype=np.float64).reshape(4, 2)
    court = CourtModel(corners, dilation=dilation)

    court_points: list[np.ndarray] = []
    kept_ids: list[np.ndarray] = []
    for feet, ids in zip(feet_per_frame, ids_per_frame):
        if feet.shape[0] == 0:
            court_points.append(np.empty((0, 2), dtype=np.float32))
            kept_ids.append(np.zeros(0, dtype=np.int64))
            continue
        mask = np.array([court.on_court(x, y) for x, y in feet], dtype=bool)
        on = feet[mask]
        proj = (
            court.to_court_plane(on)
            if on.shape[0]
            else np.empty((0, 2), dtype=np.float32)
        )
        court_points.append(proj)
        kept_ids.append(np.asarray(ids, dtype=np.int64).reshape(-1)[mask])
    return court_points, kept_ids


def features_from_raw(
    raw: dict[str, np.ndarray], dilation: float = DEFAULT_DILATION
) -> dict[str, np.ndarray]:
    """Build the per-frame feature series from a raw cache + a court dilation."""
    t = np.asarray(raw["t"], dtype=np.float64).reshape(-1)
    court_points, kept_ids = apply_court(raw, dilation)
    return compute_frame_features(t, court_points, track_ids_per_frame=kept_ids)


def load_features(
    path: str | Path, dilation: float = DEFAULT_DILATION
) -> dict[str, np.ndarray]:
    """Load a raw cache and build its feature series at ``dilation`` in one call."""
    return features_from_raw(load_feature_series(path), dilation)
