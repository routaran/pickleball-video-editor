"""Video probing utility using ffprobe.

This module provides functionality to extract video metadata using ffprobe
(part of FFmpeg suite). It extracts:
- Frame rate (fps)
- Duration in seconds
- Resolution (width x height)
- Codec information

Requires ffprobe to be installed on the system (part of ffmpeg package).
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


__all__ = ["VideoInfo", "probe_video", "ProbeError", "frames_to_timecode", "timecode_to_frames"]


class ProbeError(Exception):
    """Raised when video probing fails."""
    pass


@dataclass
class VideoInfo:
    """Container for video metadata extracted by ffprobe.

    Attributes:
        path: Path to the video file
        width: Video width in pixels
        height: Video height in pixels
        fps: Frames per second (as float for variable frame rates)
        duration: Duration in seconds
        codec_name: Video codec name (e.g., "h264", "hevc")
        codec_long_name: Human-readable codec name
        bit_rate: Video bitrate in bits per second (optional)
        frame_count: Total number of frames (optional, may be estimated)
    """
    path: str
    width: int
    height: int
    fps: float
    duration: float
    codec_name: str
    codec_long_name: str
    bit_rate: int | None = None
    frame_count: int | None = None

    @property
    def resolution(self) -> str:
        """Get resolution as string (e.g., '1920x1080')."""
        return f"{self.width}x{self.height}"

    @property
    def aspect_ratio(self) -> float:
        """Get aspect ratio (width / height)."""
        return self.width / self.height if self.height > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration": self.duration,
            "codec_name": self.codec_name,
            "codec_long_name": self.codec_long_name,
            "bit_rate": self.bit_rate,
            "frame_count": self.frame_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoInfo":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            duration=data["duration"],
            codec_name=data["codec_name"],
            codec_long_name=data["codec_long_name"],
            bit_rate=data.get("bit_rate"),
            frame_count=data.get("frame_count"),
        )


def _parse_frame_rate(rate_str: str) -> float:
    """Parse frame rate string (e.g., '60/1' or '59.94') to float.

    Args:
        rate_str: Frame rate string from ffprobe

    Returns:
        Frame rate as float
    """
    if "/" in rate_str:
        num, den = rate_str.split("/")
        return float(num) / float(den) if float(den) != 0 else 0.0
    return float(rate_str)


def probe_video(path: str | Path) -> VideoInfo:
    """Probe a video file to extract metadata using ffprobe.

    This function uses ffprobe (part of FFmpeg) to extract comprehensive
    video metadata including resolution, frame rate, duration, and codec info.

    Args:
        path: Path to the video file

    Returns:
        VideoInfo object containing video metadata

    Raises:
        ProbeError: If the file doesn't exist, isn't a valid video,
                   or ffprobe fails to process it
        FileNotFoundError: If ffprobe is not installed
    """
    path = Path(path)

    # Check file exists before invoking ffprobe
    if not path.exists():
        raise ProbeError(f"Video file not found: {path}")

    if not path.is_file():
        raise ProbeError(f"Path is not a file: {path}")

    # Build ffprobe command
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-select_streams", "v:0",  # First video stream only
        str(path)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
    except FileNotFoundError:
        raise ProbeError(
            "ffprobe not found. Please install ffmpeg: sudo pacman -S ffmpeg"
        )
    except subprocess.TimeoutExpired:
        raise ProbeError(f"ffprobe timed out while processing: {path}")

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        raise ProbeError(f"ffprobe failed: {error_msg}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ProbeError(f"Failed to parse ffprobe output: {e}")

    # Extract video stream info (check exists before accessing)
    streams = data.get("streams", [])
    if not streams:
        raise ProbeError(f"No video stream found in: {path}")

    stream = streams[0]
    format_info = data.get("format", {})

    # Extract frame rate (try avg_frame_rate first, then r_frame_rate)
    fps_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate", "0/1")
    fps = _parse_frame_rate(fps_str)

    if fps <= 0:
        # Fallback: try r_frame_rate if avg was 0
        fps_str = stream.get("r_frame_rate", "30/1")
        fps = _parse_frame_rate(fps_str)

    # Extract duration (from stream or format)
    duration_str = stream.get("duration") or format_info.get("duration", "0")
    try:
        duration = float(duration_str)
    except ValueError:
        duration = 0.0

    # Extract dimensions
    width = stream.get("width", 0)
    height = stream.get("height", 0)

    if width <= 0 or height <= 0:
        raise ProbeError(f"Invalid video dimensions: {width}x{height}")

    # Extract codec info
    codec_name = stream.get("codec_name", "unknown")
    codec_long_name = stream.get("codec_long_name", codec_name)

    # Extract optional info
    bit_rate_str = stream.get("bit_rate") or format_info.get("bit_rate")
    bit_rate = int(bit_rate_str) if bit_rate_str else None

    # Frame count (may be estimated from duration * fps)
    nb_frames = stream.get("nb_frames")
    if nb_frames:
        frame_count = int(nb_frames)
    elif duration > 0 and fps > 0:
        frame_count = int(duration * fps)
    else:
        frame_count = None

    return VideoInfo(
        path=str(path),
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        codec_name=codec_name,
        codec_long_name=codec_long_name,
        bit_rate=bit_rate,
        frame_count=frame_count,
    )


def frames_to_timecode(frame: int, fps: float) -> str:
    """Convert frame number to Kdenlive timecode (HH:MM:SS.mmm).

    Kdenlive uses a timecode format with milliseconds for precise timing.
    This is used when generating XML project files.

    Args:
        frame: Frame number (0-based)
        fps: Frames per second

    Returns:
        Timecode string in HH:MM:SS.mmm format

    Raises:
        ValueError: If fps is non-positive
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")

    total_seconds = frame / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def timecode_to_frames(timecode: str, fps: float) -> int:
    """Convert Kdenlive timecode to frame number.

    Parses a timecode string (HH:MM:SS.mmm) and converts it to a frame number
    based on the given frame rate.

    Args:
        timecode: Timecode string in HH:MM:SS.mmm format
        fps: Frames per second

    Returns:
        Frame number (0-based)

    Raises:
        ValueError: If fps is non-positive or timecode format is invalid
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")

    parts = timecode.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid timecode format: {timecode}")

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except ValueError as e:
        raise ValueError(f"Invalid timecode format: {timecode}") from e

    total_seconds = hours * 3600 + minutes * 60 + seconds
    return int(total_seconds * fps)
