"""Tests for ConfigDialog UI component.

Tests the configuration dialog which provides a tabbed interface for editing:
- Keyboard shortcuts for rally actions
- Video skip durations for buttons and arrows
- Window size constraints

The dialog validates inputs in real-time and prevents invalid configurations
from being applied.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from src.core.app_config import AppSettings, ShortcutConfig, SkipDurationConfig, WindowSizeConfig
from src.ui.dialogs.config_dialog import ConfigDialog, ConfigDialogResult


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def default_settings():
    """Create default AppSettings for testing."""
    return AppSettings()


@pytest.fixture
def custom_settings():
    """Create custom AppSettings for testing."""
    return AppSettings(
        shortcuts=ShortcutConfig(
            rally_start="X",
            server_wins="Y",
            receiver_wins="Z",
            undo="Q",
        ),
        skip_durations=SkipDurationConfig(
            small_backward=2.0,
            large_backward=10.0,
            small_forward=2.5,
            large_forward=7.5,
            arrow_left=-5.0,
            arrow_right=8.0,
            arrow_down=-20.0,
            arrow_up=40.0,
        ),
        window_size=WindowSizeConfig(
            min_width=1600,
            min_height=1200,
            max_width=2560,
            max_height=1440,
        ),
    )


class TestBasicDialog:
    """Test basic dialog creation and structure."""

    def test_dialog_creation(self, qapp, default_settings):
        """Dialog creates without error."""
        dialog = ConfigDialog(default_settings)
        assert dialog is not None
        assert dialog.windowTitle() == "Configuration"
        assert dialog.isModal()

    def test_dialog_has_tabs(self, qapp, default_settings):
        """Dialog has 3 tabs (Shortcuts, Skip Durations, Window Size)."""
        dialog = ConfigDialog(default_settings)
        assert dialog.tab_widget.count() == 3
        assert dialog.tab_widget.tabText(0) == "Shortcuts"
        assert dialog.tab_widget.tabText(1) == "Skip Durations"
        assert dialog.tab_widget.tabText(2) == "Window Size"

    def test_dialog_displays_current_config(self, qapp, custom_settings):
        """Shows current settings values."""
        dialog = ConfigDialog(custom_settings)

        # Check shortcuts
        assert dialog.rally_start_input.text() == "X"
        assert dialog.server_wins_input.text() == "Y"
        assert dialog.receiver_wins_input.text() == "Z"
        assert dialog.undo_input.text() == "Q"

        # Check skip durations (playback buttons)
        assert dialog.small_backward_spin.value() == 2.0
        assert dialog.large_backward_spin.value() == 10.0
        assert dialog.small_forward_spin.value() == 2.5
        assert dialog.large_forward_spin.value() == 7.5

        # Check skip durations (arrows)
        assert dialog.arrow_left_spin.value() == -5.0
        assert dialog.arrow_right_spin.value() == 8.0
        assert dialog.arrow_down_spin.value() == -20.0
        assert dialog.arrow_up_spin.value() == 40.0

        # Check window size
        assert dialog.min_width_spin.value() == 1600
        assert dialog.min_height_spin.value() == 1200
        assert dialog.max_width_spin.value() == 2560
        assert dialog.max_height_spin.value() == 1440


class TestShortcutsTab:
    """Test Shortcuts tab functionality."""

    def test_shortcuts_tab_shows_defaults(self, qapp, default_settings):
        """Default shortcuts displayed."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        assert dialog.rally_start_input.text() == "C"
        assert dialog.server_wins_input.text() == "S"
        assert dialog.receiver_wins_input.text() == "R"
        assert dialog.undo_input.text() == "U"

    def test_shortcuts_tab_shows_custom_values(self, qapp, custom_settings):
        """Custom shortcuts displayed."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        assert dialog.rally_start_input.text() == "X"
        assert dialog.server_wins_input.text() == "Y"
        assert dialog.receiver_wins_input.text() == "Z"
        assert dialog.undo_input.text() == "Q"

    def test_duplicate_shortcut_validation(self, qapp, default_settings):
        """Error shown for duplicates."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Set duplicate shortcuts
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")

        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "X")

        # Validation should fail
        assert len(dialog.validation_errors) > 0
        assert dialog.error_label.isVisible()
        assert not dialog.apply_button.isEnabled()
        assert "Duplicate" in dialog.error_label.text()

    def test_duplicate_shortcut_case_insensitive(self, qapp, default_settings):
        """Error shown for duplicates (case-insensitive check)."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Set duplicate shortcuts with different cases
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "a")

        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "A")

        # Validation should fail (case-insensitive)
        assert len(dialog.validation_errors) > 0
        assert dialog.error_label.isVisible()
        assert not dialog.apply_button.isEnabled()
        assert "Duplicate" in dialog.error_label.text()

    def test_invalid_shortcut_validation(self, qapp, default_settings):
        """Error shown for invalid chars."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Set invalid shortcut (non-alphanumeric)
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "!")

        # Validation should fail
        assert len(dialog.validation_errors) > 0
        assert dialog.error_label.isVisible()
        assert not dialog.apply_button.isEnabled()
        assert "alphanumeric" in dialog.error_label.text()

    def test_empty_shortcut_validation(self, qapp, default_settings):
        """Error shown for empty shortcuts."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Clear a shortcut
        dialog.rally_start_input.clear()

        # Validation should fail
        assert len(dialog.validation_errors) > 0
        assert dialog.error_label.isVisible()
        assert not dialog.apply_button.isEnabled()
        assert "Empty" in dialog.error_label.text()

    def test_valid_shortcuts_enable_apply(self, qapp, default_settings):
        """Apply button enabled when shortcuts are valid."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Set all valid, unique shortcuts
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "A")

        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "B")

        dialog.receiver_wins_input.clear()
        QTest.keyClicks(dialog.receiver_wins_input, "C")

        dialog.undo_input.clear()
        QTest.keyClicks(dialog.undo_input, "D")

        # Validation should pass
        assert len(dialog.validation_errors) == 0
        assert not dialog.error_label.isVisible()
        assert dialog.apply_button.isEnabled()

    def test_reset_to_defaults_button(self, qapp, custom_settings):
        """Reset button works."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(0)  # Shortcuts tab

        # Verify custom values are loaded
        assert dialog.rally_start_input.text() == "X"
        assert dialog.server_wins_input.text() == "Y"

        # Click reset button
        reset_button = dialog.shortcuts_tab.findChild(type(None), "reset_button")
        if reset_button:
            # Alternative: directly call the method
            dialog._reset_shortcuts_to_defaults()
        else:
            dialog._reset_shortcuts_to_defaults()

        # Verify defaults are restored
        assert dialog.rally_start_input.text() == "C"
        assert dialog.server_wins_input.text() == "S"
        assert dialog.receiver_wins_input.text() == "R"
        assert dialog.undo_input.text() == "U"


class TestSkipDurationsTab:
    """Test Skip Durations tab functionality."""

    def test_skip_durations_tab_shows_defaults(self, qapp, default_settings):
        """Default durations displayed."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(1)  # Skip Durations tab

        # Playback buttons
        assert dialog.small_backward_spin.value() == 1.0
        assert dialog.large_backward_spin.value() == 5.0
        assert dialog.small_forward_spin.value() == 1.0
        assert dialog.large_forward_spin.value() == 5.0

        # Arrow keys
        assert dialog.arrow_left_spin.value() == -3.0
        assert dialog.arrow_right_spin.value() == 5.0
        assert dialog.arrow_down_spin.value() == -15.0
        assert dialog.arrow_up_spin.value() == 30.0

    def test_skip_durations_spinbox_ranges(self, qapp, default_settings):
        """SpinBoxes have correct range (0.5-60.0)."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(1)  # Skip Durations tab

        # Check playback button ranges (positive)
        assert dialog.small_backward_spin.minimum() == 0.5
        assert dialog.small_backward_spin.maximum() == 60.0
        assert dialog.large_backward_spin.minimum() == 0.5
        assert dialog.large_backward_spin.maximum() == 60.0
        assert dialog.small_forward_spin.minimum() == 0.5
        assert dialog.small_forward_spin.maximum() == 60.0
        assert dialog.large_forward_spin.minimum() == 0.5
        assert dialog.large_forward_spin.maximum() == 60.0

        # Check arrow key ranges (some negative)
        assert dialog.arrow_left_spin.minimum() == -60.0
        assert dialog.arrow_left_spin.maximum() == 0.0
        assert dialog.arrow_right_spin.minimum() == 0.5
        assert dialog.arrow_right_spin.maximum() == 60.0
        assert dialog.arrow_down_spin.minimum() == -60.0
        assert dialog.arrow_down_spin.maximum() == 0.0
        assert dialog.arrow_up_spin.minimum() == 0.5
        assert dialog.arrow_up_spin.maximum() == 60.0

    def test_skip_durations_single_step(self, qapp, default_settings):
        """SpinBoxes have correct single step (0.5)."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(1)  # Skip Durations tab

        assert dialog.small_backward_spin.singleStep() == 0.5
        assert dialog.large_backward_spin.singleStep() == 0.5
        assert dialog.small_forward_spin.singleStep() == 0.5
        assert dialog.large_forward_spin.singleStep() == 0.5
        assert dialog.arrow_left_spin.singleStep() == 0.5
        assert dialog.arrow_right_spin.singleStep() == 0.5
        assert dialog.arrow_down_spin.singleStep() == 0.5
        assert dialog.arrow_up_spin.singleStep() == 0.5

    def test_skip_durations_custom_values(self, qapp, custom_settings):
        """Custom durations displayed."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(1)  # Skip Durations tab

        # Playback buttons
        assert dialog.small_backward_spin.value() == 2.0
        assert dialog.large_backward_spin.value() == 10.0
        assert dialog.small_forward_spin.value() == 2.5
        assert dialog.large_forward_spin.value() == 7.5

        # Arrow keys
        assert dialog.arrow_left_spin.value() == -5.0
        assert dialog.arrow_right_spin.value() == 8.0
        assert dialog.arrow_down_spin.value() == -20.0
        assert dialog.arrow_up_spin.value() == 40.0


class TestWindowSizeTab:
    """Test Window Size tab functionality."""

    def test_window_size_tab_shows_defaults(self, qapp, default_settings):
        """Default sizes displayed."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        assert dialog.min_width_spin.value() == 1400
        assert dialog.min_height_spin.value() == 1080
        assert dialog.max_width_spin.value() == 0  # Unlimited
        assert dialog.max_height_spin.value() == 0  # Unlimited

    def test_window_size_tab_shows_custom_values(self, qapp, custom_settings):
        """Custom sizes displayed."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        assert dialog.min_width_spin.value() == 1600
        assert dialog.min_height_spin.value() == 1200
        assert dialog.max_width_spin.value() == 2560
        assert dialog.max_height_spin.value() == 1440

    def test_unlimited_checkbox_default(self, qapp, default_settings):
        """Checkbox checked for unlimited max sizes."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        # Default has unlimited max (0, 0)
        assert dialog.unlimited_max_checkbox.isChecked()
        assert not dialog.max_width_spin.isEnabled()
        assert not dialog.max_height_spin.isEnabled()

    def test_unlimited_checkbox_custom(self, qapp, custom_settings):
        """Checkbox unchecked for limited max sizes."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        # Custom has limited max (2560, 1440)
        assert not dialog.unlimited_max_checkbox.isChecked()
        assert dialog.max_width_spin.isEnabled()
        assert dialog.max_height_spin.isEnabled()

    def test_unlimited_checkbox_disables_spinboxes(self, qapp, custom_settings):
        """Checkbox disables max spinboxes when checked."""
        dialog = ConfigDialog(custom_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        # Initially unchecked
        assert not dialog.unlimited_max_checkbox.isChecked()
        assert dialog.max_width_spin.isEnabled()
        assert dialog.max_height_spin.isEnabled()

        # Check the checkbox
        dialog.unlimited_max_checkbox.setChecked(True)

        # Max spinboxes should be disabled and set to 0
        assert not dialog.max_width_spin.isEnabled()
        assert not dialog.max_height_spin.isEnabled()
        assert dialog.max_width_spin.value() == 0
        assert dialog.max_height_spin.value() == 0

    def test_unlimited_checkbox_enables_spinboxes(self, qapp, default_settings):
        """Checkbox enables max spinboxes when unchecked."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        # Initially checked
        assert dialog.unlimited_max_checkbox.isChecked()
        assert not dialog.max_width_spin.isEnabled()
        assert not dialog.max_height_spin.isEnabled()

        # Uncheck the checkbox
        dialog.unlimited_max_checkbox.setChecked(False)

        # Max spinboxes should be enabled
        assert dialog.max_width_spin.isEnabled()
        assert dialog.max_height_spin.isEnabled()

    def test_window_size_spinbox_ranges(self, qapp, default_settings):
        """SpinBoxes have correct ranges."""
        dialog = ConfigDialog(default_settings)
        dialog.tab_widget.setCurrentIndex(2)  # Window Size tab

        # Minimum size ranges
        assert dialog.min_width_spin.minimum() == 800
        assert dialog.min_width_spin.maximum() == 3840
        assert dialog.min_height_spin.minimum() == 600
        assert dialog.min_height_spin.maximum() == 2160

        # Maximum size ranges (0 = unlimited)
        assert dialog.max_width_spin.minimum() == 0
        assert dialog.max_width_spin.maximum() == 7680
        assert dialog.max_height_spin.minimum() == 0
        assert dialog.max_height_spin.maximum() == 4320


