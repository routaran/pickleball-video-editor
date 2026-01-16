"""Tests for PlaybackControls widget with configurable skip durations.

This module tests the PlaybackControls widget from src/ui/widgets/playback_controls.py,
including initialization, property access, signal emissions, tooltip configuration,
and time display formatting.
"""

import pytest
from PyQt6.QtWidgets import QApplication

from src.ui.widgets.playback_controls import PlaybackControls


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for widget tests.

    This fixture creates a single QApplication instance for all tests in this module.
    PyQt6 requires a QApplication to exist before creating any widgets.

    Yields:
        QApplication: The application instance (or existing one if already created)
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ============================================================================
# Initialization Tests
# ============================================================================


def test_default_skip_durations(qapp):
    """Test that PlaybackControls uses default skip durations.

    Default values:
    - small_skip: 1.0 seconds
    - large_skip: 5.0 seconds
    """
    controls = PlaybackControls()

    assert controls.small_skip_duration == 1.0
    assert controls.large_skip_duration == 5.0


def test_custom_skip_durations(qapp):
    """Test that PlaybackControls accepts custom skip durations."""
    controls = PlaybackControls(small_skip=2.0, large_skip=10.0)

    assert controls.small_skip_duration == 2.0
    assert controls.large_skip_duration == 10.0


def test_widget_creation(qapp):
    """Test that PlaybackControls widget creates without error."""
    controls = PlaybackControls()

    # Widget should be created successfully
    assert controls is not None
    assert controls.isWidgetType()

    # Check that key UI elements exist
    assert hasattr(controls, "_btn_play_pause")
    assert hasattr(controls, "_btn_skip_back_5s")
    assert hasattr(controls, "_btn_skip_forward_5s")
    assert hasattr(controls, "_time_label")
    assert hasattr(controls, "_btn_speed_normal")


# ============================================================================
# Property Tests
# ============================================================================


def test_small_skip_duration_property(qapp):
    """Test that small_skip_duration property returns correct value."""
    controls = PlaybackControls(small_skip=0.5, large_skip=5.0)

    assert controls.small_skip_duration == 0.5


def test_large_skip_duration_property(qapp):
    """Test that large_skip_duration property returns correct value."""
    controls = PlaybackControls(small_skip=1.0, large_skip=15.0)

    assert controls.large_skip_duration == 15.0


# ============================================================================
# Signal Tests
# ============================================================================


class SignalCollector:
    """Helper class to collect signal emissions for testing."""

    def __init__(self):
        """Initialize empty signal tracking lists."""
        self.signals_emitted = []
        self.values_emitted = []

    def slot(self, *args):
        """Slot to receive signal emissions.

        Args:
            *args: Signal arguments (if any)
        """
        self.signals_emitted.append(True)
        if args:
            self.values_emitted.append(args[0] if len(args) == 1 else args)

    def reset(self):
        """Clear collected signals."""
        self.signals_emitted.clear()
        self.values_emitted.clear()

    @property
    def count(self) -> int:
        """Get number of signals emitted."""
        return len(self.signals_emitted)


def test_skip_back_5s_signal(qapp):
    """Test that skip back 5s button emits skip_back_5s signal."""
    controls = PlaybackControls()
    collector = SignalCollector()
    controls.skip_back_5s.connect(collector.slot)

    # Click the skip back (large duration) button
    controls._btn_skip_back_5s.click()

    # Signal should be emitted once
    assert collector.count == 1


def test_skip_requested_signal_backward(qapp):
    """Test that skip back button emits negative duration in skip_requested signal."""
    controls = PlaybackControls(small_skip=2.0, large_skip=10.0)
    collector = SignalCollector()
    controls.skip_requested.connect(collector.slot)

    # Click skip back large button
    controls._btn_skip_back_5s.click()

    # Should emit negative large_skip value
    assert collector.count == 1
    assert collector.values_emitted[0] == -10.0

    # Clear collector and test small skip back
    collector.reset()
    controls._btn_skip_back_1s.click()

    # Should emit negative small_skip value
    assert collector.count == 1
    assert collector.values_emitted[0] == -2.0


