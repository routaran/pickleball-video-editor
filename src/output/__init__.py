"""Output generation module for Pickleball Video Editor.

This module provides:
- SRT subtitle generation from rally segments
- Kdenlive MLT project file generation
- FFmpeg direct MP4 export with hardware encoding
- Hardware encoder detection and configuration
- File output to standardized directory structure
"""

from src.output.subtitle_generator import SubtitleGenerator
from src.output.kdenlive_generator import KdenliveGenerator
from src.output.ffmpeg_exporter import FFmpegExporter
from src.output.hardware_detect import (
    EncoderConfig,
    detect_nvenc_available,
    get_optimal_config,
)

__all__ = [
    "SubtitleGenerator",
    "KdenliveGenerator",
    "FFmpegExporter",
    "EncoderConfig",
    "detect_nvenc_available",
    "get_optimal_config",
]
