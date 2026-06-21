"""Compare audio-only vs motion-fused rally segmentation on labelled videos.

For each ``.training.json`` this runs the audio model once, derives the
audio-only baseline intervals and the motion-fused intervals from the same
probability stream, and scores both against ground truth with the existing
``ml.evaluation.event_metrics`` harness.  The table shows the delta so the
precision / ``fp_active_seconds`` improvement (the whole point of the fusion) is
visible at a glance.

Motion features are read from the cache written by
``ml/tools/extract_motion_features.py``.  Videos without a cached feature file
fall back to audio-only (fused == baseline) and are flagged.

To avoid the leakage that made the 0.508 baseline optimistic, evaluate on a
held-out split (pass explicit held-out files or a held-out ``--dir``) and
exclude the known-bad files noted in the training report.

Usage::

    # Tune/inspect on a held-out directory:
    python -m ml.tools.evaluate_fused --dir ~/Videos/pickleball/held_out --iou 0.5

    # Custom fusion thresholds + veto-only (sustain disabled):
    python -m ml.tools.evaluate_fused --dir ~/Videos/pickleball/held_out \\
        --veto-max-detections 1.0 --hysteresis 3 --no-sustain
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main", "run_fused_evaluation"]


def _feature_path_for(out_dir: Path, video_path: Path) -> Path:
    return out_dir / f"{video_path.stem}.npz"


def run_fused_evaluation(
    paths: list[Path],
    dirs: list[Path],
    feature_dir: Path,
    iou_threshold: float,
    model_path: Path | None,
    inference_config: Any | None,
    fusion_config: Any | None,
    half_window_s: float,
) -> dict[str, Any]:
    """Evaluate baseline and fused predictions; return a structured result."""
    from ml.evaluation.event_metrics import (  # noqa: PLC0415
        aggregate_video_metrics,
        interval_detection_metrics,
    )
    from ml.motion.features import load_feature_series  # noqa: PLC0415
    from ml.motion.predict_fused import audio_window_probs, fuse_to_intervals  # noqa: PLC0415
    from ml.predict import predictions_to_rallies  # noqa: PLC0415
    from ml.tools.evaluate_boundaries import _load_ground_truth_intervals  # noqa: PLC0415
    from ml.config import InferenceConfig  # noqa: PLC0415

    inference_config = inference_config or InferenceConfig()

    candidate_paths: list[Path] = list(paths)
    for d in dirs:
        if d.exists():
            candidate_paths.extend(sorted(d.rglob("*.training.json")))
        else:
            print(f"[evaluate_fused] WARN: directory not found: {d}", file=sys.stderr)

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in sorted(candidate_paths):
        rp = p.resolve() if p.exists() else p
        if rp not in seen:
            seen.add(rp)
            unique_paths.append(p)

    per_video: list[dict[str, Any]] = []
    n_skipped = 0
    n_no_motion = 0

    for json_path in unique_paths:
        if not json_path.exists():
            print(f"[evaluate_fused] WARN: file not found: {json_path}", file=sys.stderr)
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
            print(f"[evaluate_fused] WARN: video missing: {video_path}", file=sys.stderr)
            n_skipped += 1
            continue

        # One audio pass; derive both baseline and fused from it.
        probs, center_times = audio_window_probs(
            video_path, model_path=model_path, inference_config=inference_config
        )
        base_rallies = predictions_to_rallies(probs, center_times, inference_config)
        baseline = [(r["start_seconds"], r["end_seconds"]) for r in base_rallies]

        feat_path = _feature_path_for(feature_dir, video_path)
        features = load_feature_series(feat_path) if feat_path.exists() else None
        if features is None:
            n_no_motion += 1
        fused = fuse_to_intervals(
            probs, center_times, features, inference_config, fusion_config, half_window_s
        )

        m_base = interval_detection_metrics(baseline, gt, iou_threshold)
        m_fused = interval_detection_metrics(fused, gt, iou_threshold)
        per_video.append(
            {
                "json_path": str(json_path),
                "video_path": str(video_path),
                "has_motion": features is not None,
                "baseline": m_base,
                "fused": m_fused,
            }
        )

    agg_base = aggregate_video_metrics([r["baseline"] for r in per_video])
    agg_fused = aggregate_video_metrics([r["fused"] for r in per_video])

    return {
        "iou_threshold": iou_threshold,
        "per_video": per_video,
        "aggregate_baseline": agg_base,
        "aggregate_fused": agg_fused,
        "n_skipped": n_skipped,
        "n_no_motion": n_no_motion,
    }


def _render_table(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 84)
    lines.append("  Rally Boundary Evaluation — audio-only (B) vs motion-fused (F)")
    lines.append("=" * 84)
    lines.append(f"  IoU threshold : {result['iou_threshold']}")
    lines.append(
        f"  Videos        : {len(result['per_video'])} evaluated, "
        f"{result['n_skipped']} skipped, {result['n_no_motion']} without motion (audio-only)"
    )
    lines.append("")

    name_w = 30
    header = (
        f"  {'Video':<{name_w}}{'P(B→F)':>16}{'R(B→F)':>16}"
        f"{'F1(B→F)':>16}{'fpSec(B→F)':>16}"
    )
    lines.append(header)
    lines.append("  " + "-" * (name_w + 16 * 4))

    def _pair(b: float, f: float, pct: bool = True) -> str:
        if pct:
            return f"{b:.0%}→{f:.0%}"
        return f"{b:.0f}→{f:.0f}"

    for row in result["per_video"]:
        b, f = row["baseline"], row["fused"]
        name = Path(row["video_path"]).name
        name = name[: name_w - 1] if len(name) > name_w - 1 else name
        flag = "" if row["has_motion"] else " (a)"
        lines.append(
            f"  {name:<{name_w}}"
            f"{_pair(b['precision'], f['precision']):>16}"
            f"{_pair(b['recall'], f['recall']):>16}"
            f"{_pair(b['f1'], f['f1']):>16}"
            f"{_pair(b['fp_active_seconds'], f['fp_active_seconds'], pct=False):>16}"
            f"{flag}"
        )

    ab, af = result["aggregate_baseline"], result["aggregate_fused"]
    lines.append("  " + "-" * (name_w + 16 * 4))
    lines.append(
        f"  {'AGGREGATE':<{name_w}}"
        f"{_pair(ab['precision'], af['precision']):>16}"
        f"{_pair(ab['recall'], af['recall']):>16}"
        f"{_pair(ab['f1'], af['f1']):>16}"
        f"{_pair(ab['fp_active_seconds'], af['fp_active_seconds'], pct=False):>16}"
    )
    lines.append("")
    lines.append(
        f"  baseline : P={ab['precision']:.1%} R={ab['recall']:.1%} F1={ab['f1']:.1%} "
        f"fpSec={ab['fp_active_seconds']:.0f} over_segs={ab['n_over_segs']} "
        f"bMAE={_mae(ab['boundary_mae_s'])}"
    )
    lines.append(
        f"  fused    : P={af['precision']:.1%} R={af['recall']:.1%} F1={af['f1']:.1%} "
        f"fpSec={af['fp_active_seconds']:.0f} over_segs={af['n_over_segs']} "
        f"bMAE={_mae(af['boundary_mae_s'])}"
    )
    lines.append("  (a) = audio-only fallback (no cached motion features)")
    lines.append("=" * 84)
    lines.append("")
    return "\n".join(lines)


def _mae(v: float | None) -> str:
    return f"{v:.2f}s" if v is not None else "N/A"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evaluate_fused",
        description="Compare audio-only vs motion-fused rally segmentation.",
    )
    p.add_argument("paths", metavar="PATH", nargs="*", type=Path)
    p.add_argument("--dir", dest="dirs", metavar="DIR", action="append", type=Path, default=[])
    p.add_argument("--feature-dir", type=Path, default=None,
                   help="Motion feature cache dir (default: ml/cache/motion).")
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--json", dest="emit_json", action="store_true")
    p.add_argument("--model-path", type=Path, default=None)
    p.add_argument("--half-window", type=float, default=0.5,
                   help="Half-width (s) for resampling motion onto audio windows.")
    # Audio post-processing overrides (mirror evaluate_boundaries).
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--merge-gap", type=float, default=None)
    p.add_argument("--min-rally", type=float, default=None)
    p.add_argument("--smooth-kernel", type=int, default=None)
    # Fusion thresholds.
    p.add_argument("--veto-max-detections", type=float, default=None)
    p.add_argument("--veto-max-displacement", type=float, default=None)
    p.add_argument("--sustain-min-detections", type=float, default=None)
    p.add_argument("--sustain-min-symmetry", type=float, default=None)
    p.add_argument("--hysteresis", type=int, default=None)
    p.add_argument("--no-veto", dest="no_veto", action="store_true")
    p.add_argument("--no-sustain", dest="no_sustain", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    from ml.config import InferenceConfig  # noqa: PLC0415
    from ml.motion.fusion import FusionConfig  # noqa: PLC0415

    inf_cfg = InferenceConfig()
    if args.threshold is not None:
        inf_cfg.threshold = args.threshold
    if args.merge_gap is not None:
        inf_cfg.merge_gap_seconds = args.merge_gap
    if args.min_rally is not None:
        inf_cfg.min_rally_seconds = args.min_rally
    if args.smooth_kernel is not None:
        inf_cfg.smooth_kernel = args.smooth_kernel

    fus_cfg = FusionConfig()
    if args.veto_max_detections is not None:
        fus_cfg.veto_max_detections = args.veto_max_detections
    if args.veto_max_displacement is not None:
        fus_cfg.veto_max_displacement = args.veto_max_displacement
    if args.sustain_min_detections is not None:
        fus_cfg.sustain_min_detections = args.sustain_min_detections
    if args.sustain_min_symmetry is not None:
        fus_cfg.sustain_min_symmetry = args.sustain_min_symmetry
    if args.hysteresis is not None:
        fus_cfg.hysteresis = args.hysteresis
    if args.no_veto:
        fus_cfg.enable_veto = False
    if args.no_sustain:
        fus_cfg.enable_sustain = False

    feature_dir = args.feature_dir
    if feature_dir is None:
        from ml.config import PathConfig  # noqa: PLC0415
        feature_dir = PathConfig().cache_dir / "motion"
    feature_dir = feature_dir.expanduser().resolve()

    model_path = args.model_path.expanduser().resolve() if args.model_path else None

    explicit = [p.expanduser().resolve() for p in (args.paths or [])]
    dirs = [d.expanduser().resolve() for d in (args.dirs or [])]
    if not explicit and not dirs:
        dirs = [(Path.home() / "Videos" / "pickleball").resolve()]
        print(f"[evaluate_fused] No inputs; defaulting to {dirs[0]}", file=sys.stderr)

    result = run_fused_evaluation(
        paths=explicit,
        dirs=dirs,
        feature_dir=feature_dir,
        iou_threshold=args.iou,
        model_path=model_path,
        inference_config=inf_cfg,
        fusion_config=fus_cfg,
        half_window_s=args.half_window,
    )

    if not result["per_video"]:
        print("[evaluate_fused] No evaluable files found.", file=sys.stderr)
        return 1

    if args.emit_json:
        print(json.dumps(result, indent=2))
    else:
        print(_render_table(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
