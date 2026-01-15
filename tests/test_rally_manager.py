"""Tests for RallyManager rally tracking and undo functionality.

Tests:
- Rally start with pre-padding
- Rally end with post-padding
- Undo of rally start and end
- Multiple rally sequences
- Segment export format
"""

import pytest
from src.core.rally_manager import RallyManager
from src.core.models import ScoreSnapshot, Rally, ActionType


class TestRallyManager:
    """Test rally marking functionality."""

    def test_start_rally(self):
        """Test rally start with padding."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(10.0, snapshot)

        assert manager.is_rally_in_progress()
        # 10.0 - 0.5 padding = 9.5s = 570 frames
        assert frame == 570

    def test_start_rally_at_zero(self):
        """Test rally start at video beginning handles padding correctly."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(0.3, snapshot)

        # 0.3 - 0.5 padding would be negative, should clamp to 0
        assert frame == 0
        assert manager.is_rally_in_progress()

    def test_end_rally(self):
        """Test rally end with padding."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        rally = manager.end_rally(15.0, "server", "0-0-2", snapshot)

        assert not manager.is_rally_in_progress()
        assert rally.winner == "server"
        assert rally.score_at_start == "0-0-2"
        # 15.0 + 1.0 padding = 16.0s = 960 frames
        assert rally.end_frame == 960
        assert rally.start_frame == 570

    def test_cannot_end_without_start(self):
        """Test that ending rally without start raises error."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        with pytest.raises(ValueError, match="No rally in progress"):
            manager.end_rally(15.0, "server", "0-0-2", snapshot)

    def test_cannot_start_twice(self):
        """Test that starting rally twice raises error."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)

        with pytest.raises(ValueError, match="Rally already in progress"):
            manager.start_rally(15.0, snapshot)

    def test_undo_rally_end(self):
        """Test undo of rally end."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        assert manager.get_rally_count() == 1

        action, seek_pos = manager.undo()

        # Verify undo returns an Action object with RALLY_END type
        assert action.action_type == ActionType.RALLY_END
        assert action.timestamp == 15.0
        assert manager.get_rally_count() == 0
        assert manager.is_rally_in_progress()  # Back to in-progress
        # Should seek to where rally ended
        assert seek_pos == 15.0

    def test_undo_rally_start(self):
        """Test undo of rally start."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)

        assert manager.is_rally_in_progress()

        action, seek_pos = manager.undo()

        # Verify undo returns an Action object with RALLY_START type
        assert action.action_type == ActionType.RALLY_START
        assert action.timestamp == 10.0
        assert not manager.is_rally_in_progress()
        assert seek_pos == 10.0

    def test_undo_empty_raises_error(self):
        """Test undo on empty manager raises error."""
        manager = RallyManager(fps=60.0)

        with pytest.raises(ValueError, match="Nothing to undo"):
            manager.undo()

    def test_multiple_rallies(self):
        """Test multiple rally sequence."""
        manager = RallyManager(fps=60.0)

        # Rally 1
        snap1 = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)
        manager.start_rally(10.0, snap1)
        manager.end_rally(15.0, "server", "0-0-2", snap1)

        # Rally 2
        snap2 = ScoreSnapshot(score=(1, 0), serving_team=0, server_number=2)
        manager.start_rally(20.0, snap2)
        manager.end_rally(25.0, "receiver", "1-0-2", snap2)

        # Rally 3
        snap3 = ScoreSnapshot(score=(1, 0), serving_team=1, server_number=1)
        manager.start_rally(30.0, snap3)
        manager.end_rally(35.0, "server", "1-0-1", snap3)

        assert manager.get_rally_count() == 3
        rallies = manager.get_rallies()
        assert rallies[0].winner == "server"
        assert rallies[1].winner == "receiver"
        assert rallies[2].winner == "server"

    def test_undo_chain(self):
        """Test undoing multiple actions in sequence."""
        manager = RallyManager(fps=60.0)
        snap = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snap)
        manager.end_rally(15.0, "server", "0-0-2", snap)
        manager.start_rally(20.0, snap)
        manager.end_rally(25.0, "receiver", "1-0-2", snap)

        assert manager.get_rally_count() == 2

        # Undo rally 2 end
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_END
        assert manager.get_rally_count() == 1
        assert manager.is_rally_in_progress()

        # Undo rally 2 start
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_START
        assert manager.get_rally_count() == 1
        assert not manager.is_rally_in_progress()

        # Undo rally 1 end
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_END
        assert manager.get_rally_count() == 0
        assert manager.is_rally_in_progress()

        # Undo rally 1 start
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_START
        assert manager.get_rally_count() == 0
        assert not manager.is_rally_in_progress()

    def test_to_segments(self):
        """Test segment export format."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        segments = manager.to_segments()

        assert len(segments) == 1
        assert "in" in segments[0]
        assert "out" in segments[0]
        assert "score" in segments[0]
        assert segments[0]["in"] == 570
        assert segments[0]["out"] == 960
        assert segments[0]["score"] == "0-0-2"

    def test_to_segments_multiple(self):
        """Test segment export with multiple rallies."""
        manager = RallyManager(fps=60.0)

        # Rally 1
        snap1 = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)
        manager.start_rally(10.0, snap1)
        manager.end_rally(15.0, "server", "0-0-2", snap1)

        # Rally 2
        snap2 = ScoreSnapshot(score=(1, 0), serving_team=0, server_number=2)
        manager.start_rally(20.0, snap2)
        manager.end_rally(25.0, "receiver", "1-0-2", snap2)

        segments = manager.to_segments()

        assert len(segments) == 2
        assert segments[0]["score"] == "0-0-2"
        assert segments[1]["score"] == "1-0-2"

    def test_to_segments_empty(self):
        """Test segment export with no rallies."""
        manager = RallyManager(fps=60.0)
        segments = manager.to_segments()
        assert segments == []

    def test_to_segments_incomplete_rally(self):
        """Test segment export ignores incomplete rally."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        # Don't end it

        segments = manager.to_segments()
        assert segments == []

    def test_rally_in_progress_state(self):
        """Test rally in-progress state tracking."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        # No rally in progress initially
        assert not manager.is_rally_in_progress()

        # Start rally
        manager.start_rally(10.0, snapshot)
        assert manager.is_rally_in_progress()

        # End rally
        manager.end_rally(15.0, "server", "0-0-2", snapshot)
        assert not manager.is_rally_in_progress()

    def test_fps_conversion(self):
        """Test frame calculation with different FPS."""
        manager = RallyManager(fps=30.0)  # 30fps instead of 60
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(10.0, snapshot)
        # 10.0 - 0.5 = 9.5s * 30fps = 285 frames
        assert frame == 285

        rally = manager.end_rally(15.0, "server", "0-0-2", snapshot)
        # 15.0 + 1.0 = 16.0s * 30fps = 480 frames
        assert rally.end_frame == 480


class TestRallyModel:
    """Test Rally dataclass behavior."""

    def test_rally_creation(self):
        """Test creating a Rally object."""
        rally = Rally(
            start_frame=570,
            end_frame=960,
            score_at_start="0-0-2",
            winner="server",
            comment="Great rally",
        )

        assert rally.start_frame == 570
        assert rally.end_frame == 960
        assert rally.winner == "server"
        assert rally.score_at_start == "0-0-2"
        assert rally.comment == "Great rally"

    def test_rally_without_comment(self):
        """Test Rally without optional comment."""
        rally = Rally(
            start_frame=570,
            end_frame=960,
            score_at_start="0-0-2",
            winner="server",
        )

        assert rally.start_frame == 570
        assert rally.end_frame == 960
        assert rally.winner == "server"
        assert rally.comment is None
