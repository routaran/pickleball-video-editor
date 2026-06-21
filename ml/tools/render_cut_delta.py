"""Render what motion fusion changed vs the audio-only baseline.

Standalone CLI + importable pure functions for comparing two rally-interval
lists and emitting human-reviewable artifacts: a markdown/JSON report listing
each delta segment with timestamps and a ``footage_confusion`` summary, plus
optional ffmpeg commands (or live extraction) for eyeballing the deltas without
watching entire matches.

**Fully offline** — the pure functions (``cut_deltas``, ``write_delta_report``,
``get_ffmpeg_commands``) carry no heavy dependencies and are safe to import in
tests.  The ``--from-video`` path that invokes the audio + fusion models imports
``ml.motion.predict_fused`` *lazily* (inside the function) so this module loads
cleanly even while the motion package is mid-refactor elsewhere.

Usage examples::

    # Compare two pre-computed interval lists; write a markdown report:
    python -m ml.tools.render_cut_delta \\
        --baseline '[[0.0,30.5],[60.2,90.1]]' \\
        --candidate '[[5.0,35.5],[58.0,88.0]]' \\
        --gt '[[0.0,30.0],[60.0,90.0]]' \\
        --report delta_report.md

    # Same but emit JSON instead of markdown:
    python -m ml.tools.render_cut_delta \\
        --baseline '[[0.0,30.5],[60.2,90.1]]' \\
        --candidate '[[5.0,35.5],[58.0,88.0]]' \\
        --json

    # Compute baseline (audio-only) and candidate (fused) from a video and
    # extract the delta clips to ./delta_clips/:
    python -m ml.tools.render_cut_delta \\
        --from-video /path/to/match.mp4 \\
        --feature-path /path/to/match.npz \\
        --gt '[[0.0,30.0],[60.0,90.0]]' \\
        --report delta_report.md \\
        --extract --out-dir ./delta_clips

    # Pre-computed intervals + clip extraction (--video needed for --extract):
    python -m ml.tools.render_cut_delta \\
        --baseline '[[0,30],[60,90]]' \\
        --candidate '[[5,35],[58,88]]' \\
        --video /path/to/match.mp4 \\
        --extract --out-dir ./delta_clips
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ml.evaluation.event_metrics import footage_confusion

__all__ = [
    "cut_deltas",
    "write_delta_report",
    "get_ffmpeg_commands",
    "main",
]


# ---------------------------------------------------------------------------
# Internal interval helpers (self-contained; avoids coupling to private APIs)
# ---------------------------------------------------------------------------


def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Union-merge overlapping/touching intervals into a sorted non-overlapping list.

    Invalid intervals where start > end are silently dropped.
    """
    valid = [(s, e) for s, e in intervals if s <= e]
    if not valid:
        return []
    valid.sort(key=lambda x: x[0])
    merged: list[tuple[float, float]] = [valid[0]]
    for s, e in valid[1:]:
        ms, me = merged[-1]
        if s <= me:
            merged[-1] = (ms, max(me, e))
        else:
            merged.append((s, e))
    return merged


