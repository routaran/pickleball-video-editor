"""Audio-only post-processing parameter sweep on the VAL split.

Caches raw (un-smoothed) per-window probabilities **once** per video, then
evaluates every post-processing configuration in a grid with zero repeated
model inference.  This makes the sweep fast enough to run on CPU in a single
session.

The expensive part (audio model inference) is run *once* per video in Phase 1
with ``smooth_kernel=1`` so that raw logits are returned.  Phase 2 sweeps
``smooth_kernel`` (applied in Python) together with ``threshold``,
``merge_gap_seconds``, and ``min_rally_seconds`` across all combinations.

Metrics reported per config (aggregate over VAL split):

* ``precision``, ``recall``, ``F1``        — interval-level (IoU ≥ 0.5)
* ``n_over_segs``                          — GT intervals split by > 1 prediction
* ``sMAE``, ``eMAE``                       — boundary errors (guardrail, not target)
* ``fp_active_seconds``                    — dead-time covered by FP predictions
* ``footage_recall``                       — fraction of rally seconds kept (primary)
* ``junk_fraction``                        — fraction of predicted cut that is dead time
* ``n_fully_missed_rallies``               — irreversible losses (guard hard)

Usage (val only — never point at test)::

    cd /home/rkalluri/Documents/source/pickleball_editing
    .venv/bin/python -m ml.tools.sweep_audio_postproc \\
        --dir ml/splits/audio_clean_2026_06_17/val \\
        --out ml/cache/audio_postproc_sweep_val_2026-06-21.md

    # Custom knob ranges:
    .venv/bin/python -m ml.tools.sweep_audio_postproc \\
        --dir ml/splits/audio_clean_2026_06_17/val \\
        --threshold 0.5 0.55 0.6 0.65 \\
        --merge-gap 0.5 1.0 1.5 2.0 \\
        --min-rally 1.0 1.5 2.0 2.5 \\
        --smooth-kernel 3 5 7 9 \\
        --out ml/cache/audio_postproc_sweep_val_2026-06-21.md
"""

from __future__ import annotations