def test_skip_requested_signal_forward(qapp):
    """Test that skip forward button emits positive duration in skip_requested signal."""
    controls = PlaybackControls(small_skip=1.5, large_skip=7.0)
    collector = SignalCollector()
    controls.skip_requested.connect(collector.slot)

    # Click skip forward large button
    controls._btn_skip_forward_5s.click()

    # Should emit positive large_skip value
    assert collector.count == 1
    assert collector.values_emitted[0] == 7.0

    # Clear collector and test small skip forward
    collector.reset()
    controls._btn_skip_forward_1s.click()

    # Should emit positive small_skip value
    assert collector.count == 1
    assert collector.values_emitted[0] == 1.5


def test_play_pause_signal(qapp):
    """Test that play button emits play_pause signal."""
    controls = PlaybackControls()
    collector = SignalCollector()
    controls.play_pause.connect(collector.slot)

    # Click play/pause button
    controls._btn_play_pause.click()

    # Signal should be emitted once
    assert collector.count == 1


def test_speed_changed_signal(qapp):
    """Test that speed buttons emit correct speed_changed values."""
    controls = PlaybackControls()
    collector = SignalCollector()
    controls.speed_changed.connect(collector.slot)

    # Click half speed button
    controls._btn_speed_half.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == 0.5

    # Click double speed button
    collector.reset()
    controls._btn_speed_double.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == 2.0

    # Click normal speed button
    collector.reset()
    controls._btn_speed_normal.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == 1.0


def test_speed_changed_signal_not_emitted_on_same_speed(qapp):
    """Test that clicking the same speed button twice doesn't emit signal second time."""
    controls = PlaybackControls()
    collector = SignalCollector()
    controls.speed_changed.connect(collector.slot)

    # Normal speed is already selected by default, clicking again should not emit
    controls._btn_speed_normal.click()
    assert collector.count == 0

    # Change to half speed
    controls._btn_speed_half.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == 0.5

    # Click half speed again (already selected)
    collector.reset()
    controls._btn_speed_half.click()
    assert collector.count == 0


# ============================================================================
# Tooltip Tests
# ============================================================================


def test_tooltips_show_custom_durations(qapp):
    """Test that tooltips reflect configured skip durations."""
    controls = PlaybackControls(small_skip=0.5, large_skip=10.0)

    # Check skip back tooltips
    assert controls._btn_skip_back_1s.toolTip() == "Skip back 0.5s"
    assert controls._btn_skip_back_5s.toolTip() == "Skip back 10s"

    # Check skip forward tooltips
    assert controls._btn_skip_forward_1s.toolTip() == "Skip forward 0.5s"
    assert controls._btn_skip_forward_5s.toolTip() == "Skip forward 10s"

    # Check play/pause tooltip (default state)
    assert controls._btn_play_pause.toolTip() == "Play / Pause"


def test_tooltips_integer_durations(qapp):
    """Test that integer durations are formatted without decimal point."""
    controls = PlaybackControls(small_skip=1.0, large_skip=5.0)

    # Integer values should be formatted as "1s" not "1.0s"
    assert controls._btn_skip_back_1s.toolTip() == "Skip back 1s"
    assert controls._btn_skip_back_5s.toolTip() == "Skip back 5s"
    assert controls._btn_skip_forward_1s.toolTip() == "Skip forward 1s"
    assert controls._btn_skip_forward_5s.toolTip() == "Skip forward 5s"


def test_play_pause_tooltip_updates(qapp):
    """Test that play/pause button tooltip changes with playback state."""
    controls = PlaybackControls()

    # Initial state: not playing
    assert controls._btn_play_pause.toolTip() == "Play / Pause"

    # Set playing state
    controls.set_playing(True)
    assert controls._btn_play_pause.toolTip() == "Pause"

    # Set paused state
    controls.set_playing(False)
    assert controls._btn_play_pause.toolTip() == "Play"


# ============================================================================
# Time Display Tests
# ============================================================================


