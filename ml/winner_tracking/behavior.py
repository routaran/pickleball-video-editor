"""Post-rally player-behavior features for rally-winner prediction (no ball GT).

Hypothesis (GPT-5.5-reviewed pivot): after a rally ends, the winning vs losing side
move differently — who chases the dead ball, who resets to serve, who disengages.
This is measurable from person boxes + the homography, using the 1,847 existing
rally-winner labels and NO ball ground truth.

Design discipline:
- Foot-points (box bottom-centre) map to the canonical court (ground-plane homography
  is valid for feet).  Team 1 = canonical top half (y<64), Team 2 = bottom (y>64).
- Features are **side-differenced** (Team1-side minus Team2-side) wherever natural, so
  they are court-side-absolute (matching the label) and robust to camera/date bias.
- Detection-quality fields are kept SEPARATE (q_*) for abstention/nuisance control,
  never used as predictive inputs.
- Window starts at/after rally_end; clips are extracted from the FULL source video, so
  the post-rally window always exists (no highlight-cut truncation in the audit).
"""

import argparse
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from ml.video_features import CANONICAL_SIZE, compute_homography
from ml.winner_tracking.clip_io import extract_raw_frames
from ml.winner_tracking.corpus import RallyRecord, load_rally_records, stratified_dev_sample

logger = logging.getLogger("behavior_audit")
_W, _H = CANONICAL_SIZE
_NET_Y = _H / 2.0
_DEFAULT_OUT = Path(__file__).parent / "cache" / "dev_behavior.jsonl"


def _footpoints_canonical(boxes, homography) -> np.ndarray:
    """Map box bottom-centres to canonical court coords; return (N,2) or empty."""
    if not boxes:
        return np.zeros((0, 2))
    pts = np.array([[(x1 + x2) / 2.0, y2] for (x1, y1, x2, y2) in boxes], np.float32)
    can = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), homography).reshape(-1, 2)
    return can


def _side_centroids(per_frame_pts: list[np.ndarray]) -> dict:
    """Per-frame per-side centroid + count.  Side 0 = top (y<net), side 1 = bottom."""
    traj0, traj1, cnt0, cnt1 = [], [], [], []
    for pts in per_frame_pts:
        if len(pts) == 0:
            traj0.append(None); traj1.append(None); cnt0.append(0); cnt1.append(0); continue
        top = pts[pts[:, 1] < _NET_Y]
        bot = pts[pts[:, 1] >= _NET_Y]
        traj0.append(top.mean(axis=0) if len(top) else None)
        traj1.append(bot.mean(axis=0) if len(bot) else None)
        cnt0.append(len(top)); cnt1.append(len(bot))
    return {"traj0": traj0, "traj1": traj1, "cnt0": cnt0, "cnt1": cnt1}


def _path_len(traj, lo=0, hi=None) -> float:
    hi = len(traj) if hi is None else hi
    pts = [p for p in traj[lo:hi] if p is not None]
    return float(sum(np.linalg.norm(pts[i] - pts[i - 1]) for i in range(1, len(pts))))


def _first_last(traj):
    pts = [p for p in traj if p is not None]
    return (pts[0], pts[-1]) if pts else (None, None)


