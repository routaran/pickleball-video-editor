"""Reviewed re-export diff tool for the Pickleball ML pipeline.

Compares an auto-generated training JSON against a human-reviewed re-export of
the same video.  Every human-reviewed re-export is a (model output, human-
corrected) pair — the cleanest evaluation data available for field accuracy,
hard-example mining, and regression tracking across model versions.

Usage (single pair)::

    python -m ml.tools.diff_reexport \\
        --auto auto.training.json \\
        --reviewed reviewed.training.json \\
        [--json out.json] [--iou 0.5]

Usage (batch — pair files by identical video.path field)::

    python -m ml.tools.diff_reexport \\
        --auto-dir /path/to/auto \\
        --reviewed-dir /path/to/reviewed \\
        [--json out.json] [--iou 0.5]

Flags
-----
--auto PATH             Auto-generated .training.json file.
--reviewed PATH         Human-reviewed .training.json file.
--auto-dir DIR          Directory of auto .training.json files (batch mode).
--reviewed-dir DIR      Directory of reviewed .training.json files (batch mode).
--json PATH             Write full JSON results to this file (table is still
                        printed to stdout).
--iou FLOAT             IoU threshold for matching rallies (default: 0.5).
--include-post-game     Include is_post_game rallies in the diff (excluded by
                        default).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


__all__ = [
    "diff_training_pair",
    "diff_batch",
    "main",
    "run_diff",
]


# ---------------------------------------------------------------------------
# Timestamp resolution
# ---------------------------------------------------------------------------

def _rally_timestamps(rally: dict[str, Any], fps: float) -> tuple[float, float]:
    """Extract (start_seconds, end_seconds) from a training-JSON rally dict.

    Prefers ``raw.start_seconds`` / ``raw.end_seconds`` when present.  Falls
    back to ``raw.start_frame / fps`` when only frame counts are available.
    If ``raw`` is absent or null, falls back to ``padded`` timestamps.

    Args:
        rally: A single rally dict from a .training.json file.
        fps:   Video frames-per-second from the top-level ``video.fps`` field.

    Returns:
        ``(start_seconds, end_seconds)`` as floats.
    """
    raw = rally.get("raw")
    if raw is not None:
        if "start_seconds" in raw and "end_seconds" in raw:
            return float(raw["start_seconds"]), float(raw["end_seconds"])
        if "start_frame" in raw and "end_frame" in raw and fps > 0:
            return raw["start_frame"] / fps, raw["end_frame"] / fps

    padded = rally.get("padded")
    if padded is not None:
        if "start_seconds" in padded and "end_seconds" in padded:
            return float(padded["start_seconds"]), float(padded["end_seconds"])
        if "start_frame" in padded and "end_frame" in padded and fps > 0:
            return padded["start_frame"] / fps, padded["end_frame"] / fps

    # Very old format: top-level start_frame/end_frame
    if "start_frame" in rally and "end_frame" in rally and fps > 0:
        return rally["start_frame"] / fps, rally["end_frame"] / fps

    return 0.0, 0.0


# ---------------------------------------------------------------------------
# IoU computation and greedy matching
# ---------------------------------------------------------------------------

def _interval_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Compute intersection-over-union for two 1-D time intervals.

    Args:
        a_start: Start of interval A in seconds.
        a_end:   End of interval A in seconds.
        b_start: Start of interval B in seconds.
        b_end:   End of interval B in seconds.

    Returns:
        IoU value in [0.0, 1.0]; 0.0 if both intervals are zero-length.
    """
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    if union <= 0.0:
        return 0.0
    return intersection / union


