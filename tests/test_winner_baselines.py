"""Tests for ml.evaluation.baselines."""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.evaluation.baselines import (
    ALL_BASELINES,
    AlwaysTeam0Baseline,
    AlwaysTeam1Baseline,
    MajorityClassBaseline,
    ScoreLeadBaseline,
    ScoreTrailBaseline,
    evaluate_baseline,
    make_baselines,
)
from ml.examples import RallyExample


_FAKE_JSON_PATH = Path("/fake/game.training.json")
_FAKE_VIDEO_PATH = Path("/fake/video.mp4")
_FAKE_CORNERS: tuple[tuple[int, int], ...] = (
    (10, 20),
    (310, 20),
    (310, 220),
    (10, 220),
)


def _make_example(
    score_at_start: str,
    winner: str,
    winning_team: int,
    *,
    rally_index: int = 0,
    serving_team: int | None = None,
) -> RallyExample:
    """Build a RallyExample via from_rally_dict.

    Args:
        score_at_start: Score string, e.g. ``"5-3-2"`` or ``"5-3"``.
        winner: Raw winner string (``"server"`` or ``"receiver"``).
        winning_team: Ground-truth label (0 or 1).
        rally_index: Position within the source file.
        serving_team: When not ``None``, injects a ``score_snapshot_at_start``
            dict so that ``example.serving_team`` is populated with the
            absolute serving team index.  ``None`` produces a legacy example
            without a snapshot.
    """
    rally_dict: dict = {
        "index": rally_index,
        "score_at_start": score_at_start,
        "winner": winner,
        "winning_team": winning_team,
        "is_post_game": False,
        "comment": None,
        "raw": {"start_seconds": 10.0, "end_seconds": 20.0},
    }
    if serving_team is not None:
        # Inject a minimal score_snapshot_at_start matching the shape
        # produced by ScoreSnapshot.to_dict (see src/core/models.py).
        parts = [int(p) for p in score_at_start.split("-") if p.isdigit()]
        score_list = list(parts)
        rally_dict["score_snapshot_at_start"] = {
            "score": score_list,
            "serving_team": serving_team,
            "server_number": parts[2] if len(parts) == 3 else None,
            "first_server_player_index": 0,
        }
    return RallyExample.from_rally_dict(
        source_json_path=_FAKE_JSON_PATH,
        video_path=_FAKE_VIDEO_PATH,
        court_corners=_FAKE_CORNERS,
        schema_version="1.1",
        generated_by="manual",
        rally_dict=rally_dict,
    )


class TestMakeBaselines:
    def test_names_match_catalogue(self) -> None:
        assert [baseline.name for baseline in make_baselines()] == ALL_BASELINES

    def test_each_call_returns_fresh_instances(self) -> None:
        first = make_baselines()
        second = make_baselines()
        assert len(first) == len(second)
        for left, right in zip(first, second):
            assert left is not right


class TestConstantAndMajorityBaselines:
    def test_always_team_0_predicts_0(self) -> None:
        assert AlwaysTeam0Baseline().predict(_make_example("0-0-2", "receiver", 1)) == 0

    def test_always_team_1_predicts_1(self) -> None:
        assert AlwaysTeam1Baseline().predict(_make_example("0-0-2", "server", 0)) == 1

    def test_majority_class_learns_winning_team_distribution(self) -> None:
        baseline = MajorityClassBaseline()
        baseline.fit(
            [
                _make_example("0-0-2", "server", 1, rally_index=0),
                _make_example("1-0-2", "receiver", 1, rally_index=1),
                _make_example("2-0-2", "server", 0, rally_index=2),
            ]
        )
        assert baseline.majority_class == 1
        assert baseline.predict(_make_example("5-3", "server", 0)) == 1

    def test_majority_class_tie_resolves_to_0(self) -> None:
        baseline = MajorityClassBaseline()
        baseline.fit(
            [
                _make_example("0-0-2", "server", 0, rally_index=0),
                _make_example("0-1-1", "receiver", 1, rally_index=1),
            ]
        )
        assert baseline.majority_class == 0


class TestScoreBaselines:
    @pytest.mark.parametrize(
        ("baseline", "score", "expected"),
        [
            (ScoreLeadBaseline(), "5-3", 0),
            (ScoreLeadBaseline(), "3-5", 1),
            (ScoreLeadBaseline(), "5-5", 0),
            (ScoreTrailBaseline(), "5-3", 1),
            (ScoreTrailBaseline(), "3-5", 0),
            (ScoreTrailBaseline(), "5-5", 0),
        ],
    )
    def test_predictions_follow_score_parts(
        self,
        baseline: ScoreLeadBaseline | ScoreTrailBaseline,
        score: str,
        expected: int,
    ) -> None:
        assert baseline.predict(_make_example(score, "server", 0)) == expected

    def test_score_lead_does_not_depend_on_winner_field(self) -> None:
        server_win = _make_example("7-4", "server", 0, rally_index=0)
        receiver_win = _make_example("7-4", "receiver", 1, rally_index=1)
        assert ScoreLeadBaseline().predict(server_win) == 0
        assert ScoreLeadBaseline().predict(receiver_win) == 0

    def test_score_trail_does_not_depend_on_winner_field(self) -> None:
        server_win = _make_example("2-8-1", "server", 1, rally_index=0)
        receiver_win = _make_example("2-8-1", "receiver", 0, rally_index=1)
        assert ScoreTrailBaseline().predict(server_win) == 0
        assert ScoreTrailBaseline().predict(receiver_win) == 0

    @pytest.mark.parametrize("baseline", [ScoreLeadBaseline(), ScoreTrailBaseline()])
    def test_invalid_score_falls_back_to_0(
        self,
        baseline: ScoreLeadBaseline | ScoreTrailBaseline,
    ) -> None:
        assert baseline.predict(_make_example("", "server", 0)) == 0


