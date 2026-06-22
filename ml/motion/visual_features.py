"""Robust per-window visual features for audio+visual rally fusion.

The audio model emits a rally-active probability per ~1 s window at a 0.25 s hop
(``ml.predict.predict_raw``).  This module produces, on the *same* query grid, a
small set of **robust** visual features describing on-court player motion and the
reliability of that motion estimate.  Fusion (veto/trim, or a learned head)
consumes ``[p_audio, these features]``.

Design constraints (from the GPT-5.5 adversarial review):

* **No raw frame-to-frame instantaneous speed.**  At 5–10 fps, single-step
  displacement after the homography is dominated by foot-point jitter.  Instead
  every track's court-plane trajectory is lightly smoothed and speed is a
  **central difference over a ~0.4 s baseline**, then summarised over a 1–2 s
  window with **robust statistics** (median / p90), never ``max``.
* **Metric units.**  Normalised ``[0,1]^2`` court points are scaled to metres
  (court ``6.10 m`` wide × ``13.41 m`` long) so speed is in **m/s** and thresholds
  are interpretable (a brisk walk ≈ 1.4 m/s; rally movement is well above that).
* **Hygiene.**  Implausible speeds are capped, short tracklets are ignored, and
  speed is not computed across large temporal gaps in a track.
* **Reliability is a first-class feature.**  Windows with thin coverage, few
  on-court detections, or poor tracking are flagged so fusion can lean
  audio-only there instead of vetoing on noise.

The heavy cache (raw foot-points + ByteTrack ids) already exists; everything here
is cheap numpy over :func:`ml.motion.court_apply.apply_court` output — no GPU.
"""

from __future__ import annotations

import numpy as np

from ml.motion.court_apply import DEFAULT_DILATION, apply_court

__all__ = [
    "VISUAL_FEATURE_KEYS",
    "COURT_WIDTH_M",
    "COURT_LENGTH_M",
    "robust_visual_features",
]

# Standard pickleball court (both service areas): 20 ft × 44 ft.
COURT_WIDTH_M = 6.10     # sideline-to-sideline  -> normalised x in [0,1]
COURT_LENGTH_M = 13.41   # baseline-to-baseline  -> normalised y in [0,1] (net at y=0.5)

# Speed estimation knobs (defaults; tuned downstream, not here).
_SMOOTH_FRAMES = 3       # centred moving-average on each track's metric path
_SPEED_BASELINE_S = 0.4  # central-difference half-baseline ~ ±0.2 s
_MAX_SPEED_MPS = 12.0    # cap: faster than any real player => detection/track error
_MIN_TRACK_FRAMES = 3    # ignore tracklets shorter than this for speed
_MAX_GAP_S = 1.2         # don't difference across a track gap larger than this
_DEFAULT_MOVE_THRESH_MPS = 2.0   # "moving" = above a brisk walk
_MIN_WINDOW_FRAMES = 3   # a query window with fewer frames is invalid (abstain)

# Ordered feature vector.  Grouped motion / occupancy / reliability.
VISUAL_FEATURE_KEYS = (
    # motion (m/s, robust over the window)
    "speed_med",
    "speed_p90",
    "speed_mean",
    "frac_moving",
    # occupancy / court structure (robust per-frame medians / fractions)
    "n_det_med",
    "frac_ge2",
    "frac_ge4",
    "spatial_std_med",
    "symmetry_med",
    "frac_both_halves",
    # reliability (how much to trust the visual estimate in this window)
    "coverage",
    "frac_tracked",
    "n_speed_samples",
)


def _metric_path(points_norm: np.ndarray) -> np.ndarray:
    """Scale normalised ``[0,1]^2`` court points to metres (width × length)."""
    out = np.asarray(points_norm, dtype=np.float64).reshape(-1, 2).copy()
    out[:, 0] *= COURT_WIDTH_M
    out[:, 1] *= COURT_LENGTH_M
    return out