def _greedy_match(
    auto_times: list[tuple[float, float]],
    reviewed_times: list[tuple[float, float]],
    iou_threshold: float,
) -> list[tuple[int, int, float]]:
    """Greedily match auto rallies to reviewed rallies by IoU.

    Uses a greedy one-to-one assignment: candidate pairs are sorted by IoU
    descending, and each rally index may appear in at most one matched pair.

    Args:
        auto_times:     List of (start, end) tuples for auto rallies.
        reviewed_times: List of (start, end) tuples for reviewed rallies.
        iou_threshold:  Minimum IoU for a valid match.

    Returns:
        List of ``(auto_index, reviewed_index, iou)`` triples, sorted by
        ``auto_index``.
    """
    # Build all candidate pairs above threshold
    candidates: list[tuple[float, int, int]] = []
    for ai, (as_, ae) in enumerate(auto_times):
        for ri, (rs, re) in enumerate(reviewed_times):
            iou = _interval_iou(as_, ae, rs, re)
            if iou >= iou_threshold:
                candidates.append((iou, ai, ri))

    # Sort descending by IoU
    candidates.sort(key=lambda x: x[0], reverse=True)

    matched_auto: set[int] = set()
    matched_reviewed: set[int] = set()
    matches: list[tuple[int, int, float]] = []

    for iou, ai, ri in candidates:
        if ai in matched_auto or ri in matched_reviewed:
            continue
        matched_auto.add(ai)
        matched_reviewed.add(ri)
        matches.append((ai, ri, iou))

    matches.sort(key=lambda x: x[0])
    return matches


# ---------------------------------------------------------------------------
# Winner derivation
# ---------------------------------------------------------------------------

def _derive_winning_team(rally: dict[str, Any]) -> int | None:
    """Derive winning_team integer from rally fields.

    Priority:
    1. ``winning_team`` field when present and not None.
    2. ``score_snapshot_at_start.serving_team`` + ``winner`` field.
    3. Returns None when derivation is impossible.

    Args:
        rally: A single rally dict from a .training.json file.

    Returns:
        0 or 1 for team identity, or None if undeterminable.
    """
    wt = rally.get("winning_team")
    if wt is not None:
        return int(wt)

    snapshot = rally.get("score_snapshot_at_start")
    if isinstance(snapshot, dict):
        serving_team = snapshot.get("serving_team")
        winner = rally.get("winner")
        if serving_team is not None and winner in ("server", "receiver"):
            st = int(serving_team)
            return st if winner == "server" else 1 - st

    return None


# ---------------------------------------------------------------------------
# Core diff logic
# ---------------------------------------------------------------------------