class TestDialogBehavior:
    """Test dialog behavior and result handling."""

    def test_cancel_returns_none(self, qapp, default_settings):
        """Cancel doesn't return result."""
        dialog = ConfigDialog(default_settings)

        # Simulate cancel
        dialog.reject()

        result = dialog.get_result()
        assert result is None

    def test_apply_returns_config(self, qapp, default_settings):
        """Apply returns ConfigDialogResult."""
        dialog = ConfigDialog(default_settings)

        # Modify some settings
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")

        # Simulate apply
        dialog._on_apply()

        result = dialog.get_result()
        assert result is not None
        assert isinstance(result, ConfigDialogResult)
        assert isinstance(result.settings, AppSettings)
        assert result.settings.shortcuts.rally_start == "X"

    def test_apply_collects_all_settings(self, qapp, default_settings):
        """Apply collects all settings from inputs."""
        dialog = ConfigDialog(default_settings)

        # Modify shortcuts
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "A")
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "B")
        dialog.receiver_wins_input.clear()
        QTest.keyClicks(dialog.receiver_wins_input, "C")
        dialog.undo_input.clear()
        QTest.keyClicks(dialog.undo_input, "D")

        # Modify skip durations
        dialog.small_backward_spin.setValue(2.5)
        dialog.large_forward_spin.setValue(8.0)
        dialog.arrow_left_spin.setValue(-7.0)
        dialog.arrow_up_spin.setValue(25.0)

        # Modify window size
        dialog.min_width_spin.setValue(1500)
        dialog.min_height_spin.setValue(1100)
        dialog.unlimited_max_checkbox.setChecked(False)
        dialog.max_width_spin.setValue(1920)
        dialog.max_height_spin.setValue(1080)

        # Apply
        dialog._on_apply()

        result = dialog.get_result()
        assert result is not None

        # Verify shortcuts
        assert result.settings.shortcuts.rally_start == "A"
        assert result.settings.shortcuts.server_wins == "B"
        assert result.settings.shortcuts.receiver_wins == "C"
        assert result.settings.shortcuts.undo == "D"

        # Verify skip durations
        assert result.settings.skip_durations.small_backward == 2.5
        assert result.settings.skip_durations.large_forward == 8.0
        assert result.settings.skip_durations.arrow_left == -7.0
        assert result.settings.skip_durations.arrow_up == 25.0

        # Verify window size
        assert result.settings.window_size.min_width == 1500
        assert result.settings.window_size.min_height == 1100
        assert result.settings.window_size.max_width == 1920
        assert result.settings.window_size.max_height == 1080

    def test_apply_disabled_on_validation_error(self, qapp, default_settings):
        """Apply button disabled when validation errors exist."""
        dialog = ConfigDialog(default_settings)

        # Create a validation error (duplicate shortcuts)
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "X")

        # Apply button should be disabled
        assert not dialog.apply_button.isEnabled()
        assert dialog.error_label.isVisible()

    def test_apply_enabled_on_validation_success(self, qapp, default_settings):
        """Apply button enabled when validation passes."""
        dialog = ConfigDialog(default_settings)

        # Set valid shortcuts
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "A")
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "B")
        dialog.receiver_wins_input.clear()
        QTest.keyClicks(dialog.receiver_wins_input, "C")
        dialog.undo_input.clear()
        QTest.keyClicks(dialog.undo_input, "D")

        # Apply button should be enabled
        assert dialog.apply_button.isEnabled()
        assert not dialog.error_label.isVisible()

    def test_initial_state_valid_defaults(self, qapp, default_settings):
        """Dialog starts with valid defaults and enabled Apply button."""
        dialog = ConfigDialog(default_settings)

        # Default settings should be valid
        assert len(dialog.validation_errors) == 0
        assert not dialog.error_label.isVisible()
        assert dialog.apply_button.isEnabled()

    def test_result_is_none_before_apply(self, qapp, default_settings):
        """Result is None before Apply is clicked."""
        dialog = ConfigDialog(default_settings)

        result = dialog.get_result()
        assert result is None


