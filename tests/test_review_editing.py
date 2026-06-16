"""Tests for review-mode editing APIs (set_rally_timing, cascade serving_team seed).

Pure-logic; no Qt required.  All tests use real ScoreState / RallyManager
instances — no mocks — to exercise the actual scoring rules.

Coverage
--------
TestSetRallyTiming
  - Rounding: set_rally_timing uses round(), not int() (floor).
  - Validation: out-of-range index raises IndexError; start<0 raises ValueError;
    end<start raises ValueError.
  - Single-endpoint: setting only start leaves all end raw fields unchanged
    (end_frame clamped if needed); setting only end leaves all start raw fields
    unchanged.
  - Padded frames: start_frame and end_frame include START_PADDING / END_PADDING
    after an absolute set.

TestSetServingTeam
  - No-op when the same team is already serving (server_number unchanged).
  - Switches team, resets server_number to 1 (doubles).
  - Invalid value raises ValueError.
  - Singles: server_number stays None after a switch.
  - Doubles: first_server_player_index recalculated from new serving team's score.

TestCascadeWithServingTeam
  - serving_team=None is byte-for-byte identical to the default two-arg call.
  - serving_team=2 (invalid) raises ValueError before any mutation.
  - Seeding serving_team=1 at an originally team-0 anchor flips score attribution.
  - Full anchor scenario: serving_team + new_score at mid-list rally produces
    correct score strings in all downstream rallies.

TestScoringRules
  - Only the serving team's score increments on server_wins.
  - receiver_wins does not change score tallies.
  - force_side_out does not change score tallies.
  - Doubles rotation: receiver win at server 1 → server 2 (same team).
  - Doubles rotation: receiver win at server 2 → side-out to other team server 1.
  - Doubles 0-0-2 opening: receiver win → immediate side-out (score "0-0-1").
  - Win-by-2 for victory rule "11": tied 11-11 is not over; 12-10 is.
  - Win-by-2 for victory rule "9": 9-7 is over; 9-8 is not.
  - Timed games: is_game_over() always returns (False, None).
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from src.core.models import Rally, ScoreSnapshot
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState

# ---------------------------------------------------------------------------
# Stub heavy ML/torch dependencies so importing src.ui.review_mode succeeds on
# machines without those packages.  This mirrors the pattern used in
# tests/test_winner_flip.py.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]

try:
    from src.ui.review_mode import _parse_time_input as _parse_time_input_fn
    _PARSE_TIME_IMPORTABLE = True
except Exception:
    _parse_time_input_fn = None  # type: ignore[assignment]
    _PARSE_TIME_IMPORTABLE = False


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_PLAYER_NAMES = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
_SINGLES_NAMES = {"team1": ["Alice"], "team2": ["Bob"]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_doubles_manager(
    player_names: dict | None = None,
    fps: float = 60.0,
    rally_count: int = 5,
) -> tuple[RallyManager, list[str]]:
    """Return a RallyManager with *rally_count* doubles rallies (all server wins).

    Uses start_rally / end_rally so every Rally has raw_* timing fields set and
    score_snapshot_at_start populated — required for cascade_scores_from to
    restore the correct serving-team orientation.

    Rally sequence (0-0-2 opening, all server wins):
        i: i-0-2  server_wins → (i+1)-0-2

    Returns (manager, original_score_at_start_list).
    """
    if player_names is None:
        player_names = _PLAYER_NAMES

    ss = ScoreState("doubles", "11", player_names)
    manager = RallyManager(fps=fps)
    original_scores: list[str] = []

    for i in range(rally_count):
        score_str = ss.get_score_string()
        original_scores.append(score_str)

        snapshot = ScoreSnapshot(
            score=tuple(ss.score),
            serving_team=ss.serving_team,
            server_number=ss.server_number,
            first_server_player_index=ss.first_server_player_index,
        )
        start_ts = float(i * 20 + 10)
        end_ts = float(i * 20 + 15)

        manager.start_rally(start_ts, snapshot)
        manager.end_rally(end_ts, "server", score_str, snapshot)

        ss.server_wins()

    return manager, original_scores


def _make_timed_manager(
    fps: float = 60.0,
    start_seconds: float = 10.0,
    end_seconds: float = 15.0,
) -> RallyManager:
    """Return a RallyManager containing one fully-timed rally.

    Uses start_rally / end_rally so raw_start_seconds and raw_end_seconds are
    populated; these are needed by set_rally_timing's cross-validation logic.
    """
    snapshot = ScoreSnapshot(
        score=(0, 0),
        serving_team=0,
        server_number=2,
        first_server_player_index=1,
    )
    manager = RallyManager(fps=fps)
    manager.start_rally(start_seconds, snapshot)
    manager.end_rally(end_seconds, "server", "0-0-2", snapshot)
    return manager


# ===========================================================================
# TestSetRallyTiming
# ===========================================================================

class TestSetRallyTiming:
    """Absolute timing setter: rounding, validation, single-endpoint, padding."""

    # -- Rounding behaviour --------------------------------------------------

    def test_start_frame_uses_round_not_floor(self):
        """set_rally_timing rounds the padded start time (round ≠ int for x.6)."""
        # fps=10, start_seconds=1.16:
        #   padded = 1.16 + START_PADDING = 1.16 - 0.5 = 0.66
        #   round(0.66 * 10) = round(6.6) = 7   ← correct
        #   int(0.66 * 10)   = int(6.6)   = 6   ← would be wrong (floor)
        manager = _make_timed_manager(fps=10.0, start_seconds=5.0, end_seconds=10.0)

        manager.set_rally_timing(0, start_seconds=1.16, end_seconds=9.0)

        assert manager.rallies[0].start_frame == 7, (
            f"Expected start_frame=7 (round), got {manager.rallies[0].start_frame}"
        )

    def test_raw_start_frame_uses_round_not_floor(self):
        """raw_start_frame is also computed with round(), not int()."""
        # fps=10, start_seconds=1.16:
        #   round(1.16 * 10) = round(11.6) = 12   ← correct
        #   int(1.16 * 10)   = int(11.6)   = 11   ← would be wrong (floor)
        manager = _make_timed_manager(fps=10.0, start_seconds=5.0, end_seconds=10.0)

        manager.set_rally_timing(0, start_seconds=1.16, end_seconds=9.0)

        assert manager.rallies[0].raw_start_frame == 12, (
            f"Expected raw_start_frame=12 (round), got {manager.rallies[0].raw_start_frame}"
        )

    def test_end_frame_uses_round_not_floor(self):
        """end_frame (with END_PADDING) is computed with round(), not int()."""
        # fps=10, end_seconds=5.17:
        #   end_frame = round((5.17 + 1.0) * 10) = round(61.7) = 62   ← correct
        #   int(61.7) = 61   ← would be wrong (floor)
        manager = _make_timed_manager(fps=10.0, start_seconds=1.0, end_seconds=5.0)

        manager.set_rally_timing(0, start_seconds=1.0, end_seconds=5.17)

        assert manager.rallies[0].end_frame == 62, (
            f"Expected end_frame=62 (round), got {manager.rallies[0].end_frame}"
        )

    # -- Validation ----------------------------------------------------------

    def test_out_of_range_index_raises_index_error(self):
        """set_rally_timing raises IndexError for an index beyond the list."""
        manager = RallyManager(fps=60.0)  # empty
        with pytest.raises(IndexError):
            manager.set_rally_timing(0, start_seconds=5.0)

    def test_negative_start_seconds_raises_value_error(self):
        """Negative start_seconds is rejected before any field is mutated."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=10.0)
        original_start_frame = manager.rallies[0].start_frame

        with pytest.raises(ValueError, match="start_seconds must be >= 0"):
            manager.set_rally_timing(0, start_seconds=-1.0)

        # No mutation occurred
        assert manager.rallies[0].start_frame == original_start_frame

    def test_negative_end_seconds_raises_value_error(self):
        """Negative end_seconds is rejected even when raw_start_seconds is None (legacy rally)."""
        # A rally without raw_start_seconds (e.g. imported from old session) must
        # still reject a negative end_seconds — the previous code skipped this
        # check when eff_start was None.
        manager = RallyManager(fps=60.0)
        from src.core.models import Rally
        legacy = Rally(start_frame=0, end_frame=100, score_at_start="0-0-2", winner="server")
        # Deliberately leave raw_start_seconds = None (legacy rally)
        manager.rallies.append(legacy)

        with pytest.raises(ValueError, match="end_seconds must be >= 0"):
            manager.set_rally_timing(0, end_seconds=-1.0)

        # No mutation occurred
        assert manager.rallies[0].end_frame == 100

    def test_end_before_start_raises_value_error_when_both_supplied(self):
        """end_seconds < start_seconds raises ValueError before any mutation."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=10.0)

        with pytest.raises(ValueError, match="end_seconds.*must be >= start_seconds"):
            manager.set_rally_timing(0, start_seconds=8.0, end_seconds=6.0)

    def test_end_before_existing_raw_start_raises_value_error(self):
        """Supplying only end_seconds that is < current raw_start_seconds raises."""
        # raw_start_seconds = 10.0, but we supply end_seconds = 5.0
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)

        with pytest.raises(ValueError, match="end_seconds.*must be >= start_seconds"):
            manager.set_rally_timing(0, end_seconds=5.0)

    # -- Single-endpoint behaviour -------------------------------------------

    def test_set_start_only_leaves_raw_end_seconds_unchanged(self):
        """Setting only start_seconds leaves raw_end_seconds untouched."""
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)

        manager.set_rally_timing(0, start_seconds=8.0)

        assert manager.rallies[0].raw_end_seconds == 20.0

    def test_set_start_only_leaves_raw_end_frame_unchanged(self):
        """Setting only start_seconds leaves raw_end_frame untouched."""
        # raw_end_frame was computed by _time_to_frame (int floor) = int(20.0*60) = 1200
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)
        original_raw_end_frame = manager.rallies[0].raw_end_frame

        manager.set_rally_timing(0, start_seconds=8.0)

        assert manager.rallies[0].raw_end_frame == original_raw_end_frame

    def test_set_end_only_leaves_raw_start_seconds_unchanged(self):
        """Setting only end_seconds leaves raw_start_seconds untouched."""
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)

        manager.set_rally_timing(0, end_seconds=25.0)

        assert manager.rallies[0].raw_start_seconds == 10.0

    def test_set_end_only_leaves_start_frame_unchanged(self):
        """Setting only end_seconds leaves start_frame untouched."""
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)
        original_start_frame = manager.rallies[0].start_frame

        manager.set_rally_timing(0, end_seconds=25.0)

        assert manager.rallies[0].start_frame == original_start_frame

    def test_set_end_only_updates_end_frame_with_padding(self):
        """Setting only end_seconds updates end_frame = round((end + END_PADDING) * fps)."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=10.0)

        manager.set_rally_timing(0, end_seconds=20.0)

        # end_frame = round((20.0 + 1.0) * 60) = round(1260) = 1260
        assert manager.rallies[0].end_frame == 1260

    # -- Padded frames -------------------------------------------------------

    def test_padded_start_frame_reflects_start_padding(self):
        """start_frame = round(max(0, start + START_PADDING) * fps)."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=15.0)

        manager.set_rally_timing(0, start_seconds=5.0, end_seconds=15.0)

        # padded = max(0, 5.0 + (-0.5)) = 4.5
        # round(4.5 * 60) = round(270.0) = 270
        assert manager.rallies[0].start_frame == 270

    def test_padded_end_frame_reflects_end_padding(self):
        """end_frame = round((end + END_PADDING) * fps)."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=15.0)

        manager.set_rally_timing(0, start_seconds=5.0, end_seconds=15.0)

        # round((15.0 + 1.0) * 60) = round(960.0) = 960
        assert manager.rallies[0].end_frame == 960

    def test_start_padding_at_video_start_clamps_to_zero(self):
        """start_frame is clamped to 0 when start_seconds < |START_PADDING|."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=10.0)

        # start_seconds=0.1: padded = max(0, 0.1 - 0.5) = max(0, -0.4) = 0
        manager.set_rally_timing(0, start_seconds=0.1, end_seconds=10.0)

        assert manager.rallies[0].start_frame == 0

    def test_raw_fields_updated_correctly(self):
        """raw_start_seconds, raw_end_seconds match the supplied values exactly."""
        manager = _make_timed_manager(fps=60.0, start_seconds=10.0, end_seconds=20.0)

        manager.set_rally_timing(0, start_seconds=12.5, end_seconds=18.0)

        assert manager.rallies[0].raw_start_seconds == 12.5
        assert manager.rallies[0].raw_end_seconds == 18.0

    def test_both_none_is_no_op(self):
        """Calling set_rally_timing with no endpoint args leaves rally unchanged."""
        manager = _make_timed_manager(fps=60.0, start_seconds=5.0, end_seconds=10.0)
        original_start = manager.rallies[0].start_frame
        original_end = manager.rallies[0].end_frame

        result = manager.set_rally_timing(0)  # start_seconds=None, end_seconds=None

        assert result is manager.rallies[0]
        assert manager.rallies[0].start_frame == original_start
        assert manager.rallies[0].end_frame == original_end


# ===========================================================================
# TestSetServingTeam
# ===========================================================================

class TestSetServingTeam:
    """ScoreState.set_serving_team sets serving team without changing score tallies."""

    def test_no_op_when_same_team_already_serving(self):
        """Calling set_serving_team with the team already serving is a no-op."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # Default: serving_team=0, server_number=2, first_server_player_index=1
        original_server_number = ss.server_number
        original_first_server = ss.first_server_player_index

        ss.set_serving_team(0)  # team 0 is already serving — no-op

        assert ss.server_number == original_server_number
        assert ss.first_server_player_index == original_first_server

    def test_switches_serving_team(self):
        """set_serving_team(1) changes serving_team from 0 to 1."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        ss.set_serving_team(1)

        assert ss.serving_team == 1

    def test_doubles_switch_resets_server_number_to_one(self):
        """Switching to a different team resets server_number to 1 in doubles."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # Default server_number is 2 (game start).
        assert ss.server_number == 2

        ss.set_serving_team(1)

        assert ss.server_number == 1

    def test_invalid_value_raises_value_error(self):
        """set_serving_team raises ValueError for any value other than 0 or 1."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        with pytest.raises(ValueError, match="serving_team must be 0 or 1"):
            ss.set_serving_team(2)

    def test_singles_switch_does_not_change_server_number(self):
        """Singles has no server_number; switching teams leaves it None."""
        ss = ScoreState("singles", "11", _SINGLES_NAMES)
        assert ss.server_number is None

        ss.set_serving_team(1)

        assert ss.server_number is None
        assert ss.serving_team == 1

    def test_score_tallies_unchanged_after_switch(self):
        """Switching serving team must not alter score values."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [3, 5]

        ss.set_serving_team(1)

        assert ss.score == [3, 5]

    def test_doubles_recalculates_first_server_even_score(self):
        """After switching to a team whose score is even, first_server_player_index=0."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [3, 4]  # team1 (index 1) has score 4 — even

        ss.set_serving_team(1)

        assert ss.first_server_player_index == 0  # even → player 0 is first server

    def test_doubles_recalculates_first_server_odd_score(self):
        """After switching to a team whose score is odd, first_server_player_index=1."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [3, 5]  # team1 (index 1) has score 5 — odd

        ss.set_serving_team(1)

        assert ss.first_server_player_index == 1  # odd → player 1 is first server

    def test_round_trip_switch_recomputes_first_server(self):
        """Switching team0→1→0 recalculates first_server each time."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [7, 4]  # team0 score=7 (odd), team1 score=4 (even)

        ss.set_serving_team(1)  # team1: score=4 (even) → first_server=0
        assert ss.first_server_player_index == 0

        ss.set_serving_team(0)  # team0: score=7 (odd) → first_server=1
        assert ss.first_server_player_index == 1


# ===========================================================================
# TestCascadeWithServingTeam
# ===========================================================================

class TestCascadeWithServingTeam:
    """cascade_scores_from with explicit serving_team seed."""

    def test_serving_team_none_matches_default_behavior(self):
        """cascade_scores_from(serving_team=None) is byte-for-byte identical to no arg."""
        manager1, _ = _build_doubles_manager()
        manager2, _ = _build_doubles_manager()

        ss1 = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss2 = ScoreState("doubles", "11", _PLAYER_NAMES)

        manager1.cascade_scores_from(1, ss1)
        manager2.cascade_scores_from(1, ss2, serving_team=None)

        for i, (r1, r2) in enumerate(zip(manager1.rallies, manager2.rallies)):
            assert r1.score_at_start == r2.score_at_start, (
                f"Rally {i}: default={r1.score_at_start!r} vs "
                f"serving_team=None={r2.score_at_start!r}"
            )

    def test_invalid_serving_team_raises_value_error_before_mutation(self):
        """serving_team=2 raises ValueError and does NOT mutate any rally."""
        manager, original_scores = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        with pytest.raises(ValueError):
            manager.cascade_scores_from(0, ss, serving_team=2)

        # All score strings must be unchanged.
        for i, rally in enumerate(manager.rallies):
            assert rally.score_at_start == original_scores[i], (
                f"Rally {i} was mutated despite ValueError: {rally.score_at_start!r}"
            )

    def test_serving_team_seed_updates_anchor_score_string(self):
        """Seeding serving_team=1 at the anchor rally refreshes its score string."""
        manager, _ = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        # rally[0] snapshot: score=[0,0], serving_team=0, server_number=2
        # After set_serving_team(1): serving_team=1, server_number=1, first_server=0
        # get_score_string(): serving=score[1]=0, receiving=score[0]=0, server#=1 → "0-0-1"
        manager.cascade_scores_from(0, ss, serving_team=1)

        assert manager.rallies[0].score_at_start == "0-0-1"

    def test_serving_team_seed_cascades_downstream_correctly(self):
        """Downstream rallies after a serving_team flip have correct score strings."""
        manager, _ = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        # Seed: team1 serving at index 0 (score=[0,0] → "0-0-1")
        # rally[0].winner = "server" → score[team1=1] += 1 → score=[0,1]
        # rally[1]: serving=score[1]=1, receiving=score[0]=0, server#=1 → "1-0-1"
        manager.cascade_scores_from(0, ss, serving_team=1)

        assert manager.rallies[1].score_at_start == "1-0-1"
        # rally[1].winner = "server" → score[1] = 2
        # rally[2]: "2-0-1"
        assert manager.rallies[2].score_at_start == "2-0-1"

    def test_rallies_before_anchor_are_unchanged(self):
        """Rallies before the cascade anchor index keep their original score strings."""
        manager, original_scores = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        manager.cascade_scores_from(2, ss, serving_team=1)

        assert manager.rallies[0].score_at_start == original_scores[0]  # "0-0-2"
        assert manager.rallies[1].score_at_start == original_scores[1]  # "1-0-2"

    def test_cascade_returns_empty_changed_indices_without_predictions(self):
        """cascade_scores_from returns [] when no rallies have predicted_team set."""
        manager, _ = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        changed = manager.cascade_scores_from(0, ss, serving_team=1)

        assert changed == []

    def test_full_anchor_cascade_with_serving_team_and_new_score(self):
        """Set serving_team=1 and new_score at rally 2, verify all downstream scores.

        Original state (all server wins):
            rally[0]: 0-0-2, rally[1]: 1-0-2, rally[2]: 2-0-2, ...

        Anchor override at index 2:
            serving_team=1, new_score="0-3-1"
            → set_serving_team(1): team1 now serving
            → set_score("0-3-1"): score[1]=0, score[0]=3, server_number=1

        After:
            rally[2].score_at_start = "0-3-1"
            server wins → score[1] += 1 → [3, 1]
            rally[3].score_at_start = "1-3-1"
            server wins → score[1] += 1 → [3, 2]
            rally[4].score_at_start = "2-3-1"
        """
        manager, _ = _build_doubles_manager()
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)

        manager.cascade_scores_from(2, ss, new_score="0-3-1", serving_team=1)

        # Pre-anchor rallies unchanged
        assert manager.rallies[0].score_at_start == "0-0-2"
        assert manager.rallies[1].score_at_start == "1-0-2"

        # Anchor and downstream
        assert manager.rallies[2].score_at_start == "0-3-1"
        assert manager.rallies[3].score_at_start == "1-3-1"
        assert manager.rallies[4].score_at_start == "2-3-1"


# ===========================================================================
# TestScoringRules
# ===========================================================================

class TestScoringRules:
    """Pickleball scoring rule correctness: server_wins, receiver_wins, rotation, win-by-2."""

    # -- Basic score attribution ---------------------------------------------

    def test_server_wins_increments_serving_team_score(self):
        """server_wins() adds 1 to score[serving_team] and leaves the other alone."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # Drive out of 0-0-2 special state first: receiver win → side-out to team1
        ss.receiver_wins()  # 0-0-2 → team1 server1, score=[0,0]
        ss.server_wins()    # team1 scores → score=[0,1]

        serving = ss.serving_team   # team1 = index 1
        receiving = 1 - serving

        score_before = list(ss.score)
        ss.server_wins()

        assert ss.score[serving] == score_before[serving] + 1
        assert ss.score[receiving] == score_before[receiving]

    def test_receiver_wins_does_not_change_scores(self):
        """receiver_wins() changes who serves but leaves score tallies unchanged."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # Advance out of 0-0-2 to a normal server_number=1 position
        ss.receiver_wins()  # 0-0-2 → team1 server1
        ss.server_wins()    # team1 scores: score=[0,1]

        score_before = list(ss.score)
        ss.receiver_wins()  # team1 server1 → team1 server2

        assert ss.score == score_before

    def test_force_side_out_does_not_change_scores(self):
        """force_side_out() switches the serve without altering score tallies."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.server_wins()   # drive score to [1, 0] (avoids 0-0-2 special case later)

        score_before = list(ss.score)
        ss.force_side_out()

        assert ss.score == score_before

    # -- Doubles rotation ----------------------------------------------------

    def test_doubles_receiver_win_at_server1_switches_to_server2(self):
        """Receiver wins at server 1 → same team keeps serve but at server 2."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # 0-0-2 → receiver wins → team1 server1
        ss.receiver_wins()
        assert ss.serving_team == 1
        assert ss.server_number == 1

        serving_team_before = ss.serving_team
        ss.receiver_wins()   # team1 server1 loses

        assert ss.serving_team == serving_team_before   # same team still serving
        assert ss.server_number == 2                     # switched to server 2

    def test_doubles_receiver_win_at_server2_causes_side_out(self):
        """Receiver wins at server 2 → side-out to the other team's server 1."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        # 0-0-2 → receiver wins → team1 server1
        ss.receiver_wins()
        serving_team_before = ss.serving_team  # team1 = 1

        # Advance to server 2 without a side-out: server1 receiver loss → server2
        ss.receiver_wins()
        assert ss.server_number == 2

        ss.receiver_wins()   # team1 server2 loses → side-out

        assert ss.serving_team == 1 - serving_team_before   # switched teams
        assert ss.server_number == 1                          # new team at server 1

    def test_doubles_0_0_2_receiver_win_is_immediate_side_out(self):
        """At 0-0-2 (game opening), receiver win is an immediate side-out to team1."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        assert ss.get_score_string() == "0-0-2"

        ss.receiver_wins()

        # After immediate side-out: serving_team=1, server_number=1, score unchanged
        assert ss.serving_team == 1
        assert ss.server_number == 1
        assert ss.score == [0, 0]
        assert ss.get_score_string() == "0-0-1"

    # -- Win-by-2 for standard games -----------------------------------------

    def test_game_11_not_over_when_tied_at_11(self):
        """Victory rule '11': 11-11 is NOT over (need win by 2)."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [11, 11]

        is_over, winner = ss.is_game_over()

        assert not is_over
        assert winner is None

    def test_game_11_not_over_when_leading_by_one(self):
        """Victory rule '11': 11-10 is NOT over (one point shy of win-by-2)."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [11, 10]

        is_over, winner = ss.is_game_over()

        assert not is_over

    def test_game_11_over_when_leading_by_two(self):
        """Victory rule '11': 12-10 IS over; winner is team with 12."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [12, 10]
        ss.serving_team = 0

        is_over, winner = ss.is_game_over()

        assert is_over
        assert winner == 0

    def test_game_11_normal_win_at_eleven_nine(self):
        """Victory rule '11': 11-9 (lead ≥ 2 and at target) IS over."""
        ss = ScoreState("doubles", "11", _PLAYER_NAMES)
        ss.score = [11, 9]
        ss.serving_team = 0

        is_over, winner = ss.is_game_over()

        assert is_over
        assert winner == 0

    def test_game_9_not_over_at_nine_eight(self):
        """Victory rule '9': 9-8 is NOT over (win-by-2 required)."""
        ss = ScoreState("singles", "9", _SINGLES_NAMES)
        ss.score = [9, 8]

        is_over, winner = ss.is_game_over()

        assert not is_over

    def test_game_9_over_at_nine_seven(self):
        """Victory rule '9': 9-7 (lead ≥ 2 at target) IS over."""
        ss = ScoreState("singles", "9", _SINGLES_NAMES)
        ss.score = [9, 7]
        ss.serving_team = 0

        is_over, winner = ss.is_game_over()

        assert is_over
        assert winner == 0

    def test_game_9_over_at_extended_ten_eight(self):
        """Victory rule '9': if tied at 9-9, play extends; 10-8 is over."""
        ss = ScoreState("singles", "9", _SINGLES_NAMES)
        ss.score = [10, 8]
        ss.serving_team = 0

        is_over, winner = ss.is_game_over()

        assert is_over
        assert winner == 0

    def test_timed_game_never_auto_ends(self):
        """Victory rule 'timed': is_game_over() always returns (False, None)."""
        ss = ScoreState("doubles", "timed", _PLAYER_NAMES)
        ss.score = [20, 3]  # absurdly lopsided — still not auto-over

        is_over, winner = ss.is_game_over()

        assert not is_over
        assert winner is None

    def test_timed_game_never_auto_ends_for_singles(self):
        """Timed singles also never auto-ends regardless of score."""
        ss = ScoreState("singles", "timed", _SINGLES_NAMES)
        ss.score = [100, 0]

        is_over, winner = ss.is_game_over()

        assert not is_over
        assert winner is None


