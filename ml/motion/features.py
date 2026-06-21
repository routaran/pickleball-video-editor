"""Per-frame motion features + the raw-detection cache they are computed from.

The audio model classifies ~1 s windows at a 0.25 s hop.  Motion is sampled
independently (e.g. 5 fps), so we compute a small set of per-frame scalar
features and then resample them onto the audio window centre-times before
fusion.

Per-frame features:

* ``n_detections``       — on-court person count (≈4 during a rally).
* ``spatial_std``        — spread of on-court foot-points on the court plane
                           (high when players are distributed, low when clustered
                           at the net or a bench).
* ``cross_net_symmetry`` — ``2*min(near, far)/total`` in ``[0, 1]``; 1.0 for a
                           balanced two-and-two, 0.0 when everyone is on one side.
* ``displacement``       — mean per-track frame-to-frame court-plane motion.  With
                           ByteTrack ids (Change 2) this is a **real per-player**
                           motion signal (smooth, not the old anonymous-centroid
                           proxy); fusion's optional displacement gate keys off it.
                           When :func:`compute_frame_features` is called *without*
                           track ids it falls back to the legacy anonymous-centroid
                           displacement.

Cache layout (Change 0): the heavy GPU pass caches the **raw, pre-court-filter**
geometry — every detection's foot-point (in extracted-frame pixel space) plus its
track id — and the court corners.  The court-polygon filter, projection and the
feature compute above run later in the cheap path (:mod:`ml.motion.court_apply`),
so the court-dilation knob tunes with no GPU re-run.  Ragged per-frame detections
are stored flat (all detections concatenated) with ``frame_offsets`` slice
boundaries.  See :func:`save_feature_series` for the exact key list.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = [
    "FEATURE_KEYS",
    "RAW_SCHEMA_VERSION",
    "compute_frame_features",
    "resample_features",
    "flatten_detections",
    "save_feature_series",
    "load_feature_series",
]

FEATURE_KEYS = ("n_detections", "spatial_std", "cross_net_symmetry", "displacement")

# Bumped whenever the .npz cache layout changes.  v2 = raw foot-points + track ids
# (Change 0/2); v1 (computed-feature aggregates) had no ``schema_version`` key and
# is rejected by :func:`load_feature_series` so a stale cache can never be misread.
RAW_SCHEMA_VERSION = 2


def compute_frame_features(
    times_s: np.ndarray,
    court_points_per_frame: list[np.ndarray],
    track_ids_per_frame: list[np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """Compute the per-frame scalar feature series.

    Args:
        times_s: ``(F,)`` frame timestamps in seconds.
        court_points_per_frame: Length-``F`` list of ``(k_i, 2)`` normalised
            court-plane foot-points for each frame.
        track_ids_per_frame: Optional length-``F`` list of ``(k_i,)`` track ids
            aligned with ``court_points_per_frame``.  When given, ``displacement``
            is the mean over tracks present in consecutive frames of each track's
            court-plane movement (ids ``< 0`` are ignored).  When ``None``,
            ``displacement`` falls back to the legacy anonymous-centroid motion.

    Returns:
        Dict with ``"t"`` plus every key in :data:`FEATURE_KEYS`, each a
        ``(F,)`` float array.
    """
    f = len(times_s)
    n = np.zeros(f, dtype=np.float64)
    spatial_std = np.zeros(f, dtype=np.float64)
    symmetry = np.zeros(f, dtype=np.float64)
    displacement = np.zeros(f, dtype=np.float64)

    have_tracks = track_ids_per_frame is not None
    prev_centroid: np.ndarray | None = None
    prev_track_xy: dict[int, np.ndarray] = {}

    for i, pts in enumerate(court_points_per_frame):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        k = len(pts)
        n[i] = k
        if k == 0:
            # No on-court players -> drop the motion reference so the next
            # populated frame doesn't register a spurious jump.
            prev_centroid = None
            prev_track_xy = {}
            continue

        if k >= 2:
            spatial_std[i] = float(np.sqrt(pts[:, 0].var() + pts[:, 1].var()))
            near = int(np.sum(pts[:, 1] < 0.5))
            far = k - near
            symmetry[i] = (2.0 * min(near, far)) / k

        if have_tracks:
            ids = np.asarray(track_ids_per_frame[i], dtype=np.int64).reshape(-1)
            m = min(k, ids.shape[0])
            cur = {int(ids[j]): pts[j] for j in range(m) if int(ids[j]) >= 0}
            common = prev_track_xy.keys() & cur.keys()
            if common:
                displacement[i] = float(
                    np.mean(
                        [np.linalg.norm(cur[t] - prev_track_xy[t]) for t in common]
                    )
                )
            prev_track_xy = cur
        else:
            centroid = pts.mean(axis=0)
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


def flatten_detections(
    frames,
    *,
    scaled_corners,
    extract_size,
    fps_out: float,
    video_path: str | Path,
) -> dict[str, np.ndarray]:
    """Flatten per-frame raw detections into the flat ``.npz`` cache dict.

    Ragged per-frame detections are concatenated into flat ``foot_x``/``foot_y``/
    ``track_id`` arrays with a ``frame_offsets`` index, ready for
    :func:`save_feature_series`.

    Args:
        frames: Iterable of objects with ``foot_points`` ``(k, 2)``, ``track_ids``
            ``(k,)`` and ``time_s`` attributes (e.g.
            :class:`ml.motion.detector.FrameDetections`).
        scaled_corners: ``(4, 2)`` court corners in extracted-frame pixel space.
        extract_size: ``(width, height)`` the frames were decoded at.
        fps_out: Detection sample rate.
        video_path: Source video path (provenance).

    Returns:
        Dict of arrays keyed by the v2 schema (see :func:`save_feature_series`).
    """
    foot_x_parts: list[np.ndarray] = []
    foot_y_parts: list[np.ndarray] = []
    tid_parts: list[np.ndarray] = []
    offsets: list[int] = [0]
    t_list: list[float] = []

    for fd in frames:
        pts = np.asarray(fd.foot_points, dtype=np.float32).reshape(-1, 2)
        ids = np.asarray(fd.track_ids, dtype=np.int64).reshape(-1)
        if ids.shape[0] != pts.shape[0]:  # defensive: never misalign points/ids
            ids = np.full(pts.shape[0], -1, dtype=np.int64)
        foot_x_parts.append(pts[:, 0])
        foot_y_parts.append(pts[:, 1])
        tid_parts.append(ids)
        offsets.append(offsets[-1] + pts.shape[0])
        t_list.append(float(fd.time_s))

    def _cat(parts: list[np.ndarray], dtype) -> np.ndarray:
        return (
            np.concatenate(parts).astype(dtype)
            if parts
            else np.zeros(0, dtype=dtype)
        )

    return {
        "schema_version": np.asarray(RAW_SCHEMA_VERSION, dtype=np.int64),
        "foot_x": _cat(foot_x_parts, np.float32),
        "foot_y": _cat(foot_y_parts, np.float32),
        "frame_offsets": np.asarray(offsets, dtype=np.int64),
        "track_id": _cat(tid_parts, np.int64),
        "scaled_corners": np.asarray(scaled_corners, dtype=np.float32).reshape(4, 2),
        "extract_size": np.asarray(extract_size, dtype=np.int64).reshape(2),
        "t": np.asarray(t_list, dtype=np.float64),
        "fps_out": np.asarray(fps_out, dtype=np.float64),
        "video_path": np.asarray(str(video_path)),
    }


def save_feature_series(path: str | Path, raw: dict[str, np.ndarray]) -> None:
    """Persist a raw-detection series (v2 schema) to a ``.npz`` file.

    The heavy YOLO+tracking pass is run once and the raw geometry cached here so
    the cheap path (court filter + projection + feature compute) — and the
    court-dilation knob — re-run with no GPU.

    Args:
        path: Destination ``.npz`` path (parent dirs are created).
        raw: Dict produced by :func:`flatten_detections`.  Keys (v2 schema):

            * ``schema_version`` — scalar int (== :data:`RAW_SCHEMA_VERSION`)
            * ``foot_x``, ``foot_y`` — ``(N_total,)`` float32, all detections
              concatenated in time order
            * ``frame_offsets`` — ``(F+1,)`` int64 slice boundaries per frame
            * ``track_id`` — ``(N_total,)`` int64 (``-1`` = untracked)
            * ``scaled_corners`` — ``(4, 2)`` float32 (extracted-frame pixels)
            * ``extract_size`` — ``(2,)`` int64 ``(width, height)``
            * ``t`` — ``(F,)`` float64 frame timestamps (s)
            * ``fps_out`` — scalar float64
            * ``video_path`` — scalar str
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **raw)


def load_feature_series(path: str | Path) -> dict[str, np.ndarray]:
    """Load a raw-detection series saved by :func:`save_feature_series`.

    Returns:
        Dict with the v2 schema keys (see :func:`save_feature_series`).  Pass it
        to :func:`ml.motion.court_apply.features_from_raw` to obtain the feature
        series.

    Raises:
        ValueError: If the file is a legacy (pre-v2) cache with no
            ``schema_version`` key — it must be re-extracted, never silently
            misread under the new schema.
    """
    with np.load(path, allow_pickle=False) as data:
        if "schema_version" not in data.files:
            raise ValueError(
                f"{path}: legacy motion cache (no 'schema_version'). The cache "
                "schema changed to raw foot-points + track ids (Change 0/2). "
                "Re-extract in .venv-motion with "
                "`python -m ml.tools.extract_motion_features --overwrite ...`."
            )
        return {key: data[key] for key in data.files}