import argparse
import dataclasses
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
class PostprocRow:
    """One row in the sweep table: config + aggregate metrics."""
    label: str
    threshold: float
    merge_gap: float
    min_rally: float
    smooth_kernel: int
    # interval-level
    precision: float
    recall: float
    f1: float
    n_over_segs: int
    sMAE: float | None
    eMAE: float | None
    fp_active_seconds: float
    n_gt: int
    n_pred: int
    n_matched: int
    # footage-level
    footage_recall: float
    junk_fraction: float
    n_fully_missed: int


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sweep(
    paths: list[Path],
    dirs: list[Path],
    iou_threshold: float,
    model_path: Path | None,
    grid_threshold: list[float],
    grid_merge_gap: list[float],
    grid_min_rally: list[float],
    grid_smooth_kernel: list[int],
) -> list[PostprocRow]:
    """Cache raw probs once per video; evaluate each post-proc config in a loop.

    Args:
        paths: Explicit ``.training.json`` file paths.
        dirs: Directories to scan for ``.training.json`` files.
        iou_threshold: IoU threshold for ``interval_detection_metrics``.
        model_path: Audio model checkpoint (``None`` → project default).
        grid_threshold: Values of ``InferenceConfig.threshold`` to sweep.
        grid_merge_gap: Values of ``InferenceConfig.merge_gap_seconds`` to sweep.
        grid_min_rally: Values of ``InferenceConfig.min_rally_seconds`` to sweep.
        grid_smooth_kernel: Values of ``smooth_kernel`` to sweep.

    Returns:
        Sweep rows sorted F1 descending (baseline row first).
    """
    from ml.config import InferenceConfig, PathConfig  # noqa: PLC0415
    from ml.evaluation.event_metrics import (  # noqa: PLC0415
        aggregate_video_metrics,
        footage_confusion,
        interval_detection_metrics,
    )
    from ml.motion.predict_fused import audio_window_probs  # noqa: PLC0415
    from ml.predict import predictions_to_rallies, smooth_predictions  # noqa: PLC0415
    from ml.tools.evaluate_boundaries import _load_ground_truth_intervals  # noqa: PLC0415

    # ------------------------------------------------------------------
    # Collect JSON paths
    # ------------------------------------------------------------------
    candidate_paths: list[Path] = list(paths)
    for d in dirs:
        if d.exists():
            candidate_paths.extend(sorted(d.rglob("*.training.json")))
        else:
            print(f"[sweep_audio_postproc] WARN: directory not found: {d}", file=sys.stderr)

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in sorted(candidate_paths):
        rp = p.resolve() if p.exists() else p
        if rp not in seen:
            seen.add(rp)
            unique_paths.append(p)

    # ------------------------------------------------------------------
    # Phase 1 — one audio pass per video (smooth_kernel=1 → raw probs).
    # WAV files are cached by extract_audio so this is fast when already extracted.
    # ------------------------------------------------------------------
    print(
        f"[sweep_audio_postproc] Phase 1: audio inference on {len(unique_paths)} video(s)...",
        file=sys.stderr,
    )

    # InferenceConfig with smooth_kernel=1 disables smoothing in audio_window_probs.
    raw_inf_cfg = InferenceConfig(smooth_kernel=1)

    per_video_cache: list[dict] = []
    n_skipped = 0

    for json_path in unique_paths:
        if not json_path.exists():
            print(f"[sweep_audio_postproc] WARN: not found: {json_path}", file=sys.stderr)
            n_skipped += 1
            continue

        gt = _load_ground_truth_intervals(json_path)
        if gt is None:
            n_skipped += 1
            continue

        with json_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        video_path = Path(data.get("video", {}).get("path", ""))
        if not video_path.exists():
            print(
                f"[sweep_audio_postproc] WARN: video missing: {video_path}",
                file=sys.stderr,
            )
            n_skipped += 1
            continue

        stem = video_path.stem
        print(f"[sweep_audio_postproc]   audio pass → {stem}", file=sys.stderr)
        # smooth_kernel=1 → smooth_predictions is a no-op → raw probs returned
        raw_probs, center_times = audio_window_probs(
            video_path, model_path=model_path, inference_config=raw_inf_cfg
        )

        per_video_cache.append(
            {
                "stem": stem,
                "json_path": str(json_path),
                "video_path": str(video_path),
                "gt": gt,
                "raw_probs": raw_probs,
                "center_times": center_times,
            }
        )

    print(
        f"[sweep_audio_postproc] Phase 1 done — {len(per_video_cache)} evaluated, "
        f"{n_skipped} skipped.",
        file=sys.stderr,
    )

    if not per_video_cache:
        return []

    # ------------------------------------------------------------------
    # Phase 2 — score baseline + every config in the grid.
    # ------------------------------------------------------------------

    def _eval_config(
        threshold: float,
        merge_gap: float,
        min_rally: float,
        smooth_kernel: int,
    ) -> tuple[dict, dict[str, float]]:
        """Return (aggregate_interval_metrics, aggregate_footage_metrics)."""
        cfg = InferenceConfig(
            threshold=threshold,
            merge_gap_seconds=merge_gap,
            min_rally_seconds=min_rally,
            smooth_kernel=smooth_kernel,  # unused in predictions_to_rallies but kept for reference
        )
        per_vid_interval: list[dict] = []
        footage_agg: dict[str, float] = {
            "footage_recall_sum": 0.0,
            "junk_fraction_sum": 0.0,
            "n_fully_missed_sum": 0,
            "n_vids": 0,
        }

        for v in per_video_cache:
            smoothed = smooth_predictions(v["raw_probs"], smooth_kernel)
            rallies = predictions_to_rallies(smoothed, v["center_times"], cfg)
            pred_intervals = [(r["start_seconds"], r["end_seconds"]) for r in rallies]

            per_vid_interval.append(
                interval_detection_metrics(pred_intervals, v["gt"], iou_threshold)
            )

            fc = footage_confusion(pred_intervals, v["gt"])
            footage_agg["footage_recall_sum"] += fc["footage_recall"]
            footage_agg["junk_fraction_sum"] += fc["junk_fraction"]
            footage_agg["n_fully_missed_sum"] += fc["n_fully_missed_rallies"]
            footage_agg["n_vids"] += 1

        agg_int = aggregate_video_metrics(per_vid_interval)

        n_vids = footage_agg["n_vids"]
        agg_footage = {
            "footage_recall": footage_agg["footage_recall_sum"] / n_vids if n_vids else 0.0,
            "junk_fraction": footage_agg["junk_fraction_sum"] / n_vids if n_vids else 0.0,
            "n_fully_missed": footage_agg["n_fully_missed_sum"],
        }
        return agg_int, agg_footage

    def _make_row(
        label: str,
        threshold: float,
        merge_gap: float,
        min_rally: float,
        smooth_kernel: int,
        agg_int: dict,
        agg_footage: dict,
    ) -> PostprocRow:
        return PostprocRow(
            label=label,
            threshold=threshold,
            merge_gap=merge_gap,
            min_rally=min_rally,
            smooth_kernel=smooth_kernel,
            precision=agg_int["precision"],
            recall=agg_int["recall"],
            f1=agg_int["f1"],
            n_over_segs=agg_int["n_over_segs"],
            sMAE=agg_int["start_mae_s"],
            eMAE=agg_int["end_mae_s"],
            fp_active_seconds=agg_int["fp_active_seconds"],
            n_gt=agg_int["n_ground_truth"],
            n_pred=agg_int["n_predicted"],
            n_matched=agg_int["n_matched"],
            footage_recall=agg_footage["footage_recall"],
            junk_fraction=agg_footage["junk_fraction"],
            n_fully_missed=agg_footage["n_fully_missed"],
        )

    # Default InferenceConfig values for the baseline row.
    _default = InferenceConfig()
    DEFAULT_THRESHOLD = _default.threshold
    DEFAULT_MERGE_GAP = _default.merge_gap_seconds
    DEFAULT_MIN_RALLY = _default.min_rally_seconds
    DEFAULT_KERNEL = _default.smooth_kernel

    print("[sweep_audio_postproc] Phase 2: scoring baseline...", file=sys.stderr)
    base_int, base_footage = _eval_config(
        DEFAULT_THRESHOLD, DEFAULT_MERGE_GAP, DEFAULT_MIN_RALLY, DEFAULT_KERNEL
    )
    rows: list[PostprocRow] = [
        _make_row(
            "BASELINE (defaults)",
            DEFAULT_THRESHOLD,
            DEFAULT_MERGE_GAP,
            DEFAULT_MIN_RALLY,
            DEFAULT_KERNEL,
            base_int,
            base_footage,
        )
    ]

    configs = list(
        itertools.product(grid_threshold, grid_merge_gap, grid_min_rally, grid_smooth_kernel)
    )
    print(
        f"[sweep_audio_postproc] Phase 2: evaluating {len(configs)} config(s)...",
        file=sys.stderr,
    )

    for thr, mg, mr, sk in configs:
        # Skip the config that exactly matches the baseline (already computed).
        if (thr == DEFAULT_THRESHOLD and mg == DEFAULT_MERGE_GAP
                and mr == DEFAULT_MIN_RALLY and sk == DEFAULT_KERNEL):
            continue

        agg_int, agg_footage = _eval_config(thr, mg, mr, sk)
        label = f"thr={thr:.2f} mg={mg:.1f} mr={mr:.1f} sk={sk}"
        rows.append(_make_row(label, thr, mg, mr, sk, agg_int, agg_footage))

    # Sort: baseline first, then by F1 descending.
    baseline_row = rows[0]
    config_rows = sorted(rows[1:], key=lambda r: r.f1, reverse=True)
    print(
        f"[sweep_audio_postproc] Phase 2 done — {len(rows)} rows.",
        file=sys.stderr,
    )
    return [baseline_row] + config_rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _mae_str(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else " N/A"


def render_table(rows: list[PostprocRow]) -> str:
    """Render sweep results as a markdown table."""
    lines: list[str] = []
    lines.append(
        "| Config | P | R | F1 | over_segs | sMAE | eMAE | fpSec | "
        "fRecall | junkFrac | missed | GT | Pred | Match |"
    )
    lines.append(
        "|--------|---|---|----|-----------|------|------|-------|"
        "---------|----------|--------|----|----|-------|"
    )
    for r in rows:
        lines.append(
            f"| {r.label} "
            f"| {r.precision:.1%} "
            f"| {r.recall:.1%} "
            f"| {r.f1:.1%} "
            f"| {r.n_over_segs} "
            f"| {_mae_str(r.sMAE)} "
            f"| {_mae_str(r.eMAE)} "
            f"| {r.fp_active_seconds:.0f} "
            f"| {r.footage_recall:.1%} "
            f"| {r.junk_fraction:.1%} "
            f"| {r.n_fully_missed} "
            f"| {r.n_gt} "
            f"| {r.n_pred} "
            f"| {r.n_matched} |"
        )
    return "\n".join(lines)


def render_top_configs(rows: list[PostprocRow], n: int = 20) -> str:
    """Return a markdown block showing the top-n configs."""
    lines: list[str] = [f"\n## Top {n} configs by F1\n"]
    lines.append(render_table(rows[:1] + rows[1:n + 1]))
    return "\n".join(lines)


def render_recommendation(rows: list[PostprocRow]) -> str:
    """Pick the best config that cuts over-segmentation while guarding recall."""
    baseline = rows[0]
    base_recall = baseline.recall
    base_footage_recall = baseline.footage_recall
    base_missed = baseline.n_fully_missed

    # Hard constraints:
    #   1. footage_recall ≥ baseline footage_recall − 0.02 (≤ 2 pp drop)
    #   2. n_fully_missed_rallies ≤ baseline (never increase irreversible failures)
    # Soft objective: max precision, then F1.
    candidates = [
        r for r in rows[1:]
        if (r.footage_recall >= base_footage_recall - 0.02)
        and (r.n_fully_missed <= base_missed)
        and (r.precision > baseline.precision)
    ]
    candidates.sort(key=lambda r: (r.precision, r.f1), reverse=True)

    lines: list[str] = ["", "## Recommendation", ""]

    if not candidates:
        lines.append(
            "_No config beats the baseline on precision while keeping footage_recall "
            "flat and n_fully_missed_rallies ≤ baseline._"
        )
        return "\n".join(lines)

    best = candidates[0]
    dp = best.precision - baseline.precision
    dr = best.recall - baseline.recall
    df = best.f1 - baseline.f1
    dfr = best.footage_recall - baseline.footage_recall
    djf = best.junk_fraction - baseline.junk_fraction

    lines.append(f"**Best config:** `{best.label}`\n")
    lines.append(f"| Metric | Baseline | Best | Delta |")
    lines.append(f"|--------|----------|------|-------|")
    lines.append(f"| Precision | {baseline.precision:.1%} | {best.precision:.1%} | {dp:+.1%} |")
    lines.append(f"| Recall | {baseline.recall:.1%} | {best.recall:.1%} | {dr:+.1%} |")
    lines.append(f"| F1 | {baseline.f1:.1%} | {best.f1:.1%} | {df:+.1%} |")
    lines.append(f"| over_segs | {baseline.n_over_segs} | {best.n_over_segs} | {best.n_over_segs - baseline.n_over_segs:+d} |")
    lines.append(f"| footage_recall | {baseline.footage_recall:.1%} | {best.footage_recall:.1%} | {dfr:+.1%} |")
    lines.append(f"| junk_fraction | {baseline.junk_fraction:.1%} | {best.junk_fraction:.1%} | {djf:+.1%} |")
    lines.append(f"| n_fully_missed | {baseline.n_fully_missed} | {best.n_fully_missed} | {best.n_fully_missed - baseline.n_fully_missed:+d} |")
    lines.append("")
    lines.append("### Recommended `InferenceConfig` override")
    lines.append("```python")
    lines.append("InferenceConfig(")
    lines.append(f"    threshold={best.threshold},")
    lines.append(f"    merge_gap_seconds={best.merge_gap},")
    lines.append(f"    min_rally_seconds={best.min_rally},")
    lines.append(f"    smooth_kernel={best.smooth_kernel},")
    lines.append(")")
    lines.append("```")

    if len(candidates) > 1:
        lines.append("\n### Runner-up configs (same guard constraints)\n")
        for r in candidates[1:4]:
            lines.append(
                f"- `{r.label}`: P={r.precision:.1%}, R={r.recall:.1%}, F1={r.f1:.1%}, "
                f"fRecall={r.footage_recall:.1%}, missed={r.n_fully_missed}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sweep_audio_postproc",
        description=(
            "Sweep audio-only post-processing knobs on the VAL split. "
            "Caches raw model probs once per video, then evaluates all "
            "post-proc combinations (threshold × merge_gap × min_rally × "
            "smooth_kernel) without re-running the audio model."
        ),
    )
    p.add_argument("paths", metavar="PATH", nargs="*", type=Path,
                   help=".training.json file(s) to evaluate")
    p.add_argument("--dir", dest="dirs", metavar="DIR", action="append",
                   type=Path, default=[],
                   help="Directory to scan for .training.json files")
    p.add_argument("--iou", type=float, default=0.5,
                   help="IoU threshold for interval matching (default: 0.5)")
    p.add_argument("--model-path", type=Path, default=None,
                   help="Audio model checkpoint (default: ml/checkpoints/best_model.pt)")
    p.add_argument(
        "--threshold", type=float, nargs="+",
        default=[0.40, 0.45, 0.50, 0.55, 0.60],
        metavar="T",
        help="Grid of threshold values (default: 0.40 0.45 0.50 0.55 0.60)",
    )
    p.add_argument(
        "--merge-gap", type=float, nargs="+",
        default=[0.0, 0.3, 0.5, 1.0, 1.5],
        metavar="MG",
        help="Grid of merge_gap_seconds values (default: 0.0 0.3 0.5 1.0 1.5)",
    )
    p.add_argument(
        "--min-rally", type=float, nargs="+",
        default=[0.5, 1.0, 1.5, 2.0],
        metavar="MR",
        help="Grid of min_rally_seconds values (default: 0.5 1.0 1.5 2.0)",
    )
    p.add_argument(
        "--smooth-kernel", type=int, nargs="+",
        default=[3, 5, 7, 9],
        metavar="SK",
        help="Grid of smooth_kernel values (default: 3 5 7 9)",
    )
    p.add_argument("--top", type=int, default=30,
                   help="Number of top configs to include in the report (default: 30)")
    p.add_argument("--out", type=Path, default=None,
                   help="Write markdown report to this path (also printed to stdout)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    model_path = args.model_path.expanduser().resolve() if args.model_path else None

    explicit = [p.expanduser().resolve() for p in (args.paths or [])]
    dirs = [d.expanduser().resolve() for d in (args.dirs or [])]
    if not explicit and not dirs:
        # Default to val split for safety (never touch test).
        default_dir = (
            Path(__file__).parent.parent / "splits" / "audio_clean_2026_06_17" / "val"
        )
        dirs = [default_dir.resolve()]
        print(
            f"[sweep_audio_postproc] No inputs; defaulting to {dirs[0]}",
            file=sys.stderr,
        )

    rows = run_sweep(
        paths=explicit,
        dirs=dirs,
        iou_threshold=args.iou,
        model_path=model_path,
        grid_threshold=args.threshold,
        grid_merge_gap=args.merge_gap,
        grid_min_rally=args.min_rally,
        grid_smooth_kernel=args.smooth_kernel,
    )

    if not rows:
        print("[sweep_audio_postproc] No evaluable files found.", file=sys.stderr)
        return 1

    baseline = rows[0]
    top_n = min(args.top, len(rows) - 1)

    header = (
        "# Audio Post-Processing Sweep — VAL split (audio_clean_2026_06_17/val)\n\n"
        f"**Val videos:** {baseline.n_gt} GT rallies across all videos  \n"
        f"**Grid:** threshold × merge_gap × min_rally × smooth_kernel = "
        f"{len(args.threshold)} × {len(args.merge_gap)} × {len(args.min_rally)} × "
        f"{len(args.smooth_kernel)} = "
        f"{len(args.threshold) * len(args.merge_gap) * len(args.min_rally) * len(args.smooth_kernel)} configs  \n"
        f"**IoU threshold:** {args.iou}\n\n"
    )

    top_table_str = render_top_configs(rows, n=top_n)
    rec_str = render_recommendation(rows)

    # Baseline summary
    base_summary = (
        "\n## Baseline (InferenceConfig defaults)\n\n"
        f"threshold={baseline.threshold}, merge_gap={baseline.merge_gap}, "
        f"min_rally={baseline.min_rally}, smooth_kernel={baseline.smooth_kernel}  \n"
        f"P={baseline.precision:.1%}  R={baseline.recall:.1%}  F1={baseline.f1:.1%}  "
        f"over_segs={baseline.n_over_segs}  "
        f"fRecall={baseline.footage_recall:.1%}  "
        f"junkFrac={baseline.junk_fraction:.1%}  "
        f"missed={baseline.n_fully_missed}  "
        f"GT={baseline.n_gt}  Pred={baseline.n_pred}\n"
    )

    full_report = header + base_summary + top_table_str + rec_str + "\n"

    print(full_report)

    if args.out:
        out_path = args.out.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(full_report, encoding="utf-8")
        print(f"\n[sweep_audio_postproc] Report written to {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
