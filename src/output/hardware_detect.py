"""Hardware encoder detection and optimal configuration.

This module detects available hardware encoders (NVENC, libx264) and provides
optimal encoding configurations based on system capabilities.
"""

from dataclasses import dataclass
import shutil
import subprocess


@dataclass
class EncoderConfig:
    """Optimal encoder configuration based on hardware.

    Attributes:
        codec: FFmpeg codec name (e.g., "h264_nvenc" or "libx264")
        preset: Encoder preset (e.g., "p5" for NVENC, "medium" for libx264)
        rate_control: Rate control arguments as a list
        extra_opts: Additional encoder-specific options
    """

    codec: str
    preset: str
    rate_control: list[str]
    extra_opts: list[str]


def detect_nvenc_available() -> bool:
    """Check if h264_nvenc encoder is available.

    Runs ffmpeg to query available encoders and checks for NVENC support.
    This requires both FFmpeg NVENC support and NVIDIA drivers.

    Returns:
        True if h264_nvenc is available, False otherwise
    """
    # LBYL: First check if ffmpeg exists in PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        return False

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return False

        return "h264_nvenc" in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        # Timeout or OS error - fall back to software encoding
        return False


def get_optimal_config() -> EncoderConfig:
    """Get optimal encoder config based on available hardware.

    Detects NVENC availability and returns appropriate configuration.
    Falls back to libx264 software encoding if NVENC is unavailable.

    Returns:
        EncoderConfig with optimal settings for available hardware
    """
    if detect_nvenc_available():
        return EncoderConfig(
            codec="h264_nvenc",
            preset="p5",
            rate_control=["-rc", "constqp", "-qp", "20"],
            extra_opts=[
                "-rc-lookahead",
                "32",
                "-spatial-aq",
                "1",
                "-temporal-aq",
                "1",
            ],
        )
    else:
        return EncoderConfig(
            codec="libx264",
            preset="medium",
            rate_control=["-crf", "20"],
            extra_opts=[],
        )


__all__ = ["EncoderConfig", "detect_nvenc_available", "get_optimal_config"]
