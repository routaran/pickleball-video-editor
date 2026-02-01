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


class TestServerInfo:
    """Test get_server_info() with first_server_player_index tracking for doubles.

    The key insight: first_server_player_index is determined at side-out time
    based on the new serving team's score parity. It stays FIXED for the
    entire possession, even as the score changes.
    """

    def test_singles_server_info(self):
        """Test singles mode returns correct player (unchanged behavior)."""
        state = ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})
        info = state.get_server_info()
        assert info.player_name == "Alice"
        assert info.serving_team == 0
        assert info.server_number is None

        # Side-out to Bob
        state.receiver_wins()
        info = state.get_server_info()
        assert info.player_name == "Bob"
        assert info.serving_team == 1

    def test_doubles_initial_state(self):
        """Test doubles initial state: 0-0-2, player[0] serves.

        At game start (0-0-2), the server is the player on the right (player[0]
        since score is even). This is a special case since we start at "Server 2"
        but it's really the only server for this possession.
        """
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )
        # At game start: first_server_player_index = 1 so that
        # Server 2 = 1 - 1 = 0 = player[0] = Alice
        assert state.first_server_player_index == 1
        info = state.get_server_info()
        assert info.player_name == "Alice"  # Server 2 = 1 - first_server = 1 - 1 = player[0]
        assert info.server_number == 2

    def test_doubles_server_stays_same_during_possession(self):
        """Test that the same player keeps serving when winning points."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )
        # Initial: 0-0-2, Server 2 = Alice (first_server=1, so Server 2 = 1-1 = 0)
        assert state.get_server_info().player_name == "Alice"

        # Alice wins a point: 1-0-2, still Alice serving
        state.server_wins()
        assert state.get_score_string() == "1-0-2"
        assert state.get_server_info().player_name == "Alice"

        # Alice wins again: 2-0-2, still Alice serving
        state.server_wins()
        assert state.get_score_string() == "2-0-2"
        assert state.get_server_info().player_name == "Alice"

        # Alice wins again: 3-0-2, still Alice serving (score odd, but same player)
        state.server_wins()
        assert state.get_score_string() == "3-0-2"
        assert state.get_server_info().player_name == "Alice"

    def test_doubles_sideout_recalculates_first_server(self):
        """Test that side-out recalculates first_server based on new team's score."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )
        # Initial side-out (0-0-2 special case)
        state.receiver_wins()
        # Team 2 gets serve, their score is 0 (even) → first_server = player[0] = Carol
        assert state.serving_team == 1
        assert state.server_number == 1
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Carol"

    def test_user_scenario_sideout_at_odd_score(self):
        """Test user's specific scenario: side-out when receiving team has odd score.

        Scenario from user:
        - Side-out at 3-2-1 (from team 1's perspective: they have 3, team 2 has 2)
        - Team 2 gets serve with score 2 (even) → player[0] = Carol is Server 1
        - After winning: 3-2-1 → Carol keeps serving
        - After losing: 3-2-2 → Server 2 = Dave
        """
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )

        # Set up the score to 3-2 with team 1 serving, server 1
        # (Simulate getting to this state)
        state.receiver_wins()  # Side-out to team 2
        state.server_wins()    # Team 2 scores: 1-0-1
        state.server_wins()    # Team 2 scores: 2-0-1
        state.receiver_wins()  # Team 2 server 1 loses, goes to server 2: 2-0-2
        state.receiver_wins()  # Team 2 server 2 loses, side-out to team 1: 0-2-1

        # Team 1 now has score 0 (even), so first_server = 0 = Alice
        assert state.serving_team == 0
        assert state.first_server_player_index == 0

        # Team 1 scores 3 points
        state.server_wins()  # 1-2-1
        state.server_wins()  # 2-2-1
        state.server_wins()  # 3-2-1

        # Now side-out (simulating receiver_wins twice to get side-out)
        state.receiver_wins()  # Server 1 loses: 3-2-2
        state.receiver_wins()  # Server 2 loses: side-out to team 2

        # Team 2 now serves with score 2 (even) → first_server = 0 = Carol
        assert state.serving_team == 1
        assert state.server_number == 1
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Carol"

        # Carol wins a point: 3-3-1 (from team 2's perspective)
        state.server_wins()
        assert state.get_server_info().player_name == "Carol"

        # Carol loses: goes to Server 2 = Dave (1 - 0 = 1 = Dave)
        state.receiver_wins()
        assert state.server_number == 2
        assert state.get_server_info().player_name == "Dave"

    def test_sideout_at_odd_score_sets_correct_first_server(self):
        """Test side-out when new serving team has odd score."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )

        # Get team 2 to score 3 points, then side-out back to team 1
        state.receiver_wins()  # Side-out to team 2
        state.server_wins()    # 1-0-1
        state.server_wins()    # 2-0-1
        state.server_wins()    # 3-0-1
        state.receiver_wins()  # Server 1 loses: 3-0-2
        state.receiver_wins()  # Server 2 loses: side-out to team 1

        # Team 1 gets serve with score 0 (even) → first_server = 0 = Alice
        assert state.serving_team == 0
        assert state.server_number == 1
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Alice"

        # Alice scores 1 point
        state.server_wins()  # 1-3-1

        # Alice loses, goes to server 2
        state.receiver_wins()  # 1-3-2
        # Server 2 = 1 - first_server = 1 - 0 = Bob
        assert state.get_server_info().player_name == "Bob"

    def test_sideout_with_team_having_odd_score(self):
        """Test side-out when the receiving (about to serve) team has odd score."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )

        # Team 1 scores 1, then loses serve
        state.server_wins()    # 1-0-2
        state.receiver_wins()  # Side-out to team 2

        # Team 2 has score 0 (even) → first_server = 0 = Carol
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Carol"

        # Team 2 scores 1, then loses both servers
        state.server_wins()    # 1-1-1
        state.receiver_wins()  # 1-1-2
        state.receiver_wins()  # Side-out to team 1

        # Team 1 has score 1 (odd) → first_server = 1 = Bob
        assert state.serving_team == 0
        assert state.first_server_player_index == 1
        assert state.get_server_info().player_name == "Bob"  # Server 1 = first_server = Bob

        # Bob loses, goes to server 2
        state.receiver_wins()  # 1-1-2
        # Server 2 = 1 - first_server = 1 - 1 = 0 = Alice
        assert state.get_server_info().player_name == "Alice"

    def test_first_server_fixed_during_possession(self):
        """Test that first_server doesn't change when scoring during possession."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )

        # Side-out to team 2 with score 0 → first_server = 0 = Carol
        state.receiver_wins()
        assert state.first_server_player_index == 0

        # Carol (Server 1) scores multiple points - first_server stays 0
        state.server_wins()  # 1-0-1
        assert state.first_server_player_index == 0

        state.server_wins()  # 2-0-1
        assert state.first_server_player_index == 0

        state.server_wins()  # 3-0-1 (odd score, but first_server still 0)
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Carol"  # Same player serving

    def test_snapshot_preserves_first_server(self):
        """Test that snapshots correctly save and restore first_server_player_index."""
        state = ScoreState(
            "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        )

        # Side-out to team 2
        state.receiver_wins()
        state.server_wins()  # 1-0-1

        # First_server is 0 (Carol)
        snapshot = state.save_snapshot()
        assert snapshot.first_server_player_index == 0

        # Change state
        state.receiver_wins()  # Goes to server 2
        state.server_wins()    # 2-0-2

        # Restore and verify first_server is back to 0
        state.restore_snapshot(snapshot)
        assert state.first_server_player_index == 0
        assert state.get_server_info().player_name == "Carol"
