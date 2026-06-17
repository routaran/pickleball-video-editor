"""Interval-level detection metrics for Stage-1 audio rally detection.

This module provides pure functions that evaluate the quality of rally-boundary
predictions against ground-truth interval lists.  All functions are torch-free
and operate on plain Python lists.

Typical usage::

    from ml.evaluation.event_metrics import interval_detection_metrics, aggregate_video_metrics

    per_video = []
    for video in held_out_videos:
        m = interval_detection_metrics(predicted_intervals[video], gt_intervals[video])
        per_video.append(m)

    agg = aggregate_video_metrics(per_video)
    print(f"Precision={agg['precision']:.1%}  Recall={agg['recall']:.1%}  F1={agg['f1']:.1%}")

**Design notes on MAE=None:**
When ``n_matched == 0`` there are no aligned pairs from which to compute
boundary errors, so ``start_mae_s``, ``end_mae_s``, and ``boundary_mae_s``
are returned as ``None`` rather than 0.0.  Callers must guard against ``None``
before arithmetic.  ``aggregate_video_metrics`` handles this by weighting MAEs
by ``n_matched``; a video with zero matches contributes nothing to the
aggregate boundary error.
"""

__all__ = [
    "match_intervals",
    "interval_detection_metrics",
    "aggregate_video_metrics",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iou_1d(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Compute Intersection-over-Union for two 1-D intervals.

    Args:
        a: First interval as ``(start_s, end_s)``.
        b: Second interval as ``(start_s, end_s)``.

    Returns:
        IoU in ``[0.0, 1.0]``; returns ``0.0`` when there is no overlap or
        when the union is non-positive.
    """
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    if overlap == 0.0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - overlap
    if union <= 0.0:
        return 0.0
    return overlap / union


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_intervals(
    predicted: list[tuple[float, float]],
    ground_truth: list[tuple[float, float]],
    iou_threshold: float = 0.5,
) -> list[tuple[int, int]]:
    """Greedy one-to-one matching of predicted intervals to ground-truth intervals.

    Matching proceeds by sorting all (predicted, ground_truth) candidate pairs
    by descending IoU and then greedily assigning pairs, ensuring that each
    predicted interval and each ground-truth interval appears in at most one
    matched pair.  This follows the standard object-detection matching protocol
    (as used in PASCAL VOC / COCO metrics).

    Args:
        predicted: Detected intervals as ``list[tuple[start_s, end_s]]``.
        ground_truth: Reference intervals as ``list[tuple[start_s, end_s]]``.
        iou_threshold: Minimum IoU required for a pair to be considered a match
            (default: 0.5).

    Returns:
        List of ``(predicted_index, ground_truth_index)`` pairs in ascending
        order of ``predicted_index``.  Returns an empty list when either input
        is empty or when no pair exceeds ``iou_threshold``.
    """
    if not predicted or not ground_truth:
        return []

    # Build all candidate pairs that clear the IoU threshold.
    candidates: list[tuple[float, int, int]] = []
    for pi, p in enumerate(predicted):
        for gi, g in enumerate(ground_truth):
            iou = _iou_1d(p, g)
            if iou >= iou_threshold:
                candidates.append((iou, pi, gi))

    # Sort by descending IoU so highest-quality matches win contention.
    candidates.sort(key=lambda x: -x[0])

    matched_pred: set[int] = set()
    matched_gt: set[int] = set()
    matches: list[tuple[int, int]] = []

    for _iou, pi, gi in candidates:
        if pi in matched_pred or gi in matched_gt:
            continue
        matches.append((pi, gi))
        matched_pred.add(pi)
        matched_gt.add(gi)

    # Return in ascending predicted-index order for determinism.
    matches.sort(key=lambda x: x[0])
    return matches


def interval_detection_metrics(
    predicted: list[tuple[float, float]],
    ground_truth: list[tuple[float, float]],
    iou_threshold: float = 0.5,
) -> dict:
    """Compute detection-style precision/recall/F1, boundary error, and failure-mode metrics.

    Metrics are computed over the matched subset returned by
    :func:`match_intervals`.  Boundary-error MAEs are ``None`` when there are
    no matched pairs (see module docstring).

    Failure-mode metrics (merge count, over-segmentation count, and
    false-positive active seconds) are always present in the returned dict.

    Args:
        predicted: Detected intervals as ``list[tuple[start_s, end_s]]``.
        ground_truth: Reference intervals as ``list[tuple[start_s, end_s]]``.
        iou_threshold: IoU threshold forwarded to :func:`match_intervals`
            (default: 0.5).

    Returns:
        Dictionary with the following keys:

        - ``"n_predicted"``      — number of predicted intervals.
        - ``"n_ground_truth"``   — number of ground-truth intervals.
        - ``"n_matched"``        — number of matched pairs.
        - ``"precision"``        — ``n_matched / n_predicted`` (0.0 if none predicted).
        - ``"recall"``           — ``n_matched / n_ground_truth`` (0.0 if none in GT).
        - ``"f1"``               — harmonic mean of precision and recall (0.0 if both 0).
        - ``"count_error"``      — ``n_predicted - n_ground_truth`` (signed).
        - ``"start_mae_s"``      — mean |pred_start − gt_start| over matched pairs, or
          ``None`` when ``n_matched == 0``.
        - ``"end_mae_s"``        — mean |pred_end − gt_end| over matched pairs, or
          ``None`` when ``n_matched == 0``.
        - ``"boundary_mae_s"``   — mean of ``start_mae_s`` and ``end_mae_s``, or
          ``None`` when ``n_matched == 0``.
        - ``"n_merges"``         — number of predicted intervals that overlap
          more than one ground-truth interval (under-segmentation).
        - ``"n_over_segs"``      — number of ground-truth intervals covered by
          more than one predicted interval (over-segmentation).
        - ``"fp_active_seconds"``— total seconds of predicted intervals that
          fall entirely within true dead time (no overlap with any GT interval).
    """
    n_predicted = len(predicted)
    n_ground_truth = len(ground_truth)

    matches = match_intervals(predicted, ground_truth, iou_threshold)
    n_matched = len(matches)

    # Precision / recall
    precision = n_matched / n_predicted if n_predicted > 0 else 0.0
    recall = n_matched / n_ground_truth if n_ground_truth > 0 else 0.0

    # F1
    if precision + recall > 0.0:
        f1 = 2.0 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    count_error = n_predicted - n_ground_truth

    # Boundary errors — only over matched pairs
    start_mae_s: float | None = None
    end_mae_s: float | None = None
    boundary_mae_s: float | None = None

    if n_matched > 0:
        start_errors: list[float] = []
        end_errors: list[float] = []
        for pi, gi in matches:
            start_errors.append(abs(predicted[pi][0] - ground_truth[gi][0]))
            end_errors.append(abs(predicted[pi][1] - ground_truth[gi][1]))
        start_mae_s = sum(start_errors) / n_matched
        end_mae_s = sum(end_errors) / n_matched
        boundary_mae_s = (start_mae_s + end_mae_s) / 2.0

    # ------------------------------------------------------------------
    # Failure-mode metrics
    # ------------------------------------------------------------------

    # n_merges: predicted intervals that overlap (IoU > 0) more than one GT.
    # Uses raw overlap (any positive intersection), not the iou_threshold, so
    # that a prediction straddling two GT rallies is counted even if it does
    # not clear the match threshold for either.
    n_merges = 0
    for p in predicted:
        gt_overlaps = sum(
            1 for g in ground_truth if min(p[1], g[1]) - max(p[0], g[0]) > 0.0
        )
        if gt_overlaps > 1:
            n_merges += 1

    # n_over_segs: GT intervals covered by more than one predicted interval.
    n_over_segs = 0
    for g in ground_truth:
        pred_overlaps = sum(
            1 for p in predicted if min(p[1], g[1]) - max(p[0], g[0]) > 0.0
        )
        if pred_overlaps > 1:
            n_over_segs += 1

    # fp_active_seconds: duration of predicted intervals with zero overlap
    # with any GT interval (pure false positives during dead time).
    fp_active_seconds = 0.0
    for p in predicted:
        has_any_overlap = any(
            min(p[1], g[1]) - max(p[0], g[0]) > 0.0 for g in ground_truth
        )
        if not has_any_overlap:
            fp_active_seconds += p[1] - p[0]

    return {
        "n_predicted": n_predicted,
        "n_ground_truth": n_ground_truth,
        "n_matched": n_matched,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "count_error": count_error,
        "start_mae_s": start_mae_s,
        "end_mae_s": end_mae_s,
        "boundary_mae_s": boundary_mae_s,
        "n_merges": n_merges,
        "n_over_segs": n_over_segs,
        "fp_active_seconds": fp_active_seconds,
    }


def aggregate_video_metrics(per_video: list[dict]) -> dict:
    """Micro-aggregate per-video metrics into a single summary.

    Counts are summed across all videos and precision/recall/F1 are
    recomputed from the aggregated counts (micro-averaging).  Boundary MAEs
    are computed as a weighted mean where the weight for each video is its
    ``n_matched`` count; videos with zero matches do not contribute.

    Args:
        per_video: List of per-video metric dicts as returned by
            :func:`interval_detection_metrics`.

    Returns:
        Aggregated metrics dict with the same keys as
        :func:`interval_detection_metrics` plus ``"n_videos"``.
        Boundary MAEs are ``None`` when the total ``n_matched`` across all
        videos is zero.  The failure-mode counts (``n_merges``,
        ``n_over_segs``, ``fp_active_seconds``) are summed across videos.
    """
    if not per_video:
        return {
            "n_videos": 0,
            "n_predicted": 0,
            "n_ground_truth": 0,
            "n_matched": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "count_error": 0,
            "start_mae_s": None,
            "end_mae_s": None,
            "boundary_mae_s": None,
            "n_merges": 0,
            "n_over_segs": 0,
            "fp_active_seconds": 0.0,
        }

    total_predicted = sum(v["n_predicted"] for v in per_video)
    total_ground_truth = sum(v["n_ground_truth"] for v in per_video)
    total_matched = sum(v["n_matched"] for v in per_video)

    precision = total_matched / total_predicted if total_predicted > 0 else 0.0
    recall = total_matched / total_ground_truth if total_ground_truth > 0 else 0.0

    if precision + recall > 0.0:
        f1 = 2.0 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    count_error = total_predicted - total_ground_truth

    # Weighted-mean MAEs; videos with n_matched == 0 or None MAE are excluded.
    start_mae_s: float | None = None
    end_mae_s: float | None = None
    boundary_mae_s: float | None = None

    if total_matched > 0:
        weighted_start = 0.0
        weighted_end = 0.0
        for v in per_video:
            nm = v["n_matched"]
            s_mae = v.get("start_mae_s")
            e_mae = v.get("end_mae_s")
            if nm > 0 and s_mae is not None and e_mae is not None:
                weighted_start += nm * s_mae
                weighted_end += nm * e_mae
        start_mae_s = weighted_start / total_matched
        end_mae_s = weighted_end / total_matched
        boundary_mae_s = (start_mae_s + end_mae_s) / 2.0

    # Sum failure-mode counts across all videos (default to 0 for older dicts
    # that pre-date these fields so callers stay backwards-compatible).
    total_merges = sum(v.get("n_merges", 0) for v in per_video)
    total_over_segs = sum(v.get("n_over_segs", 0) for v in per_video)
    total_fp_active = sum(v.get("fp_active_seconds", 0.0) for v in per_video)

    return {
        "n_videos": len(per_video),
        "n_predicted": total_predicted,
        "n_ground_truth": total_ground_truth,
        "n_matched": total_matched,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "count_error": count_error,
        "start_mae_s": start_mae_s,
        "end_mae_s": end_mae_s,
        "boundary_mae_s": boundary_mae_s,
        "n_merges": total_merges,
        "n_over_segs": total_over_segs,
        "fp_active_seconds": total_fp_active,
    }
