"""Application configuration management with JSON persistence.

This module provides user-configurable settings for the Pickleball Video Editor:
- Keyboard shortcuts for rally actions
- Video skip durations for buttons and arrow keys
- Window size constraints
- FFmpeg encoder profiles for video export

Settings are stored in ~/.config/pickleball-editor/config.json.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
from functools import cache


__all__ = [
    "ShortcutConfig",
    "SkipDurationConfig",
    "WindowSizeConfig",
    "EncoderProfile",
    "EncoderSettings",
    "AppSettings",
    "get_default_config_dir",
]


@cache
def get_default_config_dir() -> Path:
    """Get the default configuration directory."""
    return Path.home() / ".config" / "pickleball-editor"


@dataclass
class ShortcutConfig:
    """Keyboard shortcut configuration for rally actions.

    All shortcuts are single-character strings (case-insensitive).
    """

    rally_start: str = "C"
    server_wins: str = "S"
    receiver_wins: str = "R"
    undo: str = "U"

    def validate(self) -> list[str]:
        """Validate shortcuts - no duplicates, single alphanumeric characters.

        Returns:
            List of error messages (empty if valid).
        """
        errors: list[str] = []

        # Collect all shortcuts
        shortcuts = {
            "rally_start": self.rally_start,
            "server_wins": self.server_wins,
            "receiver_wins": self.receiver_wins,
            "undo": self.undo,
        }

        # Check each shortcut is valid
        for name, key in shortcuts.items():
            if not key:
                errors.append(f"{name}: Empty shortcut not allowed")
                continue

            if len(key) != 1:
                errors.append(f"{name}: Shortcut must be single character (got '{key}')")
                continue

            if not key.isalnum():
                errors.append(f"{name}: Shortcut must be alphanumeric (got '{key}')")

        # Check for duplicates (case-insensitive)
        seen: dict[str, str] = {}
        for name, key in shortcuts.items():
            key_upper = key.upper()
            if key_upper in seen:
                errors.append(
                    f"Duplicate shortcut '{key}' used for both {seen[key_upper]} and {name}"
                )
            else:
                seen[key_upper] = name

        return errors

    def to_dict(self) -> dict[str, str]:
        """Serialize to dictionary for JSON export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "ShortcutConfig":
        """Deserialize from dictionary.

        Missing fields are filled with defaults.
        """
        return cls(
            rally_start=data.get("rally_start", "C"),
            server_wins=data.get("server_wins", "S"),
            receiver_wins=data.get("receiver_wins", "R"),
            undo=data.get("undo", "U"),
        )


@dataclass
class SkipDurationConfig:
    """Video skip duration configuration in seconds.

    PlaybackControls buttons use absolute values (always positive).
    Keyboard arrow keys use signed values (negative = backward).
    """

    # PlaybackControls buttons (absolute values, always positive)
    small_backward: float = 1.0
    large_backward: float = 5.0
    small_forward: float = 1.0
    large_forward: float = 5.0

    # Keyboard arrow keys (negative = backward)
    arrow_left: float = -3.0
    arrow_right: float = 5.0
    arrow_down: float = -15.0
    arrow_up: float = 30.0

    def to_dict(self) -> dict[str, float]:
        """Serialize to dictionary for JSON export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "SkipDurationConfig":
        """Deserialize from dictionary.

        Missing fields are filled with defaults.
        """
        return cls(
            small_backward=data.get("small_backward", 1.0),
            large_backward=data.get("large_backward", 5.0),
            small_forward=data.get("small_forward", 1.0),
            large_forward=data.get("large_forward", 5.0),
            arrow_left=data.get("arrow_left", -3.0),
            arrow_right=data.get("arrow_right", 5.0),
            arrow_down=data.get("arrow_down", -15.0),
            arrow_up=data.get("arrow_up", 30.0),
        )


@dataclass
class WindowSizeConfig:
    """Window size constraint configuration.

    A value of 0 for max_width/max_height means unlimited.
    """

    min_width: int = 1400
    min_height: int = 1080
    max_width: int = 0  # 0 = unlimited
    max_height: int = 0  # 0 = unlimited

    def to_dict(self) -> dict[str, int]:
        """Serialize to dictionary for JSON export."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "WindowSizeConfig":
        """Deserialize from dictionary.

        Missing fields are filled with defaults.
        """
        return cls(
            min_width=data.get("min_width", 1400),
            min_height=data.get("min_height", 1080),
            max_width=data.get("max_width", 0),
            max_height=data.get("max_height", 0),
        )


