"""Hardware encoder detection and optimal configuration.

This module detects available hardware encoders (NVENC, libx264) and provides
optimal encoding configurations based on system capabilities or user settings.

Configuration can be provided via ~/.config/pickleball-editor/config.json
in the "encoder" section. Set active_profile to a profile name to use that
profile, or "auto" for hardware-based auto-detection.
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.app_config import EncoderSettings


@dataclass
class EncoderConfig:
    """Encoder configuration for FFmpeg export.

    Attributes:
        codec: FFmpeg codec name (e.g., "h264_nvenc" or "libx264")
        preset: Encoder preset (e.g., "p5" for NVENC, "medium" for libx264)
        rate_control: Rate control arguments as a list
        extra_opts: Additional encoder-specific options
        audio_codec: Audio codec (default: "aac")
        audio_bitrate: Audio bitrate (default: "192k")
    """

    codec: str
    preset: str
    rate_control: list[str]
    extra_opts: list[str]
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


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


def _get_auto_config() -> EncoderConfig:
    """Get auto-detected encoder config based on hardware.

    Returns:
        EncoderConfig with NVENC if available, otherwise libx264
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


def get_optimal_config(encoder_settings: EncoderSettings | None = None) -> EncoderConfig:
    """Get encoder config based on settings or hardware auto-detection.

    If encoder_settings is provided and has an active profile (not "auto"),
    uses that profile's configuration. Otherwise, auto-detects based on
    available hardware.

    Args:
        encoder_settings: Optional EncoderSettings from AppSettings.
                         If None or active_profile is "auto", uses auto-detection.

    Returns:
        EncoderConfig with optimal settings
    """
    # Check if we have settings with a specific profile
    if encoder_settings is not None:
        profile = encoder_settings.get_active_profile()
        if profile is not None:
            return EncoderConfig(
                codec=profile.codec,
                preset=profile.preset,
                rate_control=list(profile.rate_control),
                extra_opts=list(profile.extra_video_opts),
                audio_codec=profile.audio_codec,
                audio_bitrate=profile.audio_bitrate,
            )

    # Fall back to auto-detection
    return _get_auto_config()


__all__ = ["EncoderConfig", "detect_nvenc_available", "get_optimal_config"]