def test_set_time_updates_display(qapp):
    """Test that set_time() updates the time label display."""
    controls = PlaybackControls()

    # Set time to 3 minutes 45 seconds out of 9 minutes 15 seconds
    controls.set_time(225.0, 555.0)

    # Label should show MM:SS / MM:SS format
    assert controls._time_label.text() == "03:45 / 09:15"


def test_time_format(qapp):
    """Test that time is formatted correctly as MM:SS."""
    controls = PlaybackControls()

    # Test various time formats
    controls.set_time(0.0, 0.0)
    assert controls._time_label.text() == "00:00 / 00:00"

    controls.set_time(65.5, 130.8)  # Fractional seconds should be truncated
    assert controls._time_label.text() == "01:05 / 02:10"

    controls.set_time(3725.8, 7200.0)  # Over 60 minutes
    assert controls._time_label.text() == "62:05 / 120:00"


def test_time_format_negative_values(qapp):
    """Test that negative time values are clamped to 00:00."""
    controls = PlaybackControls()

    # Negative values should be treated as 0
    controls.set_time(-10.0, 100.0)
    assert controls._time_label.text() == "00:00 / 01:40"


def test_initial_time_display(qapp):
    """Test that time display shows 00:00 / 00:00 initially."""
    controls = PlaybackControls()

    # Default time should be zero
    assert controls._time_label.text() == "00:00 / 00:00"


# ============================================================================
# Playback State Tests
# ============================================================================


def test_set_playing_updates_button_icon(qapp):
    """Test that set_playing() updates the play/pause button text."""
    controls = PlaybackControls()

    # Initial state: paused (play icon)
    assert controls._btn_play_pause.text() == "▶"

    # Set to playing state
    controls.set_playing(True)
    assert controls._btn_play_pause.text() == "❚❚"

    # Set back to paused state
    controls.set_playing(False)
    assert controls._btn_play_pause.text() == "▶"


def test_internal_playing_state_tracking(qapp):
    """Test that internal _is_playing state is tracked correctly."""
    controls = PlaybackControls()

    # Initial state
    assert controls._is_playing is False

    # Set playing
    controls.set_playing(True)
    assert controls._is_playing is True

    # Set paused
    controls.set_playing(False)
    assert controls._is_playing is False


# ============================================================================
# Speed Control Tests
# ============================================================================


def test_initial_speed_is_normal(qapp):
    """Test that initial playback speed is 1.0x (normal)."""
    controls = PlaybackControls()

    assert controls.get_speed() == 1.0
    assert controls._btn_speed_normal.isChecked()
    assert not controls._btn_speed_half.isChecked()
    assert not controls._btn_speed_double.isChecked()


def test_set_speed_programmatically(qapp):
    """Test that set_speed() updates UI without emitting signal."""
    controls = PlaybackControls()
    collector = SignalCollector()
    controls.speed_changed.connect(collector.slot)

    # Set speed to 0.5x programmatically
    controls.set_speed(0.5)

    # UI should update
    assert controls.get_speed() == 0.5
    assert controls._btn_speed_half.isChecked()

    # No signal should be emitted
    assert collector.count == 0

    # Set speed to 2.0x
    controls.set_speed(2.0)
    assert controls.get_speed() == 2.0
    assert controls._btn_speed_double.isChecked()
    assert collector.count == 0


def test_speed_buttons_mutually_exclusive(qapp):
    """Test that speed buttons are mutually exclusive."""
    controls = PlaybackControls()

    # Initially normal speed is checked
    assert controls._btn_speed_normal.isChecked()

    # Click half speed
    controls._btn_speed_half.click()
    assert controls._btn_speed_half.isChecked()
    assert not controls._btn_speed_normal.isChecked()
    assert not controls._btn_speed_double.isChecked()

    # Click double speed
    controls._btn_speed_double.click()
    assert controls._btn_speed_double.isChecked()
    assert not controls._btn_speed_normal.isChecked()
    assert not controls._btn_speed_half.isChecked()