def _smooth(path: np.ndarray, k: int) -> np.ndarray:
    """Centred moving average over ``k`` frames (edge-replicated)."""
    n = path.shape[0]
    if n < 2 or k <= 1:
        return path
    k = min(k, n if n % 2 else n - 1)  # keep it odd and <= n
    if k < 3:
        return path
    pad = k // 2
    padded = np.pad(path, ((pad, pad), (0, 0)), mode="edge")
    kernel = np.ones(k) / k
    sx = np.convolve(padded[:, 0], kernel, mode="valid")
    sy = np.convolve(padded[:, 1], kernel, mode="valid")
    return np.stack([sx, sy], axis=1)


def _track_speed_samples(
    court_points: list[np.ndarray],
    track_ids: list[np.ndarray],
    times: np.ndarray,
    fps: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-(track, frame) smoothed central-difference speeds in m/s.

    Returns ``(sample_times, sample_speeds)`` concatenated over all tracks.
    Untracked detections (id < 0) and tracklets shorter than
    :data:`_MIN_TRACK_FRAMES` contribute no speed sample.
    """
    # Gather each track's (time, metric_xy) sequence in frame order.
    seqs: dict[int, list[tuple[float, float, float]]] = {}
    for fi, (pts, ids) in enumerate(zip(court_points, track_ids)):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        ids = np.asarray(ids, dtype=np.int64).reshape(-1)
        m = min(pts.shape[0], ids.shape[0])
        for j in range(m):
            tid = int(ids[j])
            if tid < 0:
                continue
            xm = pts[j, 0] * COURT_WIDTH_M
            ym = pts[j, 1] * COURT_LENGTH_M
            seqs.setdefault(tid, []).append((float(times[fi]), xm, ym))

    k = max(1, int(round((_SPEED_BASELINE_S * 0.5) * max(fps, 1e-6))))  # half-baseline in frames
    s_t: list[float] = []
    s_v: list[float] = []
    for seq in seqs.values():
        if len(seq) < _MIN_TRACK_FRAMES:
            continue
        arr = np.asarray(seq, dtype=np.float64)
        tt = arr[:, 0]
        path = _smooth(arr[:, 1:3], _SMOOTH_FRAMES)
        n = path.shape[0]
        for i in range(n):
            a, b = i - k, i + k
            if a < 0 or b >= n:
                continue
            span = tt[b] - tt[a]
            if span <= 0.0 or span > _MAX_GAP_S:
                continue
            v = float(np.linalg.norm(path[b] - path[a]) / span)
            if v > _MAX_SPEED_MPS:
                v = _MAX_SPEED_MPS
            s_t.append(tt[i])
            s_v.append(v)
    return np.asarray(s_t, dtype=np.float64), np.asarray(s_v, dtype=np.float64)


def _per_frame_occupancy(
    court_points: list[np.ndarray], track_ids: list[np.ndarray]
) -> dict[str, np.ndarray]:
    """Per-frame occupancy / structure scalars aligned to the frame timeline."""
    f = len(court_points)
    n_det = np.zeros(f)
    n_trk = np.zeros(f)
    sstd = np.zeros(f)
    sym = np.zeros(f)
    both = np.zeros(f, dtype=bool)
    for i, (pts, ids) in enumerate(zip(court_points, track_ids)):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        ids = np.asarray(ids, dtype=np.int64).reshape(-1)
        k = pts.shape[0]
        n_det[i] = k
        n_trk[i] = int(np.sum(ids >= 0))
        if k >= 2:
            sstd[i] = float(np.sqrt(pts[:, 0].var() + pts[:, 1].var()))
            near = int(np.sum(pts[:, 1] < 0.5))
            far = k - near
            sym[i] = (2.0 * min(near, far)) / k
            both[i] = near >= 1 and far >= 1
    return {"n_det": n_det, "n_trk": n_trk, "sstd": sstd, "sym": sym, "both": both}


def robust_visual_features(
    raw: dict[str, np.ndarray],
    query_times_s: np.ndarray,
    *,
    dilation: float = DEFAULT_DILATION,
    half_window_s: float = 1.0,
    move_thresh_mps: float = _DEFAULT_MOVE_THRESH_MPS,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Build robust per-window visual features aligned to ``query_times_s``.

    Args:
        raw: A raw-detection cache dict (see
            :func:`ml.motion.features.load_feature_series`).
        query_times_s: ``(Q,)`` audio window centre-times to align onto.
        dilation: Court-polygon dilation for the on-court filter (cheap-path knob).
        half_window_s: Half-width of the aggregation window (``1.0`` → 2 s window).
        move_thresh_mps: Speed above which a sample counts toward ``frac_moving``.

    Returns:
        ``(features, valid)``: ``features`` has every key in
        :data:`VISUAL_FEATURE_KEYS` (each ``(Q,)`` float64); ``valid`` is a
        ``(Q,)`` bool array, ``True`` where the window had enough frame coverage
        to trust the estimate.  Invalid windows have their features left at 0.
    """
    q = np.asarray(query_times_s, dtype=np.float64).reshape(-1)
    out = {key: np.zeros(q.shape[0], dtype=np.float64) for key in VISUAL_FEATURE_KEYS}
    valid = np.zeros(q.shape[0], dtype=bool)

    t = np.asarray(raw["t"], dtype=np.float64).reshape(-1)
    if t.size == 0 or q.size == 0:
        return out, valid
    fps = float(raw.get("fps_out", 10.0)) if hasattr(raw, "get") else float(raw["fps_out"])

    court_points, track_ids = apply_court(raw, dilation)
    occ = _per_frame_occupancy(court_points, track_ids)
    s_t, s_v = _track_speed_samples(court_points, track_ids, t, fps)

    order = np.argsort(t)
    t_sorted = t[order]
    s_order = np.argsort(s_t) if s_t.size else np.empty(0, dtype=int)
    s_t_sorted = s_t[s_order] if s_t.size else s_t
    s_v_sorted = s_v[s_order] if s_t.size else s_v

    expected = max(1.0, 2.0 * half_window_s * fps)

    for i, qt in enumerate(q):
        lo = np.searchsorted(t_sorted, qt - half_window_s, side="left")
        hi = np.searchsorted(t_sorted, qt + half_window_s, side="right")
        count = hi - lo
        if count < _MIN_WINDOW_FRAMES:
            continue
        valid[i] = True
        fidx = order[lo:hi]

        n_det = occ["n_det"][fidx]
        out["n_det_med"][i] = float(np.median(n_det))
        out["frac_ge2"][i] = float(np.mean(n_det >= 2))
        out["frac_ge4"][i] = float(np.mean(n_det >= 4))
        out["spatial_std_med"][i] = float(np.median(occ["sstd"][fidx]))
        out["symmetry_med"][i] = float(np.median(occ["sym"][fidx]))
        out["frac_both_halves"][i] = float(np.mean(occ["both"][fidx]))
        out["coverage"][i] = float(min(1.0, count / expected))
        n_trk_med = float(np.median(occ["n_trk"][fidx]))
        out["frac_tracked"][i] = n_trk_med / max(out["n_det_med"][i], 1e-6)

        if s_t_sorted.size:
            slo = np.searchsorted(s_t_sorted, qt - half_window_s, side="left")
            shi = np.searchsorted(s_t_sorted, qt + half_window_s, side="right")
            if shi > slo:
                w = s_v_sorted[slo:shi]
                out["speed_med"][i] = float(np.median(w))
                out["speed_p90"][i] = float(np.percentile(w, 90))
                out["speed_mean"][i] = float(np.mean(w))
                out["frac_moving"][i] = float(np.mean(w > move_thresh_mps))
                out["n_speed_samples"][i] = float(w.size)

    return out, valid