class TestRealTimeValidation:
    """Test real-time validation feedback."""

    def test_validation_updates_on_text_change(self, qapp, default_settings):
        """Validation runs on every text change."""
        dialog = ConfigDialog(default_settings)

        # Start with valid state
        assert dialog.apply_button.isEnabled()

        # Type an invalid character
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "@")

        # Validation should fail immediately
        assert not dialog.apply_button.isEnabled()
        assert dialog.error_label.isVisible()

        # Fix it
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "A")

        # Validation should pass again
        assert dialog.apply_button.isEnabled()
        assert not dialog.error_label.isVisible()

    def test_validation_error_message_content(self, qapp, default_settings):
        """Validation error messages are descriptive."""
        dialog = ConfigDialog(default_settings)

        # Create duplicate error
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "X")

        error_text = dialog.error_label.text()
        assert "Duplicate" in error_text
        assert "Rally Start" in error_text or "Server Wins" in error_text

    def test_validation_multiple_errors(self, qapp, default_settings):
        """Multiple validation errors are shown."""
        dialog = ConfigDialog(default_settings)

        # Create multiple errors
        dialog.rally_start_input.clear()  # Empty error
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "!")  # Invalid char error

        error_text = dialog.error_label.text()
        assert "Empty" in error_text
        assert "alphanumeric" in error_text