def diff_training_pair(
    auto: dict[str, Any],
    reviewed: dict[str, Any],
    iou_threshold: float = 0.5,
    include_post_game: bool = False,
) -> dict[str, Any]:
    """Diff a single (auto, reviewed) training-JSON pair.

    All heavy computation lives here; the CLI is a thin wrapper.

    Args:
        auto:             Parsed auto-generated training JSON dict.
        reviewed:         Parsed human-reviewed training JSON dict.
        iou_threshold:    Minimum IoU to consider two rallies matched.
        include_post_game: When False (default), is_post_game rallies are
                          excluded from both sides before comparison.

    Returns:
        Result dict with keys: ``video``, ``n_auto``, ``n_reviewed``,
        ``n_matched``, ``boundary``, ``detection``, ``winner``, ``score``,
        ``hard_examples``.
    """
    video_path = auto.get("video", {}).get("path", "")
    fps = float(auto.get("video", {}).get("fps") or 30.0)

    # --- filter rallies ---
    def _keep(rally: dict[str, Any]) -> bool:
        return include_post_game or not rally.get("is_post_game", False)

    auto_rallies: list[dict[str, Any]] = [r for r in auto.get("rallies", []) if _keep(r)]
    reviewed_rallies: list[dict[str, Any]] = [r for r in reviewed.get("rallies", []) if _keep(r)]

    auto_times = [_rally_timestamps(r, fps) for r in auto_rallies]
    reviewed_times = [_rally_timestamps(r, fps) for r in reviewed_rallies]

    matches = _greedy_match(auto_times, reviewed_times, iou_threshold)

    matched_auto_idx = {m[0] for m in matches}
    matched_reviewed_idx = {m[1] for m in matches}

    # --- boundary corrections ---
    start_deltas: list[float] = []
    end_deltas: list[float] = []
    large_boundary_pairs: list[dict[str, Any]] = []

    for ai, ri, iou in matches:
        a_start, a_end = auto_times[ai]
        r_start, r_end = reviewed_times[ri]

        sd = abs(r_start - a_start)
        ed = abs(r_end - a_end)
        start_deltas.append(sd)
        end_deltas.append(ed)

        if sd > 0.5 or ed > 0.5:
            large_boundary_pairs.append({
                "auto_index": auto_rallies[ai].get("index", ai),
                "reviewed_index": reviewed_rallies[ri].get("index", ri),
                "auto_start": round(a_start, 3),
                "auto_end": round(a_end, 3),
                "reviewed_start": round(r_start, 3),
                "reviewed_end": round(r_end, 3),
                "abs_start_delta": round(sd, 3),
                "abs_end_delta": round(ed, 3),
            })

    boundary_result: dict[str, Any] = {
        "n_matched": len(matches),
        "mean_abs_start_delta": round(statistics.mean(start_deltas), 4) if start_deltas else None,
        "median_abs_start_delta": round(statistics.median(start_deltas), 4) if start_deltas else None,
        "mean_abs_end_delta": round(statistics.mean(end_deltas), 4) if end_deltas else None,
        "median_abs_end_delta": round(statistics.median(end_deltas), 4) if end_deltas else None,
        "large_deltas": large_boundary_pairs,
    }

    # --- detection errors ---
    false_positives: list[dict[str, Any]] = []
    for ai, (a_start, a_end) in enumerate(auto_times):
        if ai not in matched_auto_idx:
            false_positives.append({
                "auto_index": auto_rallies[ai].get("index", ai),
                "start_seconds": round(a_start, 3),
                "end_seconds": round(a_end, 3),
                "score_at_start": auto_rallies[ai].get("score_at_start"),
            })

    missed: list[dict[str, Any]] = []
    for ri, (r_start, r_end) in enumerate(reviewed_times):
        if ri not in matched_reviewed_idx:
            missed.append({
                "reviewed_index": reviewed_rallies[ri].get("index", ri),
                "start_seconds": round(r_start, 3),
                "end_seconds": round(r_end, 3),
                "score_at_start": reviewed_rallies[ri].get("score_at_start"),
            })

    detection_result: dict[str, Any] = {
        "n_false_positives": len(false_positives),
        "n_missed": len(missed),
        "false_positives": false_positives,
        "missed": missed,
    }

    # --- winner agreement ---
    n_winner_compared = 0
    n_winner_correct = 0
    caveat_raw_strings = False
    winner_mismatches: list[dict[str, Any]] = []

    for ai, ri, iou in matches:
        ar = auto_rallies[ai]
        rr = reviewed_rallies[ri]

        auto_wt = _derive_winning_team(ar)
        reviewed_wt = _derive_winning_team(rr)

        used_caveat = False

        if auto_wt is None or reviewed_wt is None:
            # Fall back to raw winner strings
            auto_winner_raw = ar.get("winner")
            reviewed_winner_raw = rr.get("winner")
            if auto_winner_raw is None or reviewed_winner_raw is None:
                continue  # cannot compare this pair
            used_caveat = True
            caveat_raw_strings = True
            matches_winner = (auto_winner_raw == reviewed_winner_raw)
            auto_wt_display: Any = auto_winner_raw
            reviewed_wt_display: Any = reviewed_winner_raw
        else:
            matches_winner = (auto_wt == reviewed_wt)
            auto_wt_display = auto_wt
            reviewed_wt_display = reviewed_wt

        n_winner_compared += 1
        if matches_winner:
            n_winner_correct += 1
        else:
            a_start, _ = auto_times[ai]
            mismatch_entry: dict[str, Any] = {
                "auto_index": ar.get("index", ai),
                "reviewed_index": rr.get("index", ri),
                "auto_time": round(a_start, 3),
                "auto_winner": auto_wt_display,
                "reviewed_winner": reviewed_wt_display,
                "caveat_raw_strings": used_caveat,
            }
            winner_mismatches.append(mismatch_entry)

    winner_result: dict[str, Any] = {
        "n_compared": n_winner_compared,
        "n_correct": n_winner_correct,
        "n_wrong": n_winner_compared - n_winner_correct,
        "accuracy": (
            round(n_winner_correct / n_winner_compared, 4)
            if n_winner_compared > 0 else None
        ),
        "caveat_raw_strings": caveat_raw_strings,
        "mismatches": winner_mismatches,
    }

    # --- score-string agreement ---
    n_score_compared = 0
    n_score_matching = 0
    first_divergence_index: int | None = None

    for seq_pos, (ai, ri, iou) in enumerate(matches):
        auto_score = auto_rallies[ai].get("score_at_start")
        reviewed_score = reviewed_rallies[ri].get("score_at_start")
        if auto_score is None or reviewed_score is None:
            continue
        n_score_compared += 1
        if auto_score == reviewed_score:
            n_score_matching += 1
        elif first_divergence_index is None:
            first_divergence_index = seq_pos

    score_result: dict[str, Any] = {
        "n_compared": n_score_compared,
        "n_matching": n_score_matching,
        "accuracy": (
            round(n_score_matching / n_score_compared, 4)
            if n_score_compared > 0 else None
        ),
        "first_divergence_index": first_divergence_index,
    }

    # --- hard-example mining ---
    hard_examples: list[dict[str, Any]] = []

    for entry in large_boundary_pairs:
        a_start = auto_times[
            next(i for i, r in enumerate(auto_rallies) if r.get("index", i) == entry["auto_index"])
        ][0]
        hard_examples.append({
            "video": video_path,
            "type": "boundary_shift",
            "auto_index": entry["auto_index"],
            "reviewed_index": entry["reviewed_index"],
            "auto_time": round(a_start, 3),
            "detail": {
                "abs_start_delta": entry["abs_start_delta"],
                "abs_end_delta": entry["abs_end_delta"],
            },
        })

    for mismatch in winner_mismatches:
        hard_examples.append({
            "video": video_path,
            "type": "winner_flip",
            "auto_index": mismatch["auto_index"],
            "reviewed_index": mismatch["reviewed_index"],
            "auto_time": mismatch["auto_time"],
            "detail": {
                "auto_winner": mismatch["auto_winner"],
                "reviewed_winner": mismatch["reviewed_winner"],
                "caveat_raw_strings": mismatch["caveat_raw_strings"],
            },
        })

    for fp in false_positives:
        hard_examples.append({
            "video": video_path,
            "type": "false_positive",
            "auto_index": fp["auto_index"],
            "reviewed_index": None,
            "auto_time": fp["start_seconds"],
            "detail": {
                "score_at_start": fp["score_at_start"],
            },
        })

    for ms in missed:
        hard_examples.append({
            "video": video_path,
            "type": "missed_rally",
            "auto_index": None,
            "reviewed_index": ms["reviewed_index"],
            "auto_time": ms["start_seconds"],
            "detail": {
                "score_at_start": ms["score_at_start"],
            },
        })

    hard_examples.sort(key=lambda x: (x["auto_time"] is None, x["auto_time"] or 0.0))

    return {
        "video": video_path,
        "n_auto": len(auto_rallies),
        "n_reviewed": len(reviewed_rallies),
        "n_matched": len(matches),
        "boundary": boundary_result,
        "detection": detection_result,
        "winner": winner_result,
        "score": score_result,
        "hard_examples": hard_examples,
    }


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