class TestScoreBaselinesAbsoluteTeam:
    """Verify absolute-team mapping when serving_team snapshot is present."""

    def test_lead_with_serving_team_1_score_5_3_predicts_1(self) -> None:
        # serving_team=1 → team1_score=5, team0_score=3 → team 1 leads → predict 1
        ex = _make_example("5-3-2", "server", 0, serving_team=1)
        assert ex.serving_team == 1
        assert ScoreLeadBaseline().predict(ex) == 1

    def test_trail_with_serving_team_1_score_5_3_predicts_0(self) -> None:
        # serving_team=1 → team1_score=5, team0_score=3 → team 0 trails → predict 0
        ex = _make_example("5-3-2", "server", 0, serving_team=1)
        assert ScoreTrailBaseline().predict(ex) == 0

    def test_lead_with_serving_team_0_score_5_3_predicts_0(self) -> None:
        # serving_team=0 → team0_score=5, team1_score=3 → team 0 leads → predict 0
        ex = _make_example("5-3-2", "server", 0, serving_team=0)
        assert ScoreLeadBaseline().predict(ex) == 0

    def test_trail_with_serving_team_0_score_5_3_predicts_1(self) -> None:
        # serving_team=0 → team0_score=5, team1_score=3 → team 1 trails → predict 1
        ex = _make_example("5-3-2", "server", 0, serving_team=0)
        assert ScoreTrailBaseline().predict(ex) == 1

    def test_lead_tie_resolves_to_0_with_snapshot(self) -> None:
        # team0_score=5, team1_score=5 → tie → predict 0
        ex = _make_example("5-5-2", "server", 0, serving_team=0)
        assert ScoreLeadBaseline().predict(ex) == 0

    def test_trail_tie_resolves_to_0_with_snapshot(self) -> None:
        # tie → predict 0
        ex = _make_example("5-5-2", "server", 0, serving_team=1)
        assert ScoreTrailBaseline().predict(ex) == 0

    def test_label_fields_not_consulted_lead(self) -> None:
        # Two examples with identical score + serving_team but different labels
        # must produce the same prediction.
        ex_label0 = _make_example("7-3-1", "server", 0, serving_team=1, rally_index=0)
        ex_label1 = _make_example("7-3-1", "receiver", 1, serving_team=1, rally_index=1)
        assert ScoreLeadBaseline().predict(ex_label0) == ScoreLeadBaseline().predict(ex_label1)

    def test_label_fields_not_consulted_trail(self) -> None:
        ex_label0 = _make_example("7-3-1", "server", 0, serving_team=0, rally_index=0)
        ex_label1 = _make_example("7-3-1", "receiver", 1, serving_team=0, rally_index=1)
        assert ScoreTrailBaseline().predict(ex_label0) == ScoreTrailBaseline().predict(ex_label1)

    def test_legacy_example_has_serving_team_none(self) -> None:
        # Without a snapshot kwarg, serving_team must be None.
        ex = _make_example("5-3-2", "server", 0)
        assert ex.serving_team is None

    def test_legacy_lead_perspective_relative_unchanged(self) -> None:
        # Legacy: score_parts[0]=5 > score_parts[1]=3 → predict 0
        ex = _make_example("5-3-2", "server", 0)
        assert ScoreLeadBaseline().predict(ex) == 0

    def test_legacy_trail_perspective_relative_unchanged(self) -> None:
        # Legacy: score_parts[0]=5 > score_parts[1]=3 → trailing side is 1
        ex = _make_example("5-3-2", "server", 0)
        assert ScoreTrailBaseline().predict(ex) == 1


class TestEvaluateBaseline:
    def test_metrics_are_computed_from_winning_team(self) -> None:
        examples = [
            _make_example("9-4", "receiver", 1, rally_index=0),
            _make_example("8-6", "server", 0, rally_index=1),
            _make_example("1-5", "server", 1, rally_index=2),
            _make_example("7-2", "receiver", 0, rally_index=3),
        ]

        result = evaluate_baseline(ScoreLeadBaseline(), examples)

        assert result == {
            "n_total": 4,
            "n_correct": 3,
            "n_wrong": 1,
            "accuracy": pytest.approx(0.75),
        }

    def test_empty_examples_return_zero_metrics(self) -> None:
        assert evaluate_baseline(AlwaysTeam0Baseline(), []) == {
            "n_total": 0,
            "n_correct": 0,
            "n_wrong": 0,
            "accuracy": 0.0,
        }
