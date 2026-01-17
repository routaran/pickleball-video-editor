"""Tests for Mark Game Completed feature.

Tests cover:
- GameCompletionInfo dataclass serialization
- Final score calculation
- Timeline extension logic
- Final subtitle generation
- ASS text escaping
- Integration with Kdenlive export
- Edge cases and error handling
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from src.core.models import GameCompletionInfo, SessionState
from src.output.kdenlive_generator import KdenliveGenerator, _escape_ass_text
from src.video.probe import VideoInfo


class TestGameCompletionInfo:
    """Tests for GameCompletionInfo dataclass."""

    def test_default_values(self):
        """Test default initialization values."""
        info = GameCompletionInfo()

        assert info.is_completed is False
        assert info.final_score == ""
        assert info.winning_team == 0
        assert info.winning_team_names == []
        assert info.extension_seconds == 8.0

    def test_initialization_with_values(self):
        """Test initialization with custom values."""
        info = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=1,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=10.0
        )

        assert info.is_completed is True
        assert info.final_score == "11-9"
        assert info.winning_team == 1
        assert info.winning_team_names == ["Jane", "Joe"]
        assert info.extension_seconds == 10.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        info = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=1,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=8.0
        )

        data = info.to_dict()

        assert data == {
            "is_completed": True,
            "final_score": "11-9",
            "winning_team": 1,
            "winning_team_names": ["Jane", "Joe"],
            "extension_seconds": 8.0,
        }

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "is_completed": True,
            "final_score": "11-9",
            "winning_team": 1,
            "winning_team_names": ["Jane", "Joe"],
            "extension_seconds": 8.0,
        }

        info = GameCompletionInfo.from_dict(data)

        assert info.is_completed is True
        assert info.final_score == "11-9"
        assert info.winning_team == 1
        assert info.winning_team_names == ["Jane", "Joe"]
        assert info.extension_seconds == 8.0

    def test_from_dict_with_missing_fields(self):
        """Test deserialization with missing fields uses defaults."""
        data = {"is_completed": True}

        info = GameCompletionInfo.from_dict(data)

        assert info.is_completed is True
        assert info.final_score == ""
        assert info.winning_team == 0
        assert info.winning_team_names == []
        assert info.extension_seconds == 8.0

    def test_from_dict_empty(self):
        """Test deserialization from empty dict."""
        info = GameCompletionInfo.from_dict({})

        assert info.is_completed is False
        assert info.final_score == ""
        assert info.winning_team == 0
        assert info.winning_team_names == []
        assert info.extension_seconds == 8.0


class TestGameCompletionInfoInSessionState:
    """Tests for GameCompletionInfo integration with SessionState."""

    def test_session_state_includes_game_completion(self):
        """Test SessionState includes game_completion field."""
        state = SessionState()

        assert hasattr(state, 'game_completion')
        assert isinstance(state.game_completion, GameCompletionInfo)

    def test_session_state_serialization_with_game_completion(self):
        """Test SessionState serializes game_completion correctly."""
        state = SessionState(
            game_completion=GameCompletionInfo(
                is_completed=True,
                final_score="11-9",
                winning_team=0,
                winning_team_names=["Alice", "Bob"]
            )
        )

        data = state.to_dict()

        assert "game_completion" in data
        assert data["game_completion"]["is_completed"] is True
        assert data["game_completion"]["final_score"] == "11-9"
        assert data["game_completion"]["winning_team"] == 0
        assert data["game_completion"]["winning_team_names"] == ["Alice", "Bob"]

    def test_session_state_deserialization_with_game_completion(self):
        """Test SessionState deserializes game_completion correctly."""
        data = {
            "version": "1.0",
            "video_path": "/path/to/video.mp4",
            "game_completion": {
                "is_completed": True,
                "final_score": "11-9",
                "winning_team": 1,
                "winning_team_names": ["Jane", "Joe"],
                "extension_seconds": 10.0
            }
        }

        state = SessionState.from_dict(data)

        assert state.game_completion.is_completed is True
        assert state.game_completion.final_score == "11-9"
        assert state.game_completion.winning_team == 1
        assert state.game_completion.winning_team_names == ["Jane", "Joe"]
        assert state.game_completion.extension_seconds == 10.0


class TestASSEscaping:
    """Tests for ASS subtitle text escaping."""

    def test_escape_backslash(self):
        """Test backslash escaping."""
        result = _escape_ass_text("Player\\Name")
        assert result == "Player\\\\Name"

    def test_escape_curly_braces(self):
        """Test curly brace escaping."""
        result = _escape_ass_text("Player{Name}")
        assert result == "Player\\{Name\\}"

    def test_escape_combined_special_chars(self):
        """Test escaping all special characters together."""
        result = _escape_ass_text("Test\\{Player}")
        assert result == "Test\\\\\\{Player\\}"

    def test_escape_normal_text(self):
        """Test normal text passes through unchanged."""
        result = _escape_ass_text("Alice & Bob")
        assert result == "Alice & Bob"

    def test_escape_empty_string(self):
        """Test escaping empty string."""
        result = _escape_ass_text("")
        assert result == ""

    def test_escape_multiple_backslashes(self):
        """Test escaping multiple consecutive backslashes."""
        result = _escape_ass_text("Path\\\\Server")
        assert result == "Path\\\\\\\\Server"

    def test_escape_nested_braces(self):
        """Test escaping nested curly braces."""
        result = _escape_ass_text("{{nested}}")
        assert result == "\\{\\{nested\\}\\}"


class TestKdenliveGeneratorWithGameCompletion:
    """Tests for Kdenlive generator with game completion."""

    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """Create a mock video file for testing."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    @pytest.fixture
    def basic_segments(self):
        """Create basic test segments."""
        return [
            {"in": 0, "out": 300, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
        ]

    def test_timeline_length_without_game_completion(self, mock_video_file, basic_segments):
        """Test timeline length calculation without game completion."""
        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=basic_segments,
            fps=60.0,
            game_completion=None
        )

        # Without game completion: (300-0) + (900-600) = 300 + 300 = 600 frames
        assert generator._calculate_timeline_length() == 600

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo object."""
        return VideoInfo(
            path="/tmp/test_video.mp4",
            width=1920,
            height=1080,
            fps=60.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            bit_rate=8000000,
            frame_count=3600
        )

    def test_timeline_length_with_game_completion(self, mock_video_file, basic_segments, mock_video_info):
        """Test timeline length includes extension when game is completed."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Alice", "Bob"],
            extension_seconds=8.0
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=basic_segments,
            fps=60.0,
            game_completion=game_completion
        )

        # With game completion: 600 + (8.0 * 60) = 600 + 480 = 1080 frames
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            assert generator._calculate_timeline_length() == 1080

    def test_timeline_length_game_completion_not_marked(self, mock_video_file, basic_segments):
        """Test timeline length when game_completion exists but is_completed is False."""
        game_completion = GameCompletionInfo(
            is_completed=False,  # Not marked as completed
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Alice", "Bob"],
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=basic_segments,
            fps=60.0,
            game_completion=game_completion
        )

        # Should NOT include extension since is_completed is False
        assert generator._calculate_timeline_length() == 600

    def test_timeline_length_custom_extension(self, mock_video_file, basic_segments, mock_video_info):
        """Test timeline length with custom extension duration."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Alice", "Bob"],
            extension_seconds=5.0  # Custom 5 seconds
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=basic_segments,
            fps=60.0,
            game_completion=game_completion
        )

        # With custom extension: 600 + (5.0 * 60) = 600 + 300 = 900 frames
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            assert generator._calculate_timeline_length() == 900


class TestFinalScoreSubtitle:
    """Tests for final score subtitle formatting."""

    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """Create a mock video file for testing."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    def test_format_final_score_subtitle_doubles(self, mock_video_file):
        """Test final score subtitle formatting for doubles."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        assert result == "11-9\\NJane & Joe Win"

    def test_format_final_score_subtitle_singles(self, mock_video_file):
        """Test final score subtitle formatting for singles."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-7",
            winning_team=1,
            winning_team_names=["Alice"],  # Singles - one player
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        assert result == "11-7\\NAlice Wins"  # Singular "Wins"

    def test_format_final_score_subtitle_no_names(self, mock_video_file):
        """Test final score subtitle when no winner names provided."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=[],  # No names
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        assert result == "11-9\\NGame Over"

    def test_format_final_score_with_special_chars(self, mock_video_file):
        """Test final score subtitle escapes special characters in names."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Player{One}", "Player\\Two"],
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        # Names should be escaped
        assert "\\{" in result
        assert "\\}" in result
        assert "\\\\" in result

    def test_format_final_score_multiple_players(self, mock_video_file):
        """Test final score subtitle with three or more players."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Alice", "Bob", "Charlie"],
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        # Multiple players use "Win" not "Wins"
        assert result == "11-9\\NAlice & Bob & Charlie Win"


class TestASSFileWithGameCompletion:
    """Tests for ASS subtitle file generation with game completion."""

    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """Create a mock video file for testing."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo object."""
        return VideoInfo(
            path="/tmp/test_video.mp4",
            width=1920,
            height=1080,
            fps=60.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            bit_rate=8000000,
            frame_count=3600
        )

    def test_ass_file_includes_final_subtitle(self, mock_video_file, tmp_path, mock_video_info):
        """Test that ASS file includes final subtitle when game is completed."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=8.0
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[
                {"in": 0, "out": 300, "score": "0-0-2"},
                {"in": 600, "out": 900, "score": "1-0-2"},
            ],
            fps=60.0,
            output_dir=tmp_path,
            game_completion=game_completion
        )

        # Generate the files with mocked probe_video
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            kdenlive_path, ass_path = generator.generate()

        # Read the ASS file
        ass_content = ass_path.read_text()

        # Verify final subtitle is present
        assert "11-9" in ass_content
        assert "Jane & Joe Win" in ass_content

        # Verify it's a Dialogue line
        assert "Dialogue:" in ass_content
        dialogue_lines = [l for l in ass_content.split('\n') if l.startswith('Dialogue:')]
        assert len(dialogue_lines) >= 3  # At least 2 rally subtitles + 1 final

    def test_ass_file_no_final_subtitle_when_not_completed(self, mock_video_file, tmp_path, mock_video_info):
        """Test ASS file doesn't include final subtitle when game is not completed."""
        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[
                {"in": 0, "out": 300, "score": "0-0-2"},
            ],
            fps=60.0,
            output_dir=tmp_path,
            game_completion=None  # No game completion
        )

        # Generate the files with mocked probe_video
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            kdenlive_path, ass_path = generator.generate()

        # Read the ASS file
        ass_content = ass_path.read_text()

        # Should only have the rally score, no "Win" in subtitles
        assert "0-0-2" in ass_content
        # Count dialogue lines - should not contain "Win" text
        dialogue_lines = [l for l in ass_content.split('\n') if l.startswith('Dialogue:')]
        win_lines = [l for l in dialogue_lines if "Win" in l]
        assert len(win_lines) == 0

    def test_ass_file_timing_with_completion(self, mock_video_file, tmp_path, mock_video_info):
        """Test ASS file timing for final subtitle."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=8.0
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[
                {"in": 0, "out": 300, "score": "0-0-2"},  # 5 seconds
            ],
            fps=60.0,
            output_dir=tmp_path,
            game_completion=game_completion
        )

        # Generate the files with mocked probe_video
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            kdenlive_path, ass_path = generator.generate()

        # Read the ASS file
        ass_content = ass_path.read_text()

        # Final subtitle should start at end of last segment (5 seconds)
        # and end at 5 + 8 = 13 seconds
        assert "0:00:05.00,0:00:13.00" in ass_content


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """Create a mock video file for testing."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo object."""
        return VideoInfo(
            path="/tmp/test_video.mp4",
            width=1920,
            height=1080,
            fps=60.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            bit_rate=8000000,
            frame_count=3600
        )

    def test_single_rally_with_completion(self, mock_video_file, tmp_path, mock_video_info):
        """Test game completion with only one rally."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-0",
            winning_team=0,
            winning_team_names=["Dominator"],
            extension_seconds=8.0
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0"}],
            fps=60.0,
            output_dir=tmp_path,
            game_completion=game_completion
        )

        # Should not raise
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            kdenlive_path, ass_path = generator.generate()

        assert kdenlive_path.exists()
        assert ass_path.exists()

    def test_extension_with_different_fps(self, mock_video_file):
        """Test extension frame calculation with non-60fps video."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=8.0  # 240 frames at 30fps
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 150, "score": "0-0-2"}],  # 150 frames
            fps=30.0,
            game_completion=game_completion
        )

        # Create mock video info with 30fps
        mock_video_info_30fps = VideoInfo(
            path="/tmp/test_video.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            bit_rate=8000000,
            frame_count=1800
        )

        # 150 + (8.0 * 30) = 150 + 240 = 390 frames
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info_30fps):
            assert generator._calculate_timeline_length() == 390

    def test_custom_extension_duration(self, mock_video_file, mock_video_info):
        """Test with custom extension duration."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=5.0  # Custom 5 seconds instead of default 8
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        # 300 + (5.0 * 60) = 300 + 300 = 600 frames
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            assert generator._calculate_timeline_length() == 600

    def test_tie_score_completion(self, mock_video_file):
        """Test game completion with tied score (edge case)."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="5-5",  # Tie score
            winning_team=0,
            winning_team_names=[],  # No winner for tie
            extension_seconds=8.0
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        result = generator._format_final_score_subtitle()

        # Should show "Game Over" for tie
        assert result == "5-5\\NGame Over"

    def test_zero_extension_duration(self, mock_video_file, mock_video_info):
        """Test with zero extension duration."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=0.0  # No extension
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        # Should still show final subtitle, just with 0 duration
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            assert generator._calculate_timeline_length() == 300

    def test_fractional_extension_frames(self, mock_video_file, mock_video_info):
        """Test extension with fractional frame calculation."""
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score="11-9",
            winning_team=0,
            winning_team_names=["Jane", "Joe"],
            extension_seconds=7.5  # Results in 450 frames at 60fps
        )

        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            game_completion=game_completion
        )

        # 300 + int(7.5 * 60) = 300 + 450 = 750 frames
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            assert generator._calculate_timeline_length() == 750


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """Create a mock video file for testing."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video data")
        return video_path

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo object."""
        return VideoInfo(
            path="/tmp/test_video.mp4",
            width=1920,
            height=1080,
            fps=60.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            bit_rate=8000000,
            frame_count=3600
        )

    def test_generator_works_without_game_completion(self, mock_video_file, tmp_path, mock_video_info):
        """Test KdenliveGenerator works without game_completion parameter."""
        # Old-style instantiation without game_completion
        generator = KdenliveGenerator(
            video_path=mock_video_file,
            segments=[{"in": 0, "out": 300, "score": "0-0-2"}],
            fps=60.0,
            output_dir=tmp_path,
        )

        # Should work without error
        with patch('src.output.kdenlive_generator.probe_video', return_value=mock_video_info):
            kdenlive_path, ass_path = generator.generate()

        assert kdenlive_path.exists()
        assert ass_path.exists()

    def test_session_state_loads_without_game_completion(self):
        """Test SessionState loads old sessions without game_completion field."""
        # Simulate an old session JSON without game_completion
        old_session_data = {
            "version": "1.0",
            "video_path": "/path/to/video.mp4",
            "video_hash": "abc123",
            "game_type": "doubles",
            "victory_rules": "11",
            # Note: no game_completion field
        }

        state = SessionState.from_dict(old_session_data)

        # Should have default GameCompletionInfo
        assert state.game_completion is not None
        assert state.game_completion.is_completed is False
        assert state.game_completion.final_score == ""
        assert state.game_completion.winning_team == 0
        assert state.game_completion.winning_team_names == []
        assert state.game_completion.extension_seconds == 8.0

    def test_generator_ignores_game_completion_when_none(self, mock_video_file):
        """Test generator behaves identically when game_completion is None."""
        segments = [{"in": 0, "out": 300, "score": "0-0-2"}]

        # Generator with explicit None
        gen1 = KdenliveGenerator(
            video_path=mock_video_file,
            segments=segments,
            fps=60.0,
            game_completion=None
        )

        # Generator without parameter (defaults to None)
        gen2 = KdenliveGenerator(
            video_path=mock_video_file,
            segments=segments,
            fps=60.0
        )

        # Both should calculate same timeline length
        assert gen1._calculate_timeline_length() == gen2._calculate_timeline_length()
        assert gen1._calculate_timeline_length() == 300
