#!/usr/bin/env python3
"""Unit tests for PlaybackControls widget.

Tests the widget's API and signal emissions without requiring a display.
"""

import sys
from pathlib import Path

from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.widgets.playback_controls import PlaybackControls, _format_time


def test_format_time() -> None:
    """Test time formatting function."""
    print("Testing _format_time()...")

    assert _format_time(0.0) == "00:00", "Zero seconds should format as 00:00"
    assert _format_time(5.0) == "00:05", "5 seconds should format as 00:05"
    assert _format_time(65.0) == "01:05", "65 seconds should format as 01:05"
    assert _format_time(125.5) == "02:05", "125.5 seconds should format as 02:05"
    assert _format_time(3725.0) == "62:05", "3725 seconds should format as 62:05"
    assert _format_time(-10.0) == "00:00", "Negative should clamp to 00:00"

    print("✓ _format_time() tests passed")


def test_widget_api(app: QApplication) -> None:
    """Test PlaybackControls API methods."""
    print("\nTesting PlaybackControls API...")

    controls = PlaybackControls()

    # Test initial state
    assert controls.get_speed() == 1.0, "Initial speed should be 1.0"
    print("✓ Initial speed is 1.0")

    # Test set_speed()
    controls.set_speed(0.5)
    assert controls.get_speed() == 0.5, "Speed should change to 0.5"
    print("✓ set_speed(0.5) works")

    controls.set_speed(2.0)
    assert controls.get_speed() == 2.0, "Speed should change to 2.0"
    print("✓ set_speed(2.0) works")

    controls.set_speed(1.0)
    assert controls.get_speed() == 1.0, "Speed should change to 1.0"
    print("✓ set_speed(1.0) works")

    # Test set_playing()
    controls.set_playing(True)
    assert controls._btn_play_pause.text() == "❚❚", "Button should show pause icon"
    print("✓ set_playing(True) updates button to pause icon")

    controls.set_playing(False)
    assert controls._btn_play_pause.text() == "▶", "Button should show play icon"
    print("✓ set_playing(False) updates button to play icon")

    # Test set_time()
    controls.set_time(125.0, 555.0)
    expected_text = "02:05 / 09:15"
    assert controls._time_label.text() == expected_text, \
        f"Time display should be {expected_text}"
    print(f"✓ set_time(125.0, 555.0) displays as {expected_text}")

    print("✓ All API tests passed")


def test_signals(app: QApplication) -> None:
    """Test signal emissions."""
    print("\nTesting signal emissions...")

    controls = PlaybackControls()

    # Test navigation signals
    play_spy = QSignalSpy(controls.play_pause)
    controls._btn_play_pause.click()
    assert len(play_spy) == 1, "play_pause signal should emit"
    print("✓ play_pause signal emits on button click")

    skip_back_5s_spy = QSignalSpy(controls.skip_back_5s)
    controls._btn_skip_back_5s.click()
    assert len(skip_back_5s_spy) == 1, "skip_back_5s signal should emit"
    print("✓ skip_back_5s signal emits on button click")

    skip_forward_1s_spy = QSignalSpy(controls.skip_forward_1s)
    controls._btn_skip_forward_1s.click()
    assert len(skip_forward_1s_spy) == 1, "skip_forward_1s signal should emit"
    print("✓ skip_forward_1s signal emits on button click")

    # Test speed_changed signal
    speed_spy = QSignalSpy(controls.speed_changed)

    controls._btn_speed_half.click()
    assert len(speed_spy) == 1, "speed_changed should emit once"
    assert speed_spy[0][0] == 0.5, "speed_changed should emit 0.5"
    print("✓ speed_changed emits 0.5 when 0.5x button clicked")

    controls._btn_speed_double.click()
    assert len(speed_spy) == 2, "speed_changed should emit twice"
    assert speed_spy[1][0] == 2.0, "speed_changed should emit 2.0"
    print("✓ speed_changed emits 2.0 when 2x button clicked")

    # Test that set_speed() doesn't emit signal
    speed_spy_new = QSignalSpy(controls.speed_changed)
    controls.set_speed(0.5)
    assert len(speed_spy_new) == 0, "set_speed() should not emit signal"
    print("✓ set_speed() does not emit signal (programmatic change)")

    print("✓ All signal tests passed")


def test_exclusive_speed_buttons(app: QApplication) -> None:
    """Test that speed buttons are mutually exclusive."""
    print("\nTesting exclusive speed button selection...")

    controls = PlaybackControls()

    # Initially 1x should be selected
    assert controls._btn_speed_normal.isChecked(), "1x should be initially selected"
    assert not controls._btn_speed_half.isChecked(), "0.5x should not be selected"
    assert not controls._btn_speed_double.isChecked(), "2x should not be selected"
    print("✓ Initial state: only 1x is selected")

    # Click 0.5x
    controls._btn_speed_half.click()
    assert controls._btn_speed_half.isChecked(), "0.5x should be selected"
    assert not controls._btn_speed_normal.isChecked(), "1x should not be selected"
    assert not controls._btn_speed_double.isChecked(), "2x should not be selected"
    print("✓ After clicking 0.5x: only 0.5x is selected")

    # Click 2x
    controls._btn_speed_double.click()
    assert not controls._btn_speed_half.isChecked(), "0.5x should not be selected"
    assert not controls._btn_speed_normal.isChecked(), "1x should not be selected"
    assert controls._btn_speed_double.isChecked(), "2x should be selected"
    print("✓ After clicking 2x: only 2x is selected")

    print("✓ Speed buttons are mutually exclusive")


def main() -> None:
    """Run all tests."""
    app = QApplication(sys.argv)

    print("=" * 60)
    print("PlaybackControls Widget Unit Tests")
    print("=" * 60)

    try:
        test_format_time()
        test_widget_api(app)
        test_signals(app)
        test_exclusive_speed_buttons(app)

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
