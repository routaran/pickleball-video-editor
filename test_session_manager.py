#!/usr/bin/env python3
"""Test script for SessionManager functionality."""

import tempfile
from pathlib import Path
from datetime import datetime

from src.core import SessionManager, SessionState, Rally


def test_session_manager():
    """Test basic SessionManager operations."""
    # Create temporary directory for test sessions
    with tempfile.TemporaryDirectory() as temp_dir:
        session_dir = Path(temp_dir)
        manager = SessionManager(session_dir=session_dir)

        print(f"Session directory: {session_dir}")

        # Create a temporary test video file
        test_video = session_dir / "test_video.mp4"
        test_video.write_bytes(b"fake video content for testing")
        print(f"Created test video: {test_video}")

        # Test 1: Check that no session exists initially
        print("\n--- Test 1: Check for existing session ---")
        existing = manager.find_existing(str(test_video))
        print(f"Existing session: {existing}")
        assert existing is None, "Should not find session for new video"

        # Test 2: Create and save a new session
        print("\n--- Test 2: Create and save session ---")
        state = SessionState(
            version="1.0",
            video_path=str(test_video),
            game_type="doubles",
            victory_rules="11",
            player_names={
                "team1": ["Player 1A", "Player 1B"],
                "team2": ["Player 2A", "Player 2B"]
            },
            current_score=[3, 2, 1],
            serving_team=0,
            server_number=1,
            last_position=45.5,
            created_at=datetime.now().isoformat(),
            modified_at=datetime.now().isoformat(),
        )

        # Add some rallies
        state.rallies = [
            Rally(start_frame=100, end_frame=500, score_at_start="0-0-2", winner="server"),
            Rally(start_frame=600, end_frame=900, score_at_start="1-0-1", winner="receiver"),
            Rally(start_frame=1000, end_frame=1400, score_at_start="1-0-2", winner="server"),
        ]

        saved_path = manager.save(state, str(test_video))
        print(f"Session saved to: {saved_path}")
        assert saved_path is not None, "Session save should succeed"
        assert saved_path.exists(), "Session file should exist"

        # Test 3: Find existing session
        print("\n--- Test 3: Find existing session ---")
        found = manager.find_existing(str(test_video))
        print(f"Found session: {found}")
        assert found is not None, "Should find saved session"
        assert found == saved_path, "Found path should match saved path"

        # Test 4: Load session
        print("\n--- Test 4: Load session ---")
        loaded_state = manager.load(str(test_video))
        assert loaded_state is not None, "Should load session"
        print(f"Game type: {loaded_state.game_type}")
        print(f"Current score: {loaded_state.current_score}")
        print(f"Rally count: {len(loaded_state.rallies)}")
        print(f"Last position: {loaded_state.last_position}")
        assert loaded_state.game_type == "doubles", "Game type should match"
        assert loaded_state.current_score == [3, 2, 1], "Score should match"
        assert len(loaded_state.rallies) == 3, "Should have 3 rallies"
        assert loaded_state.last_position == 45.5, "Position should match"

        # Test 5: Get session info
        print("\n--- Test 5: Get session info ---")
        info = manager.get_session_info(str(test_video))
        assert info is not None, "Should get session info"
        print(f"Rally count: {info['rally_count']}")
        print(f"Current score: {info['current_score']}")
        print(f"Last position: {info['last_position']}")
        print(f"Game type: {info['game_type']}")
        print(f"Last modified: {info['last_modified']}")
        assert info["rally_count"] == 3, "Rally count should be 3"
        assert info["current_score"] == "3-2-1", "Score should be formatted as 3-2-1"
        assert info["game_type"] == "doubles", "Game type should be doubles"

        # Test 6: Delete session
        print("\n--- Test 6: Delete session ---")
        deleted = manager.delete(str(test_video))
        print(f"Session deleted: {deleted}")
        assert deleted is True, "Delete should succeed"
        assert not saved_path.exists(), "Session file should be deleted"

        # Test 7: Verify session is gone
        print("\n--- Test 7: Verify session is gone ---")
        not_found = manager.find_existing(str(test_video))
        print(f"Session after delete: {not_found}")
        assert not_found is None, "Should not find deleted session"

        # Test 8: Test with non-existent video
        print("\n--- Test 8: Non-existent video ---")
        fake_video = "/path/to/nonexistent/video.mp4"
        no_session = manager.load(fake_video)
        print(f"Load non-existent video: {no_session}")
        assert no_session is None, "Should return None for non-existent video"

        print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_session_manager()
