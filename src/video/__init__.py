"""
Video playback and metadata extraction.

This package contains:
- player: VideoWidget wrapping python-mpv for embedded playback
- probe: FFprobe wrapper for video metadata (duration, fps, resolution)
"""

from .player import VideoWidget
from .probe import (
    ProbeError,
    VideoInfo,
    frames_to_timecode,
    probe_video,
    timecode_to_frames,
)

__all__ = [
    "ProbeError",
    "VideoInfo",
    "VideoWidget",
    "frames_to_timecode",
    "probe_video",
    "timecode_to_frames",
]