def behavior_features(
    rec: RallyRecord, person, window_s: float = 4.0, fps: int = 12
) -> tuple[dict, dict]:
    """Return (predictive_features, quality_fields) for one rally's post window."""
    frames, _ = extract_raw_frames(rec.video_path, rec.end_s, rec.end_s + window_s, fps,
                                   rec.native_size)
    boxes = person.boxes_per_frame(frames, stride=1)
    homography = compute_homography([(int(x), int(y)) for x, y in rec.corners])
    pf = [_footpoints_canonical(b, homography) for b in boxes]
    sc = _side_centroids(pf)
    n = len(frames)
    one, two = max(1, fps), max(1, 2 * fps)

    feats: dict[str, float] = {}
    qual: dict[str, float] = {}

    # Per-side scalar summaries (canonical units).
    for s, traj, cnt in ((0, sc["traj0"], sc["cnt0"]), (1, sc["traj1"], sc["cnt1"])):
        first, last = _first_last(traj)
        base_y = 0.0 if s == 0 else float(_H)            # own baseline
        # toward-own-baseline displacement (+ = moved toward own baseline / to retrieve-deep)
        toward_base = 0.0
        toward_net = 0.0
        end_depth = 0.0   # distance behind net (how deep on own side)
        if first is not None and last is not None:
            toward_base = -(last[1] - first[1]) if s == 0 else (last[1] - first[1])
            toward_net = (last[1] - first[1]) if s == 0 else -(last[1] - first[1])
            end_depth = abs(last[1] - _NET_Y)
        feats[f"path_s{s}"] = _path_len(traj)
        feats[f"path1s_s{s}"] = _path_len(traj, 0, one)
        feats[f"path2s_s{s}"] = _path_len(traj, 0, two)
        feats[f"towardbase_s{s}"] = toward_base
        feats[f"towardnet_s{s}"] = toward_net
        feats[f"enddepth_s{s}"] = end_depth
        feats[f"endcount_s{s}"] = float(cnt[-1] if cnt else 0)
        feats[f"meancount_s{s}"] = float(np.mean(cnt)) if cnt else 0.0

    # Side-differenced features (Team1 - Team2): court-side-absolute, camera-robust.
    for stem in ("path", "path1s", "path2s", "towardbase", "towardnet",
                 "enddepth", "endcount", "meancount"):
        feats[f"d_{stem}"] = feats[f"{stem}_s0"] - feats[f"{stem}_s1"]

    # Quality / coverage (abstention only).
    counts = [c0 + c1 for c0, c1 in zip(sc["cnt0"], sc["cnt1"])]
    qual["n_frames"] = float(n)
    qual["mean_persons"] = float(np.mean(counts)) if counts else 0.0
    qual["frac_ge2"] = float(np.mean([c >= 2 for c in counts])) if counts else 0.0
    qual["frac_ge3"] = float(np.mean([c >= 3 for c in counts])) if counts else 0.0
    qual["side0_detfrac"] = float(np.mean([c > 0 for c in sc["cnt0"]])) if sc["cnt0"] else 0.0
    qual["side1_detfrac"] = float(np.mean([c > 0 for c in sc["cnt1"]])) if sc["cnt1"] else 0.0
    qual["covered"] = 1.0 if (counts and np.mean(counts) >= 1.0) else 0.0
    return feats, qual


def run_behavior_audit(records, out_path, window_s, fps):
    from ml.winner_tracking.person import PersonDetector
    person = PersonDetector()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        done = {json.loads(l)["key"] for l in out_path.read_text().splitlines() if l.strip()}
    todo = [r for r in records if r.key not in done]
    logger.info("Behavior audit: %d rallies (%d done, %d todo), device=%s",
                len(records), len(done), len(todo), person.device)
    t_start = time.time()
    with out_path.open("a") as fh:
        for i, rec in enumerate(todo):
            try:
                feats, qual = behavior_features(rec, person, window_s, fps)
                row = {"key": rec.key, "video": rec.video_name, "date_group": rec.date_group,
                       "winning_team": rec.winning_team, "winner_role": rec.winner_role}
                row.update({f"f_{k}": round(float(v), 5) for k, v in feats.items()})
                row.update({f"q_{k}": round(float(v), 5) for k, v in qual.items()})
            except Exception as exc:  # noqa: BLE001
                logger.warning("FAILED %s: %s", rec.key, exc)
                row = {"key": rec.key, "winning_team": rec.winning_team, "error": str(exc)}
            fh.write(json.dumps(row) + "\n"); fh.flush()
            if (i + 1) % 10 == 0 or i == 0:
                rate = (time.time() - t_start) / (i + 1)
                logger.info("  [%d/%d] %s  eta=%.0fmin", i + 1, len(todo), rec.key,
                            rate * (len(todo) - i - 1) / 60)
    logger.info("Behavior audit done -> %s (%.1f min)", out_path, (time.time() - t_start) / 60)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--target", type=int, default=200)
    ap.add_argument("--window", type=float, default=4.0)
    ap.add_argument("--fps", type=int, default=12)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    records = load_rally_records()
    if args.target > 0:
        records = stratified_dev_sample(records, target=args.target)
    run_behavior_audit(records, args.out, args.window, args.fps)


if __name__ == "__main__":
    main()
