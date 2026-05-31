"""Tests for ml/evaluation/baselines.py.

Verifies each baseline's predictions on small in-memory fixtures.  All tests
are torch-free; no video files or .training.json files are read from disk.

Test classes
------------
TestAlwaysTeam0Baseline       -- constant prediction of 0
TestAlwaysTeam1Baseline       -- constant prediction of 1
TestMajorityClassBaseline     -- learned majority from winning_team distribution
TestServingTeamWinsBaseline   -- score-part-count guard + server-wins logic
TestReceivingTeamWinsBaseline -- score-part-count guard + receiver-wins logic
TestBaselineNames             -- each baseline exposes a non-empty .name string
TestScorePartCountGuard       -- guard behaviour for invalid / edge-case score formats
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.evaluation.baselines import (
    AlwaysTeam0Baseline,
    AlwaysTeam1Baseline,
    MajorityClassBaseline,
    ReceivingTeamWinsBaseline,
    ServingTeamWinsBaseline,
)
from ml.examples import RallyExample


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

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
    raw_start: float = 10.0,
    raw_end: float = 20.0,
) -> RallyExample:
    """Construct a minimal :class:`RallyExample` without touching disk.

    Args:
        score_at_start: Score string, e.g. ``"0-0-2"`` (doubles) or ``"5-3"``
            (singles).
        winner: ``"server"`` or ``"receiver"``.
        winning_team: Ground-truth team index (0 or 1).
        rally_index: Zero-based position within the originating file.
        raw_start: Start timestamp in seconds.
        raw_end: End timestamp in seconds.

    Returns:
        A frozen :class:`RallyExample` with minimal metadata.
    """
    rally_dict = {
        "index": rally_index,
        "score_at_start": score_at_start,
        "winner": winner,
        "winning_team": winning_team,
        "is_post_game": False,
        "comment": None,
        "raw": {"start_seconds": raw_start, "end_seconds": raw_end},
    }
    return RallyExample.from_rally_dict(
        source_json_path=_FAKE_JSON_PATH,
        video_path=_FAKE_VIDEO_PATH,
        court_corners=_FAKE_CORNERS,
        schema_version="1.1",
        generated_by="manual",
        rally_dict=rally_dict,
    )


# ---------------------------------------------------------------------------
# Doubles fixture examples (score_at_start has 3 parts)
# ---------------------------------------------------------------------------

# Team 0 serving (game start): server wins -> winning_team = 0
_DOUBLES_SERVER_WINS = _make_example("0-0-2", "server", 0, rally_index=0)

# Team 0 serving: receiver wins -> winning_team = 1
_DOUBLES_RECEIVER_WINS = _make_example("1-0-2", "receiver", 1, rally_index=1)

# Team 1 serving (after side-out): server wins -> winning_team = 1
# score_at_start "0-1-1" means team 1 has 1 point, team 0 has 0, server 1
_DOUBLES_T1_SERVER_WINS = _make_example("0-1-1", "server", 1, rally_index=2)

# Team 1 serving: receiver wins -> winning_team = 0
_DOUBLES_T1_RECEIVER_WINS = _make_example("1-1-2", "receiver", 0, rally_index=3)


# ---------------------------------------------------------------------------
# Singles fixture examples (score_at_start has 2 parts)
# ---------------------------------------------------------------------------

# Team 0 serving: server wins -> winning_team = 0
_SINGLES_SERVER_WINS = _make_example("5-3", "server", 0, rally_index=0)

# Team 0 serving: receiver wins -> winning_team = 1
_SINGLES_RECEIVER_WINS = _make_example("5-4", "receiver", 1, rally_index=1)


# ---------------------------------------------------------------------------
# Example with invalid score (empty score_parts, server_num=None)
# ---------------------------------------------------------------------------

_INVALID_SCORE = _make_example("", "server", 0, rally_index=99)


# ---------------------------------------------------------------------------
# TestAlwaysTeam0Baseline
# ---------------------------------------------------------------------------


class TestAlwaysTeam0Baseline:
    """AlwaysTeam0Baseline returns 0 for every example regardless of content."""

    @pytest.fixture()
    def baseline(self) -> AlwaysTeam0Baseline:
        return AlwaysTeam0Baseline()

    def test_predict_doubles_server_wins(self, baseline: AlwaysTeam0Baseline) -> None:
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 0

    def test_predict_doubles_receiver_wins(self, baseline: AlwaysTeam0Baseline) -> None:
        """Still returns 0 even when the receiver actually won."""
        assert baseline.predict(_DOUBLES_RECEIVER_WINS) == 0

    def test_predict_singles_server_wins(self, baseline: AlwaysTeam0Baseline) -> None:
        assert baseline.predict(_SINGLES_SERVER_WINS) == 0

    def test_predict_singles_receiver_wins(self, baseline: AlwaysTeam0Baseline) -> None:
        assert baseline.predict(_SINGLES_RECEIVER_WINS) == 0

    def test_predict_invalid_score(self, baseline: AlwaysTeam0Baseline) -> None:
        assert baseline.predict(_INVALID_SCORE) == 0

    def test_predict_returns_int(self, baseline: AlwaysTeam0Baseline) -> None:
        assert isinstance(baseline.predict(_DOUBLES_SERVER_WINS), int)


# ---------------------------------------------------------------------------
# TestAlwaysTeam1Baseline
# ---------------------------------------------------------------------------


class TestAlwaysTeam1Baseline:
    """AlwaysTeam1Baseline returns 1 for every example regardless of content."""

    @pytest.fixture()
    def baseline(self) -> AlwaysTeam1Baseline:
        return AlwaysTeam1Baseline()

    def test_predict_doubles_server_wins(self, baseline: AlwaysTeam1Baseline) -> None:
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 1

    def test_predict_doubles_receiver_wins(self, baseline: AlwaysTeam1Baseline) -> None:
        assert baseline.predict(_DOUBLES_RECEIVER_WINS) == 1

    def test_predict_singles_server_wins(self, baseline: AlwaysTeam1Baseline) -> None:
        assert baseline.predict(_SINGLES_SERVER_WINS) == 1

    def test_predict_singles_receiver_wins(self, baseline: AlwaysTeam1Baseline) -> None:
        assert baseline.predict(_SINGLES_RECEIVER_WINS) == 1

    def test_predict_invalid_score(self, baseline: AlwaysTeam1Baseline) -> None:
        assert baseline.predict(_INVALID_SCORE) == 1

    def test_predict_returns_int(self, baseline: AlwaysTeam1Baseline) -> None:
        assert isinstance(baseline.predict(_DOUBLES_SERVER_WINS), int)


# ---------------------------------------------------------------------------
# TestMajorityClassBaseline
# ---------------------------------------------------------------------------


class TestMajorityClassBaseline:
    """MajorityClassBaseline learns the majority winning_team from training data."""

    @pytest.fixture()
    def baseline(self) -> MajorityClassBaseline:
        return MajorityClassBaseline()

    def test_default_majority_class_is_0(self, baseline: MajorityClassBaseline) -> None:
        """Before fitting, majority_class defaults to 0."""
        assert baseline.majority_class == 0

    def test_predict_before_fit_returns_0(self, baseline: MajorityClassBaseline) -> None:
        """predict() before fit() uses the default majority_class of 0."""
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 0

    def test_fit_all_team_0_wins(self, baseline: MajorityClassBaseline) -> None:
        """When all training examples have winning_team=0, majority is 0."""
        examples = [
            _make_example("0-0-2", "server", 0),
            _make_example("1-0-2", "server", 0),
            _make_example("2-0-2", "server", 0),
        ]
        baseline.fit(examples)
        assert baseline.majority_class == 0

    def test_fit_all_team_1_wins(self, baseline: MajorityClassBaseline) -> None:
        """When all training examples have winning_team=1, majority is 1."""
        examples = [
            _make_example("0-0-2", "receiver", 1),
            _make_example("0-1-1", "server", 1),
        ]
        baseline.fit(examples)
        assert baseline.majority_class == 1

    def test_fit_majority_team_0(self, baseline: MajorityClassBaseline) -> None:
        """3 team-0 wins vs 2 team-1 wins -> majority is 0."""
        examples = [
            _make_example("0-0-2", "server", 0),
            _make_example("1-0-2", "server", 0),
            _make_example("2-0-2", "server", 0),
            _make_example("0-3-1", "receiver", 0),
            _make_example("0-1-1", "server", 1),
            _make_example("1-1-1", "receiver", 0),
        ]
        # Count: 5 x team0, 1 x team1 -> majority = 0
        baseline.fit(examples)
        assert baseline.majority_class == 0

    def test_fit_majority_team_1(self, baseline: MajorityClassBaseline) -> None:
        """2 team-0 wins vs 3 team-1 wins -> majority is 1."""
        examples = [
            _make_example("0-0-2", "server", 0),
            _make_example("1-0-2", "receiver", 1),
            _make_example("0-1-1", "server", 1),
            _make_example("1-1-1", "server", 1),
            _make_example("2-1-1", "receiver", 0),
        ]
        # Count: 2 x team0, 3 x team1 -> majority = 1
        baseline.fit(examples)
        assert baseline.majority_class == 1

    def test_fit_tie_resolves_to_0(self, baseline: MajorityClassBaseline) -> None:
        """Equal counts of team-0 and team-1 wins resolves to 0 (deterministic)."""
        examples = [
            _make_example("0-0-2", "server", 0),
            _make_example("0-0-1", "server", 1),
        ]
        baseline.fit(examples)
        assert baseline.majority_class == 0

    def test_fit_empty_list_leaves_default(self, baseline: MajorityClassBaseline) -> None:
        """Fitting on an empty list leaves majority_class at default 0."""
        baseline.fit([])
        assert baseline.majority_class == 0

    def test_predict_after_fit_is_constant(self, baseline: MajorityClassBaseline) -> None:
        """predict() returns the same value for every example after fitting."""
        examples = [
            _make_example("0-1-1", "server", 1),
            _make_example("1-1-1", "server", 1),
            _make_example("2-1-1", "server", 1),
        ]
        baseline.fit(examples)
        # Majority is 1; every prediction must return 1 regardless of example content.
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 1
        assert baseline.predict(_DOUBLES_RECEIVER_WINS) == 1
        assert baseline.predict(_SINGLES_SERVER_WINS) == 1

    def test_predict_returns_int(self, baseline: MajorityClassBaseline) -> None:
        baseline.fit([_make_example("0-0-2", "server", 0)])
        assert isinstance(baseline.predict(_DOUBLES_SERVER_WINS), int)


# ---------------------------------------------------------------------------
# TestServingTeamWinsBaseline
# ---------------------------------------------------------------------------


class TestServingTeamWinsBaseline:
    """ServingTeamWinsBaseline uses score-part-count guard + server-wins logic.

    Convention: team 0 is treated as the serving team.

    Prediction rule:
        winner == "server"   -> predict 0  (serving team = team 0 by convention)
        winner == "receiver" -> predict 1  (receiving team = team 1 by convention)
        invalid score_parts  -> predict 0  (fallback)

    The score-part-count guard (2 = singles, 3 = doubles) is the same guard
    used in ml.tools.backfill_winner_labels._backfill_game.
    """

    @pytest.fixture()
    def baseline(self) -> ServingTeamWinsBaseline:
        return ServingTeamWinsBaseline()

    # -- doubles examples (3-part score) ------------------------------------

    def test_doubles_server_wins_predicts_0(self, baseline: ServingTeamWinsBaseline) -> None:
        """Doubles, winner=server -> predict 0 (serving team by convention)."""
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 0

    def test_doubles_receiver_wins_predicts_1(self, baseline: ServingTeamWinsBaseline) -> None:
        """Doubles, winner=receiver -> predict 1 (receiving team by convention)."""
        assert baseline.predict(_DOUBLES_RECEIVER_WINS) == 1

    def test_doubles_t1_server_wins_predicts_0(self, baseline: ServingTeamWinsBaseline) -> None:
        """Doubles with team-1 serving, winner=server -> predict 0 (convention: server=team0).

        This example demonstrates where the baseline is imprecise: the actual server
        is team 1, but the baseline predicts 0 (team 0) because it cannot determine
        the absolute serving team from a single RallyExample.
        """
        assert baseline.predict(_DOUBLES_T1_SERVER_WINS) == 0

    def test_doubles_t1_receiver_wins_predicts_1(self, baseline: ServingTeamWinsBaseline) -> None:
        """Doubles with team-1 serving, winner=receiver -> predict 1 (convention: receiver=team1)."""
        assert baseline.predict(_DOUBLES_T1_RECEIVER_WINS) == 1

    # -- singles examples (2-part score) ------------------------------------

    def test_singles_server_wins_predicts_0(self, baseline: ServingTeamWinsBaseline) -> None:
        """Singles, winner=server -> predict 0."""
        assert baseline.predict(_SINGLES_SERVER_WINS) == 0

    def test_singles_receiver_wins_predicts_1(self, baseline: ServingTeamWinsBaseline) -> None:
        """Singles, winner=receiver -> predict 1."""
        assert baseline.predict(_SINGLES_RECEIVER_WINS) == 1

    # -- score-part-count guard edge cases ----------------------------------

    def test_invalid_score_parts_falls_back_to_0(self, baseline: ServingTeamWinsBaseline) -> None:
        """Empty score_parts (unrecognised format) falls back to 0."""
        assert baseline.predict(_INVALID_SCORE) == 0

    def test_predict_returns_int(self, baseline: ServingTeamWinsBaseline) -> None:
        assert isinstance(baseline.predict(_DOUBLES_SERVER_WINS), int)

    def test_predict_value_in_0_1(self, baseline: ServingTeamWinsBaseline) -> None:
        for ex in [
            _DOUBLES_SERVER_WINS,
            _DOUBLES_RECEIVER_WINS,
            _SINGLES_SERVER_WINS,
            _SINGLES_RECEIVER_WINS,
            _INVALID_SCORE,
        ]:
            assert baseline.predict(ex) in (0, 1)


# ---------------------------------------------------------------------------
# TestReceivingTeamWinsBaseline
# ---------------------------------------------------------------------------


class TestReceivingTeamWinsBaseline:
    """ReceivingTeamWinsBaseline uses score-part-count guard + receiver-wins logic.

    Prediction rule (inverse of ServingTeamWinsBaseline):
        winner == "receiver" -> predict 1  (receiving team = team 1 by convention)
        winner == "server"   -> predict 0  (serving team = team 0 by convention)
        invalid score_parts  -> predict 0  (fallback)
    """

    @pytest.fixture()
    def baseline(self) -> ReceivingTeamWinsBaseline:
        return ReceivingTeamWinsBaseline()

    # -- doubles examples ---------------------------------------------------

    def test_doubles_receiver_wins_predicts_1(self, baseline: ReceivingTeamWinsBaseline) -> None:
        """Doubles, winner=receiver -> predict 1."""
        assert baseline.predict(_DOUBLES_RECEIVER_WINS) == 1

    def test_doubles_server_wins_predicts_0(self, baseline: ReceivingTeamWinsBaseline) -> None:
        """Doubles, winner=server -> predict 0 (not a receiver win)."""
        assert baseline.predict(_DOUBLES_SERVER_WINS) == 0

    def test_doubles_t1_receiver_wins_predicts_1(
        self, baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Doubles with team-1 serving, winner=receiver -> predict 1."""
        assert baseline.predict(_DOUBLES_T1_RECEIVER_WINS) == 1

    def test_doubles_t1_server_wins_predicts_0(
        self, baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Doubles with team-1 serving, winner=server -> predict 0."""
        assert baseline.predict(_DOUBLES_T1_SERVER_WINS) == 0

    # -- singles examples ---------------------------------------------------

    def test_singles_receiver_wins_predicts_1(
        self, baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Singles, winner=receiver -> predict 1."""
        assert baseline.predict(_SINGLES_RECEIVER_WINS) == 1

    def test_singles_server_wins_predicts_0(self, baseline: ReceivingTeamWinsBaseline) -> None:
        """Singles, winner=server -> predict 0."""
        assert baseline.predict(_SINGLES_SERVER_WINS) == 0

    # -- guard edge cases ---------------------------------------------------

    def test_invalid_score_parts_falls_back_to_0(
        self, baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Empty score_parts (unrecognised format) falls back to 0."""
        assert baseline.predict(_INVALID_SCORE) == 0

    def test_predict_returns_int(self, baseline: ReceivingTeamWinsBaseline) -> None:
        assert isinstance(baseline.predict(_DOUBLES_RECEIVER_WINS), int)

    def test_predict_value_in_0_1(self, baseline: ReceivingTeamWinsBaseline) -> None:
        for ex in [
            _DOUBLES_SERVER_WINS,
            _DOUBLES_RECEIVER_WINS,
            _SINGLES_SERVER_WINS,
            _SINGLES_RECEIVER_WINS,
            _INVALID_SCORE,
        ]:
            assert baseline.predict(ex) in (0, 1)


# ---------------------------------------------------------------------------
# TestBaselineNames
# ---------------------------------------------------------------------------


class TestBaselineNames:
    """Each baseline exposes a non-empty, string .name attribute."""

    def test_always_team_0_has_name(self) -> None:
        assert isinstance(AlwaysTeam0Baseline().name, str)
        assert AlwaysTeam0Baseline().name != ""

    def test_always_team_1_has_name(self) -> None:
        assert isinstance(AlwaysTeam1Baseline().name, str)
        assert AlwaysTeam1Baseline().name != ""

    def test_majority_class_has_name(self) -> None:
        assert isinstance(MajorityClassBaseline().name, str)
        assert MajorityClassBaseline().name != ""

    def test_serving_team_wins_has_name(self) -> None:
        assert isinstance(ServingTeamWinsBaseline().name, str)
        assert ServingTeamWinsBaseline().name != ""

    def test_receiving_team_wins_has_name(self) -> None:
        assert isinstance(ReceivingTeamWinsBaseline().name, str)
        assert ReceivingTeamWinsBaseline().name != ""

    def test_all_names_are_distinct(self) -> None:
        """Every baseline must have a unique name so reports are unambiguous."""
        names = [
            AlwaysTeam0Baseline().name,
            AlwaysTeam1Baseline().name,
            MajorityClassBaseline().name,
            ServingTeamWinsBaseline().name,
            ReceivingTeamWinsBaseline().name,
        ]
        assert len(names) == len(set(names)), f"Duplicate names found: {names}"


# ---------------------------------------------------------------------------
# TestScorePartCountGuard
# ---------------------------------------------------------------------------


class TestScorePartCountGuard:
    """The score-part-count guard (singles=2, doubles=3) behaves correctly.

    Mirrors the guard in _backfill_game:
        expected_parts = 2 if game_type == "singles" else 3
    """

    @pytest.fixture()
    def serving_baseline(self) -> ServingTeamWinsBaseline:
        return ServingTeamWinsBaseline()

    @pytest.fixture()
    def receiving_baseline(self) -> ReceivingTeamWinsBaseline:
        return ReceivingTeamWinsBaseline()

    def test_two_part_score_is_valid(self, serving_baseline: ServingTeamWinsBaseline) -> None:
        """2-part score (singles) passes the guard and produces a non-fallback result."""
        singles = _make_example("7-5", "server", 0)
        # singles score_parts = (7, 5) — 2 parts — should not fall back to 0 unconditionally
        # winner == "server" -> predict 0 (valid path through guard)
        assert serving_baseline.predict(singles) == 0

    def test_three_part_score_is_valid(self, serving_baseline: ServingTeamWinsBaseline) -> None:
        """3-part score (doubles) passes the guard."""
        doubles = _make_example("3-2-1", "receiver", 0)
        # winner == "receiver" -> predict 1 (valid path through guard)
        assert serving_baseline.predict(doubles) == 1

    def test_empty_score_parts_falls_back(
        self, serving_baseline: ServingTeamWinsBaseline
    ) -> None:
        """score_parts == () (empty string score) triggers the fallback -> 0."""
        assert serving_baseline.predict(_INVALID_SCORE) == 0

    def test_empty_score_parts_falls_back_receiving(
        self, receiving_baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Same fallback applies for ReceivingTeamWinsBaseline."""
        assert receiving_baseline.predict(_INVALID_SCORE) == 0

    def test_guard_singles_receiver_wins(
        self, receiving_baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Singles, 2-part score, receiver wins -> predict 1 through the guard."""
        singles_recv = _make_example("4-6", "receiver", 1)
        assert receiving_baseline.predict(singles_recv) == 1

    def test_guard_doubles_server_wins(
        self, receiving_baseline: ReceivingTeamWinsBaseline
    ) -> None:
        """Doubles, 3-part score, server wins -> predict 0 (not a receiver win)."""
        doubles_srv = _make_example("5-4-2", "server", 0)
        assert receiving_baseline.predict(doubles_srv) == 0