def test_get_speed(qapp):
    """Test that get_speed() returns current speed value."""
    controls = PlaybackControls()

    # Initial speed
    assert controls.get_speed() == 1.0

    # Change via button click
    controls._btn_speed_half.click()
    assert controls.get_speed() == 0.5

    controls._btn_speed_double.click()
    assert controls.get_speed() == 2.0


# ============================================================================
# Integration Tests
# ============================================================================


def test_multiple_skip_signals(qapp):
    """Test that both specific and generic skip signals are emitted."""
    controls = PlaybackControls(small_skip=1.0, large_skip=5.0)

    # Listen to both skip_forward_1s and skip_requested signals
    specific_collector = SignalCollector()
    generic_collector = SignalCollector()
    controls.skip_forward_1s.connect(specific_collector.slot)
    controls.skip_requested.connect(generic_collector.slot)

    # Click small forward skip button
    controls._btn_skip_forward_1s.click()

    # Both signals should be emitted
    assert specific_collector.count == 1
    assert generic_collector.count == 1
    assert generic_collector.values_emitted[0] == 1.0


def test_all_transport_buttons_emit_signals(qapp):
    """Test that all transport buttons emit their respective signals."""
    controls = PlaybackControls()

    # Create collectors for all transport signals
    skip_back_5s_collector = SignalCollector()
    skip_back_1s_collector = SignalCollector()
    play_pause_collector = SignalCollector()
    skip_forward_1s_collector = SignalCollector()
    skip_forward_5s_collector = SignalCollector()

    controls.skip_back_5s.connect(skip_back_5s_collector.slot)
    controls.skip_back_1s.connect(skip_back_1s_collector.slot)
    controls.play_pause.connect(play_pause_collector.slot)
    controls.skip_forward_1s.connect(skip_forward_1s_collector.slot)
    controls.skip_forward_5s.connect(skip_forward_5s_collector.slot)

    # Click all buttons
    controls._btn_skip_back_5s.click()
    controls._btn_skip_back_1s.click()
    controls._btn_play_pause.click()
    controls._btn_skip_forward_1s.click()
    controls._btn_skip_forward_5s.click()

    # All signals should be emitted exactly once
    assert skip_back_5s_collector.count == 1
    assert skip_back_1s_collector.count == 1
    assert play_pause_collector.count == 1
    assert skip_forward_1s_collector.count == 1
    assert skip_forward_5s_collector.count == 1


def test_fractional_skip_durations(qapp):
    """Test that fractional skip durations work correctly."""
    controls = PlaybackControls(small_skip=0.25, large_skip=2.5)

    collector = SignalCollector()
    controls.skip_requested.connect(collector.slot)

    # Test forward skip with fractional duration
    controls._btn_skip_forward_1s.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == 0.25

    # Test backward skip with fractional duration
    collector.reset()
    controls._btn_skip_back_5s.click()
    assert collector.count == 1
    assert collector.values_emitted[0] == -2.5


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_zero_skip_durations(qapp):
    """Test that zero skip durations are accepted."""
    controls = PlaybackControls(small_skip=0.0, large_skip=0.0)

    assert controls.small_skip_duration == 0.0
    assert controls.large_skip_duration == 0.0

    collector = SignalCollector()
    controls.skip_requested.connect(collector.slot)
    controls._btn_skip_forward_1s.click()

    assert collector.count == 1
    assert collector.values_emitted[0] == 0.0


def test_large_time_values(qapp):
    """Test that very large time values are formatted correctly."""
    controls = PlaybackControls()

    # Test time over 99 minutes
    controls.set_time(6000.0, 12000.0)
    assert controls._time_label.text() == "100:00 / 200:00"


def test_speed_tolerance_for_invalid_values(qapp):
    """Test that set_speed() handles values outside standard speeds."""
    controls = PlaybackControls()

    # Set an unusual speed value
    controls.set_speed(1.5)

    # Should default to normal speed (1x button)
    assert controls._btn_speed_normal.isChecked()
    assert controls.get_speed() == 1.5
