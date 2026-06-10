"""Tests for ml.tools.diff_reexport.

Covers: perfect agreement, boundary shift, false positive, missed rally,
winner flip (winning_team path + snapshot+winner derivation path), score
divergence, post-game exclusion, and batch pairing with unpaired-file warning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ml.tools.diff_reexport import (
    diff_training_pair,
    diff_batch,
    run_diff,
    _interval_iou,
    _rally_timestamps,
    _greedy_match,
    _derive_winning_team,
)


# ---------------------------------------------------------------------------
# Helpers for building synthetic training dicts
# ---------------------------------------------------------------------------

def _make_rally(
    index: int,
    start_seconds: float,
    end_seconds: float,
    score_at_start: str = "0-0-2",
    winner: str = "server",
    winning_team: int | None = 0,
    is_post_game: bool = False,
    score_snapshot_at_start: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal training-JSON rally dict."""
    fps = 30.0
    r: dict[str, Any] = {
        "index": index,
        "score_at_start": score_at_start,
        "winner": winner,
        "winning_team": winning_team,
        "is_post_game": is_post_game,
        "comment": None,
        "raw": {
            "start_frame": round(start_seconds * fps),
            "end_frame": round(end_seconds * fps),
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
        },
        "padded": {
            "start_frame": round((start_seconds - 0.5) * fps),
            "end_frame": round((end_seconds + 1.0) * fps),
            "start_seconds": start_seconds - 0.5,
            "end_seconds": end_seconds + 1.0,
        },
    }
    if score_snapshot_at_start is not None:
        r["score_snapshot_at_start"] = score_snapshot_at_start
    return r