@dataclass
class EncoderProfile:
    """FFmpeg encoder profile configuration.

    Defines codec, preset, rate control, and additional options for video encoding.
    Users can edit these in config.json to customize FFmpeg export behavior.

    Attributes:
        codec: FFmpeg video codec (e.g., "h264_nvenc", "libx264")
        preset: Encoder preset (e.g., "p5" for NVENC, "medium" for libx264)
        rate_control: Rate control arguments as list (e.g., ["-crf", "20"])
        extra_video_opts: Additional encoder options as list
        audio_codec: Audio codec (default: "aac")
        audio_bitrate: Audio bitrate (default: "192k")
    """

    codec: str
    preset: str
    rate_control: list[str] = field(default_factory=list)
    extra_video_opts: list[str] = field(default_factory=list)
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        return {
            "codec": self.codec,
            "preset": self.preset,
            "rate_control": self.rate_control,
            "extra_video_opts": self.extra_video_opts,
            "audio_codec": self.audio_codec,
            "audio_bitrate": self.audio_bitrate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncoderProfile":
        """Deserialize from dictionary."""
        return cls(
            codec=data.get("codec", "libx264"),
            preset=data.get("preset", "medium"),
            rate_control=data.get("rate_control", ["-crf", "20"]),
            extra_video_opts=data.get("extra_video_opts", []),
            audio_codec=data.get("audio_codec", "aac"),
            audio_bitrate=data.get("audio_bitrate", "192k"),
        )


@dataclass
class EncoderSettings:
    """FFmpeg encoder settings with multiple profiles.

    Provides named encoder profiles that can be selected via active_profile.
    Set active_profile to "auto" for hardware-based auto-detection.

    Example config.json encoder section:
        "encoder": {
            "active_profile": "auto",
            "profiles": {
                "nvenc_quality": {
                    "codec": "h264_nvenc",
                    "preset": "p5",
                    "rate_control": ["-rc", "constqp", "-qp", "20"],
                    "extra_video_opts": ["-rc-lookahead", "32", "-spatial-aq", "1"],
                    "audio_codec": "aac",
                    "audio_bitrate": "192k"
                }
            }
        }
    """

    active_profile: str = "auto"
    profiles: dict[str, EncoderProfile] = field(default_factory=dict)

    @classmethod
    def get_defaults(cls) -> "EncoderSettings":
        """Get factory-default encoder settings with common profiles."""
        return cls(
            active_profile="auto",
            profiles={
                "nvenc_quality": EncoderProfile(
                    codec="h264_nvenc",
                    preset="p5",
                    rate_control=["-rc", "constqp", "-qp", "20"],
                    extra_video_opts=["-rc-lookahead", "32", "-spatial-aq", "1", "-temporal-aq", "1"],
                ),
                "nvenc_fast": EncoderProfile(
                    codec="h264_nvenc",
                    preset="p3",
                    rate_control=["-rc", "constqp", "-qp", "24"],
                    extra_video_opts=[],
                ),
                "x264_quality": EncoderProfile(
                    codec="libx264",
                    preset="slow",
                    rate_control=["-crf", "18"],
                    extra_video_opts=[],
                ),
                "x264_fast": EncoderProfile(
                    codec="libx264",
                    preset="veryfast",
                    rate_control=["-crf", "23"],
                    extra_video_opts=[],
                ),
            },
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""
        return {
            "active_profile": self.active_profile,
            "profiles": {name: profile.to_dict() for name, profile in self.profiles.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncoderSettings":
        """Deserialize from dictionary."""
        active_profile = data.get("active_profile", "auto")
        profiles_data = data.get("profiles", {})

        profiles: dict[str, EncoderProfile] = {}
        for name, profile_data in profiles_data.items():
            if isinstance(profile_data, dict):
                profiles[name] = EncoderProfile.from_dict(profile_data)

        # If no profiles loaded, use defaults
        if not profiles:
            defaults = cls.get_defaults()
            profiles = defaults.profiles

        return cls(active_profile=active_profile, profiles=profiles)

    def get_active_profile(self) -> EncoderProfile | None:
        """Get the active encoder profile, or None if set to 'auto'."""
        if self.active_profile == "auto":
            return None
        return self.profiles.get(self.active_profile)


@dataclass
class AppSettings:
    """Application settings container with JSON persistence.

    Settings are stored in ~/.config/pickleball-editor/config.json.
    """

    shortcuts: ShortcutConfig = field(default_factory=ShortcutConfig)
    skip_durations: SkipDurationConfig = field(default_factory=SkipDurationConfig)
    window_size: WindowSizeConfig = field(default_factory=WindowSizeConfig)
    encoder: EncoderSettings = field(default_factory=EncoderSettings.get_defaults)

    def save(self, config_dir: Path | None = None) -> bool:
        """Save settings to JSON configuration file.

        Args:
            config_dir: Directory to save config.json in.
                       Defaults to ~/.config/pickleball-editor/

        Returns:
            True if save succeeded, False otherwise.
        """
        if config_dir is None:
            config_dir = get_default_config_dir()

        # Create config directory if it doesn't exist
        if not config_dir.exists():
            try:
                config_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                return False

        config_path = config_dir / "config.json"

        # Serialize to nested dictionary
        config_dict = {
            "shortcuts": self.shortcuts.to_dict(),
            "skip_durations": self.skip_durations.to_dict(),
            "window_size": self.window_size.to_dict(),
            "encoder": self.encoder.to_dict(),
        }

        # Write JSON file
        try:
            config_path.write_text(
                json.dumps(config_dict, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8"
            )
            return True
        except (OSError, PermissionError, TypeError):
            return False

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "AppSettings":
        """Load settings from JSON configuration file.

        If the file is missing or invalid, returns default settings.
        Partial configs are supported - missing fields use defaults.

        Args:
            config_dir: Directory to load config.json from.
                       Defaults to ~/.config/pickleball-editor/

        Returns:
            AppSettings instance (defaults if file missing/invalid).
        """
        if config_dir is None:
            config_dir = get_default_config_dir()

        config_path = config_dir / "config.json"

        # Return defaults if file doesn't exist
        if not config_path.exists():
            return cls()

        # Try to load and parse JSON
        try:
            content = config_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError):
            # Return defaults if file is unreadable or invalid JSON
            return cls()

        # Validate data is a dictionary
        if not isinstance(data, dict):
            return cls()

        # Deserialize each section (missing sections use defaults)
        shortcuts_data = data.get("shortcuts", {})
        skip_durations_data = data.get("skip_durations", {})
        window_size_data = data.get("window_size", {})
        encoder_data = data.get("encoder", {})

        shortcuts = ShortcutConfig.from_dict(shortcuts_data if isinstance(shortcuts_data, dict) else {})
        skip_durations = SkipDurationConfig.from_dict(skip_durations_data if isinstance(skip_durations_data, dict) else {})
        window_size = WindowSizeConfig.from_dict(window_size_data if isinstance(window_size_data, dict) else {})
        encoder = EncoderSettings.from_dict(encoder_data if isinstance(encoder_data, dict) else {})

        return cls(
            shortcuts=shortcuts,
            skip_durations=skip_durations,
            window_size=window_size,
            encoder=encoder,
        )

    def to_dict(self) -> dict:
        """Serialize to nested dictionary for JSON export."""
        return {
            "shortcuts": self.shortcuts.to_dict(),
            "skip_durations": self.skip_durations.to_dict(),
            "window_size": self.window_size.to_dict(),
            "encoder": self.encoder.to_dict(),
        }
