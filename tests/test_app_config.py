"""Tests for AppSettings configuration management.

Tests all configuration classes:
- ShortcutConfig: Keyboard shortcut validation
- SkipDurationConfig: Video skip durations
- WindowSizeConfig: Window size constraints
- AppSettings: Configuration persistence (save/load)
"""

import pytest
import json
from pathlib import Path
from src.core.app_config import (
    AppSettings,
    ShortcutConfig,
    SkipDurationConfig,
    WindowSizeConfig,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    return tmp_path / "config"


class TestShortcutConfig:
    """Test ShortcutConfig validation and serialization."""

    def test_default_values(self):
        """Verify default shortcuts are C, S, R, U."""
        config = ShortcutConfig()
        assert config.rally_start == "C"
        assert config.server_wins == "S"
        assert config.receiver_wins == "R"
        assert config.undo == "U"

    def test_validate_success(self):
        """Valid config passes validation."""
        config = ShortcutConfig(
            rally_start="Q",
            server_wins="W",
            receiver_wins="E",
            undo="Z"
        )
        errors = config.validate()
        assert errors == []

    def test_validate_duplicate_keys(self):
        """Duplicate keys fail validation."""
        config = ShortcutConfig(
            rally_start="A",
            server_wins="B",
            receiver_wins="A",  # Duplicate of rally_start
            undo="D"
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Duplicate shortcut 'A'" in errors[0]
        assert "rally_start" in errors[0]
        assert "receiver_wins" in errors[0]

    def test_validate_case_insensitive_duplicates(self):
        """'c' and 'C' are treated as duplicates."""
        config = ShortcutConfig(
            rally_start="c",
            server_wins="S",
            receiver_wins="R",
            undo="C"  # Duplicate of rally_start (case-insensitive)
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "Duplicate shortcut" in errors[0]
        assert ("rally_start" in errors[0] and "undo" in errors[0]) or \
               ("undo" in errors[0] and "rally_start" in errors[0])

    def test_validate_empty_key(self):
        """Empty string fails validation."""
        config = ShortcutConfig(
            rally_start="",
            server_wins="S",
            receiver_wins="R",
            undo="U"
        )
        errors = config.validate()
        assert len(errors) >= 1
        assert any("Empty shortcut not allowed" in err for err in errors)
        assert any("rally_start" in err for err in errors)

    def test_validate_multi_char_key(self):
        """Multi-character shortcut 'CC' fails validation."""
        config = ShortcutConfig(
            rally_start="CC",
            server_wins="S",
            receiver_wins="R",
            undo="U"
        )
        errors = config.validate()
        assert len(errors) >= 1
        assert any("must be single character" in err for err in errors)
        assert any("'CC'" in err for err in errors)

    def test_validate_non_alphanumeric(self):
        """Non-alphanumeric shortcut '!' fails validation."""
        config = ShortcutConfig(
            rally_start="!",
            server_wins="S",
            receiver_wins="R",
            undo="U"
        )
        errors = config.validate()
        assert len(errors) >= 1
        assert any("must be alphanumeric" in err for err in errors)
        assert any("'!'" in err for err in errors)

    def test_validate_numeric_key(self):
        """Numeric shortcut '1' passes validation."""
        config = ShortcutConfig(
            rally_start="1",
            server_wins="2",
            receiver_wins="3",
            undo="4"
        )
        errors = config.validate()
        assert errors == []

    def test_validate_multiple_errors(self):
        """Multiple validation errors are all reported."""
        config = ShortcutConfig(
            rally_start="",      # Empty
            server_wins="XX",    # Multi-char
            receiver_wins="@",   # Non-alphanumeric
            undo="A"             # Valid
        )
        errors = config.validate()
        assert len(errors) >= 3
        # Check all error types are present
        error_text = " ".join(errors)
        assert "Empty shortcut" in error_text
        assert "single character" in error_text
        assert "alphanumeric" in error_text

    def test_to_dict_from_dict_roundtrip(self):
        """Serialization and deserialization preserves values."""
        original = ShortcutConfig(
            rally_start="Q",
            server_wins="W",
            receiver_wins="E",
            undo="Z"
        )
        data = original.to_dict()
        restored = ShortcutConfig.from_dict(data)

        assert restored.rally_start == original.rally_start
        assert restored.server_wins == original.server_wins
        assert restored.receiver_wins == original.receiver_wins
        assert restored.undo == original.undo

    def test_from_dict_missing_fields_use_defaults(self):
        """Missing fields in from_dict use default values."""
        data = {
            "rally_start": "Q",
            # Missing: server_wins, receiver_wins, undo
        }
        config = ShortcutConfig.from_dict(data)

        assert config.rally_start == "Q"
        assert config.server_wins == "S"    # Default
        assert config.receiver_wins == "R"  # Default
        assert config.undo == "U"           # Default

    def test_from_dict_empty_dict(self):
        """Empty dict uses all defaults."""
        config = ShortcutConfig.from_dict({})

        assert config.rally_start == "C"
        assert config.server_wins == "S"
        assert config.receiver_wins == "R"
        assert config.undo == "U"


class TestSkipDurationConfig:
    """Test SkipDurationConfig serialization and storage."""

    def test_default_values(self):
        """Verify all default skip durations."""
        config = SkipDurationConfig()

        # PlaybackControls buttons (absolute, always positive)
        assert config.small_backward == 1.0
        assert config.large_backward == 5.0
        assert config.small_forward == 1.0
        assert config.large_forward == 5.0

        # Keyboard arrow keys (negative = backward)
        assert config.arrow_left == -3.0
        assert config.arrow_right == 5.0
        assert config.arrow_down == -15.0
        assert config.arrow_up == 30.0

    def test_custom_values(self):
        """Custom values are stored correctly."""
        config = SkipDurationConfig(
            small_backward=2.5,
            large_backward=10.0,
            small_forward=1.5,
            large_forward=7.5,
            arrow_left=-5.0,
            arrow_right=10.0,
            arrow_down=-30.0,
            arrow_up=60.0,
        )

        assert config.small_backward == 2.5
        assert config.large_backward == 10.0
        assert config.small_forward == 1.5
        assert config.large_forward == 7.5
        assert config.arrow_left == -5.0
        assert config.arrow_right == 10.0
        assert config.arrow_down == -30.0
        assert config.arrow_up == 60.0

    def test_to_dict_from_dict_roundtrip(self):
        """Serialization and deserialization preserves values."""
        original = SkipDurationConfig(
            small_backward=2.0,
            large_backward=8.0,
            small_forward=1.5,
            large_forward=6.0,
            arrow_left=-4.0,
            arrow_right=7.0,
            arrow_down=-20.0,
            arrow_up=45.0,
        )
        data = original.to_dict()
        restored = SkipDurationConfig.from_dict(data)

        assert restored.small_backward == original.small_backward
        assert restored.large_backward == original.large_backward
        assert restored.small_forward == original.small_forward
        assert restored.large_forward == original.large_forward
        assert restored.arrow_left == original.arrow_left
        assert restored.arrow_right == original.arrow_right
        assert restored.arrow_down == original.arrow_down
        assert restored.arrow_up == original.arrow_up

    def test_from_dict_missing_fields_use_defaults(self):
        """Missing fields in from_dict use default values."""
        data = {
            "small_backward": 3.0,
            "arrow_left": -10.0,
            # Missing: other fields
        }
        config = SkipDurationConfig.from_dict(data)

        assert config.small_backward == 3.0
        assert config.arrow_left == -10.0
        # Defaults for missing fields
        assert config.large_backward == 5.0
        assert config.small_forward == 1.0
        assert config.large_forward == 5.0
        assert config.arrow_right == 5.0
        assert config.arrow_down == -15.0
        assert config.arrow_up == 30.0

    def test_from_dict_empty_dict(self):
        """Empty dict uses all defaults."""
        config = SkipDurationConfig.from_dict({})

        assert config.small_backward == 1.0
        assert config.large_backward == 5.0
        assert config.small_forward == 1.0
        assert config.large_forward == 5.0
        assert config.arrow_left == -3.0
        assert config.arrow_right == 5.0
        assert config.arrow_down == -15.0
        assert config.arrow_up == 30.0


class TestWindowSizeConfig:
    """Test WindowSizeConfig serialization and constraints."""

    def test_default_values(self):
        """Verify default min 1400x1080, max unlimited (0x0)."""
        config = WindowSizeConfig()

        assert config.min_width == 1400
        assert config.min_height == 1080
        assert config.max_width == 0   # 0 = unlimited
        assert config.max_height == 0  # 0 = unlimited

    def test_unlimited_max(self):
        """Max width/height of 0 means unlimited."""
        config = WindowSizeConfig()
        assert config.max_width == 0
        assert config.max_height == 0
        # Semantic meaning: 0 = no maximum constraint

    def test_custom_values(self):
        """Custom window size constraints are stored correctly."""
        config = WindowSizeConfig(
            min_width=1920,
            min_height=1080,
            max_width=3840,
            max_height=2160,
        )

        assert config.min_width == 1920
        assert config.min_height == 1080
        assert config.max_width == 3840
        assert config.max_height == 2160

    def test_to_dict_from_dict_roundtrip(self):
        """Serialization and deserialization preserves values."""
        original = WindowSizeConfig(
            min_width=1600,
            min_height=900,
            max_width=2560,
            max_height=1440,
        )
        data = original.to_dict()
        restored = WindowSizeConfig.from_dict(data)

        assert restored.min_width == original.min_width
        assert restored.min_height == original.min_height
        assert restored.max_width == original.max_width
        assert restored.max_height == original.max_height

    def test_from_dict_missing_fields_use_defaults(self):
        """Missing fields in from_dict use default values."""
        data = {
            "min_width": 1920,
            # Missing: min_height, max_width, max_height
        }
        config = WindowSizeConfig.from_dict(data)

        assert config.min_width == 1920
        assert config.min_height == 1080  # Default
        assert config.max_width == 0      # Default
        assert config.max_height == 0     # Default

    def test_from_dict_empty_dict(self):
        """Empty dict uses all defaults."""
        config = WindowSizeConfig.from_dict({})

        assert config.min_width == 1400
        assert config.min_height == 1080
        assert config.max_width == 0
        assert config.max_height == 0


class TestAppSettings:
    """Test AppSettings configuration persistence (save/load)."""

    def test_default_settings(self):
        """Fresh AppSettings has default values for all sections."""
        settings = AppSettings()

        # Verify shortcuts defaults
        assert settings.shortcuts.rally_start == "C"
        assert settings.shortcuts.server_wins == "S"
        assert settings.shortcuts.receiver_wins == "R"
        assert settings.shortcuts.undo == "U"

        # Verify skip durations defaults
        assert settings.skip_durations.small_backward == 1.0
        assert settings.skip_durations.large_backward == 5.0
        assert settings.skip_durations.arrow_left == -3.0
        assert settings.skip_durations.arrow_up == 30.0

        # Verify window size defaults
        assert settings.window_size.min_width == 1400
        assert settings.window_size.min_height == 1080
        assert settings.window_size.max_width == 0
        assert settings.window_size.max_height == 0

    def test_save_creates_directory(self, temp_config_dir):
        """save() creates config directory if it doesn't exist."""
        settings = AppSettings()

        # Directory doesn't exist yet
        assert not temp_config_dir.exists()

        # Save should create it
        result = settings.save(temp_config_dir)
        assert result is True
        assert temp_config_dir.exists()
        assert temp_config_dir.is_dir()

    def test_save_creates_config_file(self, temp_config_dir):
        """save() creates config.json file."""
        settings = AppSettings()
        result = settings.save(temp_config_dir)

        assert result is True
        config_path = temp_config_dir / "config.json"
        assert config_path.exists()
        assert config_path.is_file()

    def test_save_and_load_roundtrip(self, temp_config_dir):
        """save() then load() returns same values."""
        # Create settings with custom values
        original = AppSettings(
            shortcuts=ShortcutConfig(
                rally_start="Q",
                server_wins="W",
                receiver_wins="E",
                undo="Z"
            ),
            skip_durations=SkipDurationConfig(
                small_backward=2.0,
                large_backward=8.0,
                arrow_left=-5.0,
                arrow_up=45.0,
            ),
            window_size=WindowSizeConfig(
                min_width=1920,
                min_height=1080,
                max_width=3840,
                max_height=2160,
            ),
        )

        # Save and load
        save_result = original.save(temp_config_dir)
        assert save_result is True

        loaded = AppSettings.load(temp_config_dir)

        # Verify shortcuts
        assert loaded.shortcuts.rally_start == "Q"
        assert loaded.shortcuts.server_wins == "W"
        assert loaded.shortcuts.receiver_wins == "E"
        assert loaded.shortcuts.undo == "Z"

        # Verify skip durations
        assert loaded.skip_durations.small_backward == 2.0
        assert loaded.skip_durations.large_backward == 8.0
        assert loaded.skip_durations.arrow_left == -5.0
        assert loaded.skip_durations.arrow_up == 45.0

        # Verify window size
        assert loaded.window_size.min_width == 1920
        assert loaded.window_size.min_height == 1080
        assert loaded.window_size.max_width == 3840
        assert loaded.window_size.max_height == 2160

    def test_load_missing_file(self, temp_config_dir):
        """Returns defaults when config file doesn't exist."""
        # Ensure directory doesn't exist
        assert not temp_config_dir.exists()

        settings = AppSettings.load(temp_config_dir)

        # Should return defaults
        assert settings.shortcuts.rally_start == "C"
        assert settings.skip_durations.small_backward == 1.0
        assert settings.window_size.min_width == 1400

    def test_load_corrupt_json(self, temp_config_dir):
        """Returns defaults when JSON is invalid."""
        # Create directory and write invalid JSON
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_path = temp_config_dir / "config.json"
        config_path.write_text("{ this is not valid JSON }", encoding="utf-8")

        settings = AppSettings.load(temp_config_dir)

        # Should return defaults
        assert settings.shortcuts.rally_start == "C"
        assert settings.skip_durations.small_backward == 1.0
        assert settings.window_size.min_width == 1400

    def test_load_partial_config(self, temp_config_dir):
        """Missing fields use defaults when loading partial config."""
        # Create directory and write partial config
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_path = temp_config_dir / "config.json"

        partial_config = {
            "shortcuts": {
                "rally_start": "Q",
                # Missing: server_wins, receiver_wins, undo
            },
            # Missing: skip_durations, window_size
        }

        config_path.write_text(
            json.dumps(partial_config, indent=2),
            encoding="utf-8"
        )

        settings = AppSettings.load(temp_config_dir)

        # Custom value preserved
        assert settings.shortcuts.rally_start == "Q"

        # Missing shortcuts use defaults
        assert settings.shortcuts.server_wins == "S"
        assert settings.shortcuts.receiver_wins == "R"
        assert settings.shortcuts.undo == "U"

        # Missing sections use defaults
        assert settings.skip_durations.small_backward == 1.0
        assert settings.skip_durations.arrow_up == 30.0
        assert settings.window_size.min_width == 1400
        assert settings.window_size.max_height == 0

    def test_load_non_dict_json(self, temp_config_dir):
        """Returns defaults when JSON is not a dictionary."""
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_path = temp_config_dir / "config.json"

        # Write JSON array instead of object
        config_path.write_text('["not", "a", "dict"]', encoding="utf-8")

        settings = AppSettings.load(temp_config_dir)

        # Should return defaults
        assert settings.shortcuts.rally_start == "C"
        assert settings.skip_durations.small_backward == 1.0
        assert settings.window_size.min_width == 1400

    def test_load_invalid_section_types(self, temp_config_dir):
        """Returns defaults for sections that are not dicts."""
        temp_config_dir.mkdir(parents=True, exist_ok=True)
        config_path = temp_config_dir / "config.json"

        invalid_config = {
            "shortcuts": "not a dict",
            "skip_durations": 123,
            "window_size": ["array"],
        }

        config_path.write_text(
            json.dumps(invalid_config, indent=2),
            encoding="utf-8"
        )

        settings = AppSettings.load(temp_config_dir)

        # All sections should use defaults
        assert settings.shortcuts.rally_start == "C"
        assert settings.skip_durations.small_backward == 1.0
        assert settings.window_size.min_width == 1400

    def test_to_dict_structure(self):
        """to_dict() returns correct nested structure."""
        settings = AppSettings(
            shortcuts=ShortcutConfig(rally_start="X"),
            skip_durations=SkipDurationConfig(small_backward=3.0),
            window_size=WindowSizeConfig(min_width=1600),
        )

        data = settings.to_dict()

        # Check structure
        assert "shortcuts" in data
        assert "skip_durations" in data
        assert "window_size" in data

        # Check shortcuts section
        assert data["shortcuts"]["rally_start"] == "X"
        assert data["shortcuts"]["server_wins"] == "S"

        # Check skip_durations section
        assert data["skip_durations"]["small_backward"] == 3.0
        assert data["skip_durations"]["large_backward"] == 5.0

        # Check window_size section
        assert data["window_size"]["min_width"] == 1600
        assert data["window_size"]["min_height"] == 1080

    def test_save_json_format(self, temp_config_dir):
        """Saved JSON is well-formatted and readable."""
        settings = AppSettings()
        settings.save(temp_config_dir)

        config_path = temp_config_dir / "config.json"
        content = config_path.read_text(encoding="utf-8")

        # Should be valid JSON
        data = json.loads(content)
        assert isinstance(data, dict)

        # Should be indented (not minified)
        assert "\n" in content
        assert "  " in content  # 2-space indent

        # Should end with newline
        assert content.endswith("\n")

    def test_save_permission_error_returns_false(self, temp_config_dir):
        """save() returns False if directory creation fails."""
        # Create a file where directory should be
        temp_config_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_config_dir.write_text("blocking file")

        settings = AppSettings()
        result = settings.save(temp_config_dir)

        # Should return False (cannot create dir over file)
        assert result is False

    def test_multiple_save_load_cycles(self, temp_config_dir):
        """Multiple save/load cycles preserve data correctly."""
        # First cycle
        settings1 = AppSettings(
            shortcuts=ShortcutConfig(rally_start="A"),
        )
        settings1.save(temp_config_dir)

        # Load and modify
        settings2 = AppSettings.load(temp_config_dir)
        settings2.shortcuts.server_wins = "B"
        settings2.save(temp_config_dir)

        # Load and modify again
        settings3 = AppSettings.load(temp_config_dir)
        settings3.shortcuts.receiver_wins = "C"
        settings3.save(temp_config_dir)

        # Final load
        settings4 = AppSettings.load(temp_config_dir)

        # All modifications should be preserved
        assert settings4.shortcuts.rally_start == "A"
        assert settings4.shortcuts.server_wins == "B"
        assert settings4.shortcuts.receiver_wins == "C"
        assert settings4.shortcuts.undo == "U"  # Default unchanged