def _scan_training_jsons(directory: Path) -> dict[str, dict[str, Any]]:
    """Scan a directory for .training.json files and index by video.path.

    Args:
        directory: Directory path to scan recursively for ``*.training.json``.

    Returns:
        Dict mapping ``video.path`` string to the parsed JSON dict.  Files that
        cannot be parsed are silently skipped with a warning to stderr.
    """
    index: dict[str, dict[str, Any]] = {}
    for json_path in sorted(directory.glob("**/*.training.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"[diff_reexport] WARNING: skipping {json_path}: {exc}",
                file=sys.stderr,
            )
            continue
        video_path = data.get("video", {}).get("path", "")
        if not video_path:
            print(
                f"[diff_reexport] WARNING: {json_path} has no video.path — skipped.",
                file=sys.stderr,
            )
            continue
        index[video_path] = data
    return index


def diff_batch(
    auto_dir: Path,
    reviewed_dir: Path,
    iou_threshold: float = 0.5,
    include_post_game: bool = False,
) -> dict[str, Any]:
    """Diff all matched pairs from two directories of training JSONs.

    Files are paired by identical ``video.path`` field.  Unpaired files are
    reported as warnings.

    Args:
        auto_dir:         Directory containing auto-generated .training.json files.
        reviewed_dir:     Directory containing human-reviewed .training.json files.
        iou_threshold:    IoU threshold forwarded to :func:`diff_training_pair`.
        include_post_game: Forwarded to :func:`diff_training_pair`.

    Returns:
        Dict with keys ``"pairs"`` (list of per-pair results), ``"unpaired_auto"``,
        ``"unpaired_reviewed"``, and ``"aggregate"`` summary.
    """
    auto_index = _scan_training_jsons(auto_dir)
    reviewed_index = _scan_training_jsons(reviewed_dir)

    auto_keys = set(auto_index.keys())
    reviewed_keys = set(reviewed_index.keys())

    paired_keys = auto_keys & reviewed_keys
    unpaired_auto = sorted(auto_keys - reviewed_keys)
    unpaired_reviewed = sorted(reviewed_keys - auto_keys)

    for key in unpaired_auto:
        print(
            f"[diff_reexport] WARNING: auto-only (no reviewed match): {key}",
            file=sys.stderr,
        )
    for key in unpaired_reviewed:
        print(
            f"[diff_reexport] WARNING: reviewed-only (no auto match): {key}",
            file=sys.stderr,
        )

    pair_results: list[dict[str, Any]] = []
    for key in sorted(paired_keys):
        result = diff_training_pair(
            auto_index[key],
            reviewed_index[key],
            iou_threshold=iou_threshold,
            include_post_game=include_post_game,
        )
        pair_results.append(result)

    aggregate = _aggregate_pair_results(pair_results)

    return {
        "pairs": pair_results,
        "unpaired_auto": unpaired_auto,
        "unpaired_reviewed": unpaired_reviewed,
        "aggregate": aggregate,
    }


def _aggregate_pair_results(
    pair_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute aggregate statistics across multiple pair diff results.

    Args:
        pair_results: List of dicts returned by :func:`diff_training_pair`.

    Returns:
        Dict with totals and overall accuracy metrics.
    """
    if not pair_results:
        return {
            "n_pairs": 0,
            "total_auto": 0,
            "total_reviewed": 0,
            "total_matched": 0,
            "total_false_positives": 0,
            "total_missed": 0,
            "winner_accuracy": None,
            "score_accuracy": None,
            "mean_abs_start_delta": None,
            "mean_abs_end_delta": None,
            "total_hard_examples": 0,
        }

    total_auto = sum(p["n_auto"] for p in pair_results)
    total_reviewed = sum(p["n_reviewed"] for p in pair_results)
    total_matched = sum(p["n_matched"] for p in pair_results)
    total_fp = sum(p["detection"]["n_false_positives"] for p in pair_results)
    total_missed = sum(p["detection"]["n_missed"] for p in pair_results)

    total_winner_compared = sum(p["winner"]["n_compared"] for p in pair_results)
    total_winner_correct = sum(p["winner"]["n_correct"] for p in pair_results)
    winner_accuracy = (
        round(total_winner_correct / total_winner_compared, 4)
        if total_winner_compared > 0 else None
    )

    total_score_compared = sum(p["score"]["n_compared"] for p in pair_results)
    total_score_matching = sum(p["score"]["n_matching"] for p in pair_results)
    score_accuracy = (
        round(total_score_matching / total_score_compared, 4)
        if total_score_compared > 0 else None
    )

    # Weighted mean of boundary deltas
    all_mean_starts = [
        (p["boundary"]["mean_abs_start_delta"], p["n_matched"])
        for p in pair_results
        if p["boundary"]["mean_abs_start_delta"] is not None and p["n_matched"] > 0
    ]
    all_mean_ends = [
        (p["boundary"]["mean_abs_end_delta"], p["n_matched"])
        for p in pair_results
        if p["boundary"]["mean_abs_end_delta"] is not None and p["n_matched"] > 0
    ]

    mean_abs_start = None
    if all_mean_starts:
        total_weight = sum(w for _, w in all_mean_starts)
        mean_abs_start = round(
            sum(v * w for v, w in all_mean_starts) / total_weight, 4
        )

    mean_abs_end = None
    if all_mean_ends:
        total_weight = sum(w for _, w in all_mean_ends)
        mean_abs_end = round(
            sum(v * w for v, w in all_mean_ends) / total_weight, 4
        )

    total_hard = sum(len(p["hard_examples"]) for p in pair_results)

    return {
        "n_pairs": len(pair_results),
        "total_auto": total_auto,
        "total_reviewed": total_reviewed,
        "total_matched": total_matched,
        "total_false_positives": total_fp,
        "total_missed": total_missed,
        "winner_accuracy": winner_accuracy,
        "score_accuracy": score_accuracy,
        "mean_abs_start_delta": mean_abs_start,
        "mean_abs_end_delta": mean_abs_end,
        "total_hard_examples": total_hard,
    }


# ---------------------------------------------------------------------------
# Public entry point (importable)
# ---------------------------------------------------------------------------

def run_diff(
    auto_path: Path | None = None,
    reviewed_path: Path | None = None,
    auto_dir: Path | None = None,
    reviewed_dir: Path | None = None,
    iou_threshold: float = 0.5,
    include_post_game: bool = False,
) -> dict[str, Any]:
    """Run diff in single-pair or batch mode and return result dict.

    Exactly one of (auto_path+reviewed_path) or (auto_dir+reviewed_dir) must
    be supplied.

    Args:
        auto_path:        Path to auto-generated .training.json (single mode).
        reviewed_path:    Path to reviewed .training.json (single mode).
        auto_dir:         Directory of auto files (batch mode).
        reviewed_dir:     Directory of reviewed files (batch mode).
        iou_threshold:    IoU threshold for rally matching.
        include_post_game: Whether to include is_post_game rallies.

    Returns:
        Result dict from :func:`diff_training_pair` (single) or
        :func:`diff_batch` (batch).
    """
    if auto_dir is not None and reviewed_dir is not None:
        return diff_batch(
            auto_dir=auto_dir,
            reviewed_dir=reviewed_dir,
            iou_threshold=iou_threshold,
            include_post_game=include_post_game,
        )

    if auto_path is None or reviewed_path is None:
        raise ValueError("Must supply either (--auto + --reviewed) or (--auto-dir + --reviewed-dir).")

    auto = json.loads(auto_path.read_text(encoding="utf-8"))
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    return diff_training_pair(
        auto=auto,
        reviewed=reviewed,
        iou_threshold=iou_threshold,
        include_post_game=include_post_game,
    )


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

_SEP_WIDTH = 64


def _render_single_pair(result: dict[str, Any]) -> str:
    """Render a single-pair diff result as a human-readable text table.

    Args:
        result: Dict returned by :func:`diff_training_pair`.

    Returns:
        Multi-line string for stdout.
    """
    lines: list[str] = []
    lines.append("")
    lines.append("=" * _SEP_WIDTH)
    lines.append("  Re-export Diff")
    lines.append("=" * _SEP_WIDTH)
    lines.append(f"  Video   : {result['video']}")
    lines.append(f"  Auto    : {result['n_auto']} rallies")
    lines.append(f"  Reviewed: {result['n_reviewed']} rallies")
    lines.append(f"  Matched : {result['n_matched']}")
    lines.append("")

    # Detection
    det = result["detection"]
    lines.append(f"  Detection")
    lines.append(f"    False positives (auto not in reviewed) : {det['n_false_positives']}")
    lines.append(f"    Missed rallies  (reviewed not in auto) : {det['n_missed']}")
    lines.append("")

    # Boundary
    bnd = result["boundary"]
    lines.append("  Boundary Corrections (matched pairs)")
    _fmt = lambda v: f"{v:.3f}s" if v is not None else "  N/A"
    lines.append(f"    Mean   |start delta| : {_fmt(bnd['mean_abs_start_delta'])}")
    lines.append(f"    Median |start delta| : {_fmt(bnd['median_abs_start_delta'])}")
    lines.append(f"    Mean   |end delta|   : {_fmt(bnd['mean_abs_end_delta'])}")
    lines.append(f"    Median |end delta|   : {_fmt(bnd['median_abs_end_delta'])}")
    lines.append(f"    Pairs with |delta|>0.5s : {len(bnd['large_deltas'])}")
    lines.append("")

    # Winner
    win = result["winner"]
    acc_str = f"{win['accuracy']:.1%}" if win["accuracy"] is not None else "N/A"
    caveat = " (caveat: raw winner strings)" if win["caveat_raw_strings"] else ""
    lines.append("  Winner Agreement")
    lines.append(f"    Compared : {win['n_compared']}")
    lines.append(f"    Correct  : {win['n_correct']}")
    lines.append(f"    Wrong    : {win['n_wrong']}")
    lines.append(f"    Accuracy : {acc_str}{caveat}")
    lines.append("")

    # Score
    scr = result["score"]
    scr_acc_str = f"{scr['accuracy']:.1%}" if scr["accuracy"] is not None else "N/A"
    div_str = str(scr["first_divergence_index"]) if scr["first_divergence_index"] is not None else "none"
    lines.append("  Score-string Agreement")
    lines.append(f"    Compared            : {scr['n_compared']}")
    lines.append(f"    Matching            : {scr['n_matching']}")
    lines.append(f"    Accuracy            : {scr_acc_str}")
    lines.append(f"    First divergence at : match #{div_str}")
    lines.append("")

    # Hard examples
    hard = result["hard_examples"]
    lines.append(f"  Hard Examples ({len(hard)} total)")
    if hard:
        col_type = 18
        col_ai = 6
        col_ri = 8
        col_time = 9
        col_detail = 26
        header = (
            f"  {'type':<{col_type}}"
            f"{'auto':>{col_ai}}"
            f"{'reviewed':>{col_ri}}"
            f"{'time(s)':>{col_time}}"
            f"  {'detail':<{col_detail}}"
        )
        lines.append(header)
        lines.append("  " + "-" * (col_type + col_ai + col_ri + col_time + 2 + col_detail))
        for ex in hard:
            ai_s = str(ex["auto_index"]) if ex["auto_index"] is not None else "-"
            ri_s = str(ex["reviewed_index"]) if ex["reviewed_index"] is not None else "-"
            t_s = f"{ex['auto_time']:.2f}" if ex["auto_time"] is not None else "-"
            detail = _compact_detail(ex)
            lines.append(
                f"  {ex['type']:<{col_type}}"
                f"{ai_s:>{col_ai}}"
                f"{ri_s:>{col_ri}}"
                f"{t_s:>{col_time}}"
                f"  {detail:<{col_detail}}"
            )
    lines.append("=" * _SEP_WIDTH)
    lines.append("")
    return "\n".join(lines)


def _compact_detail(ex: dict[str, Any]) -> str:
    """Format the detail dict of a hard example into a short string.

    Args:
        ex: Hard-example dict from ``result["hard_examples"]``.

    Returns:
        Single-line summary string.
    """
    d = ex.get("detail", {})
    t = ex["type"]
    if t == "boundary_shift":
        return f"start={d.get('abs_start_delta', '?'):.3f}s end={d.get('abs_end_delta', '?'):.3f}s"
    if t == "winner_flip":
        return f"auto={d.get('auto_winner')} rev={d.get('reviewed_winner')}"
    if t in ("false_positive", "missed_rally"):
        return f"score={d.get('score_at_start', '?')}"
    return str(d)


def _render_batch(result: dict[str, Any]) -> str:
    """Render batch diff results as a human-readable summary table.

    Args:
        result: Dict returned by :func:`diff_batch`.

    Returns:
        Multi-line string for stdout.
    """
    lines: list[str] = []
    agg = result["aggregate"]
    lines.append("")
    lines.append("=" * _SEP_WIDTH)
    lines.append("  Re-export Diff  (batch)")
    lines.append("=" * _SEP_WIDTH)
    lines.append(f"  Pairs           : {agg['n_pairs']}")
    lines.append(f"  Unpaired auto   : {len(result['unpaired_auto'])}")
    lines.append(f"  Unpaired reviewed: {len(result['unpaired_reviewed'])}")
    lines.append("")

    lines.append(f"  Rally counts")
    lines.append(f"    Total auto              : {agg['total_auto']}")
    lines.append(f"    Total reviewed          : {agg['total_reviewed']}")
    lines.append(f"    Total matched           : {agg['total_matched']}")
    lines.append(f"    Total false positives   : {agg['total_false_positives']}")
    lines.append(f"    Total missed            : {agg['total_missed']}")
    lines.append("")

    _fmt = lambda v: f"{v:.3f}s" if v is not None else "  N/A"
    lines.append(f"  Boundary (weighted mean across pairs)")
    lines.append(f"    Mean |start delta| : {_fmt(agg['mean_abs_start_delta'])}")
    lines.append(f"    Mean |end delta|   : {_fmt(agg['mean_abs_end_delta'])}")
    lines.append("")

    win_acc = f"{agg['winner_accuracy']:.1%}" if agg["winner_accuracy"] is not None else "N/A"
    scr_acc = f"{agg['score_accuracy']:.1%}" if agg["score_accuracy"] is not None else "N/A"
    lines.append(f"  Overall winner accuracy : {win_acc}")
    lines.append(f"  Overall score accuracy  : {scr_acc}")
    lines.append(f"  Total hard examples     : {agg['total_hard_examples']}")
    lines.append("")

    if result["pairs"]:
        col_v = 30
        col_m = 9
        col_fp = 6
        col_ms = 6
        col_wacc = 9
        header = (
            f"  {'video (basename)':<{col_v}}"
            f"{'matched':>{col_m}}"
            f"{'FP':>{col_fp}}"
            f"{'miss':>{col_ms}}"
            f"{'w_acc':>{col_wacc}}"
        )
        lines.append(header)
        lines.append("  " + "-" * (col_v + col_m + col_fp + col_ms + col_wacc))
        for pair in result["pairs"]:
            vbase = Path(pair["video"]).name if pair["video"] else "-"
            if len(vbase) > col_v:
                vbase = vbase[:col_v - 3] + "..."
            det = pair["detection"]
            wacc = pair["winner"]["accuracy"]
            wacc_s = f"{wacc:.1%}" if wacc is not None else " N/A"
            lines.append(
                f"  {vbase:<{col_v}}"
                f"{pair['n_matched']:>{col_m}}"
                f"{det['n_false_positives']:>{col_fp}}"
                f"{det['n_missed']:>{col_ms}}"
                f"{wacc_s:>{col_wacc}}"
            )

    lines.append("=" * _SEP_WIDTH)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diff_reexport",
        description=(
            "Diff auto-generated and human-reviewed training JSONs to compute "
            "field accuracy, detect hard examples, and track model regression."
        ),
    )

    single = parser.add_argument_group("Single-pair mode")
    single.add_argument(
        "--auto",
        dest="auto_path",
        metavar="PATH",
        type=Path,
        default=None,
        help="Auto-generated .training.json file.",
    )
    single.add_argument(
        "--reviewed",
        dest="reviewed_path",
        metavar="PATH",
        type=Path,
        default=None,
        help="Human-reviewed .training.json file.",
    )

    batch = parser.add_argument_group("Batch mode (pair by video.path)")
    batch.add_argument(
        "--auto-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="Directory of auto-generated .training.json files.",
    )
    batch.add_argument(
        "--reviewed-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="Directory of human-reviewed .training.json files.",
    )

    parser.add_argument(
        "--json",
        dest="json_out",
        metavar="PATH",
        type=Path,
        default=None,
        help="Write full JSON results to this file (table still printed to stdout).",
    )
    parser.add_argument(
        "--iou",
        dest="iou_threshold",
        type=float,
        default=0.5,
        metavar="FLOAT",
        help="IoU threshold for matching auto rallies to reviewed rallies (default: 0.5).",
    )
    parser.add_argument(
        "--include-post-game",
        action="store_true",
        default=False,
        help="Include is_post_game rallies in the diff (excluded by default).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the diff_reexport CLI.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 on success, 1 on argument error).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    batch_mode = args.auto_dir is not None or args.reviewed_dir is not None
    single_mode = args.auto_path is not None or args.reviewed_path is not None

    if batch_mode and single_mode:
        parser.error("Cannot mix --auto/--reviewed with --auto-dir/--reviewed-dir.")
        return 1

    if not batch_mode and not single_mode:
        parser.error(
            "Must supply either --auto + --reviewed, or --auto-dir + --reviewed-dir."
        )
        return 1

    if batch_mode and (args.auto_dir is None or args.reviewed_dir is None):
        parser.error("Both --auto-dir and --reviewed-dir are required for batch mode.")
        return 1

    if single_mode and (args.auto_path is None or args.reviewed_path is None):
        parser.error("Both --auto and --reviewed are required for single-pair mode.")
        return 1

    result = run_diff(
        auto_path=args.auto_path,
        reviewed_path=args.reviewed_path,
        auto_dir=args.auto_dir,
        reviewed_dir=args.reviewed_dir,
        iou_threshold=args.iou_threshold,
        include_post_game=args.include_post_game,
    )

    is_batch = "pairs" in result
    if is_batch:
        print(_render_batch(result))
    else:
        print(_render_single_pair(result))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[diff_reexport] JSON written to {args.json_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