def _make_training_dict(
    video_path: str = "/videos/game.mp4",
    fps: float = 30.0,
    rallies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal top-level training JSON dict."""
    return {
        "schema_version": "1.1",
        "generated_by": "manual",
        "video": {
            "path": video_path,
            "fps": fps,
            "duration_seconds": 3600.0,
            "width": 1920,
            "height": 1080,
            "court_corners": None,
        },
        "game": {
            "type": "doubles",
            "victory_rules": "11",
            "team1_players": ["Alice", "Bob"],
            "team2_players": ["Carol", "Dave"],
            "completion": None,
        },
        "rallies": rallies or [],
        "rally_count": len(rallies or []),
    }


# ---------------------------------------------------------------------------
# Unit tests: _interval_iou
# ---------------------------------------------------------------------------

class TestIntervalIou:
    """Tests for the IoU helper."""

    def test_identical_intervals(self):
        """Identical intervals have IoU of 1.0."""
        assert _interval_iou(0.0, 10.0, 0.0, 10.0) == pytest.approx(1.0)

    def test_no_overlap(self):
        """Non-overlapping intervals have IoU of 0.0."""
        assert _interval_iou(0.0, 5.0, 6.0, 11.0) == pytest.approx(0.0)

    def test_partial_overlap(self):
        """Partially overlapping intervals have 0 < IoU < 1."""
        # [0, 10] vs [5, 15] — intersection=5, union=15
        iou = _interval_iou(0.0, 10.0, 5.0, 15.0)
        assert iou == pytest.approx(5.0 / 15.0)

    def test_contained_interval(self):
        """A fully contained interval has IoU = inner_len / outer_len."""
        # [2, 8] inside [0, 10] — intersection=6, union=10
        iou = _interval_iou(2.0, 8.0, 0.0, 10.0)
        assert iou == pytest.approx(6.0 / 10.0)

    def test_zero_length_both(self):
        """Two zero-length intervals return 0.0 (no divide by zero)."""
        assert _interval_iou(5.0, 5.0, 5.0, 5.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Unit tests: _rally_timestamps
# ---------------------------------------------------------------------------

class TestRallyTimestamps:
    """Tests for timestamp resolution."""

    def test_raw_seconds_preferred(self):
        """raw.start_seconds / end_seconds are used when present."""
        rally = _make_rally(0, 10.0, 20.0)
        start, end = _rally_timestamps(rally, fps=30.0)
        assert start == pytest.approx(10.0)
        assert end == pytest.approx(20.0)

    def test_raw_frames_fallback(self):
        """Falls back to raw.start_frame / end_frame divided by fps."""
        rally = {
            "raw": {"start_frame": 300, "end_frame": 600},
        }
        start, end = _rally_timestamps(rally, fps=30.0)
        assert start == pytest.approx(10.0)
        assert end == pytest.approx(20.0)

    def test_raw_none_uses_padded(self):
        """When raw is None, falls back to padded timestamps."""
        rally = {
            "raw": None,
            "padded": {"start_seconds": 9.5, "end_seconds": 21.0},
        }
        start, end = _rally_timestamps(rally, fps=30.0)
        assert start == pytest.approx(9.5)
        assert end == pytest.approx(21.0)

    def test_raw_absent_uses_padded(self):
        """When raw key is missing, falls back to padded."""
        rally = {
            "padded": {"start_frame": 300, "end_frame": 600},
        }
        start, end = _rally_timestamps(rally, fps=30.0)
        assert start == pytest.approx(10.0)
        assert end == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Unit tests: _derive_winning_team
# ---------------------------------------------------------------------------

class TestDeriveWinningTeam:
    """Tests for the winner derivation fallback chain."""

    def test_winning_team_field(self):
        """winning_team field takes priority."""
        rally = {"winning_team": 1, "winner": "receiver"}
        assert _derive_winning_team(rally) == 1

    def test_winning_team_zero(self):
        """winning_team = 0 is handled (not falsy-skipped)."""
        rally = {"winning_team": 0, "winner": "server"}
        assert _derive_winning_team(rally) == 0

    def test_snapshot_server_wins(self):
        """serving_team + 'server' winner derives winning_team = serving_team."""
        rally = {
            "winning_team": None,
            "winner": "server",
            "score_snapshot_at_start": {"serving_team": 1},
        }
        assert _derive_winning_team(rally) == 1

    def test_snapshot_receiver_wins(self):
        """serving_team + 'receiver' winner derives winning_team = 1 - serving_team."""
        rally = {
            "winning_team": None,
            "winner": "receiver",
            "score_snapshot_at_start": {"serving_team": 1},
        }
        assert _derive_winning_team(rally) == 0

    def test_no_winning_team_no_snapshot_returns_none(self):
        """Returns None when no derivation is possible."""
        rally = {"winner": "server"}
        assert _derive_winning_team(rally) is None


# ---------------------------------------------------------------------------
# Integration tests: diff_training_pair
# ---------------------------------------------------------------------------

class TestDiffTrainingPairPerfectAgreement:
    """Perfect agreement — all fields match, no corrections."""

    def test_perfect_agreement_counts(self):
        """All rallies match, zero boundary errors, 100% winner accuracy."""
        rallies = [
            _make_rally(0, 10.0, 20.0, score_at_start="0-0-2", winner="server", winning_team=0),
            _make_rally(1, 30.0, 40.0, score_at_start="1-0-1", winner="receiver", winning_team=1),
        ]
        auto = _make_training_dict(rallies=rallies)
        reviewed = _make_training_dict(rallies=rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["n_matched"] == 2
        assert result["detection"]["n_false_positives"] == 0
        assert result["detection"]["n_missed"] == 0
        assert result["winner"]["accuracy"] == pytest.approx(1.0)
        assert result["score"]["accuracy"] == pytest.approx(1.0)
        assert len(result["hard_examples"]) == 0

    def test_perfect_agreement_boundary_zero(self):
        """Mean boundary deltas are zero on perfect agreement."""
        rallies = [_make_rally(0, 10.0, 20.0)]
        auto = _make_training_dict(rallies=rallies)
        reviewed = _make_training_dict(rallies=rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["boundary"]["mean_abs_start_delta"] == pytest.approx(0.0)
        assert result["boundary"]["mean_abs_end_delta"] == pytest.approx(0.0)
        assert result["boundary"]["large_deltas"] == []


class TestDiffTrainingPairBoundaryShift:
    """Human shifted boundary by 1.0s — MAE and hard-example output."""

    def test_boundary_shift_mae(self):
        """Mean absolute start delta equals the introduced shift."""
        auto_rallies = [_make_rally(0, 10.0, 20.0)]
        reviewed_rallies = [_make_rally(0, 11.0, 21.0)]  # shifted +1.0s both ends

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["n_matched"] == 1
        assert result["boundary"]["mean_abs_start_delta"] == pytest.approx(1.0)
        assert result["boundary"]["mean_abs_end_delta"] == pytest.approx(1.0)
        assert result["boundary"]["median_abs_start_delta"] == pytest.approx(1.0)

    def test_boundary_shift_emits_hard_example(self):
        """A shift > 0.5s produces a hard example of type boundary_shift."""
        auto_rallies = [_make_rally(0, 10.0, 20.0)]
        reviewed_rallies = [_make_rally(0, 11.0, 21.0)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        hard = result["hard_examples"]
        assert len(hard) == 1
        assert hard[0]["type"] == "boundary_shift"
        assert hard[0]["detail"]["abs_start_delta"] == pytest.approx(1.0)
        assert hard[0]["detail"]["abs_end_delta"] == pytest.approx(1.0)

    def test_small_shift_no_hard_example(self):
        """A shift <= 0.5s does not produce a hard example."""
        auto_rallies = [_make_rally(0, 10.0, 20.0)]
        reviewed_rallies = [_make_rally(0, 10.3, 20.3)]  # 0.3s shift

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["boundary"]["mean_abs_start_delta"] == pytest.approx(0.3)
        boundary_hard = [e for e in result["hard_examples"] if e["type"] == "boundary_shift"]
        assert len(boundary_hard) == 0


class TestDiffTrainingPairFalsePositive:
    """Auto has a rally the human deleted (false positive)."""

    def test_false_positive_count(self):
        """Deleted auto rally is recorded as false positive."""
        auto_rallies = [
            _make_rally(0, 10.0, 20.0),
            _make_rally(1, 50.0, 60.0),  # human deleted this one
        ]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0),
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["detection"]["n_false_positives"] == 1
        assert result["detection"]["n_missed"] == 0
        fp = result["detection"]["false_positives"]
        assert len(fp) == 1
        assert fp[0]["start_seconds"] == pytest.approx(50.0)

    def test_false_positive_hard_example(self):
        """False positive auto rally appears in hard_examples."""
        auto_rallies = [
            _make_rally(0, 10.0, 20.0),
            _make_rally(1, 50.0, 60.0),
        ]
        reviewed_rallies = [_make_rally(0, 10.0, 20.0)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        fp_hard = [e for e in result["hard_examples"] if e["type"] == "false_positive"]
        assert len(fp_hard) == 1
        assert fp_hard[0]["auto_time"] == pytest.approx(50.0)


class TestDiffTrainingPairMissedRally:
    """Human added a rally that auto missed."""

    def test_missed_count(self):
        """Added reviewed rally is recorded as missed."""
        auto_rallies = [_make_rally(0, 10.0, 20.0)]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0),
            _make_rally(1, 50.0, 60.0),  # human added this one
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["detection"]["n_missed"] == 1
        assert result["detection"]["n_false_positives"] == 0

    def test_missed_hard_example(self):
        """Missed reviewed rally appears in hard_examples."""
        auto_rallies = [_make_rally(0, 10.0, 20.0)]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0),
            _make_rally(1, 50.0, 60.0),
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        ms_hard = [e for e in result["hard_examples"] if e["type"] == "missed_rally"]
        assert len(ms_hard) == 1


class TestDiffTrainingPairWinnerFlip:
    """Winner disagreement on a matched pair."""

    def test_winner_flip_via_winning_team(self):
        """Disagreement on winning_team field registers as wrong."""
        auto_rallies = [_make_rally(0, 10.0, 20.0, winning_team=0)]
        reviewed_rallies = [_make_rally(0, 10.0, 20.0, winning_team=1)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["winner"]["n_correct"] == 0
        assert result["winner"]["n_wrong"] == 1
        assert result["winner"]["accuracy"] == pytest.approx(0.0)
        assert not result["winner"]["caveat_raw_strings"]

    def test_winner_flip_hard_example(self):
        """A winning_team flip emits a winner_flip hard example."""
        auto_rallies = [_make_rally(0, 10.0, 20.0, winning_team=0)]
        reviewed_rallies = [_make_rally(0, 10.0, 20.0, winning_team=1)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        wf = [e for e in result["hard_examples"] if e["type"] == "winner_flip"]
        assert len(wf) == 1
        assert wf[0]["detail"]["auto_winner"] == 0
        assert wf[0]["detail"]["reviewed_winner"] == 1

    def test_winner_flip_via_snapshot_derivation(self):
        """Disagreement derived from score_snapshot_at_start + winner field."""
        # Auto: serving_team=0, winner=server → winning_team derived = 0
        auto_rallies = [
            _make_rally(
                0, 10.0, 20.0,
                winning_team=None,
                winner="server",
                score_snapshot_at_start={"serving_team": 0},
            )
        ]
        # Reviewed: serving_team=0, winner=receiver → winning_team derived = 1
        reviewed_rallies = [
            _make_rally(
                0, 10.0, 20.0,
                winning_team=None,
                winner="receiver",
                score_snapshot_at_start={"serving_team": 0},
            )
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["winner"]["n_compared"] == 1
        assert result["winner"]["n_correct"] == 0
        assert result["winner"]["n_wrong"] == 1
        assert not result["winner"]["caveat_raw_strings"]

    def test_winner_caveat_raw_strings_set_when_no_derivation(self):
        """caveat_raw_strings is True when raw winner strings must be used."""
        # No winning_team, no snapshot → raw string comparison
        auto_rallies = [
            {"index": 0, "score_at_start": "0-0-2", "winner": "server",
             "winning_team": None, "is_post_game": False, "comment": None,
             "raw": {"start_seconds": 10.0, "end_seconds": 20.0}, "padded": {}}
        ]
        reviewed_rallies = [
            {"index": 0, "score_at_start": "0-0-2", "winner": "receiver",
             "winning_team": None, "is_post_game": False, "comment": None,
             "raw": {"start_seconds": 10.0, "end_seconds": 20.0}, "padded": {}}
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["winner"]["caveat_raw_strings"] is True
        assert result["winner"]["n_wrong"] == 1


class TestDiffTrainingPairScoreDivergence:
    """Score-string agreement and first divergence index."""

    def test_score_perfect_agreement(self):
        """All scores match — accuracy 1.0, no divergence index."""
        rallies = [
            _make_rally(0, 10.0, 20.0, score_at_start="0-0-2"),
            _make_rally(1, 30.0, 40.0, score_at_start="1-0-1"),
        ]
        auto = _make_training_dict(rallies=rallies)
        reviewed = _make_training_dict(rallies=rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["score"]["accuracy"] == pytest.approx(1.0)
        assert result["score"]["first_divergence_index"] is None

    def test_score_divergence_at_second_match(self):
        """Score diverges at match index 1; first_divergence_index == 1."""
        auto_rallies = [
            _make_rally(0, 10.0, 20.0, score_at_start="0-0-2"),
            _make_rally(1, 30.0, 40.0, score_at_start="1-0-1"),
        ]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0, score_at_start="0-0-2"),
            _make_rally(1, 30.0, 40.0, score_at_start="0-1-1"),  # different score
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["score"]["n_matching"] == 1
        assert result["score"]["first_divergence_index"] == 1
        assert result["score"]["accuracy"] == pytest.approx(0.5)

    def test_score_divergence_at_first_match(self):
        """Score diverges immediately; first_divergence_index == 0."""
        auto_rallies = [_make_rally(0, 10.0, 20.0, score_at_start="0-0-2")]
        reviewed_rallies = [_make_rally(0, 10.0, 20.0, score_at_start="1-0-2")]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed)

        assert result["score"]["first_divergence_index"] == 0


class TestDiffTrainingPairPostGame:
    """Post-game rally exclusion."""

    def test_post_game_excluded_by_default(self):
        """is_post_game rallies are excluded from matching."""
        auto_rallies = [
            _make_rally(0, 10.0, 20.0, is_post_game=False),
            _make_rally(1, 50.0, 60.0, is_post_game=True),
        ]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0, is_post_game=False),
            _make_rally(1, 50.0, 60.0, is_post_game=True),
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed, include_post_game=False)

        # Only 1 non-post-game rally on each side
        assert result["n_auto"] == 1
        assert result["n_reviewed"] == 1
        assert result["n_matched"] == 1

    def test_post_game_included_when_flag_set(self):
        """is_post_game rallies are included when include_post_game=True."""
        auto_rallies = [
            _make_rally(0, 10.0, 20.0, is_post_game=False),
            _make_rally(1, 50.0, 60.0, is_post_game=True),
        ]
        reviewed_rallies = [
            _make_rally(0, 10.0, 20.0, is_post_game=False),
            _make_rally(1, 50.0, 60.0, is_post_game=True),
        ]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed, include_post_game=True)

        assert result["n_auto"] == 2
        assert result["n_reviewed"] == 2
        assert result["n_matched"] == 2


class TestDiffTrainingPairIoUThreshold:
    """IoU threshold controls whether a pair is matched."""

    def test_iou_below_threshold_not_matched(self):
        """Rallies with IoU below threshold are treated as FP + missed."""
        # [0, 10] vs [8, 18] — intersection=2, union=18, IoU=2/18 ≈ 0.11
        auto_rallies = [_make_rally(0, 0.0, 10.0)]
        reviewed_rallies = [_make_rally(0, 8.0, 18.0)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed, iou_threshold=0.5)

        assert result["n_matched"] == 0
        assert result["detection"]["n_false_positives"] == 1
        assert result["detection"]["n_missed"] == 1

    def test_iou_at_threshold_is_matched(self):
        """Rallies with IoU exactly at threshold are matched."""
        # [0, 10] vs [5, 15] — intersection=5, union=15, IoU=1/3 ≈ 0.333
        # [0, 10] vs [0, 10] — IoU=1.0 (trivially above any threshold)
        auto_rallies = [_make_rally(0, 0.0, 10.0)]
        reviewed_rallies = [_make_rally(0, 0.0, 10.0)]

        auto = _make_training_dict(rallies=auto_rallies)
        reviewed = _make_training_dict(rallies=reviewed_rallies)

        result = diff_training_pair(auto, reviewed, iou_threshold=1.0)

        assert result["n_matched"] == 1


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

class TestDiffBatch:
    """Batch mode: pair by video.path, warn on unpaired files."""

    def _write_training_json(
        self,
        directory: Path,
        filename: str,
        video_path: str,
        rallies: list[dict[str, Any]],
    ) -> None:
        data = _make_training_dict(video_path=video_path, rallies=rallies)
        (directory / filename).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def test_paired_files_are_diffed(self, tmp_path: Path):
        """Files with matching video.path are paired and diffed."""
        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()

        rallies = [_make_rally(0, 10.0, 20.0)]
        self._write_training_json(auto_dir, "game.training.json", "/v/game.mp4", rallies)
        self._write_training_json(rev_dir, "game.training.json", "/v/game.mp4", rallies)

        result = diff_batch(auto_dir, rev_dir)

        assert result["aggregate"]["n_pairs"] == 1
        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["n_matched"] == 1

    def test_unpaired_auto_file_warned(self, tmp_path: Path, capsys):
        """Auto-only file is reported as unpaired (stderr warning)."""
        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()

        rallies = [_make_rally(0, 10.0, 20.0)]
        # Only in auto dir
        self._write_training_json(auto_dir, "game.training.json", "/v/game.mp4", rallies)

        result = diff_batch(auto_dir, rev_dir)

        assert "/v/game.mp4" in result["unpaired_auto"]
        assert result["aggregate"]["n_pairs"] == 0

        captured = capsys.readouterr()
        assert "auto-only" in captured.err

    def test_unpaired_reviewed_file_warned(self, tmp_path: Path, capsys):
        """Reviewed-only file is reported as unpaired (stderr warning)."""
        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()

        rallies = [_make_rally(0, 10.0, 20.0)]
        # Only in reviewed dir
        self._write_training_json(rev_dir, "game.training.json", "/v/game.mp4", rallies)

        result = diff_batch(auto_dir, rev_dir)

        assert "/v/game.mp4" in result["unpaired_reviewed"]
        captured = capsys.readouterr()
        assert "reviewed-only" in captured.err

    def test_batch_aggregates_totals(self, tmp_path: Path):
        """Aggregate counts are summed across multiple pairs."""
        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()

        for i in range(3):
            rallies = [_make_rally(0, 10.0, 20.0, winning_team=0)]
            video = f"/v/game{i}.mp4"
            self._write_training_json(auto_dir, f"game{i}.training.json", video, rallies)
            self._write_training_json(rev_dir, f"game{i}.training.json", video, rallies)

        result = diff_batch(auto_dir, rev_dir)

        agg = result["aggregate"]
        assert agg["n_pairs"] == 3
        assert agg["total_auto"] == 3
        assert agg["total_reviewed"] == 3
        assert agg["total_matched"] == 3
        assert agg["winner_accuracy"] == pytest.approx(1.0)

    def test_batch_multiple_pairs_with_disagreement(self, tmp_path: Path):
        """Aggregate winner accuracy is computed across all pairs."""
        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()

        # Pair 0: winner agrees
        auto_r0 = [_make_rally(0, 10.0, 20.0, winning_team=0)]
        rev_r0 = [_make_rally(0, 10.0, 20.0, winning_team=0)]
        # Pair 1: winner disagrees
        auto_r1 = [_make_rally(0, 10.0, 20.0, winning_team=0)]
        rev_r1 = [_make_rally(0, 10.0, 20.0, winning_team=1)]

        self._write_training_json(auto_dir, "g0.training.json", "/v/g0.mp4", auto_r0)
        self._write_training_json(rev_dir, "g0.training.json", "/v/g0.mp4", rev_r0)
        self._write_training_json(auto_dir, "g1.training.json", "/v/g1.mp4", auto_r1)
        self._write_training_json(rev_dir, "g1.training.json", "/v/g1.mp4", rev_r1)

        result = diff_batch(auto_dir, rev_dir)

        # 1 correct, 1 wrong → 50%
        assert result["aggregate"]["winner_accuracy"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

class TestCli:
    """CLI --help and basic invocation smoke tests."""

    def test_help_exits_zero(self):
        """--help exits with code 0."""
        from ml.tools.diff_reexport import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_no_args_exits_nonzero(self):
        """No args exits with non-zero (argument error)."""
        from ml.tools.diff_reexport import main
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_single_pair_cli(self, tmp_path: Path):
        """Single-pair mode writes JSON file and returns 0."""
        from ml.tools.diff_reexport import main

        rallies = [_make_rally(0, 10.0, 20.0)]
        auto_data = _make_training_dict(rallies=rallies)
        rev_data = _make_training_dict(rallies=rallies)

        auto_path = tmp_path / "auto.training.json"
        rev_path = tmp_path / "reviewed.training.json"
        json_out = tmp_path / "out.json"

        auto_path.write_text(json.dumps(auto_data), encoding="utf-8")
        rev_path.write_text(json.dumps(rev_data), encoding="utf-8")

        exit_code = main([
            "--auto", str(auto_path),
            "--reviewed", str(rev_path),
            "--json", str(json_out),
        ])

        assert exit_code == 0
        assert json_out.exists()
        out = json.loads(json_out.read_text(encoding="utf-8"))
        assert out["n_matched"] == 1

    def test_batch_cli(self, tmp_path: Path):
        """Batch mode runs without error and writes JSON."""
        from ml.tools.diff_reexport import main

        auto_dir = tmp_path / "auto"
        rev_dir = tmp_path / "reviewed"
        auto_dir.mkdir()
        rev_dir.mkdir()
        json_out = tmp_path / "batch_out.json"

        rallies = [_make_rally(0, 10.0, 20.0)]
        for d in (auto_dir, rev_dir):
            (d / "g.training.json").write_text(
                json.dumps(_make_training_dict(video_path="/v/g.mp4", rallies=rallies)),
                encoding="utf-8",
            )

        exit_code = main([
            "--auto-dir", str(auto_dir),
            "--reviewed-dir", str(rev_dir),
            "--json", str(json_out),
        ])

        assert exit_code == 0
        assert json_out.exists()
        out = json.loads(json_out.read_text(encoding="utf-8"))
        assert out["aggregate"]["n_pairs"] == 1

    def test_mixed_mode_rejected(self):
        """Mixing single and batch args exits with non-zero."""
        from ml.tools.diff_reexport import main
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--auto", "a.json",
                "--reviewed", "r.json",
                "--auto-dir", "/some/dir",
                "--reviewed-dir", "/some/dir",
            ])
        assert exc_info.value.code != 0
