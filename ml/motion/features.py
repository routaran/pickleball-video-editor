"""Collapse per-frame on-court detections into a motion feature series.

The audio model classifies ~1 s windows at a 0.25 s hop.  Motion is sampled
independently (e.g. 5 fps), so we compute a small set of per-frame scalar
features and then resample them onto the audio window centre-times before
fusion.

Per-frame features (all identity-free, so no fragile multi-object tracking is
required):

* ``n_detections``       — on-court person count (≈4 during a rally).
* ``spatial_std``        — spread of on-court foot-points on the court plane
                           (high when players are distributed, low when clustered
                           at the net or a bench).
* ``cross_net_symmetry`` — ``2*min(near, far)/total`` in ``[0, 1]``; 1.0 for a
                           balanced two-and-two, 0.0 when everyone is on one side.
* ``displacement``       — magnitude of the on-court centroid's frame-to-frame
                           motion.  The doc rightly rejects tracking, so without
                           identity this is only a coarse motion proxy; fusion
                           **de-weights it** accordingly.

The heavy detection pass is run once per video and these features cached, so
threshold tuning re-runs only the cheap fusion step.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = [
    "FEATURE_KEYS",
    "compute_frame_features",
    "resample_features",
    "save_feature_series",
    "load_feature_series",
]

FEATURE_KEYS = ("n_detections", "spatial_std", "cross_net_symmetry", "displacement")


def compute_frame_features(
    times_s: np.ndarray,
    court_points_per_frame: list[np.ndarray],
) -> dict[str, np.ndarray]:
    """Compute the per-frame scalar feature series.

    Args:
        times_s: ``(F,)`` frame timestamps in seconds.
        court_points_per_frame: Length-``F`` list of ``(k_i, 2)`` normalised
            court-plane foot-points for each frame.

    Returns:
        Dict with ``"t"`` plus every key in :data:`FEATURE_KEYS`, each a
        ``(F,)`` float array.
    """
    f = len(times_s)
    n = np.zeros(f, dtype=np.float64)
    spatial_std = np.zeros(f, dtype=np.float64)
    symmetry = np.zeros(f, dtype=np.float64)
    displacement = np.zeros(f, dtype=np.float64)

    prev_centroid: np.ndarray | None = None
    for i, pts in enumerate(court_points_per_frame):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        k = len(pts)
        n[i] = k
        if k == 0:
            # No on-court players -> reset displacement reference so the next
            # populated frame doesn't register a spurious jump.
            prev_centroid = None
            continue

        centroid = pts.mean(axis=0)
        if k >= 2:
            spatial_std[i] = float(np.sqrt(pts[:, 0].var() + pts[:, 1].var()))
            near = int(np.sum(pts[:, 1] < 0.5))
            far = k - near
            symmetry[i] = (2.0 * min(near, far)) / k
        if prev_centroid is not None:
            displacement[i] = float(np.linalg.norm(centroid - prev_centroid))
        prev_centroid = centroid

    return {
        "t": np.asarray(times_s, dtype=np.float64),
        "n_detections": n,
        "spatial_std": spatial_std,
        "cross_net_symmetry": symmetry,
        "displacement": displacement,
    }


def resample_features(
    features: dict[str, np.ndarray],
    query_times_s: np.ndarray,
    half_window_s: float = 0.5,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Resample per-frame features onto arbitrary query times by windowed mean.

    For each query time ``q`` the feature value is the mean of all frames whose
    timestamp lies in ``[q - half_window_s, q + half_window_s]``.  Query times
    with no frames in range are marked invalid (their features are left at 0).

    Args:
        features: Output of :func:`compute_frame_features`.
        query_times_s: ``(Q,)`` times to resample onto (the audio window
            centre-times).
        half_window_s: Half-width of the averaging window; ``0.5`` gives a ~1 s
            window matching the audio model's effective resolution.

    Returns:
        ``(resampled, valid)`` where ``resampled`` has the
        :data:`FEATURE_KEYS` keys (each ``(Q,)``) and ``valid`` is a ``(Q,)``
        bool array, ``True`` where at least one frame contributed.
    """
    t = np.asarray(features["t"], dtype=np.float64)
    q = np.asarray(query_times_s, dtype=np.float64)
    out = {key: np.zeros(len(q), dtype=np.float64) for key in FEATURE_KEYS}
    valid = np.zeros(len(q), dtype=bool)

    if t.size == 0:
        return out, valid

    order = np.argsort(t)
    t_sorted = t[order]
    for i, qt in enumerate(q):
        lo = np.searchsorted(t_sorted, qt - half_window_s, side="left")
        hi = np.searchsorted(t_sorted, qt + half_window_s, side="right")
        if hi <= lo:
            continue
        idx = order[lo:hi]
        valid[i] = True
        for key in FEATURE_KEYS:
            out[key][i] = float(features[key][idx].mean())

    return out, valid


def save_feature_series(
    path: str | Path,
    features: dict[str, np.ndarray],
    fps_out: float,
    video_path: str | Path,
) -> None:
    """Persist a per-frame feature series to a ``.npz`` file.

    The heavy YOLO pass is run once and its features cached here so threshold
    tuning re-runs only the cheap fusion step.

    Args:
        path: Destination ``.npz`` path (parent dirs are created).
        features: Output of :func:`compute_frame_features`.
        fps_out: Sampling rate the features were computed at.
        video_path: Source video path (recorded for provenance).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        t=features["t"],
        n_detections=features["n_detections"],
        spatial_std=features["spatial_std"],
        cross_net_symmetry=features["cross_net_symmetry"],
        displacement=features["displacement"],
        fps_out=np.asarray(fps_out, dtype=np.float64),
        video_path=np.asarray(str(video_path)),
    )


def load_feature_series(path: str | Path) -> dict[str, np.ndarray]:
    """Load a feature series saved by :func:`save_feature_series`.

    Returns:
        Dict with ``"t"`` and every :data:`FEATURE_KEYS` key as ``(F,)`` arrays.
    """
    with np.load(path, allow_pickle=False) as data:
        return {
            "t": data["t"],
            "n_detections": data["n_detections"],
            "spatial_std": data["spatial_std"],
            "cross_net_symmetry": data["cross_net_symmetry"],
            "displacement": data["displacement"],
        }
