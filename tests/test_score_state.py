#!/usr/bin/env python3
"""Test script for ScoreState implementation.

This script tests various pickleball scoring scenarios to verify
the score state machine works correctly.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from src.core import ScoreState


def test_singles_basic():
    """Test basic singles scoring."""
    print("\n=== Test Singles Basic Scoring ===")

    player_names = {
        "team1": ["Alice"],
        "team2": ["Bob"]
    }

    state = ScoreState("singles", "11", player_names)

    # Initial state
    print(f"Initial: {state.get_score_string()}")
    assert state.get_score_string() == "0-0", "Initial score should be 0-0"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Team {server_info.serving_team})")
    assert server_info.player_name == "Alice", "Alice should serve first"

    # Alice wins point
    state.server_wins()
    print(f"After server wins: {state.get_score_string()}")
    assert state.get_score_string() == "1-0", "Score should be 1-0"

    # Alice wins another point
    state.server_wins()
    print(f"After server wins again: {state.get_score_string()}")
    assert state.get_score_string() == "2-0", "Score should be 2-0"

    # Bob wins (side-out)
    state.receiver_wins()
    print(f"After receiver wins (side-out): {state.get_score_string()}")
    assert state.get_score_string() == "0-2", "Score from Bob's perspective should be 0-2"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Team {server_info.serving_team})")
    assert server_info.player_name == "Bob", "Bob should now be serving"

    # Bob wins point
    state.server_wins()
    print(f"After Bob scores: {state.get_score_string()}")
    assert state.get_score_string() == "1-2", "Score from Bob's perspective should be 1-2"

    print("✓ Singles basic test passed!")


def test_doubles_basic():
    """Test basic doubles scoring."""
    print("\n=== Test Doubles Basic Scoring ===")

    player_names = {
        "team1": ["Alice", "Charlie"],
        "team2": ["Bob", "Diana"]
    }

    state = ScoreState("doubles", "11", player_names)

    # Initial state (0-0-2)
    print(f"Initial: {state.get_score_string()}")
    assert state.get_score_string() == "0-0-2", "Doubles should start at 0-0-2"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Server {server_info.server_number})")
    assert server_info.player_name == "Charlie", "Server 2 of Team 1 should serve first"

    # First rally: receiver wins (immediate side-out at 0-0-2)
    state.receiver_wins()
    print(f"After receiver wins at 0-0-2: {state.get_score_string()}")
    assert state.get_score_string() == "0-0-1", "Should side-out to Team 2 Server 1"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Server {server_info.server_number})")
    assert server_info.player_name == "Bob", "Bob should be serving"

    # Bob (Server 1) wins
    state.server_wins()
    print(f"After server wins: {state.get_score_string()}")
    assert state.get_score_string() == "1-0-1", "Score should be 1-0-1"

    # Bob wins again
    state.server_wins()
    print(f"After server wins again: {state.get_score_string()}")
    assert state.get_score_string() == "2-0-1", "Score should be 2-0-1"

    # Receiver wins (switch to Server 2)
    state.receiver_wins()
    print(f"After receiver wins: {state.get_score_string()}")
    assert state.get_score_string() == "2-0-2", "Should switch to Server 2"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Server {server_info.server_number})")
    assert server_info.player_name == "Diana", "Diana should be serving"

    # Receiver wins (side-out to other team)
    state.receiver_wins()
    print(f"After receiver wins again (side-out): {state.get_score_string()}")
    assert state.get_score_string() == "0-2-1", "Should side-out to Team 1 Server 1"

    server_info = state.get_server_info()
    print(f"Server: {server_info.player_name} (Server {server_info.server_number})")
    assert server_info.player_name == "Alice", "Alice should be serving"

    print("✓ Doubles basic test passed!")


def test_win_condition():
    """Test win condition detection."""
    print("\n=== Test Win Condition ===")

    player_names = {
        "team1": ["Alice"],
        "team2": ["Bob"]
    }

    state = ScoreState("singles", "11", player_names)

    # Set score to 10-9
    state.set_score("10-9")
    print(f"Score: {state.get_score_string()}")

    is_over, winner = state.is_game_over()
    print(f"Game over: {is_over}, Winner: {winner}")
    assert not is_over, "Game should not be over at 10-9 (need win by 2)"

    # Server wins (11-9, win by 2)
    state.server_wins()
    print(f"Score: {state.get_score_string()}")

    is_over, winner = state.is_game_over()
    print(f"Game over: {is_over}, Winner: {winner}")
    assert is_over, "Game should be over at 11-9"
    assert winner == 0, "Team 0 should have won"

    print("✓ Win condition test passed!")


def test_snapshot_restore():
    """Test snapshot save and restore."""
    print("\n=== Test Snapshot/Restore ===")

    player_names = {
        "team1": ["Alice"],
        "team2": ["Bob"]
    }

    state = ScoreState("singles", "11", player_names)

    # Play a few rallies
    state.server_wins()  # 1-0
    state.server_wins()  # 2-0
    print(f"Before snapshot: {state.get_score_string()}")

    # Save snapshot
    snapshot = state.save_snapshot()

    # Continue playing
    state.receiver_wins()  # Side-out
    state.server_wins()    # 1-2 from Bob's perspective
    print(f"After more rallies: {state.get_score_string()}")

    # Restore snapshot
    state.restore_snapshot(snapshot)
    print(f"After restore: {state.get_score_string()}")
    assert state.get_score_string() == "2-0", "Should restore to 2-0"

    print("✓ Snapshot/restore test passed!")


def test_serialization():
    """Test to_dict and from_dict."""
    print("\n=== Test Serialization ===")

    player_names = {
        "team1": ["Alice", "Charlie"],
        "team2": ["Bob", "Diana"]
    }

    state = ScoreState("doubles", "11", player_names)
    state.server_wins()
    state.server_wins()

    print(f"Original: {state.get_score_string()}")

    # Serialize
    data = state.to_dict()
    print(f"Serialized: {data}")

    # Deserialize
    restored = ScoreState.from_dict(data)
    print(f"Restored: {restored.get_score_string()}")

    assert restored.get_score_string() == state.get_score_string(), "Should restore correctly"

    print("✓ Serialization test passed!")


def test_manual_interventions():
    """Test manual score editing and side-out forcing."""
    print("\n=== Test Manual Interventions ===")

    player_names = {
        "team1": ["Alice", "Charlie"],
        "team2": ["Bob", "Diana"]
    }

    state = ScoreState("doubles", "11", player_names)

    # Manually set score
    state.set_score("5-3-2")
    print(f"After set_score: {state.get_score_string()}")
    assert state.get_score_string() == "5-3-2", "Score should be 5-3-2"

    # Force side-out
    state.force_side_out()
    print(f"After force_side_out: {state.get_score_string()}")
    assert state.get_score_string() == "3-5-1", "Should side-out to other team's Server 1"

    print("✓ Manual interventions test passed!")


def main():
    """Run all tests."""
    print("Testing ScoreState Implementation")
    print("=" * 50)

    try:
        test_singles_basic()
        test_doubles_basic()
        test_win_condition()
        test_snapshot_restore()
        test_serialization()
        test_manual_interventions()

        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
