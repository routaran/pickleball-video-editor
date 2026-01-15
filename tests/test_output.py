"""Tests for output generators (subtitles and Kdenlive projects).

Tests:
- SRT timestamp formatting
- SRT content generation
- Multi-segment SRT files
"""

import pytest
from pathlib import Path
from src.output.subtitle_generator import SubtitleGenerator


class TestSubtitleGenerator:
    """Test SRT subtitle generation."""

    def test_frames_to_srt_time_zero(self):
        """Test frame 0 conversion."""
        assert SubtitleGenerator.frames_to_srt_time(0, 60.0) == "00:00:00,000"

    def test_frames_to_srt_time_one_second(self):
        """Test 1 second conversion."""
        assert SubtitleGenerator.frames_to_srt_time(60, 60.0) == "00:00:01,000"

    def test_frames_to_srt_time_one_minute(self):
        """Test 1 minute conversion."""
        assert SubtitleGenerator.frames_to_srt_time(3600, 60.0) == "00:01:00,000"

    def test_frames_to_srt_time_one_hour(self):
        """Test 1 hour conversion."""
        assert SubtitleGenerator.frames_to_srt_time(216000, 60.0) == "01:00:00,000"

    def test_frames_to_srt_time_with_milliseconds(self):
        """Test conversion with fractional seconds."""
        # 1.5 seconds = 90 frames at 60fps
        assert SubtitleGenerator.frames_to_srt_time(90, 60.0) == "00:00:01,500"

    def test_frames_to_srt_time_complex(self):
        """Test complex timestamp."""
        # 1:23:45.678 = 5025.678s * 60fps = 301540.68 frames
        result = SubtitleGenerator.frames_to_srt_time(301541, 60.0)
        assert result.startswith("01:23:45,")

    def test_frames_to_srt_time_30fps(self):
        """Test conversion with 30fps."""
        # 1 second at 30fps = 30 frames
        assert SubtitleGenerator.frames_to_srt_time(30, 30.0) == "00:00:01,000"
        # 0.5 seconds at 30fps = 15 frames
        assert SubtitleGenerator.frames_to_srt_time(15, 30.0) == "00:00:00,500"

    def test_generate_srt_structure(self):
        """Test SRT content structure."""
        segments = [
            {"in": 0, "out": 300, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
        ]

        srt = SubtitleGenerator.generate_srt(segments, 60.0)

        # Check sequence numbers
        assert "1\n" in srt
        assert "2\n" in srt

        # Check scores
        assert "0-0-2" in srt
        assert "1-0-2" in srt

        # Check timestamp format
        assert "-->" in srt

        # Check structure (each subtitle has number, timestamp, text, blank line)
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert lines[2] == "0-0-2"
        assert lines[3] == ""
        assert lines[4] == "2"

    def test_generate_srt_single_segment(self):
        """Test SRT generation with single segment.

        Output timeline is cumulative, so first segment starts at frame 0.
        Segment 570-960 (length 391 frames) appears as 0-390 in output.
        """
        segments = [{"in": 570, "out": 960, "score": "0-0-2"}]

        srt = SubtitleGenerator.generate_srt(segments, 60.0)

        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        # First segment starts at 0 in output timeline
        # 391 frames - 1 = 390 frames, 390/60 = 6.5s
        assert "00:00:00,000 --> 00:00:06,500" in lines[1]
        assert lines[2] == "0-0-2"

    def test_generate_srt_empty(self):
        """Test SRT generation with no segments."""
        segments = []
        srt = SubtitleGenerator.generate_srt(segments, 60.0)
        assert srt == ""

    def test_generate_srt_multiple_segments(self):
        """Test SRT generation with multiple segments."""
        segments = [
            {"in": 0, "out": 300, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
            {"in": 1200, "out": 1500, "score": "1-0-1"},
        ]

        srt = SubtitleGenerator.generate_srt(segments, 60.0)

        # Verify all three segments present
        assert "0-0-2" in srt
        assert "1-0-2" in srt
        assert "1-0-1" in srt

        # Verify sequence numbers
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert lines[4] == "2"
        assert lines[8] == "3"

    def test_generate_srt_format_compliance(self):
        """Test SRT output is properly formatted."""
        segments = [{"in": 570, "out": 960, "score": "0-0-2"}]

        srt = SubtitleGenerator.generate_srt(segments, 60.0)

        # Don't strip - we need to check blank line
        lines = srt.split("\n")

        # Line 0: sequence number
        assert lines[0].isdigit()

        # Line 1: timestamp with -->
        assert " --> " in lines[1]
        timestamp_parts = lines[1].split(" --> ")
        assert len(timestamp_parts) == 2
        # Check timestamp format HH:MM:SS,mmm
        for ts in timestamp_parts:
            assert ts.count(":") == 2
            assert "," in ts

        # Line 2: subtitle text
        assert lines[2] == "0-0-2"

        # Line 3: blank line separator
        assert lines[3] == ""

    def test_write_srt_file(self, tmp_path):
        """Test writing SRT to file."""
        segments = [
            {"in": 0, "out": 300, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
        ]

        output_path = tmp_path / "test_output.srt"
        result_path = SubtitleGenerator.write_srt(segments, 60.0, output_path)

        assert output_path.exists()
        assert result_path == output_path

        content = output_path.read_text(encoding="utf-8")
        assert "0-0-2" in content
        assert "1-0-2" in content
        assert "-->" in content

    def test_write_srt_creates_parent_dirs(self, tmp_path):
        """Test writing SRT creates parent directories."""
        output_path = tmp_path / "subdir" / "nested" / "output.srt"
        segments = [{"in": 0, "out": 300, "score": "0-0-2"}]

        result_path = SubtitleGenerator.write_srt(segments, 60.0, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()
        assert result_path == output_path


class TestKdenliveGeneratorBasics:
    """Basic tests for Kdenlive generator structure.

    Note: Full Kdenlive XML validation would require complex XML parsing.
    These tests verify the basic API and structure.
    """

    def test_kdenlive_generator_placeholder(self):
        """Placeholder test for Kdenlive generator.

        TODO: Implement when KdenliveGenerator is finalized.
        Should test:
        - XML structure generation
        - Playlist creation
        - Track assignment
        - Transition generation
        """
        # This will be implemented once KdenliveGenerator is complete
        pass
