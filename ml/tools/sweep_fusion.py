"""Efficient threshold sweep for the motion-fusion veto parameters.

Runs the expensive audio inference pass **once** per val video, caches the
resulting ``(probs, center_times)`` arrays in memory, then evaluates every
``FusionConfig`` in the grid against the same probability stream.  This avoids
the O(N_configs × N_videos) audio passes that a naïve grid search with
``evaluate_fused`` would require.

The metric and interval post-processing are identical to ``evaluate_fused``
(same ``interval_detection_metrics``, same ``predictions_to_rallies`` for
merge-gap / min-rally, iou=0.5 by default) so results are directly comparable.

Usage (veto-only grid, sustain off)::

    python -m ml.tools.sweep_fusion \\
        --dir ml/splits/audio_clean_2026_06_17/val \\
        --no-sustain --iou 0.5

    # Custom grid knobs:
    python -m ml.tools.sweep_fusion \\
        --dir ml/splits/audio_clean_2026_06_17/val \\
        --veto-max-detections 1.0 1.5 2.0 2.5 \\
        --hysteresis 2 3 4 \\
        --veto-max-displacement 0.005 0.01 0.02 1.0 \\
        --no-sustain --iou 0.5

Audio model and feature cache locations default to the project paths in
``ml.config``; override with ``--model-path`` / ``--feature-dir``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["main", "run_sweep"]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SweepRow:
    """One row in the sweep table: a config + its aggregate metrics."""
    label: str
    veto_max_det: float
    hysteresis: int
    veto_max_disp: float
    enable_veto: bool
    enable_sustain: bool
    precision: float
    recall: float
    f1: float
    sMAE: float | None
    eMAE: float | None
    fp_active_seconds: float
    n_over_segs: int
    n_gt: int
    n_pred: int
    n_matched: int


# ---------------------------------------------------------------------------
# Core sweep logic
# ---------------------------------------------------------------------------

def run_sweep(
    paths: list[Path],
    dirs: list[Path],
    feature_dir: Path,
    iou_threshold: float,
    model_path: Path | None,
    inference_config: Any,
    grid_veto_max_detections: list[float],
    grid_hysteresis: list[int],
    grid_veto_max_displacement: list[float],
    enable_sustain: bool,
    half_window_s: float = 0.5,
    dilation: float | None = None,
) -> tuple[list[SweepRow], list[dict]]:
    """Run the sweep; return (rows, per_video_raw).

    Args:
        paths: Explicit ``.training.json`` file paths.
        dirs: Directories to scan for ``.training.json`` files.
        feature_dir: Directory containing ``<stem>.npz`` motion feature files.
        iou_threshold: IoU threshold for ``interval_detection_metrics``.
        model_path: Audio model checkpoint (``None`` → project default).
        inference_config: ``InferenceConfig`` instance; controls merge-gap, etc.
        grid_veto_max_detections: Values to sweep for ``veto_max_detections``.
        grid_hysteresis: Values to sweep for ``hysteresis``.
        grid_veto_max_displacement: Values to sweep for ``veto_max_displacement``.
        enable_sustain: Whether the sustain override is active (usually ``False``
            during the veto-only sweep).
        half_window_s: Half-width (s) for resampling motion onto audio windows.
        dilation: Court-polygon dilation for the cheap-path filter (``None`` →
            :data:`ml.motion.court_apply.DEFAULT_DILATION`).  Fixed per sweep run;
            re-run the sweep per dilation value (all offline-cheap now).

    Returns:
        ``(rows, per_video_raw)`` where ``rows`` is the sorted sweep table and
        ``per_video_raw`` contains one dict per video with probs and features
        for post-hoc inspection.
    """
    from ml.evaluation.event_metrics import (  # noqa: PLC0415
        aggregate_video_metrics,
        interval_detection_metrics,
    )
    from ml.motion.court_apply import DEFAULT_DILATION, load_features  # noqa: PLC0415
    from ml.motion.fusion import FusionConfig  # noqa: PLC0415

    if dilation is None:
        dilation = DEFAULT_DILATION
    from ml.motion.predict_fused import audio_window_probs, fuse_to_intervals  # noqa: PLC0415
    from ml.predict import predictions_to_rallies  # noqa: PLC0415
    from ml.tools.evaluate_boundaries import _load_ground_truth_intervals  # noqa: PLC0415

    # ------------------------------------------------------------------
    # Collect JSON paths
    # ------------------------------------------------------------------
    candidate_paths: list[Path] = list(paths)
    for d in dirs:
        if d.exists():
            candidate_paths.extend(sorted(d.rglob("*.training.json")))
        else:
            print(f"[sweep_fusion] WARN: directory not found: {d}", file=sys.stderr)

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in sorted(candidate_paths):
        rp = p.resolve() if p.exists() else p
        if rp not in seen:
            seen.add(rp)
            unique_paths.append(p)

    # ------------------------------------------------------------------
    # Phase 1 — one audio pass per video; load cached motion features.
    # ------------------------------------------------------------------
    print(
        f"[sweep_fusion] Phase 1: audio inference on {len(unique_paths)} video(s)...",
        file=sys.stderr,
    )

    per_video_cache: list[dict] = []
    n_skipped = 0
    n_no_motion = 0

    for json_path in unique_paths:
        if not json_path.exists():
            print(f"[sweep_fusion] WARN: not found: {json_path}", file=sys.stderr)
            n_skipped += 1
            continue

        gt = _load_ground_truth_intervals(json_path)
        if gt is None:
            n_skipped += 1
            continue

        with json_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        video_path = Path(data.get("video", {}).get("path", ""))
        if not video_path.exists():
            print(
                f"[sweep_fusion] WARN: video missing: {video_path}", file=sys.stderr
            )
            n_skipped += 1
            continue

        stem = video_path.stem
        print(f"[sweep_fusion]   audio pass → {stem}", file=sys.stderr)
        probs, center_times = audio_window_probs(
            video_path, model_path=model_path, inference_config=inference_config
        )

        # Baseline (audio-only) intervals for reference row.
        base_rallies = predictions_to_rallies(probs, center_times, inference_config)
        baseline = [(r["start_seconds"], r["end_seconds"]) for r in base_rallies]

        feat_path = feature_dir / f"{stem}.npz"
        features = load_features(feat_path, dilation) if feat_path.exists() else None
        if features is None:
            n_no_motion += 1

        per_video_cache.append(
            {
                "json_path": str(json_path),
                "video_path": str(video_path),
                "gt": gt,
                "probs": probs,
                "center_times": center_times,
                "baseline": baseline,
                "features": features,
            }
        )

    print(
        f"[sweep_fusion] Phase 1 done — {len(per_video_cache)} evaluated, "
        f"{n_skipped} skipped, {n_no_motion} without motion.",
        file=sys.stderr,
    )

    if not per_video_cache:
        return [], []

    # ------------------------------------------------------------------
    # Phase 2 — score baseline + each config in the grid.
    # ------------------------------------------------------------------

    # Baseline row.
    base_per_vid = [
        interval_detection_metrics(v["baseline"], v["gt"], iou_threshold)
        for v in per_video_cache
    ]
    agg_base = aggregate_video_metrics(base_per_vid)
    rows: list[SweepRow] = [
        SweepRow(
            label="BASELINE (audio-only)",
            veto_max_det=float("nan"),
            hysteresis=0,
            veto_max_disp=float("nan"),
            enable_veto=False,
            enable_sustain=False,
            precision=agg_base["precision"],
            recall=agg_base["recall"],
            f1=agg_base["f1"],
            sMAE=agg_base["start_mae_s"],
            eMAE=agg_base["end_mae_s"],
            fp_active_seconds=agg_base["fp_active_seconds"],
            n_over_segs=agg_base["n_over_segs"],
            n_gt=agg_base["n_ground_truth"],
            n_pred=agg_base["n_predicted"],
            n_matched=agg_base["n_matched"],
        )
    ]

    configs = list(
        itertools.product(
            grid_veto_max_detections,
            grid_hysteresis,
            grid_veto_max_displacement,
        )
    )
    print(
        f"[sweep_fusion] Phase 2: evaluating {len(configs)} config(s)...",
        file=sys.stderr,
    )

    for veto_det, hyst, veto_disp in configs:
        fus_cfg = FusionConfig(
            veto_max_detections=veto_det,
            # The gate is OFF by default in FusionConfig; the sweep explicitly
            # enables it so the displacement grid is actually exercised (a grid
            # value of 1.0 ~= gate disabled, since observed displacement < 1.0).
            enable_displacement_gate=True,
            veto_max_displacement=veto_disp,
            hysteresis=hyst,
            enable_veto=True,
            enable_sustain=enable_sustain,
        )

        vid_metrics = []
        for v in per_video_cache:
            fused = fuse_to_intervals(
                v["probs"],
                v["center_times"],
                v["features"],
                inference_config,
                fus_cfg,
                half_window_s,
            )
            vid_metrics.append(
                interval_detection_metrics(fused, v["gt"], iou_threshold)
            )

        agg = aggregate_video_metrics(vid_metrics)
        label = (
            f"veto_det={veto_det:.1f} hyst={hyst} veto_disp={veto_disp}"
        )
        rows.append(
            SweepRow(
                label=label,
                veto_max_det=veto_det,
                hysteresis=hyst,
                veto_max_disp=veto_disp,
                enable_veto=True,
                enable_sustain=enable_sustain,
                precision=agg["precision"],
                recall=agg["recall"],
                f1=agg["f1"],
                sMAE=agg["start_mae_s"],
                eMAE=agg["end_mae_s"],
                fp_active_seconds=agg["fp_active_seconds"],
                n_over_segs=agg["n_over_segs"],
                n_gt=agg["n_ground_truth"],
                n_pred=agg["n_predicted"],
                n_matched=agg["n_matched"],
            )
        )

    # Sort by F1 descending (baseline row first, then configs).
    baseline_row = rows[0]
    config_rows = sorted(rows[1:], key=lambda r: r.f1, reverse=True)
    return [baseline_row] + config_rows, per_video_cache


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _mae_str(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else " N/A"


def render_table(rows: list[SweepRow]) -> str:
    """Render the sweep table as a markdown-compatible string."""
    lines: list[str] = []
    lines.append("")
    lines.append("| Config | P | R | F1 | sMAE | eMAE | fpSec | over_segs | GT | Pred | Match |")
    lines.append("|--------|---|---|----|------|------|-------|-----------|----|------|-------|")
    for r in rows:
        lines.append(
            f"| {r.label} "
            f"| {r.precision:.1%} "
            f"| {r.recall:.1%} "
            f"| {r.f1:.1%} "
            f"| {_mae_str(r.sMAE)} "
            f"| {_mae_str(r.eMAE)} "
            f"| {r.fp_active_seconds:.0f} "
            f"| {r.n_over_segs} "
            f"| {r.n_gt} "
            f"| {r.n_pred} "
            f"| {r.n_matched} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_recommendation(rows: list[SweepRow]) -> str:
    """Identify top configs: best precision gain with recall drop ≤ 2 pp."""
    baseline = rows[0]
    base_recall = baseline.recall
    base_precision = baseline.precision

    candidates = [
        r for r in rows[1:]
        if (r.recall >= base_recall - 0.02)
        and (r.precision > base_precision)
    ]
    candidates.sort(key=lambda r: (r.precision, r.f1), reverse=True)

    lines: list[str] = []
    lines.append("")
    lines.append("## Recommendation")
    if not candidates:
        lines.append(
            "_No config beats the baseline on precision within the 2-pp recall constraint._"
        )
        return "\n".join(lines)

    for i, r in enumerate(candidates[:3]):
        dp = r.precision - base_precision
        dr = r.recall - base_recall
        df = r.f1 - baseline.f1
        lines.append(
            f"{i+1}. **{r.label}**  "
            f"P={r.precision:.1%} ({dp:+.1%}), "
            f"R={r.recall:.1%} ({dr:+.1%}), "
            f"F1={r.f1:.1%} ({df:+.1%}), "
            f"fpSec={r.fp_active_seconds:.0f} "
            f"(baseline fpSec={baseline.fp_active_seconds:.0f})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep_fusion",
        description=(
            "Efficient threshold sweep for motion-fusion veto. "
            "Runs the audio pass once per video, then scores every "
            "FusionConfig in the grid."
        ),
    )
    p.add_argument("paths", metavar="PATH", nargs="*", type=Path)
    p.add_argument(
        "--dir", dest="dirs", metavar="DIR", action="append", type=Path, default=[]
    )
    p.add_argument("--feature-dir", type=Path, default=None)
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--model-path", type=Path, default=None)
    p.add_argument("--half-window", type=float, default=0.5)
    p.add_argument("--dilation", type=float, default=None,
                   help="Court-polygon dilation for the cheap-path filter "
                        "(default: ml.motion.court_apply.DEFAULT_DILATION = 0.12). "
                        "Re-run the sweep per value to tune it (offline-cheap).")
    # Audio post-processing overrides.
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--merge-gap", type=float, default=None)
    p.add_argument("--min-rally", type=float, default=None)
    p.add_argument("--smooth-kernel", type=int, default=None)
    # Grid knobs.
    p.add_argument(
        "--veto-max-detections",
        type=float, nargs="+",
        default=[1.0, 1.5, 2.0, 2.5],
        metavar="V",
    )
    p.add_argument(
        "--hysteresis",
        type=int, nargs="+",
        default=[2, 3, 4],
        metavar="H",
    )
    p.add_argument(
        "--veto-max-displacement",
        type=float, nargs="+",
        default=[0.005, 0.01, 0.02, 1.0],
        metavar="D",
    )
    p.add_argument("--no-sustain", dest="no_sustain", action="store_true")
    p.add_argument("--out", type=Path, default=None,
                   help="Write markdown results to this path (in addition to stdout).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    from ml.config import InferenceConfig, PathConfig  # noqa: PLC0415

    inf_cfg = InferenceConfig()
    if args.threshold is not None:
        inf_cfg.threshold = args.threshold
    if args.merge_gap is not None:
        inf_cfg.merge_gap_seconds = args.merge_gap
    if args.min_rally is not None:
        inf_cfg.min_rally_seconds = args.min_rally
    if args.smooth_kernel is not None:
        inf_cfg.smooth_kernel = args.smooth_kernel

    feature_dir = args.feature_dir
    if feature_dir is None:
        feature_dir = PathConfig().cache_dir / "motion"
    feature_dir = feature_dir.expanduser().resolve()

    model_path = args.model_path.expanduser().resolve() if args.model_path else None

    explicit = [p.expanduser().resolve() for p in (args.paths or [])]
    dirs = [d.expanduser().resolve() for d in (args.dirs or [])]
    if not explicit and not dirs:
        dirs = [(Path.home() / "Videos" / "pickleball").resolve()]
        print(
            f"[sweep_fusion] No inputs; defaulting to {dirs[0]}", file=sys.stderr
        )

    rows, _ = run_sweep(
        paths=explicit,
        dirs=dirs,
        feature_dir=feature_dir,
        iou_threshold=args.iou,
        model_path=model_path,
        inference_config=inf_cfg,
        grid_veto_max_detections=args.veto_max_detections,
        grid_hysteresis=args.hysteresis,
        grid_veto_max_displacement=args.veto_max_displacement,
        enable_sustain=not args.no_sustain,
        half_window_s=args.half_window,
        dilation=args.dilation,
    )

    if not rows:
        print("[sweep_fusion] No evaluable files found.", file=sys.stderr)
        return 1

    table_str = render_table(rows)
    rec_str = render_recommendation(rows)

    print(table_str)
    print(rec_str)

    if args.out:
        out_path = args.out.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            fh.write("# Motion Fusion Threshold Sweep — VAL split\n\n")
            fh.write(table_str)
            fh.write(rec_str)
            fh.write("\n")
        print(f"\n[sweep_fusion] Results written to {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