def _subtract(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return A − B for two pre-merged (sorted, non-overlapping) interval lists.

    Uses a two-pointer sweep: *j* advances monotonically across *b* as *a*
    is scanned in order, giving O(|a| + |b|) time.
    """
    result: list[tuple[float, float]] = []
    j = 0  # persistent pointer into b (only moves forward)
    for as_, ae in a:
        # Skip b intervals that ended before the current a interval starts.
        while j < len(b) and b[j][1] <= as_:
            j += 1
        cur_start = as_
        k = j  # local scan pointer so j is not disturbed
        while k < len(b) and b[k][0] < ae:
            bs, be = b[k]
            if cur_start < bs:
                result.append((cur_start, bs))
            cur_start = max(cur_start, be)
            k += 1
        if cur_start < ae:
            result.append((cur_start, ae))
    return result


# ---------------------------------------------------------------------------
# Public pure functions
# ---------------------------------------------------------------------------


def cut_deltas(
    baseline: list[tuple[float, float]],
    candidate: list[tuple[float, float]],
) -> dict:
    """Compute what the candidate pipeline changed vs the baseline.

    Both interval lists are first union-merged so overlapping or touching
    inputs are handled correctly.  The function is pure — no I/O, no model
    imports — and safe to call from tests.

    Args:
        baseline: Rally intervals from the reference pipeline, e.g. audio-only.
            Each element is ``(start_s, end_s)``; list may be unsorted and may
            contain overlapping segments.
        candidate: Rally intervals from the candidate pipeline, e.g.
            motion-fused.  Same format as *baseline*.

    Returns:
        dict with two keys:

        ``"removed"``
            Segments present in *baseline* but absent in *candidate* — the
            portions that fusion *vetoed*.  A reviewer should watch these to
            check for false-negative vetos (real rallies cut).

        ``"added"``
            Segments present in *candidate* but absent in *baseline* — the
            portions that fusion *sustained* past the audio model.  A reviewer
            should watch these to check for false-positive sustains (dead time
            kept).

        Each segment is a tuple ``(start_s, end_s, duration_s)`` with
        ``duration_s = end_s − start_s``.
    """
    base_m = _merge(baseline)
    cand_m = _merge(candidate)

    removed_segs = _subtract(base_m, cand_m)
    added_segs = _subtract(cand_m, base_m)

    return {
        "removed": [(s, e, e - s) for s, e in removed_segs],
        "added": [(s, e, e - s) for s, e in added_segs],
    }


def get_ffmpeg_commands(
    video_path: str | Path,
    segments: list[tuple[float, float, float]],
    out_dir: str | Path,
    prefix: str = "clip",
) -> list[str]:
    """Build ffmpeg shell commands to extract each segment to a file.

    Uses the system ffmpeg CLI via ``-ss``/``-t`` (seek + duration), with
    ``-c copy`` for near-instant, lossless extraction.  Commands are returned
    as strings; the caller decides whether to print them or execute them.

    Args:
        video_path: Source video file.
        segments: List of ``(start_s, end_s, duration_s)`` as returned by
            :func:`cut_deltas`.
        out_dir: Directory where clip files will be written.
        prefix: Filename prefix (e.g. ``"removed"`` or ``"added"``).

    Returns:
        List of shell-ready command strings, one per segment.
    """
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    commands: list[str] = []
    for i, (start_s, end_s, duration_s) in enumerate(segments):
        out_file = out_dir / f"{prefix}_{i:03d}_{start_s:.1f}s-{end_s:.1f}s.mp4"
        cmd = (
            f"ffmpeg -y -ss {start_s:.3f} -t {duration_s:.3f}"
            f" -i {str(video_path)!r} -c copy {str(out_file)!r}"
        )
        commands.append(cmd)
    return commands


def write_delta_report(
    deltas: dict,
    baseline: list[tuple[float, float]],
    candidate: list[tuple[float, float]],
    gt: list[tuple[float, float]] | None = None,
    video_path: str | Path | None = None,
    total_seconds: float | None = None,
) -> str:
    """Render a markdown delta report for human review.

    The report lists each removed/added segment with timestamps and durations,
    then appends a ``footage_confusion`` summary table for both pipelines (when
    ground truth is supplied) so a reviewer knows which pipeline retains more
    rally footage and which introduces more junk.

    Args:
        deltas: Output of :func:`cut_deltas`.
        baseline: Baseline interval list (used for ``footage_confusion``).
        candidate: Candidate interval list (used for ``footage_confusion``).
        gt: Ground-truth intervals; when ``None`` the confusion tables are
            omitted.
        video_path: Source video path (informational header only).
        total_seconds: Total video duration in seconds (informational; passed
            to ``footage_confusion`` when supplied).

    Returns:
        Markdown string ready for writing to a ``.md`` file.
    """
    lines: list[str] = []
    lines.append("# Cut Delta Report")
    lines.append("")
    if video_path:
        lines.append(f"**Video:** `{video_path}`")
    if total_seconds is not None:
        lines.append(f"**Total duration:** {total_seconds:.1f}s")
    lines.append("")

    removed = deltas["removed"]
    added = deltas["added"]

    def _seg_table(segs: list[tuple[float, float, float]], heading: str) -> None:
        n = len(segs)
        lines.append(f"## {heading} ({n} segment{'s' if n != 1 else ''})")
        if not segs:
            lines.append("")
            lines.append("_None — pipelines agree on this region._")
            lines.append("")
            return
        total = sum(d for _, _, d in segs)
        lines.append(f"Total: **{total:.2f}s**")
        lines.append("")
        lines.append("| # | Start | End | Duration |")
        lines.append("|---|------:|----:|---------:|")
        for i, (s, e, d) in enumerate(segs):
            lines.append(f"| {i + 1} | {s:.2f}s | {e:.2f}s | {d:.2f}s |")
        lines.append("")

    _seg_table(removed, "Removed by candidate (fusion vetoed)")
    _seg_table(added, "Added by candidate (fusion sustained)")

    # Footage confusion summaries — only when GT is available.
    lines.append("## Footage Confusion Summaries")
    lines.append("")
    if gt is not None:
        for label, intervals in [("Baseline", baseline), ("Candidate", candidate)]:
            fc = footage_confusion(intervals, gt, total_seconds)
            lines.append(f"### {label} vs Ground Truth")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|------:|")
            lines.append(
                f"| true_rally_seconds | {fc['true_rally_seconds']:.2f}s |"
            )
            lines.append(
                f"| pred_rally_seconds | {fc['pred_rally_seconds']:.2f}s |"
            )
            lines.append(
                f"| kept_rally_seconds | {fc['kept_rally_seconds']:.2f}s |"
            )
            lines.append(
                f"| missed_rally_seconds | {fc['missed_rally_seconds']:.2f}s |"
            )
            lines.append(
                f"| **footage_recall** | **{fc['footage_recall']:.1%}** |"
            )
            lines.append(
                f"| junk_seconds | {fc['junk_seconds']:.2f}s |"
            )
            lines.append(
                f"| junk_fraction | {fc['junk_fraction']:.1%} |"
            )
            lines.append(
                f"| net_added_seconds | {fc['net_added_seconds']:+.2f}s |"
            )
            lines.append(
                f"| net_dropped_seconds | {fc['net_dropped_seconds']:+.2f}s |"
            )
            lines.append(
                f"| n_fully_missed_rallies | {fc['n_fully_missed_rallies']} |"
            )
            lines.append("")
    else:
        lines.append(
            "_No ground truth provided — pass `--gt` to enable footage confusion tables._"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Video-prediction path (lazy imports — not exercised by tests)
# ---------------------------------------------------------------------------


def _compute_from_video(
    video_path: Path,
    feature_path: Path | None = None,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Compute baseline (audio-only) and candidate (fused) intervals from a video.

    Imports ``ml.motion.predict_fused`` and the audio model lazily so that
    this module can be imported cleanly without torch or a working motion
    package present.  NOT exercised by unit tests (requires a model checkpoint
    and optionally a GPU).

    Args:
        video_path: Path to the source video.
        feature_path: Optional path to a pre-computed ``.npz`` motion feature
            cache.  When absent, fusion falls back to audio-only.

    Returns:
        ``(baseline, candidate)`` — each a list of ``(start_s, end_s)`` tuples.
    """
    # Heavy imports — all lazy.
    from ml.config import InferenceConfig  # noqa: PLC0415
    from ml.motion.predict_fused import (  # noqa: PLC0415
        audio_window_probs,
        fuse_to_intervals,
    )
    from ml.predict import predictions_to_rallies  # noqa: PLC0415

    inf_cfg = InferenceConfig()

    probs, center_times = audio_window_probs(video_path, inference_config=inf_cfg)

    # Audio-only baseline: threshold → segment.
    base_rallies = predictions_to_rallies(probs, center_times, inf_cfg)
    baseline = [(r["start_seconds"], r["end_seconds"]) for r in base_rallies]

    # Motion-fused candidate: load cached features if available.
    features = None
    if feature_path is not None and Path(feature_path).exists():
        from ml.motion.features import load_feature_series  # noqa: PLC0415

        features = load_feature_series(feature_path)

    candidate = fuse_to_intervals(probs, center_times, features, inf_cfg)
    return baseline, candidate


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _parse_intervals(value: str) -> list[tuple[float, float]]:
    """Parse a JSON interval list from an inline string or a file path.

    Inline strings must start with ``[`` (e.g. ``'[[0,30],[60,90]]'``).
    Otherwise the value is treated as a file path and loaded with ``json.load``.
    """
    stripped = value.strip()
    if stripped.startswith("["):
        data = json.loads(stripped)
    else:
        path = Path(value).expanduser()
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    return [(float(s), float(e)) for s, e in data]


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render_cut_delta",
        description=(
            "Compare two rally-interval lists and emit a delta report showing "
            "what fusion removed vs added, with footage-seconds confusion metrics."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Pre-computed intervals → markdown report:\n"
            "  python -m ml.tools.render_cut_delta \\\n"
            "      --baseline '[[0.0,30.5],[60.2,90.1]]' \\\n"
            "      --candidate '[[5.0,35.5],[58.0,88.0]]' \\\n"
            "      --gt '[[0.0,30.0],[60.0,90.0]]' --report delta.md\n\n"
            "  # From video (runs audio + fused prediction):\n"
            "  python -m ml.tools.render_cut_delta \\\n"
            "      --from-video match.mp4 --feature-path match.npz \\\n"
            "      --report delta.md --extract --out-dir ./clips\n"
        ),
    )

    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--from-video",
        metavar="PATH",
        type=Path,
        help=(
            "Compute baseline (audio-only) and candidate (fused) directly from "
            "a video. Lazy-imports the audio + motion models."
        ),
    )
    src.add_argument(
        "--baseline",
        metavar="INTERVALS",
        help=(
            "Baseline interval list: inline JSON (e.g. '[[0,30],[60,90]]') "
            "or path to a JSON file."
        ),
    )

    p.add_argument(
        "--candidate",
        metavar="INTERVALS",
        help=(
            "Candidate interval list (required when --baseline is used): "
            "inline JSON or file path."
        ),
    )
    p.add_argument(
        "--feature-path",
        metavar="PATH",
        type=Path,
        help="Cached .npz motion features for --from-video mode.",
    )
    p.add_argument(
        "--gt",
        metavar="INTERVALS",
        help="Ground-truth intervals (inline JSON or file path) for footage_confusion tables.",
    )
    p.add_argument(
        "--video",
        metavar="PATH",
        type=Path,
        help="Source video path (used for --extract when --baseline/--candidate are supplied).",
    )
    p.add_argument(
        "--total-seconds",
        metavar="SECS",
        type=float,
        default=None,
        help="Total video duration in seconds (informational; stored in confusion tables).",
    )
    p.add_argument(
        "--report",
        metavar="PATH",
        help="Write the markdown report to this file (default: print to stdout).",
    )
    p.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit JSON instead of markdown (to stdout or --report file).",
    )
    p.add_argument(
        "--extract",
        action="store_true",
        help=(
            "Extract delta segments to clip files using the system ffmpeg CLI. "
            "Requires --video or --from-video."
        ),
    )
    p.add_argument(
        "--out-dir",
        metavar="DIR",
        default="delta_clips",
        help="Directory for extracted clips (default: ./delta_clips).",
    )
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 on success, 1 on error.
    """
    p = _build_arg_parser()
    args = p.parse_args(argv)

    # ---- Resolve baseline / candidate intervals ----------------------------
    if args.from_video:
        video_path = args.from_video.expanduser().resolve()
        feature_path = (
            args.feature_path.expanduser().resolve()
            if args.feature_path
            else None
        )
        try:
            baseline, candidate = _compute_from_video(video_path, feature_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[render_cut_delta] ERROR computing from video: {exc}", file=sys.stderr)
            return 1
        effective_video = video_path
    else:
        if not args.baseline or not args.candidate:
            p.error("--baseline and --candidate are required when --from-video is not used.")
        try:
            baseline = _parse_intervals(args.baseline)
            candidate = _parse_intervals(args.candidate)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"[render_cut_delta] ERROR parsing intervals: {exc}", file=sys.stderr)
            return 1
        effective_video = args.video

    gt: list[tuple[float, float]] | None = None
    if args.gt:
        try:
            gt = _parse_intervals(args.gt)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"[render_cut_delta] ERROR parsing --gt intervals: {exc}", file=sys.stderr)
            return 1

    # ---- Compute deltas ---------------------------------------------------
    deltas = cut_deltas(baseline, candidate)

    # ---- Build output -----------------------------------------------------
    if args.emit_json:
        # JSON mode: serialize deltas + optional confusion dicts.
        output_data: dict = {
            "deltas": deltas,
        }
        if gt is not None:
            output_data["footage_confusion_baseline"] = footage_confusion(
                baseline, gt, args.total_seconds
            )
            output_data["footage_confusion_candidate"] = footage_confusion(
                candidate, gt, args.total_seconds
            )
        output_text = json.dumps(output_data, indent=2)
    else:
        output_text = write_delta_report(
            deltas,
            baseline,
            candidate,
            gt=gt,
            video_path=effective_video,
            total_seconds=args.total_seconds,
        )

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output_text, encoding="utf-8")
        print(f"[render_cut_delta] Report written to {report_path}", file=sys.stderr)
    else:
        print(output_text)

    # ---- Optional clip extraction ----------------------------------------
    if args.extract:
        if not effective_video:
            print(
                "[render_cut_delta] ERROR: --extract requires --video or --from-video.",
                file=sys.stderr,
            )
            return 1
        out_dir = Path(args.out_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        for kind in ("removed", "added"):
            segs = deltas[kind]
            if not segs:
                continue
            cmds = get_ffmpeg_commands(effective_video, segs, out_dir, prefix=kind)
            for cmd in cmds:
                print(f"[render_cut_delta] {cmd}", file=sys.stderr)
                try:
                    subprocess.run(cmd, shell=True, check=True)
                except subprocess.CalledProcessError as exc:
                    print(
                        f"[render_cut_delta] ffmpeg failed (exit {exc.returncode}): {cmd}",
                        file=sys.stderr,
                    )
                    return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
