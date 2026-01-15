"""Tests for ScoreState scoring logic.

Tests singles and doubles pickleball scoring rules including:
- Initialization
- Server wins (point awarded)
- Receiver wins (side-out)
- Server rotation (doubles)
- Game over detection
- Snapshot save/restore (undo support)
"""

import pytest
from src.core.score_state import ScoreState


class TestScoreStateSingles:
    """Test singles scoring rules."""

    def test_init_singles(self):
        """Test singles initialization."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        assert state.score == [0, 0]
        assert state.serving_team == 0
        assert state.server_number is None

    def test_server_wins_singles(self):
        """Test server scoring in singles."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        state.server_wins()
        assert state.score == [1, 0]
        assert state.serving_team == 0  # Still serving

    def test_receiver_wins_singles(self):
        """Test side-out in singles."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        state.receiver_wins()
        assert state.score == [0, 0]  # No point awarded
        assert state.serving_team == 1  # Side-out to opponent

    def test_multiple_server_wins_singles(self):
        """Test consecutive server wins in singles."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        for i in range(1, 6):
            state.server_wins()
            assert state.score == [i, 0]
            assert state.serving_team == 0

    def test_alternating_serves_singles(self):
        """Test alternating serves in singles."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        # Alice scores 2
        state.server_wins()
        state.server_wins()
        assert state.score == [2, 0]

        # Bob gets serve and scores 1
        state.receiver_wins()
        assert state.serving_team == 1
        state.server_wins()
        assert state.score == [2, 1]

    def test_game_over_singles_basic(self):
        """Test game over detection in singles (11-0)."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        # Win 11-0
        for _ in range(11):
            state.server_wins()

        is_over, winner = state.is_game_over()
        assert is_over
        assert winner == 0

    def test_game_over_singles_win_by_two(self):
        """Test win-by-two rule in singles."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        # Score to 10-10
        state.score = [10, 10]
        is_over, winner = state.is_game_over()
        assert not is_over

        # 11-10 still not over
        state.score = [11, 10]
        is_over, winner = state.is_game_over()
        assert not is_over

        # 12-10 is over
        state.score = [12, 10]
        is_over, winner = state.is_game_over()
        assert is_over
        assert winner == 0

    def test_get_score_string_singles(self):
        """Test singles score formatting (X-Y from serving team's perspective)."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        assert state.get_score_string() == "0-0"

        state.server_wins()
        assert state.get_score_string() == "1-0"

        state.receiver_wins()  # Side-out to Bob
        state.server_wins()  # Bob scores
        # From Bob's perspective: 1-1 (Bob has 1, Alice has 1)
        assert state.get_score_string() == "1-1"


class TestScoreStateDoubles:
    """Test doubles scoring rules."""

    def test_init_doubles(self):
        """Test doubles initialization (starts at server 2)."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        assert state.score == [0, 0]
        assert state.serving_team == 0
        assert state.server_number == 2  # Start at server 2

    def test_doubles_first_fault_sideout(self):
        """Test 0-0-2 immediate side-out rule."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        state.receiver_wins()  # First fault
        assert state.serving_team == 1
        assert state.server_number == 1  # Other team starts at server 1

    def test_doubles_server_rotation(self):
        """Test server 1 to server 2 rotation."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        state.receiver_wins()  # Side-out to team 2
        assert state.serving_team == 1
        assert state.server_number == 1

        state.receiver_wins()  # Server 1 loses
        assert state.serving_team == 1  # Same team
        assert state.server_number == 2  # Now server 2

    def test_doubles_server_2_sideout(self):
        """Test server 2 losing causes side-out."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        state.receiver_wins()  # Side-out to team 2, server 1
        state.receiver_wins()  # Now team 2, server 2
        assert state.server_number == 2

        state.receiver_wins()  # Server 2 loses -> side-out
        assert state.serving_team == 0
        assert state.server_number == 1

    def test_doubles_scoring_sequence(self):
        """Test full doubles scoring sequence from serving team's perspective."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        # Start: 0-0-2 (Team 1 serving)
        assert state.get_score_string() == "0-0-2"

        # Team 1 server 2 wins
        state.server_wins()
        assert state.get_score_string() == "1-0-2"

        # Team 1 server 2 wins again
        state.server_wins()
        assert state.get_score_string() == "2-0-2"

        # Team 1 server 2 loses -> side-out to team 2
        state.receiver_wins()
        # Now from Team 2's perspective: 0-2-1 (Team 2 has 0, Team 1 has 2)
        assert state.get_score_string() == "0-2-1"

        # Team 2 server 1 wins
        state.server_wins()
        assert state.get_score_string() == "1-2-1"

        # Team 2 server 1 loses -> team 2 server 2
        state.receiver_wins()
        assert state.get_score_string() == "1-2-2"

    def test_get_score_string_doubles(self):
        """Test doubles score formatting (X-Y-Z from serving team's perspective)."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        assert state.get_score_string() == "0-0-2"

        state.receiver_wins()  # Side-out to Team 2
        # Now from Team 2's perspective: 0-0-1
        assert state.get_score_string() == "0-0-1"

        state.server_wins()  # Team 2 scores
        # From Team 2's perspective: 1-0-1
        assert state.get_score_string() == "1-0-1"

    def test_game_over_doubles(self):
        """Test game over detection in doubles."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        state.score = [11, 5]
        is_over, winner = state.is_game_over()
        assert is_over
        assert winner == 0

        # Test win-by-two
        state.score = [11, 10]
        is_over, winner = state.is_game_over()
        assert not is_over


class TestScoreStateUndo:
    """Test snapshot/restore for undo functionality."""

    def test_save_restore_snapshot_singles(self):
        """Test saving and restoring singles state."""
        state = ScoreState("singles", "11", {"team1": ["A"], "team2": ["B"]})
        state.server_wins()
        state.server_wins()

        snapshot = state.save_snapshot()

        state.receiver_wins()  # Side-out

        state.restore_snapshot(snapshot)
        assert state.score == [2, 0]
        assert state.serving_team == 0

    def test_save_restore_snapshot_doubles(self):
        """Test saving and restoring doubles state including server number."""
        state = ScoreState(
            "doubles", "11", {"team1": ["A", "B"], "team2": ["C", "D"]}
        )
        state.receiver_wins()  # Side-out to team 2
        state.server_wins()  # Team 2 scores

        snapshot = state.save_snapshot()

        state.receiver_wins()  # Team 2 server 1 loses
        state.server_wins()  # Team 2 server 2 wins

        state.restore_snapshot(snapshot)
        assert state.score == [0, 1]
        assert state.serving_team == 1
        assert state.server_number == 1

    def test_multiple_snapshots(self):
        """Test multiple snapshots can be saved and restored."""
        state = ScoreState("singles", "11", {"team1": ["A"], "team2": ["B"]})

        snap1 = state.save_snapshot()  # 0-0
        state.server_wins()

        snap2 = state.save_snapshot()  # 1-0
        state.server_wins()

        snap3 = state.save_snapshot()  # 2-0

        # Restore to middle state
        state.restore_snapshot(snap2)
        assert state.score == [1, 0]

        # Restore to initial state
        state.restore_snapshot(snap1)
        assert state.score == [0, 0]

        # Restore to final state
        state.restore_snapshot(snap3)
        assert state.score == [2, 0]


class TestScoreStateEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_game_type(self):
        """Test handling of invalid game type."""
        with pytest.raises(ValueError):
            ScoreState("triples", "11", {"team1": ["A"], "team2": ["B"]})

    def test_timed_game_mode(self):
        """Test timed game mode never auto-detects game over."""
        state = ScoreState("singles", "timed", {"team1": ["A"], "team2": ["B"]})
        state.score = [15, 13]
        is_over, winner = state.is_game_over()
        assert not is_over  # Timed games never auto-end

        state.score = [100, 0]
        is_over, winner = state.is_game_over()
        assert not is_over  # Still no auto-end

    def test_deuce_scenarios(self):
        """Test various deuce scenarios."""
        state = ScoreState("singles", "11", {"team1": ["A"], "team2": ["B"]})

        # 14-14 not over
        state.score = [14, 14]
        is_over, winner = state.is_game_over()
        assert not is_over

        # 15-14 not over
        state.score = [15, 14]
        is_over, winner = state.is_game_over()
        assert not is_over

        # 16-14 is over
        state.score = [16, 14]
        is_over, winner = state.is_game_over()
        assert is_over
        assert winner == 0

        # 14-16 is over
        state.score = [14, 16]
        is_over, winner = state.is_game_over()
        assert is_over
        assert winner == 1
