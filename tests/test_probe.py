"""Unit tests for video probe functionality."""

import pytest
from pathlib import Path
from src.video.probe import (
    ProbeError,
    VideoInfo,
    frames_to_timecode,
    probe_video,
    timecode_to_frames,
    _parse_frame_rate,
)


class TestFrameRateParsing:
    """Test frame rate string parsing."""

    def test_parse_fraction_format(self):
        """Test parsing fraction format (60/1)."""
        assert _parse_frame_rate("60/1") == 60.0
        assert _parse_frame_rate("30/1") == 30.0
        assert abs(_parse_frame_rate("30000/1001") - 29.97) < 0.01

    def test_parse_decimal_format(self):
        """Test parsing decimal format (59.94)."""
        assert _parse_frame_rate("59.94") == 59.94
        assert _parse_frame_rate("30.0") == 30.0

    def test_parse_zero_denominator(self):
        """Test handling zero denominator."""
        assert _parse_frame_rate("60/0") == 0.0


class TestTimecodeConversion:
    """Test timecode conversion functions."""

    def test_frames_to_timecode_basic(self):
        """Test basic frame to timecode conversion."""
        # 30 fps: frame 0 = 0 seconds
        assert frames_to_timecode(0, 30.0) == "00:00:00.000"

        # 30 fps: frame 30 = 1 second
        assert frames_to_timecode(30, 30.0) == "00:00:01.000"

        # 30 fps: frame 1800 = 60 seconds = 1 minute
        assert frames_to_timecode(1800, 30.0) == "00:01:00.000"

        # 30 fps: frame 108000 = 3600 seconds = 1 hour
        assert frames_to_timecode(108000, 30.0) == "01:00:00.000"

    def test_frames_to_timecode_subseconds(self):
        """Test conversion with subsecond precision."""
        # 60 fps: frame 1 = 0.0167 seconds
        result = frames_to_timecode(1, 60.0)
        assert result.startswith("00:00:00.01")

        # 30 fps: frame 15 = 0.5 seconds
        assert frames_to_timecode(15, 30.0) == "00:00:00.500"

    def test_frames_to_timecode_invalid_fps(self):
        """Test error handling for invalid fps."""
        with pytest.raises(ValueError, match="fps must be positive"):
            frames_to_timecode(100, 0.0)

        with pytest.raises(ValueError, match="fps must be positive"):
            frames_to_timecode(100, -30.0)

    def test_timecode_to_frames_basic(self):
        """Test basic timecode to frame conversion."""
        # 30 fps: 1 second = frame 30
        assert timecode_to_frames("00:00:01.000", 30.0) == 30

        # 30 fps: 1 minute = frame 1800
        assert timecode_to_frames("00:01:00.000", 30.0) == 1800

        # 30 fps: 1 hour = frame 108000
        assert timecode_to_frames("01:00:00.000", 30.0) == 108000

    def test_timecode_to_frames_subseconds(self):
        """Test conversion with subsecond precision."""
        # 30 fps: 0.5 seconds = frame 15
        assert timecode_to_frames("00:00:00.500", 30.0) == 15

    def test_timecode_to_frames_invalid_format(self):
        """Test error handling for invalid timecode format."""
        with pytest.raises(ValueError, match="Invalid timecode format"):
            timecode_to_frames("invalid", 30.0)

        with pytest.raises(ValueError, match="Invalid timecode format"):
            timecode_to_frames("00:00", 30.0)

        with pytest.raises(ValueError, match="Invalid timecode format"):
            timecode_to_frames("00:00:abc", 30.0)

    def test_timecode_to_frames_invalid_fps(self):
        """Test error handling for invalid fps."""
        with pytest.raises(ValueError, match="fps must be positive"):
            timecode_to_frames("00:00:01.000", 0.0)

    def test_roundtrip_conversion(self):
        """Test that conversions are reversible."""
        fps = 30.0
        test_frames = [0, 30, 90, 1800, 108000]

        for frame in test_frames:
            timecode = frames_to_timecode(frame, fps)
            converted_frame = timecode_to_frames(timecode, fps)
            assert converted_frame == frame


class TestVideoInfo:
    """Test VideoInfo dataclass."""

    def test_resolution_property(self):
        """Test resolution string property."""
        info = VideoInfo(
            path="/test/video.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC",
        )
        assert info.resolution == "1920x1080"

    def test_aspect_ratio_property(self):
        """Test aspect ratio calculation."""
        info = VideoInfo(
            path="/test/video.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC",
        )
        assert abs(info.aspect_ratio - 16/9) < 0.01

    def test_aspect_ratio_zero_height(self):
        """Test aspect ratio with zero height."""
        info = VideoInfo(
            path="/test/video.mp4",
            width=1920,
            height=0,
            fps=30.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC",
        )
        assert info.aspect_ratio == 0.0

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        info = VideoInfo(
            path="/test/video.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            duration=60.0,
            codec_name="h264",
            codec_long_name="H.264 / AVC",
            bit_rate=5000000,
            frame_count=1800,
        )

        # Serialize
        data = info.to_dict()
        assert data["width"] == 1920
        assert data["height"] == 1080
        assert data["fps"] == 30.0
        assert data["bit_rate"] == 5000000

        # Deserialize
        restored = VideoInfo.from_dict(data)
        assert restored.width == info.width
        assert restored.height == info.height
        assert restored.fps == info.fps
        assert restored.bit_rate == info.bit_rate


class TestProbeVideo:
    """Test probe_video function."""

    def test_probe_nonexistent_file(self):
        """Test error when file doesn't exist."""
        with pytest.raises(ProbeError, match="Video file not found"):
            probe_video("/nonexistent/video.mp4")

    def test_probe_directory(self, tmp_path):
        """Test error when path is a directory."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        with pytest.raises(ProbeError, match="Path is not a file"):
            probe_video(test_dir)

    # Note: Testing actual video probing requires a real video file
    # and ffprobe installed. These tests should be run manually or
    # in CI with a test video fixture.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
