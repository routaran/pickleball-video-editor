"""Stage-1 audio rally detection evaluation CLI.

This tool is intended to be run on **held-out** videos after Stage-1 model
training to select checkpoints and confidence thresholds.  It loads
ground-truth rally intervals from ``.training.json`` label files, runs the
trained model to obtain predicted intervals via ``ml.predict.predict_video``,
and computes per-video and aggregate detection metrics using
:mod:`ml.evaluation.event_metrics`.

Torch and the audio model are imported lazily so that ``--help`` and dry-run
invocations work without a GPU or a torch installation.

Usage examples::

    # Evaluate on all training files in a directory:
    python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball

    # Evaluate on explicit files:
    python -m ml.tools.evaluate_boundaries game1.training.json game2.training.json

    # JSON output, custom IoU threshold:
    python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball --iou 0.3 --json

    # Override model path and post-processing parameters:
    python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball/val_tune/ \\
        --model-path ml/checkpoints/baseline_model.pt \\
        --threshold 0.6 --merge-gap 0.75 --smooth-kernel 7

CLI flags
---------
paths                   One or more .training.json files to evaluate.  At
                        least one of ``paths`` or ``--dir`` must be supplied.
--dir DIR               Directory to glob for *.training.json files.  May be
                        supplied multiple times.
--iou FLOAT             IoU threshold for interval matching (default: 0.5).
--json                  Emit machine-readable JSON to stdout instead of a
                        human-readable table.
--model-path PATH       Path to model checkpoint (default: ml/checkpoints/best_model.pt).
--threshold FLOAT       Detection probability threshold 0–1 (default: InferenceConfig default).
--merge-gap FLOAT       Merge rallies closer than this many seconds (default: InferenceConfig default).
--min-rally FLOAT       Discard rallies shorter than this many seconds (default: InferenceConfig default).
--smooth-kernel INT     Median filter kernel size, must be a positive odd integer
                        (default: InferenceConfig default).
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any


__all__ = ["main", "run_boundary_evaluation"]


# ---------------------------------------------------------------------------
# Ground-truth loading
# ---------------------------------------------------------------------------


def _load_ground_truth_intervals(
    json_path: Path,
) -> list[tuple[float, float]] | None:
    """Load ground-truth rally intervals from a ``.training.json`` file.

    Skips the file entirely when ``generated_by == "auto_edit"`` (returns
    ``None``).  Post-game rallies and rallies missing timestamps are silently
    excluded from the returned list.

    Args:
        json_path: Path to a ``.training.json`` file.

    Returns:
        List of ``(start_s, end_s)`` tuples for eligible rallies, or ``None``
        when the file should be skipped (auto_edit generated).  Returns an
        empty list when the file is valid but contains no eligible rallies.
    """
    with json_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    if data.get("generated_by") == "auto_edit":
        return None

    intervals: list[tuple[float, float]] = []
    for rally in data.get("rallies") or []:
        if rally.get("is_post_game", False):
            continue
        raw = rally.get("raw") or {}
        start = raw.get("start_seconds")
        end = raw.get("end_seconds")
        if start is None or end is None:
            continue
        intervals.append((float(start), float(end)))

    return intervals


# ---------------------------------------------------------------------------
# Predicted-interval extraction
# ---------------------------------------------------------------------------


def _predict_intervals(
    video_path: Path,
    model_path: Path | None = None,
    inference_config: object | None = None,
) -> list[tuple[float, float]]:
    """Run the Stage-1 model and return predicted rally intervals.

    Imports ``ml.predict`` lazily so this module can be imported (and
    ``--help`` can run) without torch being available.

    Args:
        video_path: Absolute path to the source video file.
        model_path: Optional path to a model checkpoint; uses the default
            checkpoint when ``None``.
        inference_config: Optional :class:`~ml.config.InferenceConfig`
            instance; uses the default config when ``None``.

    Returns:
        List of ``(start_s, end_s)`` tuples from the model predictions.
    """
    from ml.predict import predict_video  # noqa: PLC0415 — lazy import intentional

    raw: list[dict[str, float]] = predict_video(
        video_path,
        model_path=model_path,
        inference_config=inference_config,
    )
    return [
        (float(r["start_seconds"]), float(r["end_seconds"]))
        for r in raw
    ]


# ---------------------------------------------------------------------------
# Per-file evaluation
# ---------------------------------------------------------------------------


def _evaluate_file(
    json_path: Path,
    iou_threshold: float,
    model_path: Path | None = None,
    inference_config: object | None = None,
) -> dict[str, Any] | None:
    """Evaluate one ``.training.json`` file.

    Args:
        json_path: Path to the label file.
        iou_threshold: IoU threshold for matching.
        model_path: Optional model checkpoint path forwarded to
            :func:`_predict_intervals`.
        inference_config: Optional :class:`~ml.config.InferenceConfig`
            forwarded to :func:`_predict_intervals`.

    Returns:
        Per-video result dict or ``None`` when the file should be skipped.
    """
    # Import is at function scope so top-level import is torch-free.
    from ml.evaluation.event_metrics import interval_detection_metrics  # noqa: PLC0415

    gt_intervals = _load_ground_truth_intervals(json_path)
    if gt_intervals is None:
        # File generated by auto_edit — skip.
        print(
            f"[evaluate_boundaries] SKIP (auto_edit): {json_path}",
            file=sys.stderr,
        )
        return None

    # Resolve the video path from the JSON.
    with json_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    video_path = Path(data.get("video", {}).get("path", ""))
    if not video_path.exists():
        print(
            f"[evaluate_boundaries] WARN: video file not found, skipping: {video_path}",
            file=sys.stderr,
        )
        return None

    pred_intervals = _predict_intervals(
        video_path,
        model_path=model_path,
        inference_config=inference_config,
    )
    metrics = interval_detection_metrics(pred_intervals, gt_intervals, iou_threshold)

    return {
        "json_path": str(json_path),
        "video_path": str(video_path),
        **metrics,
    }


# ---------------------------------------------------------------------------
# Public entry point (importable)
# ---------------------------------------------------------------------------


def run_boundary_evaluation(
    paths: list[Path],
    dirs: list[Path],
    iou_threshold: float = 0.5,
    model_path: Path | None = None,
    inference_config: object | None = None,
) -> dict[str, Any]:
    """Run boundary evaluation and return a structured result.

    Args:
        paths: Explicit ``.training.json`` file paths.
        dirs: Directories to glob for ``*.training.json`` files.
        iou_threshold: IoU threshold for interval matching.
        model_path: Optional path to a model checkpoint; uses the default
            checkpoint when ``None``.
        inference_config: Optional :class:`~ml.config.InferenceConfig`
            overriding post-processing parameters; uses defaults when ``None``.

    Returns:
        Dictionary with keys:

        - ``"iou_threshold"``   — the IoU threshold used.
        - ``"per_video"``       — list of per-video result dicts.
        - ``"aggregate"``       — aggregated metrics dict from
          :func:`~ml.evaluation.event_metrics.aggregate_video_metrics`.
        - ``"n_skipped"``       — number of files skipped (auto_edit or
          missing video).
    """
    from ml.evaluation.event_metrics import aggregate_video_metrics  # noqa: PLC0415

    # Collect all candidate JSON paths (deduplicated, sorted).
    candidate_paths: list[Path] = list(paths)
    for d in dirs:
        if d.exists():
            candidate_paths.extend(sorted(d.rglob("*.training.json")))
        else:
            print(
                f"[evaluate_boundaries] WARN: directory not found: {d}",
                file=sys.stderr,
            )

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in sorted(candidate_paths):
        rp = p.resolve() if p.exists() else p
        if rp not in seen:
            seen.add(rp)
            unique_paths.append(p)

    per_video: list[dict[str, Any]] = []
    n_skipped = 0

    for json_path in unique_paths:
        if not json_path.exists():
            print(
                f"[evaluate_boundaries] WARN: file not found: {json_path}",
                file=sys.stderr,
            )
            n_skipped += 1
            continue

        result = _evaluate_file(
            json_path,
            iou_threshold,
            model_path=model_path,
            inference_config=inference_config,
        )
        if result is None:
            n_skipped += 1
        else:
            per_video.append(result)

    # Strip score-sequence lists from per_video before aggregating — they are
    # not needed for the numeric aggregate and would bloat JSON output.
    agg_input = [
        {k: v for k, v in r.items() if k not in ("json_path", "video_path")}
        for r in per_video
    ]
    aggregate = aggregate_video_metrics(agg_input)

    return {
        "iou_threshold": iou_threshold,
        "per_video": per_video,
        "aggregate": aggregate,
        "n_skipped": n_skipped,
    }


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------


def _render_table(result: dict[str, Any]) -> str:
    """Render evaluation result as a human-readable text table.

    Args:
        result: Dict returned by :func:`run_boundary_evaluation`.

    Returns:
        Multi-line string suitable for printing to stdout.
    """
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 72)
    lines.append("  Stage-1 Rally Boundary Evaluation")
    lines.append("=" * 72)
    lines.append(f"  IoU threshold : {result['iou_threshold']}")
    lines.append(f"  Videos        : {len(result['per_video'])} evaluated, "
                 f"{result['n_skipped']} skipped")
    lines.append("")

    # Column widths
    col_name = 32
    col_n = 6
    col_acc = 9

    header = (
        f"  {'Video':<{col_name}}"
        f"{'GT':>{col_n}}"
        f"{'Pred':>{col_n}}"
        f"{'Match':>{col_n}}"
        f"{'P':>{col_acc}}"
        f"{'R':>{col_acc}}"
        f"{'F1':>{col_acc}}"
        f"{'sMae':>{col_acc}}"
        f"{'eMae':>{col_acc}}"
    )
    lines.append(header)
    sep = "  " + "-" * (col_name + col_n * 3 + col_acc * 5)
    lines.append(sep)

    def _mae_str(v: float | None) -> str:
        return f"{v:.2f}s" if v is not None else "  N/A "

    for row in result["per_video"]:
        name = Path(row["video_path"]).name
        name = name[:col_name - 1] if len(name) > col_name - 1 else name
        lines.append(
            f"  {name:<{col_name}}"
            f"{row['n_ground_truth']:>{col_n}}"
            f"{row['n_predicted']:>{col_n}}"
            f"{row['n_matched']:>{col_n}}"
            f"{row['precision']:>{col_acc}.1%}"
            f"{row['recall']:>{col_acc}.1%}"
            f"{row['f1']:>{col_acc}.1%}"
            f"{_mae_str(row['start_mae_s']):>{col_acc}}"
            f"{_mae_str(row['end_mae_s']):>{col_acc}}"
        )

    agg = result["aggregate"]
    lines.append(sep)
    lines.append(
        f"  {'AGGREGATE':<{col_name}}"
        f"{agg['n_ground_truth']:>{col_n}}"
        f"{agg['n_predicted']:>{col_n}}"
        f"{agg['n_matched']:>{col_n}}"
        f"{agg['precision']:>{col_acc}.1%}"
        f"{agg['recall']:>{col_acc}.1%}"
        f"{agg['f1']:>{col_acc}.1%}"
        f"{_mae_str(agg['start_mae_s']):>{col_acc}}"
        f"{_mae_str(agg['end_mae_s']):>{col_acc}}"
    )
    lines.append("=" * 72)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluate_boundaries",
        description=(
            "Evaluate Stage-1 audio rally detection on held-out videos. "
            "Loads ground-truth intervals from .training.json label files, "
            "runs ml.predict.predict_video to obtain predicted intervals, "
            "and computes detection-style precision/recall/F1 and boundary "
            "error metrics.  Intended for checkpoint selection and threshold tuning."
        ),
    )
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        type=Path,
        help="One or more .training.json files to evaluate.",
    )
    parser.add_argument(
        "--dir",
        dest="dirs",
        metavar="DIR",
        action="append",
        type=Path,
        default=[],
        help=(
            "Directory to glob for *.training.json files. "
            "May be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.5,
        metavar="FLOAT",
        help="IoU threshold for interval matching (default: 0.5).",
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit machine-readable JSON to stdout instead of the human-readable table.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to model checkpoint to evaluate "
            "(default: ml/checkpoints/best_model.pt)."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        help=(
            "Detection probability threshold in [0, 1] "
            "(default: InferenceConfig.threshold = 0.5)."
        ),
    )
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=None,
        metavar="FLOAT",
        help=(
            "Merge rallies closer than this many seconds (must be >= 0) "
            "(default: InferenceConfig.merge_gap_seconds = 1.0)."
        ),
    )
    parser.add_argument(
        "--min-rally",
        type=float,
        default=None,
        metavar="FLOAT",
        help=(
            "Discard predicted rallies shorter than this many seconds (must be >= 0) "
            "(default: InferenceConfig.min_rally_seconds = 1.5)."
        ),
    )
    parser.add_argument(
        "--smooth-kernel",
        type=int,
        default=None,
        metavar="INT",
        help=(
            "Median filter kernel size; must be a positive odd integer "
            "(default: InferenceConfig.smooth_kernel = 5)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the evaluate_boundaries CLI.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 on success, 1 when no input files are found).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Validate override flags before any heavy imports.
    # ------------------------------------------------------------------
    errors: list[str] = []

    if args.threshold is not None and not (0.0 <= args.threshold <= 1.0):
        errors.append(
            f"--threshold must be in [0, 1]; got {args.threshold}"
        )
    if args.merge_gap is not None and args.merge_gap < 0.0:
        errors.append(
            f"--merge-gap must be >= 0; got {args.merge_gap}"
        )
    if args.min_rally is not None and args.min_rally < 0.0:
        errors.append(
            f"--min-rally must be >= 0; got {args.min_rally}"
        )
    if args.smooth_kernel is not None and (
        args.smooth_kernel < 1 or args.smooth_kernel % 2 == 0
    ):
        errors.append(
            f"--smooth-kernel must be a positive odd integer; got {args.smooth_kernel}"
        )

    if errors:
        for msg in errors:
            print(f"[evaluate_boundaries] ERROR: {msg}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # Build InferenceConfig from overrides (only when at least one is set).
    # ------------------------------------------------------------------
    inference_config = None
    if any(
        v is not None
        for v in (args.threshold, args.merge_gap, args.min_rally, args.smooth_kernel)
    ):
        from ml.config import InferenceConfig  # noqa: PLC0415 — lazy import

        cfg = InferenceConfig()
        if args.threshold is not None:
            cfg.threshold = args.threshold
        if args.merge_gap is not None:
            cfg.merge_gap_seconds = args.merge_gap
        if args.min_rally is not None:
            cfg.min_rally_seconds = args.min_rally
        if args.smooth_kernel is not None:
            cfg.smooth_kernel = args.smooth_kernel
        inference_config = cfg

    model_path: Path | None = None
    if args.model_path is not None:
        model_path = args.model_path.expanduser().resolve()
        if not model_path.exists():
            print(
                f"[evaluate_boundaries] ERROR: --model-path not found: {model_path}",
                file=sys.stderr,
            )
            return 1

    explicit_paths = [p.expanduser().resolve() for p in (args.paths or [])]
    dirs = [d.expanduser().resolve() for d in (args.dirs or [])]

    # Default: scan ~/Videos/pickleball if no inputs given.
    if not explicit_paths and not dirs:
        default_dir = (Path.home() / "Videos" / "pickleball").resolve()
        print(
            f"[evaluate_boundaries] No paths/dirs specified; "
            f"defaulting to {default_dir}",
            file=sys.stderr,
        )
        dirs = [default_dir]

    result = run_boundary_evaluation(
        paths=explicit_paths,
        dirs=dirs,
        iou_threshold=args.iou,
        model_path=model_path,
        inference_config=inference_config,
    )

    if not result["per_video"] and result["n_skipped"] == 0:
        print(
            "[evaluate_boundaries] No .training.json files found.",
            file=sys.stderr,
        )
        return 1

    if args.emit_json:
        print(json.dumps(result, indent=2))
    else:
        print(_render_table(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
