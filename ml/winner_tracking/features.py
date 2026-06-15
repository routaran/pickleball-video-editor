"""Strictly-geometric features from recovered ball tracks, in canonical court space.

The homography (from the 4 court corners) maps image pixels to a canonical
256x128 rectangle where **Team 1 is the top half (y<64), Team 2 the bottom
(y>64), and the net is the horizontal mid-line (y=64)** — absolute across videos,
which is the whole point of using geometry instead of raw appearance.

Predictive features are geometric only (terminal position, side of net, vertical
travel direction = last-hitter proxy, out-of-bounds margins).  Track-quality
fields (reward, straightness, n_tracks) are returned separately and must be used
ONLY for abstention, never as predictive inputs (they can leak visibility/court).
"""

import cv2
import numpy as np

from ml.video_features import CANONICAL_SIZE, compute_homography
from ml.winner_tracking.track import Track

__all__ = ["geometric_features", "FEATURE_NAMES", "QUALITY_NAMES"]

_W, _H = CANONICAL_SIZE            # (256, 128)
_NET_Y = _H / 2.0

FEATURE_NAMES = [
    "end_cy_norm",        # terminal y in [0,1] (0=Team1 baseline, 1=Team2 baseline)
    "end_cx_norm",        # terminal x in [0,1]
    "end_side",           # sign(end_cy - net): -1 Team1 half, +1 Team2 half
    "delta_cy_norm",      # signed vertical travel (end-start)/H: + toward Team2
    "crossed_net",        # 1 if track crosses the net line
    "min_cy_norm",        # shallowest point (closest to Team1 baseline)
    "max_cy_norm",        # deepest point (closest to/past Team2 baseline)
    "out_long_team2",     # how far past Team2 baseline (y>H), normalized
    "out_long_team1",     # how far past Team1 baseline (y<0), normalized
    "out_side",           # how far outside the side lines (x<0 or x>W), normalized
    "topk_frac_end_team2",  # fraction of top-K tracks ending in Team2 half
    "topk_mean_end_cy",   # ballistic-weighted mean terminal y over top-K, normalized
]

QUALITY_NAMES = ["best_reward", "best_straightness", "best_len", "n_tracks", "covered"]


def _to_canonical(xs: list[float], ys: list[float], homography: np.ndarray) -> np.ndarray:
    pts = np.array([[x, y] for x, y in zip(xs, ys)], dtype=np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, homography).reshape(-1, 2)  # (N,2) canonical


def _track_straightness(t: Track) -> float:
    nd = float(np.hypot(t.xs[-1] - t.xs[0], t.ys[-1] - t.ys[0]))
    pl = float(sum(np.hypot(t.xs[i] - t.xs[i - 1], t.ys[i] - t.ys[i - 1])
                   for i in range(1, len(t.xs)))) + 1e-6
    return nd / pl


def geometric_features(
    tracks: list[Track], corners: list[list[int]]
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (predictive_features, quality_fields).

    When no track was recovered, predictive features are 0 and ``covered`` is 0.0
    so the caller can abstain.
    """
    feats = {name: 0.0 for name in FEATURE_NAMES}
    qual = {name: 0.0 for name in QUALITY_NAMES}
    if not tracks:
        return feats, qual

    homography = compute_homography([(int(x), int(y)) for x, y in corners])
    best = tracks[0]
    can = _to_canonical(best.xs, best.ys, homography)  # (N,2)
    cx_end, cy_end = float(can[-1, 0]), float(can[-1, 1])
    cx_start, cy_start = float(can[0, 0]), float(can[0, 1])
    cy_all = can[:, 1]

    feats["end_cy_norm"] = cy_end / _H
    feats["end_cx_norm"] = cx_end / _W
    feats["end_side"] = float(np.sign(cy_end - _NET_Y))
    feats["delta_cy_norm"] = (cy_end - cy_start) / _H
    feats["crossed_net"] = float((cy_all.min() < _NET_Y) and (cy_all.max() > _NET_Y))
    feats["min_cy_norm"] = float(cy_all.min()) / _H
    feats["max_cy_norm"] = float(cy_all.max()) / _H
    feats["out_long_team2"] = max(0.0, (cy_end - _H) / _H)
    feats["out_long_team1"] = max(0.0, (-cy_end) / _H)
    feats["out_side"] = max(0.0, (-cx_end) / _W, (cx_end - _W) / _W)

    # Top-K aggregate (ballistic-weighted) terminal side — robust to mis-ranking #1.
    end_cys: list[float] = []
    weights: list[float] = []
    frac_team2 = 0.0
    wsum = 0.0
    for t in tracks:
        c = _to_canonical(t.xs, t.ys, homography)
        ey = float(c[-1, 1])
        w = max(t.total_reward, 0.01) * (0.5 + _track_straightness(t))
        end_cys.append(ey)
        weights.append(w)
        wsum += w
        if ey > _NET_Y:
            frac_team2 += w
    feats["topk_frac_end_team2"] = frac_team2 / (wsum + 1e-6)
    feats["topk_mean_end_cy"] = (
        float(np.average(end_cys, weights=weights)) / _H if wsum > 0 else 0.0
    )

    qual["best_reward"] = float(best.total_reward)
    qual["best_straightness"] = float(_track_straightness(best))
    qual["best_len"] = float(best.length)
    qual["n_tracks"] = float(len(tracks))
    qual["covered"] = 1.0
    return feats, qual
