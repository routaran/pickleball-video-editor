"""Tests for footage_confusion() and cut_deltas().

Coverage:
- footage_confusion: exact match, partial overlap, fully-missed rally,
  over/under-prediction, empty inputs, unsorted + overlapping inputs,
  touching intervals, total_seconds passthrough, multi-rally scenarios.
- cut_deltas: no change, removed segments, added segments, both, empty
  baseline, empty candidate.
- write_delta_report: smoke-test with and without GT.
- get_ffmpeg_commands: verify command strings are well-formed.

All tests are pure (no I/O, no model imports, no ffmpeg execution).
"""

from __future__ import annotations

import json

import pytest

from ml.evaluation.event_metrics import footage_confusion
from ml.tools.render_cut_delta import (
    cut_deltas,
    get_ffmpeg_commands,
    write_delta_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approx(val: float, abs_tol: float = 1e-9) -> pytest.ApproxBase:
    return pytest.approx(val, abs=abs_tol)


# ===========================================================================
# footage_confusion
# ===========================================================================


class TestFootageConfusionExactMatch:
    """pred == gt — perfect recall, zero junk."""

    def test_single_rally(self) -> None:
        pred = [(10.0, 40.0)]
        gt = [(10.0, 40.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(30.0)
        assert fc["pred_rally_seconds"] == _approx(30.0)
        assert fc["kept_rally_seconds"] == _approx(30.0)
        assert fc["missed_rally_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["junk_fraction"] == _approx(0.0)
        assert fc["net_added_seconds"] == _approx(0.0)
        assert fc["net_dropped_seconds"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 0

    def test_two_rallies(self) -> None:
        pred = [(10.0, 30.0), (60.0, 90.0)]
        gt = [(10.0, 30.0), (60.0, 90.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(50.0)  # 20 + 30
        assert fc["kept_rally_seconds"] == _approx(50.0)
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 0


class TestFootageConfusionPartialOverlap:
    """Pred starts later than GT — shared middle, head lost."""

    def test_head_clipped(self) -> None:
        # GT: [0, 20], pred: [5, 20] → kept=15, missed=5, junk=0
        pred = [(5.0, 20.0)]
        gt = [(0.0, 20.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(20.0)
        assert fc["pred_rally_seconds"] == _approx(15.0)
        assert fc["kept_rally_seconds"] == _approx(15.0)
        assert fc["missed_rally_seconds"] == _approx(5.0)
        assert fc["footage_recall"] == _approx(0.75)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["junk_fraction"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 0

    def test_tail_clipped(self) -> None:
        # GT: [0, 20], pred: [0, 15] → kept=15, missed=5, junk=0
        pred = [(0.0, 15.0)]
        gt = [(0.0, 20.0)]
        fc = footage_confusion(pred, gt)
        assert fc["kept_rally_seconds"] == _approx(15.0)
        assert fc["missed_rally_seconds"] == _approx(5.0)
        assert fc["footage_recall"] == _approx(0.75)
        assert fc["junk_seconds"] == _approx(0.0)

    def test_both_clipped(self) -> None:
        # GT: [0, 20], pred: [5, 15] → kept=10, missed=10, junk=0
        pred = [(5.0, 15.0)]
        gt = [(0.0, 20.0)]
        fc = footage_confusion(pred, gt)
        assert fc["kept_rally_seconds"] == _approx(10.0)
        assert fc["missed_rally_seconds"] == _approx(10.0)
        assert fc["footage_recall"] == _approx(0.5)
        assert fc["junk_seconds"] == _approx(0.0)


class TestFootageConfusionFullyMissedRally:
    """A GT interval has zero or near-zero overlap with pred."""

    def test_one_of_two_rallies_missed(self) -> None:
        pred = [(60.0, 90.0)]
        gt = [(10.0, 30.0), (60.0, 90.0)]
        fc = footage_confusion(pred, gt)
        # GT total = 50s; pred covers only (60,90) = 30s
        assert fc["true_rally_seconds"] == _approx(50.0)
        assert fc["kept_rally_seconds"] == _approx(30.0)
        assert fc["missed_rally_seconds"] == _approx(20.0)
        assert fc["footage_recall"] == _approx(30.0 / 50.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 1

    def test_all_rallies_missed(self) -> None:
        pred = [(200.0, 210.0)]  # completely off-timeline
        gt = [(10.0, 30.0), (60.0, 90.0)]
        fc = footage_confusion(pred, gt)
        assert fc["kept_rally_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(0.0)
        assert fc["junk_seconds"] == _approx(10.0)
        assert fc["n_fully_missed_rallies"] == 2

    def test_tiny_overlap_is_not_fully_missed(self) -> None:
        # 0.005s overlap — above the 1 ms threshold
        pred = [(29.995, 35.0)]
        gt = [(10.0, 30.0)]
        fc = footage_confusion(pred, gt)
        assert fc["n_fully_missed_rallies"] == 0
        assert fc["kept_rally_seconds"] == pytest.approx(0.005, abs=1e-9)

    def test_sub_millisecond_overlap_counts_as_fully_missed(self) -> None:
        # 0.0005s overlap — below the 1 ms threshold
        pred = [(29.9995, 35.0)]
        gt = [(10.0, 30.0)]
        fc = footage_confusion(pred, gt)
        assert fc["n_fully_missed_rallies"] == 1


class TestFootageConfusionOverPrediction:
    """Pred covers more than GT — junk time introduced."""

    def test_pred_extends_beyond_gt(self) -> None:
        # GT: [10, 30], pred: [0, 40] → kept=20, junk=20
        pred = [(0.0, 40.0)]
        gt = [(10.0, 30.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(20.0)
        assert fc["pred_rally_seconds"] == _approx(40.0)
        assert fc["kept_rally_seconds"] == _approx(20.0)
        assert fc["missed_rally_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_seconds"] == _approx(20.0)
        assert fc["junk_fraction"] == _approx(0.5)
        assert fc["net_added_seconds"] == _approx(20.0)
        assert fc["net_dropped_seconds"] == _approx(-20.0)

    def test_pred_spans_dead_time_between_rallies(self) -> None:
        # Two GT rallies with 20s gap; pred merges them into one.
        pred = [(0.0, 60.0)]
        gt = [(0.0, 20.0), (40.0, 60.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(40.0)
        assert fc["kept_rally_seconds"] == _approx(40.0)
        assert fc["junk_seconds"] == _approx(20.0)  # the 20s gap kept as junk
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_fraction"] == _approx(20.0 / 60.0)
        assert fc["n_fully_missed_rallies"] == 0


class TestFootageConfusionUnderPrediction:
    """Pred covers less than GT — footage missed."""

    def test_pred_covers_half(self) -> None:
        pred = [(0.0, 10.0)]
        gt = [(0.0, 20.0)]
        fc = footage_confusion(pred, gt)
        assert fc["footage_recall"] == _approx(0.5)
        assert fc["missed_rally_seconds"] == _approx(10.0)
        assert fc["net_dropped_seconds"] == _approx(10.0)
        assert fc["net_added_seconds"] == _approx(-10.0)


class TestFootageConfusionEmptyInputs:
    """Edge cases: empty pred or GT."""

    def test_empty_pred(self) -> None:
        gt = [(10.0, 30.0), (60.0, 90.0)]
        fc = footage_confusion([], gt)
        assert fc["pred_rally_seconds"] == _approx(0.0)
        assert fc["kept_rally_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(0.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["junk_fraction"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 2

    def test_empty_gt(self) -> None:
        pred = [(10.0, 30.0)]
        fc = footage_confusion(pred, [])
        assert fc["true_rally_seconds"] == _approx(0.0)
        assert fc["kept_rally_seconds"] == _approx(0.0)
        # Vacuously perfect recall: nothing to miss
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_seconds"] == _approx(20.0)
        assert fc["junk_fraction"] == _approx(1.0)
        assert fc["n_fully_missed_rallies"] == 0

    def test_both_empty(self) -> None:
        fc = footage_confusion([], [])
        assert fc["true_rally_seconds"] == _approx(0.0)
        assert fc["pred_rally_seconds"] == _approx(0.0)
        assert fc["kept_rally_seconds"] == _approx(0.0)
        assert fc["missed_rally_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(1.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["junk_fraction"] == _approx(0.0)
        assert fc["net_added_seconds"] == _approx(0.0)
        assert fc["net_dropped_seconds"] == _approx(0.0)
        assert fc["n_fully_missed_rallies"] == 0


class TestFootageConfusionUnsortedInput:
    """Out-of-order input should produce the same result as sorted input."""

    def test_unsorted_pred(self) -> None:
        gt = [(0.0, 10.0), (20.0, 30.0)]
        pred_sorted = [(0.0, 10.0), (20.0, 30.0)]
        pred_unsorted = [(20.0, 30.0), (0.0, 10.0)]
        fc_s = footage_confusion(pred_sorted, gt)
        fc_u = footage_confusion(pred_unsorted, gt)
        assert fc_s["kept_rally_seconds"] == _approx(fc_u["kept_rally_seconds"])
        assert fc_s["footage_recall"] == _approx(fc_u["footage_recall"])
        assert fc_s["n_fully_missed_rallies"] == fc_u["n_fully_missed_rallies"]

    def test_unsorted_gt(self) -> None:
        pred = [(0.0, 10.0)]
        gt_sorted = [(0.0, 10.0), (20.0, 30.0)]
        gt_unsorted = [(20.0, 30.0), (0.0, 10.0)]
        fc_s = footage_confusion(pred, gt_sorted)
        fc_u = footage_confusion(pred, gt_unsorted)
        assert fc_s["kept_rally_seconds"] == _approx(fc_u["kept_rally_seconds"])
        assert fc_s["n_fully_missed_rallies"] == fc_u["n_fully_missed_rallies"]


class TestFootageConfusionOverlappingInputs:
    """Overlapping segments in input must be merged before arithmetic."""

    def test_overlapping_pred_merged(self) -> None:
        # pred: [(0,10), (5,15)] → merged → (0,15), so pred_rally=15, not 20
        pred = [(0.0, 10.0), (5.0, 15.0)]
        gt = [(0.0, 15.0)]
        fc = footage_confusion(pred, gt)
        assert fc["pred_rally_seconds"] == _approx(15.0)
        assert fc["kept_rally_seconds"] == _approx(15.0)
        assert fc["junk_seconds"] == _approx(0.0)

    def test_overlapping_gt_merged(self) -> None:
        # gt: [(0,10), (5,15)] → merged → (0,15), so true_rally=15
        pred = [(0.0, 15.0)]
        gt = [(0.0, 10.0), (5.0, 15.0)]
        fc = footage_confusion(pred, gt)
        assert fc["true_rally_seconds"] == _approx(15.0)
        assert fc["kept_rally_seconds"] == _approx(15.0)
        assert fc["footage_recall"] == _approx(1.0)

    def test_touching_intervals_merged(self) -> None:
        # Touching intervals (share endpoint) should merge.
        pred = [(0.0, 10.0), (10.0, 20.0)]  # touching at 10s
        gt = [(0.0, 20.0)]
        fc = footage_confusion(pred, gt)
        assert fc["pred_rally_seconds"] == _approx(20.0)
        assert fc["kept_rally_seconds"] == _approx(20.0)
        assert fc["junk_seconds"] == _approx(0.0)
        assert fc["footage_recall"] == _approx(1.0)


class TestFootageConfusionTotalSeconds:
    """total_seconds is passed through when supplied."""

    def test_total_seconds_present_when_supplied(self) -> None:
        fc = footage_confusion([(0.0, 10.0)], [(0.0, 10.0)], total_seconds=120.0)
        assert "total_seconds" in fc
        assert fc["total_seconds"] == _approx(120.0)

    def test_total_seconds_absent_when_not_supplied(self) -> None:
        fc = footage_confusion([(0.0, 10.0)], [(0.0, 10.0)])
        assert "total_seconds" not in fc


class TestFootageConfusionMultiRallyScenario:
    """Complex multi-rally scenario exercising all metrics together."""

    def test_three_gt_one_missed_one_partial_one_exact(self) -> None:
        # GT:   [(0,20), (40,70), (100,120)]  → 20+30+20 = 70s
        # pred: [(5,20), (40,70), (200,210)]
        #   → rally 1 partial (kept=15, missed=5)
        #   → rally 2 exact   (kept=30)
        #   → rally 3 fully missed
        #   → junk 10s from (200,210)
        gt = [(0.0, 20.0), (40.0, 70.0), (100.0, 120.0)]
        pred = [(5.0, 20.0), (40.0, 70.0), (200.0, 210.0)]
        fc = footage_confusion(pred, gt)

        assert fc["true_rally_seconds"] == _approx(70.0)
        assert fc["pred_rally_seconds"] == _approx(15.0 + 30.0 + 10.0)  # 55s
        assert fc["kept_rally_seconds"] == _approx(15.0 + 30.0)  # 45s
        assert fc["missed_rally_seconds"] == _approx(5.0 + 20.0)  # 25s
        assert fc["footage_recall"] == _approx(45.0 / 70.0)
        assert fc["junk_seconds"] == _approx(10.0)
        assert fc["junk_fraction"] == _approx(10.0 / 55.0)
        assert fc["n_fully_missed_rallies"] == 1  # only (100,120) fully missed

    def test_identity_kept_plus_missed_equals_true(self) -> None:
        """kept + missed == true always."""
        gt = [(0.0, 30.0), (50.0, 90.0), (110.0, 140.0)]
        pred = [(5.0, 28.0), (45.0, 95.0)]
        fc = footage_confusion(pred, gt)
        assert (fc["kept_rally_seconds"] + fc["missed_rally_seconds"]) == pytest.approx(
            fc["true_rally_seconds"], abs=1e-9
        )

    def test_identity_kept_plus_junk_equals_pred(self) -> None:
        """kept + junk == pred always."""
        gt = [(0.0, 30.0), (50.0, 90.0), (110.0, 140.0)]
        pred = [(5.0, 28.0), (45.0, 95.0)]
        fc = footage_confusion(pred, gt)
        assert (fc["kept_rally_seconds"] + fc["junk_seconds"]) == pytest.approx(
            fc["pred_rally_seconds"], abs=1e-9
        )

    def test_net_added_plus_net_dropped_is_zero(self) -> None:
        """net_added + net_dropped == 0 (they are negations of each other)."""
        gt = [(0.0, 30.0), (60.0, 90.0)]
        pred = [(5.0, 25.0), (55.0, 95.0)]
        fc = footage_confusion(pred, gt)
        assert (fc["net_added_seconds"] + fc["net_dropped_seconds"]) == pytest.approx(
            0.0, abs=1e-9
        )


# ===========================================================================
# cut_deltas
# ===========================================================================


class TestCutDeltasNoChange:
    """Baseline == candidate → no deltas."""

    def test_identical_lists(self) -> None:
        ivs = [(10.0, 30.0), (60.0, 90.0)]
        result = cut_deltas(ivs, ivs)
        assert result["removed"] == []
        assert result["added"] == []

    def test_empty_lists(self) -> None:
        result = cut_deltas([], [])
        assert result["removed"] == []
        assert result["added"] == []


class TestCutDeltasRemoved:
    """Candidate removes some content from baseline."""

    def test_full_segment_removed(self) -> None:
        baseline = [(10.0, 30.0), (60.0, 90.0)]
        candidate = [(60.0, 90.0)]  # first rally vetoed
        result = cut_deltas(baseline, candidate)
        assert len(result["removed"]) == 1
        s, e, d = result["removed"][0]
        assert s == pytest.approx(10.0)
        assert e == pytest.approx(30.0)
        assert d == pytest.approx(20.0)
        assert result["added"] == []

    def test_partial_segment_removed(self) -> None:
        # Baseline: (0, 30), candidate: (10, 30) → removed (0, 10)
        baseline = [(0.0, 30.0)]
        candidate = [(10.0, 30.0)]
        result = cut_deltas(baseline, candidate)
        assert len(result["removed"]) == 1
        s, e, d = result["removed"][0]
        assert s == pytest.approx(0.0)
        assert e == pytest.approx(10.0)
        assert d == pytest.approx(10.0)

    def test_internal_gap_removed(self) -> None:
        # Baseline: (0, 40), candidate: (0, 15) + (25, 40) → removed (15, 25)
        baseline = [(0.0, 40.0)]
        candidate = [(0.0, 15.0), (25.0, 40.0)]
        result = cut_deltas(baseline, candidate)
        assert len(result["removed"]) == 1
        s, e, d = result["removed"][0]
        assert s == pytest.approx(15.0)
        assert e == pytest.approx(25.0)
        assert d == pytest.approx(10.0)
        assert result["added"] == []


class TestCutDeltasAdded:
    """Candidate adds content not in baseline."""

    def test_full_segment_added(self) -> None:
        baseline = [(60.0, 90.0)]
        candidate = [(10.0, 30.0), (60.0, 90.0)]  # fusion sustained (10, 30)
        result = cut_deltas(baseline, candidate)
        assert result["removed"] == []
        assert len(result["added"]) == 1
        s, e, d = result["added"][0]
        assert s == pytest.approx(10.0)
        assert e == pytest.approx(30.0)
        assert d == pytest.approx(20.0)

    def test_tail_extension_added(self) -> None:
        baseline = [(0.0, 20.0)]
        candidate = [(0.0, 30.0)]  # fusion extended by 10s
        result = cut_deltas(baseline, candidate)
        assert result["removed"] == []
        assert len(result["added"]) == 1
        s, e, d = result["added"][0]
        assert s == pytest.approx(20.0)
        assert e == pytest.approx(30.0)
        assert d == pytest.approx(10.0)


class TestCutDeltasBoth:
    """Candidate both removes and adds content."""

    def test_shift_right(self) -> None:
        # Baseline: (0, 20), candidate: (5, 25) → removed (0,5), added (20,25)
        baseline = [(0.0, 20.0)]
        candidate = [(5.0, 25.0)]
        result = cut_deltas(baseline, candidate)
        assert len(result["removed"]) == 1
        assert len(result["added"]) == 1
        rs, re, rd = result["removed"][0]
        assert rs == pytest.approx(0.0)
        assert re == pytest.approx(5.0)
        assert rd == pytest.approx(5.0)
        as_, ae, ad = result["added"][0]
        assert as_ == pytest.approx(20.0)
        assert ae == pytest.approx(25.0)
        assert ad == pytest.approx(5.0)

    def test_multi_segment_mixed(self) -> None:
        # Baseline: [(0,10), (20,30)], candidate: [(5,25)]
        # removed = (0,5) + (25,30); added = (10,20)
        baseline = [(0.0, 10.0), (20.0, 30.0)]
        candidate = [(5.0, 25.0)]
        result = cut_deltas(baseline, candidate)
        removed_total = sum(d for _, _, d in result["removed"])
        added_total = sum(d for _, _, d in result["added"])
        assert removed_total == pytest.approx(5.0 + 5.0)
        assert added_total == pytest.approx(10.0)


class TestCutDeltasEdgeCases:
    """Empty baseline / candidate."""

    def test_empty_baseline_all_added(self) -> None:
        baseline: list[tuple[float, float]] = []
        candidate = [(0.0, 10.0), (30.0, 50.0)]
        result = cut_deltas(baseline, candidate)
        assert result["removed"] == []
        added_total = sum(d for _, _, d in result["added"])
        assert added_total == pytest.approx(30.0)

    def test_empty_candidate_all_removed(self) -> None:
        baseline = [(0.0, 10.0), (30.0, 50.0)]
        candidate: list[tuple[float, float]] = []
        result = cut_deltas(baseline, candidate)
        assert result["added"] == []
        removed_total = sum(d for _, _, d in result["removed"])
        assert removed_total == pytest.approx(30.0)

    def test_overlapping_input_merged_before_delta(self) -> None:
        # Overlapping inputs should be merged first so delta is canonical.
        baseline = [(0.0, 10.0), (5.0, 20.0)]  # overlapping → (0, 20)
        candidate = [(10.0, 20.0)]
        result = cut_deltas(baseline, candidate)
        # Effective baseline after merge: (0, 20); removed = (0, 10)
        assert len(result["removed"]) == 1
        s, e, d = result["removed"][0]
        assert s == pytest.approx(0.0)
        assert e == pytest.approx(10.0)
        assert d == pytest.approx(10.0)

    def test_result_segments_have_duration_field(self) -> None:
        result = cut_deltas([(0.0, 30.0)], [(10.0, 20.0)])
        for seg in result["removed"] + result["added"]:
            assert len(seg) == 3
            s, e, d = seg
            assert d == pytest.approx(e - s)


# ===========================================================================
# write_delta_report (smoke tests — verify structure, not exact wording)
# ===========================================================================


class TestWriteDeltaReport:
    def _make_deltas(self) -> dict:
        return cut_deltas(
            [(0.0, 30.0), (60.0, 90.0)],
            [(5.0, 35.0), (60.0, 90.0)],
        )

    def test_returns_string(self) -> None:
        deltas = self._make_deltas()
        report = write_delta_report(deltas, [(0.0, 30.0)], [(5.0, 35.0)])
        assert isinstance(report, str)
        assert len(report) > 0

    def test_contains_removed_and_added_sections(self) -> None:
        deltas = self._make_deltas()
        report = write_delta_report(deltas, [(0.0, 30.0)], [(5.0, 35.0)])
        assert "Removed" in report or "removed" in report
        assert "Added" in report or "added" in report

    def test_with_gt_contains_footage_recall(self) -> None:
        gt = [(0.0, 30.0), (60.0, 90.0)]
        deltas = self._make_deltas()
        report = write_delta_report(
            deltas,
            baseline=[(0.0, 30.0), (60.0, 90.0)],
            candidate=[(5.0, 35.0), (60.0, 90.0)],
            gt=gt,
        )
        assert "footage_recall" in report

    def test_without_gt_no_confusion_table(self) -> None:
        deltas = self._make_deltas()
        report = write_delta_report(
            deltas,
            baseline=[(0.0, 30.0)],
            candidate=[(5.0, 35.0)],
            gt=None,
        )
        assert "footage_recall" not in report

    def test_video_path_appears_in_report(self) -> None:
        deltas = self._make_deltas()
        report = write_delta_report(
            deltas,
            baseline=[(0.0, 30.0)],
            candidate=[(5.0, 35.0)],
            video_path="/data/match.mp4",
        )
        assert "match.mp4" in report

    def test_no_delta_shows_none_message(self) -> None:
        """When there are no removed/added segments, the table shows a note."""
        deltas = cut_deltas([(0.0, 30.0)], [(0.0, 30.0)])  # identical
        report = write_delta_report(deltas, [(0.0, 30.0)], [(0.0, 30.0)])
        # Should mention zero segments or "None"
        assert "0 segment" in report or "None" in report


# ===========================================================================
# get_ffmpeg_commands
# ===========================================================================


class TestGetFfmpegCommands:
    def test_returns_one_command_per_segment(self) -> None:
        segs = [(0.0, 10.0, 10.0), (20.0, 30.0, 10.0)]
        cmds = get_ffmpeg_commands("/data/match.mp4", segs, "/out", prefix="removed")
        assert len(cmds) == 2

    def test_command_is_string(self) -> None:
        segs = [(5.0, 15.0, 10.0)]
        cmds = get_ffmpeg_commands("/data/match.mp4", segs, "/out")
        assert isinstance(cmds[0], str)

    def test_command_contains_ss_and_t_flags(self) -> None:
        segs = [(5.0, 15.0, 10.0)]
        cmd = get_ffmpeg_commands("/data/match.mp4", segs, "/out")[0]
        assert "-ss" in cmd
        assert "-t" in cmd

    def test_command_contains_source_video(self) -> None:
        segs = [(5.0, 15.0, 10.0)]
        cmd = get_ffmpeg_commands("/data/match.mp4", segs, "/out")[0]
        assert "match.mp4" in cmd

    def test_empty_segments_returns_empty_list(self) -> None:
        cmds = get_ffmpeg_commands("/data/match.mp4", [], "/out")
        assert cmds == []

    def test_prefix_appears_in_output_filename(self) -> None:
        segs = [(0.0, 5.0, 5.0)]
        cmd = get_ffmpeg_commands("/data/match.mp4", segs, "/out", prefix="added")[0]
        assert "added" in cmd

    def test_timestamps_in_command(self) -> None:
        segs = [(12.345, 22.345, 10.0)]
        cmd = get_ffmpeg_commands("/data/match.mp4", segs, "/out")[0]
        assert "12.345" in cmd
        assert "10.000" in cmd  # duration
