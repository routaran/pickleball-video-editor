"""Tests for output generators (subtitles and Kdenlive projects).

Tests:
- SRT timestamp formatting
- SRT content generation
- Multi-segment SRT files
- Kdenlive AVSplit group generation
- Timecode round-trip consistency
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.output.subtitle_generator import SubtitleGenerator
from src.output.kdenlive_generator import KdenliveGenerator
from src.video.probe import VideoInfo


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
    """Basic tests for Kdenlive generator structure."""

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo for testing."""
        info = MagicMock(spec=VideoInfo)
        info.duration = 600.0  # 10 minutes
        info.frame_count = 36000  # 60fps * 600s
        return info

    @pytest.fixture
    def mock_video_file(self, tmp_path, mock_video_info):
        """Create a mock video file and patch probe_video."""
        video_path = tmp_path / "test_video.mp4"
        video_path.write_bytes(b"fake video content")
        return video_path

    @pytest.fixture
    def generator(self, mock_video_file, mock_video_info):
        """Create a KdenliveGenerator with mocked video probing."""
        segments = [
            {"in": 100, "out": 400, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
            {"in": 1200, "out": 1500, "score": "2-0-2"},
        ]
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            gen = KdenliveGenerator(
                video_path=mock_video_file,
                segments=segments,
                fps=60.0,
                resolution=(1920, 1080),
            )
        # Patch the cached property
        gen._video_info = mock_video_info
        return gen


class TestTimecodeToFrames:
    """Test _timecode_to_frames method."""

    @pytest.fixture
    def generator(self, tmp_path):
        """Create a minimal generator for timecode tests."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        mock_info = MagicMock(spec=VideoInfo)
        mock_info.duration = 600.0
        mock_info.frame_count = 36000
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_info):
            gen = KdenliveGenerator(
                video_path=video_path,
                segments=[{"in": 0, "out": 100, "score": "0-0-2"}],
                fps=60.0,
            )
        gen._video_info = mock_info
        return gen

    def test_timecode_to_frames_zero(self, generator):
        """Test zero timecode conversion."""
        assert generator._timecode_to_frames("00:00:00.000") == 0

    def test_timecode_to_frames_one_second(self, generator):
        """Test one second converts to fps frames."""
        assert generator._timecode_to_frames("00:00:01.000") == 60

    def test_timecode_to_frames_milliseconds(self, generator):
        """Test conversion with milliseconds."""
        # 0.5 seconds = 30 frames at 60fps
        assert generator._timecode_to_frames("00:00:00.500") == 30

    def test_timecode_to_frames_complex(self, generator):
        """Test complex timecode."""
        # 1:23:45.678 = 5025.678 seconds = 301540.68 frames
        frames = generator._timecode_to_frames("01:23:45.678")
        assert frames == round(5025.678 * 60)

    def test_timecode_round_trip_consistency(self, generator):
        """Test frames -> timecode -> frames round-trip is consistent.

        This is the key property needed for AVSplit group alignment.
        """
        test_frames = [0, 60, 150, 1234, 5000, 35999]
        for original_frame in test_frames:
            timecode = generator.frames_to_timecode(original_frame)
            recovered_frame = generator._timecode_to_frames(timecode)
            assert recovered_frame == original_frame, (
                f"Round-trip failed: {original_frame} -> {timecode} -> {recovered_frame}"
            )


class TestAVSplitGroups:
    """Test AVSplit group generation for A/V clip linking."""

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo for testing."""
        info = MagicMock(spec=VideoInfo)
        info.duration = 600.0
        info.frame_count = 36000
        return info

    @pytest.fixture
    def generator_with_segments(self, tmp_path, mock_video_info):
        """Create a generator with multiple segments."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        segments = [
            {"in": 100, "out": 400, "score": "0-0-2"},   # duration: 300 frames
            {"in": 600, "out": 900, "score": "1-0-2"},   # duration: 300 frames
            {"in": 1200, "out": 1500, "score": "2-0-2"}, # duration: 300 frames
        ]
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            gen = KdenliveGenerator(
                video_path=video_path,
                segments=segments,
                fps=60.0,
            )
        gen._video_info = mock_video_info
        return gen

    def test_avsplit_groups_count(self, generator_with_segments):
        """Test correct number of AVSplit groups are generated."""
        groups_json = generator_with_segments._generate_avsplit_groups()
        groups = json.loads(groups_json)
        assert len(groups) == 3

    def test_avsplit_groups_structure(self, generator_with_segments):
        """Test AVSplit group structure is correct."""
        groups_json = generator_with_segments._generate_avsplit_groups()
        groups = json.loads(groups_json)

        for group in groups:
            assert group["type"] == "AVSplit"
            assert len(group["children"]) == 2
            for child in group["children"]:
                assert child["leaf"] == "clip"
                assert child["type"] == "Leaf"
                # Data format: "TRACK:FRAME:-1"
                parts = child["data"].split(":")
                assert len(parts) == 3
                assert parts[0] in ["1", "2"]  # Track 1 or 2
                assert parts[2] == "-1"

    def test_avsplit_groups_track_pairing(self, generator_with_segments):
        """Test each group has one track 1 and one track 2 child."""
        groups_json = generator_with_segments._generate_avsplit_groups()
        groups = json.loads(groups_json)

        for group in groups:
            tracks = [child["data"].split(":")[0] for child in group["children"]]
            assert sorted(tracks) == ["1", "2"]

    def test_avsplit_groups_use_frame_positions(self, generator_with_segments):
        """Test positions use cumulative frame positions on output timeline.

        MLT out points are INCLUSIVE, so duration = out - in + 1.
        Segments: 100-400, 600-900, 1200-1500
        Durations: 301, 301, 301 (with +1 for inclusive out)
        Positions: 0, 301, 602
        """
        groups_json = generator_with_segments._generate_avsplit_groups()
        groups = json.loads(groups_json)

        # Extract positions from track 1 children
        positions = []
        for group in groups:
            for child in group["children"]:
                if child["data"].startswith("1:"):
                    frame = int(child["data"].split(":")[1])
                    positions.append(frame)
                    break

        # Each segment is 300 frames raw, but +1 for inclusive = 301 frames each
        assert positions == [0, 301, 602]

    def test_avsplit_groups_match_audio_video_positions(self, generator_with_segments):
        """Test audio and video clip positions match within each group."""
        groups_json = generator_with_segments._generate_avsplit_groups()
        groups = json.loads(groups_json)

        for group in groups:
            positions = {}
            for child in group["children"]:
                track = child["data"].split(":")[0]
                frame = int(child["data"].split(":")[1])
                positions[track] = frame

            assert positions["1"] == positions["2"], (
                f"Audio/video position mismatch: track 1 @ {positions['1']}, track 2 @ {positions['2']}"
            )

    def test_avsplit_groups_cumulative_frame_positions(self, generator_with_segments):
        """Test AVSplit group positions are cumulative frame positions.

        Each segment's position should be the sum of all previous segment durations.
        MLT out points are INCLUSIVE, so duration = out - in + 1.
        """
        gen = generator_with_segments

        groups_json = gen._generate_avsplit_groups()
        groups = json.loads(groups_json)

        # Should have one group per segment
        assert len(groups) == len(gen.segments)

        # Calculate expected positions
        expected_positions = []
        current_frame = 0
        for i, seg in enumerate(gen.segments):
            expected_positions.append(current_frame)
            out_frame = gen._get_segment_out_frame(seg, i)
            duration = out_frame - seg["in"] + 1  # +1 for inclusive out
            current_frame += duration

        # Verify actual positions match expected
        for i, group in enumerate(groups):
            for child in group["children"]:
                frame = int(child["data"].split(":")[1])
                assert frame == expected_positions[i], (
                    f"Group {i} has position {frame}, expected {expected_positions[i]}"
                )


class TestGetSegmentOutFrame:
    """Test _get_segment_out_frame helper method."""

    @pytest.fixture
    def mock_video_info(self):
        """Create a mock VideoInfo."""
        info = MagicMock(spec=VideoInfo)
        info.duration = 600.0
        info.frame_count = 36000
        return info

    def test_regular_segment_no_extension(self, tmp_path, mock_video_info):
        """Test regular segment returns original out frame."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        segments = [
            {"in": 100, "out": 400, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
        ]
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            gen = KdenliveGenerator(
                video_path=video_path,
                segments=segments,
                fps=60.0,
            )
        gen._video_info = mock_video_info

        # First segment - not last, no extension
        assert gen._get_segment_out_frame(segments[0], 0) == 400

    def test_last_segment_without_completion_no_extension(self, tmp_path, mock_video_info):
        """Test last segment without game completion has no extension."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake")
        segments = [
            {"in": 100, "out": 400, "score": "0-0-2"},
            {"in": 600, "out": 900, "score": "1-0-2"},
        ]
        with patch("src.output.kdenlive_generator.probe_video", return_value=mock_video_info):
            gen = KdenliveGenerator(
                video_path=video_path,
                segments=segments,
                fps=60.0,
                game_completion=None,
            )
        gen._video_info = mock_video_info

        # Last segment without game completion - no extension
        assert gen._get_segment_out_frame(segments[1], 1) == 900