class TestTabSwitching:
    """Test tab switching behavior."""

    def test_tab_switching_preserves_values(self, qapp, default_settings):
        """Switching tabs preserves entered values."""
        dialog = ConfigDialog(default_settings)

        # Modify shortcuts tab
        dialog.tab_widget.setCurrentIndex(0)
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")

        # Switch to skip durations tab
        dialog.tab_widget.setCurrentIndex(1)
        dialog.small_backward_spin.setValue(3.5)

        # Switch back to shortcuts tab
        dialog.tab_widget.setCurrentIndex(0)
        assert dialog.rally_start_input.text() == "X"

        # Switch to skip durations tab again
        dialog.tab_widget.setCurrentIndex(1)
        assert dialog.small_backward_spin.value() == 3.5

    def test_validation_persists_across_tabs(self, qapp, default_settings):
        """Validation errors persist when switching tabs."""
        dialog = ConfigDialog(default_settings)

        # Create validation error on shortcuts tab
        dialog.tab_widget.setCurrentIndex(0)
        dialog.rally_start_input.clear()
        QTest.keyClicks(dialog.rally_start_input, "X")
        dialog.server_wins_input.clear()
        QTest.keyClicks(dialog.server_wins_input, "X")

        assert not dialog.apply_button.isEnabled()

        # Switch to another tab
        dialog.tab_widget.setCurrentIndex(1)

        # Error should still prevent Apply
        assert not dialog.apply_button.isEnabled()
        assert dialog.error_label.isVisible()
