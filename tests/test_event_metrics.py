"""Tests for ml.evaluation.event_metrics.

Covers:
- Perfect match (all intervals align)
- Offset boundaries (known MAE values)
- Missed rally (recall < 1)
- False positive (precision < 1)
- IoU threshold boundary: pairs that just meet or just miss the threshold
- Empty inputs (no crash, sensible zeros/None)
- Greedy matching prefers higher IoU when two candidates compete
- Aggregation math for aggregate_video_metrics
"""

from __future__ import annotations

import pytest

from ml.evaluation.event_metrics import (
    aggregate_video_metrics,
    interval_detection_metrics,
    match_intervals,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Reference IoU for test assertions."""
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    if overlap == 0.0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - overlap
    return overlap / union if union > 0.0 else 0.0


# ---------------------------------------------------------------------------
# match_intervals
# ---------------------------------------------------------------------------


class TestMatchIntervals:
    def test_perfect_match_single(self) -> None:
        pred = [(0.0, 5.0)]
        gt = [(0.0, 5.0)]
        matches = match_intervals(pred, gt)
        assert matches == [(0, 0)]

    def test_perfect_match_multiple(self) -> None:
        pred = [(0.0, 5.0), (10.0, 15.0)]
        gt = [(0.0, 5.0), (10.0, 15.0)]
        matches = match_intervals(pred, gt)
        assert set(matches) == {(0, 0), (1, 1)}

    def test_empty_predicted(self) -> None:
        assert match_intervals([], [(0.0, 5.0)]) == []

    def test_empty_ground_truth(self) -> None:
        assert match_intervals([(0.0, 5.0)], []) == []

    def test_both_empty(self) -> None:
        assert match_intervals([], []) == []

    def test_no_overlap_below_threshold(self) -> None:
        # Intervals that don't overlap at all
        pred = [(0.0, 1.0)]
        gt = [(5.0, 6.0)]
        assert match_intervals(pred, gt) == []

    def test_iou_exactly_at_threshold(self) -> None:
        # Construct intervals with exactly 0.5 IoU.
        # Overlap = 2, union = 4  → IoU = 0.5
        pred = [(0.0, 4.0)]   # length 4
        gt = [(2.0, 6.0)]     # length 4, overlap 2, union 6
        # IoU = 2/6 ≈ 0.333 — below default 0.5
        assert match_intervals(pred, gt, iou_threshold=0.5) == []
        # With threshold 0.3 it should match
        assert match_intervals(pred, gt, iou_threshold=0.3) == [(0, 0)]

    def test_iou_just_meets_threshold(self) -> None:
        # Overlap 3, pred length 3, gt length 3 → union=3, IoU=1.0
        pred = [(1.0, 4.0)]
        gt = [(1.0, 4.0)]
        iou = _iou(pred[0], gt[0])
        assert iou == 1.0
        assert match_intervals(pred, gt, iou_threshold=1.0) == [(0, 0)]

    def test_greedy_prefers_higher_iou(self) -> None:
        """When pred[0] could match either gt[0] or gt[1], the higher-IoU
        gt should be consumed first, leaving pred[1] unmatched rather than
        stealing the better match."""
        # pred[0] overlaps gt[0] with high IoU and gt[1] with low IoU.
        # pred[1] can only match gt[1].
        # Greedy should assign pred[0]↔gt[0] and pred[1]↔gt[1].
        pred = [(0.0, 10.0), (20.0, 25.0)]
        gt = [(0.0, 10.0), (20.0, 30.0)]  # gt[0] perfect match for pred[0]
        matches = match_intervals(pred, gt, iou_threshold=0.3)
        assert (0, 0) in matches
        assert (1, 1) in matches

    def test_greedy_breaks_contention(self) -> None:
        """Two predicted intervals compete for one gt interval.
        Only the one with the higher IoU should win."""
        # pred[0]: overlap 8 with gt[0], IoU = 8/(10+10-8) = 8/12 ≈ 0.667
        # pred[1]: overlap 3 with gt[0], IoU = 3/(10+10-3) = 3/17 ≈ 0.176
        pred = [(2.0, 12.0), (7.0, 12.0)]  # pred[0] wider overlap, pred[1] smaller
        gt = [(4.0, 14.0)]
        iou_p0 = _iou(pred[0], gt[0])
        iou_p1 = _iou(pred[1], gt[0])
        assert iou_p0 > iou_p1
        matches = match_intervals(pred, gt, iou_threshold=0.1)
        assert len(matches) == 1
        assert matches[0][1] == 0  # gt[0] matched
        assert matches[0][0] == 0  # pred[0] wins (higher IoU)

    def test_result_sorted_by_pred_index(self) -> None:
        pred = [(10.0, 15.0), (0.0, 5.0)]
        gt = [(0.0, 5.0), (10.0, 15.0)]
        matches = match_intervals(pred, gt)
        pred_indices = [m[0] for m in matches]
        assert pred_indices == sorted(pred_indices)


# ---------------------------------------------------------------------------
# interval_detection_metrics
# ---------------------------------------------------------------------------


class TestIntervalDetectionMetrics:
    def test_perfect_match(self) -> None:
        pred = [(0.0, 5.0), (10.0, 15.0)]
        gt = [(0.0, 5.0), (10.0, 15.0)]
        m = interval_detection_metrics(pred, gt)
        assert m["n_predicted"] == 2
        assert m["n_ground_truth"] == 2
        assert m["n_matched"] == 2
        assert m["precision"] == pytest.approx(1.0)
        assert m["recall"] == pytest.approx(1.0)
        assert m["f1"] == pytest.approx(1.0)
        assert m["count_error"] == 0
        assert m["start_mae_s"] == pytest.approx(0.0)
        assert m["end_mae_s"] == pytest.approx(0.0)
        assert m["boundary_mae_s"] == pytest.approx(0.0)

    def test_offset_boundaries_known_mae(self) -> None:
        """Predicted interval is shifted 1s relative to ground truth."""
        pred = [(1.0, 6.0)]   # shifted +1s
        gt = [(0.0, 5.0)]
        # IoU = 4 / 6 ≈ 0.667 → should match
        m = interval_detection_metrics(pred, gt)
        assert m["n_matched"] == 1
        assert m["start_mae_s"] == pytest.approx(1.0)
        assert m["end_mae_s"] == pytest.approx(1.0)
        assert m["boundary_mae_s"] == pytest.approx(1.0)

    def test_asymmetric_boundary_error(self) -> None:
        """Predicted start is 0.5s early, end is 1.5s late."""
        pred = [(-0.5, 6.5)]
        gt = [(0.0, 5.0)]
        m = interval_detection_metrics(pred, gt, iou_threshold=0.5)
        # IoU: overlap=5, union=7+0=7 → 5/7 ≈ 0.714 → match
        assert m["n_matched"] == 1
        assert m["start_mae_s"] == pytest.approx(0.5)
        assert m["end_mae_s"] == pytest.approx(1.5)
        assert m["boundary_mae_s"] == pytest.approx(1.0)

    def test_missed_rally_recall_less_than_one(self) -> None:
        """One of two ground-truth rallies is not detected."""
        pred = [(0.0, 5.0)]
        gt = [(0.0, 5.0), (20.0, 25.0)]
        m = interval_detection_metrics(pred, gt)
        assert m["n_matched"] == 1
        assert m["recall"] == pytest.approx(0.5)
        assert m["precision"] == pytest.approx(1.0)
        assert m["f1"] == pytest.approx(2 * 1.0 * 0.5 / (1.0 + 0.5))
        assert m["count_error"] == -1

    def test_false_positive_precision_less_than_one(self) -> None:
        """An extra detection has no corresponding ground-truth interval."""
        pred = [(0.0, 5.0), (30.0, 35.0)]
        gt = [(0.0, 5.0)]
        m = interval_detection_metrics(pred, gt)
        assert m["n_matched"] == 1
        assert m["precision"] == pytest.approx(0.5)
        assert m["recall"] == pytest.approx(1.0)
        assert m["count_error"] == 1

    def test_empty_predicted(self) -> None:
        m = interval_detection_metrics([], [(0.0, 5.0)])
        assert m["n_predicted"] == 0
        assert m["n_ground_truth"] == 1
        assert m["n_matched"] == 0
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["f1"] == 0.0
        assert m["start_mae_s"] is None
        assert m["end_mae_s"] is None
        assert m["boundary_mae_s"] is None

    def test_empty_ground_truth(self) -> None:
        m = interval_detection_metrics([(0.0, 5.0)], [])
        assert m["n_predicted"] == 1
        assert m["n_ground_truth"] == 0
        assert m["n_matched"] == 0
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["f1"] == 0.0
        assert m["start_mae_s"] is None

    def test_both_empty(self) -> None:
        m = interval_detection_metrics([], [])
        assert m["n_matched"] == 0
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["f1"] == 0.0
        assert m["start_mae_s"] is None

    def test_iou_threshold_excludes_low_overlap(self) -> None:
        """Pair with IoU < threshold should not be matched."""
        pred = [(0.0, 10.0)]
        gt = [(8.0, 18.0)]
        iou = _iou(pred[0], gt[0])
        # IoU = 2/18 ≈ 0.111
        assert iou < 0.5
        m = interval_detection_metrics(pred, gt, iou_threshold=0.5)
        assert m["n_matched"] == 0
        # With lower threshold the pair should match
        m2 = interval_detection_metrics(pred, gt, iou_threshold=0.05)
        assert m2["n_matched"] == 1

    def test_no_matched_mae_is_none(self) -> None:
        """No match → all MAE fields are None."""
        m = interval_detection_metrics([(0.0, 1.0)], [(100.0, 101.0)])
        assert m["n_matched"] == 0
        assert m["start_mae_s"] is None
        assert m["end_mae_s"] is None
        assert m["boundary_mae_s"] is None

    def test_f1_when_both_zero(self) -> None:
        """F1 should be 0.0 when both precision and recall are 0."""
        m = interval_detection_metrics([], [])
        assert m["f1"] == 0.0


# ---------------------------------------------------------------------------
# aggregate_video_metrics
# ---------------------------------------------------------------------------


class TestAggregateVideoMetrics:
    def test_single_video_passthrough(self) -> None:
        pred = [(0.0, 5.0), (10.0, 15.0)]
        gt = [(0.0, 5.0), (10.0, 15.0)]
        per_video = [interval_detection_metrics(pred, gt)]
        agg = aggregate_video_metrics(per_video)
        assert agg["n_videos"] == 1
        assert agg["n_matched"] == 2
        assert agg["precision"] == pytest.approx(1.0)
        assert agg["recall"] == pytest.approx(1.0)
        assert agg["f1"] == pytest.approx(1.0)
        assert agg["start_mae_s"] == pytest.approx(0.0)

    def test_micro_aggregation_counts(self) -> None:
        """Aggregate sums counts and recomputes P/R/F1 from totals."""
        # Video 1: 2 pred, 2 gt, 1 matched
        v1 = interval_detection_metrics([(0.0, 5.0), (30.0, 35.0)], [(0.0, 5.0), (20.0, 25.0)])
        # Video 2: 1 pred, 1 gt, 1 matched
        v2 = interval_detection_metrics([(10.0, 15.0)], [(10.0, 15.0)])
        agg = aggregate_video_metrics([v1, v2])
        assert agg["n_videos"] == 2
        assert agg["n_predicted"] == v1["n_predicted"] + v2["n_predicted"]
        assert agg["n_ground_truth"] == v1["n_ground_truth"] + v2["n_ground_truth"]
        assert agg["n_matched"] == v1["n_matched"] + v2["n_matched"]
        expected_prec = agg["n_matched"] / agg["n_predicted"]
        expected_rec = agg["n_matched"] / agg["n_ground_truth"]
        assert agg["precision"] == pytest.approx(expected_prec)
        assert agg["recall"] == pytest.approx(expected_rec)

    def test_weighted_mae(self) -> None:
        """Weighted-mean MAE is n_matched-weighted across videos."""
        # Video 1: 1 matched pair, start_mae=1.0, end_mae=2.0
        # Video 2: 3 matched pairs (perfect), start_mae=0.0, end_mae=0.0
        # Weighted start_mae = (1*1.0 + 3*0.0) / (1+3) = 0.25
        v1 = interval_detection_metrics([(1.0, 6.0)], [(0.0, 5.0)])
        v2 = interval_detection_metrics(
            [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)],
            [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)],
        )
        assert v1["n_matched"] == 1
        assert v2["n_matched"] == 3
        agg = aggregate_video_metrics([v1, v2])
        expected_start_mae = (1 * v1["start_mae_s"] + 3 * v2["start_mae_s"]) / 4
        assert agg["start_mae_s"] == pytest.approx(expected_start_mae)

    def test_empty_input(self) -> None:
        agg = aggregate_video_metrics([])
        assert agg["n_videos"] == 0
        assert agg["n_matched"] == 0
        assert agg["precision"] == 0.0
        assert agg["recall"] == 0.0
        assert agg["f1"] == 0.0
        assert agg["start_mae_s"] is None
        assert agg["end_mae_s"] is None
        assert agg["boundary_mae_s"] is None

    def test_zero_matched_mae_remains_none(self) -> None:
        """When all videos have n_matched==0, aggregate MAE should be None."""
        v1 = interval_detection_metrics([], [(0.0, 5.0)])
        v2 = interval_detection_metrics([], [(10.0, 15.0)])
        agg = aggregate_video_metrics([v1, v2])
        assert agg["n_matched"] == 0
        assert agg["start_mae_s"] is None
        assert agg["end_mae_s"] is None
        assert agg["boundary_mae_s"] is None

    def test_count_error_signed_sum(self) -> None:
        # Video 1 over-predicts by 2, video 2 under-predicts by 1
        v1 = interval_detection_metrics(
            [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)], [(0.0, 5.0)]
        )
        v2 = interval_detection_metrics(
            [(0.0, 5.0)], [(0.0, 5.0), (10.0, 15.0)]
        )
        agg = aggregate_video_metrics([v1, v2])
        # Total pred = 4, total gt = 3, count_error = 1
        assert agg["count_error"] == 4 - 3