# ===========================================================================
# TestParseTimeInput
# ===========================================================================

@pytest.mark.skipif(not _PARSE_TIME_IMPORTABLE, reason="src.ui.review_mode not importable")
class TestParseTimeInput:
    """Unit tests for the _parse_time_input helper (LBYL implementation).

    Covers the full contract: valid plain float, valid MM:SS, valid MM:SS.s,
    empty string, non-numeric, negative plain, and seconds >= 60 in colon form.
    All tests call the real imported function — no reimplementation.
    """

    def test_valid_plain_float(self):
        """Plain float string returns the float value."""
        assert _parse_time_input_fn("12.5") == pytest.approx(12.5)

    def test_valid_mm_ss(self):
        """MM:SS string returns total seconds (83.0 for '1:23')."""
        assert _parse_time_input_fn("1:23") == pytest.approx(83.0)

    def test_valid_mm_ss_decimal(self):
        """MM:SS.s string returns total seconds (83.4 for '1:23.4')."""
        assert _parse_time_input_fn("1:23.4") == pytest.approx(83.4)

    def test_empty_string_returns_none(self):
        """Empty input (or whitespace-only) returns None."""
        assert _parse_time_input_fn("") is None
        assert _parse_time_input_fn("   ") is None

    def test_non_numeric_returns_none(self):
        """Non-numeric string returns None."""
        assert _parse_time_input_fn("abc") is None

    def test_negative_plain_returns_none(self):
        """Negative plain number ('-5') returns None (not a valid timestamp)."""
        assert _parse_time_input_fn("-5") is None

    def test_colon_format_seconds_gte_60_returns_none(self):
        """Colon format with seconds part >= 60 returns None."""
        assert _parse_time_input_fn("1:75") is None
        assert _parse_time_input_fn("0:60") is None

    def test_zero_seconds_plain(self):
        """'0' and '0.0' are valid and return 0.0."""
        assert _parse_time_input_fn("0") == pytest.approx(0.0)
        assert _parse_time_input_fn("0.0") == pytest.approx(0.0)

    def test_colon_format_leading_zeros(self):
        """'00:42.5' (double-zero minutes) returns 42.5."""
        assert _parse_time_input_fn("00:42.5") == pytest.approx(42.5)

    # NOTE: StateAnchorWidget Qt widget tests are not added here because
    # test_review_editing.py is designated "pure-logic; no Qt required".
    # Qt widget coverage for StateAnchorWidget belongs in a test file that
    # already sets up a QApplication fixture (e.g. test_winner_flip.py).
