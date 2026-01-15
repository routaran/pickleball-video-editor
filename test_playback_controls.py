#!/usr/bin/env python3
"""Test script for PlaybackControls widget.

This script demonstrates the PlaybackControls widget with a simulated
video player that updates position every 100ms.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.widgets.playback_controls import PlaybackControls


class TestWindow(QMainWindow):
    """Test window for PlaybackControls widget."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PlaybackControls Test")
        self.resize(800, 200)

        # Simulated video state
        self._is_playing = False
        self._position = 0.0  # seconds
        self._duration = 555.0  # 9:15 total duration
        self._speed = 1.0

        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)

        # Create playback controls
        self.controls = PlaybackControls()

        # Connect signals
        self.controls.play_pause.connect(self._toggle_playback)
        self.controls.skip_back_5s.connect(lambda: self._seek(-5.0))
        self.controls.skip_back_1s.connect(lambda: self._seek(-1.0))
        self.controls.skip_forward_1s.connect(lambda: self._seek(1.0))
        self.controls.skip_forward_5s.connect(lambda: self._seek(5.0))
        self.controls.speed_changed.connect(self._change_speed)

        # Initialize display
        self.controls.set_time(self._position, self._duration)
        self.controls.set_playing(self._is_playing)
        self.controls.set_speed(self._speed)

        layout.addWidget(self.controls)
        layout.addStretch()

        # Timer for position updates
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_position)
        self._timer.setInterval(100)  # Update every 100ms

    def _toggle_playback(self) -> None:
        """Toggle play/pause state."""
        self._is_playing = not self._is_playing
        self.controls.set_playing(self._is_playing)

        if self._is_playing:
            self._timer.start()
            print(f"▶ Playing at {self._speed}x speed")
        else:
            self._timer.stop()
            print("❚❚ Paused")

    def _seek(self, offset: float) -> None:
        """Seek by offset in seconds.

        Args:
            offset: Seconds to skip (negative for backward)
        """
        new_position = max(0.0, min(self._duration, self._position + offset))
        self._position = new_position
        self.controls.set_time(self._position, self._duration)
        print(f"⏩ Seek to {self._position:.1f}s")

    def _change_speed(self, speed: float) -> None:
        """Change playback speed.

        Args:
            speed: New playback speed (0.5, 1.0, or 2.0)
        """
        self._speed = speed
        print(f"🏃 Speed changed to {speed}x")

    def _update_position(self) -> None:
        """Update position during playback (called by timer)."""
        if self._is_playing:
            # Advance position based on speed
            increment = 0.1 * self._speed  # 100ms * speed
            self._position = min(self._duration, self._position + increment)

            # Update display
            self.controls.set_time(self._position, self._duration)

            # Stop at end
            if self._position >= self._duration:
                self._is_playing = False
                self.controls.set_playing(False)
                self._timer.stop()
                print("⏹ Reached end of video")


def main() -> None:
    """Run the test application."""
    app = QApplication(sys.argv)

    # Set dark theme for better visibility
    app.setStyle("Fusion")

    window = TestWindow()
    window.show()

    print("\n=== PlaybackControls Test ===")
    print("- Click play to start simulated playback")
    print("- Use skip buttons to navigate")
    print("- Change speed with 0.5x, 1x, 2x buttons")
    print("- Watch console for event logging\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
