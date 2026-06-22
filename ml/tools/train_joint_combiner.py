"""Train + persist the audio+visual rally combiner (``joint_combiner.json``).

Builds the per-window ``[p_audio, visual…, valid]`` table for every corner-labelled
video with a motion cache (:func:`ml.motion.joint_dataset.build_window_table`),
fits the standardiser + class-balanced logistic regression
(:meth:`ml.motion.joint_fusion.JointCombiner.fit`) on the pooled windows, and
saves it.  The shipped model is trained on the full corpus; honest performance is
estimated separately by ``ml/tools/evaluate_joint.py`` (leave-one-session-out).

Usage::

    python -m ml.tools.train_joint_combiner --dir ~/Videos/pickleball
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ml.motion.joint_dataset import build_window_table
from ml.motion.joint_fusion import (
    JointCombiner,
    combiner_feature_matrix,
    default_combiner_path,
)
from ml.motion.visual_features import VISUAL_FEATURE_KEYS

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="train_joint_combiner")
    ap.add_argument("--dir", type=Path, default=Path.home() / "Videos" / "pickleball",
                    help="Directory to glob for *.training.json.")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path (default: ml/checkpoints/joint_combiner.json).")
    ap.add_argument("--exclude-video", action="append", default=[],
                    help="Substring of a video stem to exclude (repeatable).")
    args = ap.parse_args(argv)

    jsons = sorted(args.dir.rglob("*.training.json"))
    Xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    n_used = 0
    for jp in jsons:
        try:
            table = build_window_table(jp)
        except Exception as exc:  # noqa: BLE001 — skip a bad video, keep training
            print(f"[skip] {jp.name}: {type(exc).__name__}: {exc}")
            continue
        if table is None:
            continue
        stem = str(table["video"])
        if any(ex in stem for ex in args.exclude_video):
            print(f"[exclude] {stem}")
            continue
        visual = {k: table[k] for k in VISUAL_FEATURE_KEYS}
        Xs.append(combiner_feature_matrix(table["p_audio"], visual, table["valid"]))
        ys.append(np.asarray(table["label"], dtype=np.float64))
        n_used += 1
        print(f"[ok] {stem}: {table['t'].size} windows")

    if not Xs:
        print("No training tables built — is the motion cache populated?")
        return 1

    X = np.vstack(Xs)
    y = np.concatenate(ys)
    combiner = JointCombiner.fit(X, y)
    out = args.out or default_combiner_path()
    combiner.save(out)

    print("=" * 56)
    print(f"  trained on {n_used} videos, {X.shape[0]} windows "
          f"({y.mean() * 100:.1f}% rally)")
    print(f"  saved combiner -> {out}")
    print("  |coef| ranked:")
    for nm, c in sorted(zip(combiner.feature_names, combiner.coef), key=lambda z: -abs(z[1])):
        print(f"    {nm:18s} {c:+.3f}")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
