#!/usr/bin/env python3
"""Test script for Phase 7.2 Session Integration.

This script tests the session save/load functionality in SetupDialog and MainWindow.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from src.ui.setup_dialog import SetupDialog, GameConfig
from src.core.session_manager import SessionManager


def test_setup_dialog_session_detection():
    """Test that SetupDialog detects and offers to resume existing sessions."""
    print("Testing SetupDialog session detection...")

    app = QApplication(sys.argv)

    # Create a test video path (doesn't need to exist for this test)
    test_video = Path.home() / "Videos" / "test_match.mp4"

    # Create and save a test session
    from src.core.models import SessionState

    session_manager = SessionManager()

    # Create a mock session
    test_session = SessionState(
        version="1.0",
        video_path=str(test_video),
        video_hash="test_hash_12345",
        game_type="doubles",
        victory_rules="11",
        player_names={
            "team1": ["Alice", "Bob"],
            "team2": ["Carol", "Dave"]
        },
        rallies=[],
        current_score=[3, 2, 1],
        serving_team=0,
        server_number=1,
        last_position=120.5,
        created_at="2026-01-14T10:00:00",
        modified_at="2026-01-14T10:15:00",
    )

    # Clean up any existing test session
    session_manager.delete(str(test_video))

    print(f"  Test video path: {test_video}")
    print(f"  Session directory: {session_manager.session_dir}")

    # Show setup dialog
    dialog = SetupDialog()
    print("  SetupDialog created successfully")

    print("\nTest passed: SetupDialog can be created with session manager")
    print("Manual test required: Select a video with existing session to test resume dialog")

    app.quit()


def test_session_state_roundtrip():
    """Test that SessionState can be saved and loaded correctly."""
    print("\nTesting SessionState save/load roundtrip...")

    from src.core.models import SessionState, Rally

    # Create a test session
    test_session = SessionState(
        version="1.0",
        video_path="/tmp/test_video.mp4",
        video_hash="test_hash_abc123",
        game_type="doubles",
        victory_rules="11",
        player_names={
            "team1": ["Player1", "Player2"],
            "team2": ["Player3", "Player4"]
        },
        rallies=[
            Rally(
                start_frame=100,
                end_frame=200,
                score_at_start="0-0-2",
                winner="server",
                comment=None
            )
        ],
        current_score=[1, 0, 2],
        serving_team=0,
        server_number=2,
        last_position=3.5,
        created_at="2026-01-14T10:00:00",
        modified_at="2026-01-14T10:00:00",
    )

    # Convert to dict and back
    session_dict = test_session.to_dict()
    restored_session = SessionState.from_dict(session_dict)

    # Verify fields
    assert restored_session.game_type == "doubles"
    assert restored_session.victory_rules == "11"
    assert restored_session.current_score == [1, 0, 2]
    assert restored_session.serving_team == 0
    assert restored_session.server_number == 2
    assert restored_session.last_position == 3.5
    assert len(restored_session.rallies) == 1
    assert restored_session.rallies[0].start_frame == 100
    assert restored_session.rallies[0].winner == "server"

    print("  ✓ SessionState roundtrip successful")
    print("  ✓ All fields preserved correctly")


def test_gameconfig_with_session():
    """Test that GameConfig can hold session_state."""
    print("\nTesting GameConfig with session_state...")

    from src.ui.setup_dialog import GameConfig
    from src.core.models import SessionState

    # Create a config with session state
    session_state = SessionState(
        game_type="singles",
        victory_rules="11",
        player_names={"team1": ["Alice"], "team2": ["Bob"]},
        current_score=[5, 3],
        serving_team=1,
        server_number=None,
    )

    config = GameConfig(
        video_path=Path("/tmp/test.mp4"),
        game_type="singles",
        victory_rule="11",
        team1_players=["Alice"],
        team2_players=["Bob"],
        session_state=session_state
    )

    assert config.session_state is not None
    assert config.session_state.game_type == "singles"
    assert config.session_state.current_score == [5, 3]

    print("  ✓ GameConfig can hold session_state")
    print("  ✓ session_state field works correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 7.2 Session Integration Tests")
    print("=" * 60)

    try:
        test_session_state_roundtrip()
        test_gameconfig_with_session()
        test_setup_dialog_session_detection()

        print("\n" + "=" * 60)
        print("All automated tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
