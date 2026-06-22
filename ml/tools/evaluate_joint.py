"""Honest evaluation of the audio+visual combiner vs audio-only.

Leave-one-session-out (group = recording-date prefix): for each session the
combiner is trained on the *other* sessions only, then scored on it, so nothing
is evaluated on its own training data.  Reports interval-level detection metrics
(IoU 0.5) per session and pooled — precision, recall, F1, boundary MAE,
false-positive seconds and over/under-segmentation — for audio-only vs combiner.

Window tables (audio probs + visual features + labels) are cached under
``ml/cache/joint_tables/`` so re-runs skip the audio inference.

Usage::

    python -m ml.tools.evaluate_joint --dir ~/Videos/pickleball
    python -m ml.tools.evaluate_joint --rebuild        # force-rebuild tables
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np

from ml.config import InferenceConfig, PathConfig
from ml.evaluation.event_metrics import aggregate_video_metrics, interval_detection_metrics
from ml.motion.joint_dataset import build_window_table, group_id_for
from ml.motion.joint_fusion import (
    DEFAULT_EDGE_THRESHOLD,
    JointCombiner,
    combiner_feature_matrix,
    hysteresis_intervals,
    loso_interval_f1,
)
from ml.motion.visual_features import VISUAL_FEATURE_KEYS

__all__ = ["main"]


def _table_cache_dir() -> Path:
    return PathConfig().cache_dir / "joint_tables"


def _load_or_build(jp: Path, rebuild: bool) -> dict | None:
    cache = _table_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    # We don't know the stem until we read the json; cheap to peek.
    try:
        vp = (json.loads(jp.read_text(encoding="utf-8")).get("video") or {}).get("path", "")
    except Exception:
        return None
    if not vp:
        return None
    stem = Path(vp).stem
    cpath = cache / f"{stem}.npz"
    if cpath.exists() and not rebuild:
        z = np.load(cpath, allow_pickle=True)
        return {k: z[k] for k in z.files} | {"video": stem, "group": group_id_for(vp), "json": str(jp)}
    table = build_window_table(jp)
    if table is None:
        return None
    np.savez(cpath, **{k: v for k, v in table.items() if k not in ("video", "group")})
    return table | {"json": str(jp)}


def _gt_intervals(jp: str) -> list[tuple[float, float]]:
    d = json.loads(Path(jp).read_text(encoding="utf-8"))
    out = []
    for r in d.get("rallies", []):
        if r.get("is_post_game"):
            continue
        ts = r.get("raw") or r.get("padded")
        if ts and ts["end_seconds"] > ts["start_seconds"]:
            out.append((ts["start_seconds"], ts["end_seconds"]))
    return out


def _to_intervals(prob, t, inf, threshold):
    from ml.predict import predictions_to_rallies, smooth_predictions  # noqa: PLC0415

    cfg = dataclasses.replace(inf, threshold=threshold)
    sm = smooth_predictions(prob, inf.smooth_kernel)
    return [(r["start_seconds"], r["end_seconds"]) for r in predictions_to_rallies(sm, t, cfg)]


def _feat(tbl):
    vis = {k: tbl[k] for k in VISUAL_FEATURE_KEYS}
    return combiner_feature_matrix(tbl["p_audio"], vis, tbl["valid"])


def _fmt(tag, a):
    bm = a["boundary_mae_s"]
    return (f"  {tag:24s} P {a['precision']:.3f}  R {a['recall']:.3f}  F1 {a['f1']:.3f}  "
            f"bMAE {('--' if bm is None else f'{bm:.2f}')}  fpS {a['fp_active_seconds']:.0f}  "
            f"over {a['n_over_segs']}  merge {a['n_merges']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evaluate_joint")
    ap.add_argument("--dir", type=Path, default=Path.home() / "Videos" / "pickleball")
    ap.add_argument("--rebuild", action="store_true", help="Force-rebuild window tables.")
    ap.add_argument("--threshold", type=float, default=None, help="Override decision threshold.")
    args = ap.parse_args(argv)

    inf = InferenceConfig()
    threshold = args.threshold if args.threshold is not None else inf.threshold

    tables = []
    for jp in sorted(args.dir.rglob("*.training.json")):
        tbl = _load_or_build(jp, args.rebuild)
        if tbl is not None and tbl["t"].size:
            tables.append(tbl)
    if not tables:
        print("No tables (is the motion cache populated?)")
        return 1
    groups = sorted({str(t["group"]) for t in tables})
    print(f"{len(tables)} videos, {len(groups)} sessions, "
          f"{sum(int(t['label'].sum()) for t in tables)} rally windows")

    # Leave-one-session-out combiner probabilities.
    comb_prob: dict[int, np.ndarray] = {}
    for held in groups:
        tr = [t for t in tables if str(t["group"]) != held]
        X = np.vstack([_feat(t) for t in tr])
        y = np.concatenate([t["label"] for t in tr])
        model = JointCombiner.fit(X, y)
        for i, t in enumerate(tables):
            if str(t["group"]) == held:
                comb_prob[i] = model.predict_proba(_feat(t))

    a_per, c_per, by_group = [], [], {}
    for i, t in enumerate(tables):
        gt = _gt_intervals(t["json"])
        am = interval_detection_metrics(_to_intervals(t["p_audio"], t["t"], inf, threshold), gt, 0.5)
        cm_intervals = hysteresis_intervals(
            comb_prob[i], t["t"], dataclasses.replace(inf, threshold=threshold),
            DEFAULT_EDGE_THRESHOLD,
        )
        cm = interval_detection_metrics(cm_intervals, gt, 0.5)
        a_per.append(am); c_per.append(cm)
        by_group.setdefault(str(t["group"]), ([], []))
        by_group[str(t["group"])][0].append(am)
        by_group[str(t["group"])][1].append(cm)

    print(f"\n=== per-session (LOSO, interval IoU 0.5, threshold {threshold}) ===")
    for g in groups:
        a = aggregate_video_metrics(by_group[g][0]); c = aggregate_video_metrics(by_group[g][1])
        print(f"  {g}: audio F1 {a['f1']:.3f} -> combiner F1 {c['f1']:.3f}  "
              f"(P {a['precision']:.3f}->{c['precision']:.3f}, R {a['recall']:.3f}->{c['recall']:.3f})")

    A = aggregate_video_metrics(a_per)
    # Pooled combiner result via the shared LOSO helper (verifies same numbers as c_per loop).
    C = loso_interval_f1(tables, threshold=threshold)
    print(f"\n=== POOLED (visual-eligible stratum, {len(tables)} videos) ===")
    print(_fmt("audio-only", A))
    print(_fmt("audio+visual combiner", C))
    print(f"\n  F1 {A['f1']:.3f} -> {C['f1']:.3f}  (+{C['f1']-A['f1']:.3f})   "
          f"precision {A['precision']:.3f} -> {C['precision']:.3f}  (+{C['precision']-A['precision']:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
