#!/usr/bin/env python3
"""Manual test script for VideoWidget MPV embedding.

Usage:
    python tests/test_player.py <video_file>

This script creates a simple window with the VideoWidget embedded and
basic playback controls to verify that:
- MPV embedding works correctly in PyQt6
- Signals are emitted properly
- Frame stepping and seeking work

Note: This is a manual test utility, not a pytest test suite.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.video.player import VideoWidget


class PlayerDemoWindow(QMainWindow):
    """Demo window for testing VideoWidget (not a pytest test class)."""

    def __init__(self) -> None:
        """Initialize test window."""
        super().__init__()
        self.setWindowTitle("MPV Embedding Test")
        self.resize(800, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Video widget
        self.video = VideoWidget()
        layout.addWidget(self.video, stretch=1)

        # Position label
        self.position_label = QLabel("Position: 0.00s / 0.00s")
        layout.addWidget(self.position_label)

        # Controls
        controls = QHBoxLayout()

        btn_play = QPushButton("Play/Pause")
        btn_play.clicked.connect(self.video.toggle_pause)
        controls.addWidget(btn_play)

        btn_step_back = QPushButton("<< Frame")
        btn_step_back.clicked.connect(self.video.frame_back_step)
        controls.addWidget(btn_step_back)

        btn_step = QPushButton("Frame >>")
        btn_step.clicked.connect(self.video.frame_step)
        controls.addWidget(btn_step)

        btn_slow = QPushButton("0.5x")
        btn_slow.clicked.connect(lambda: self.video.set_speed(0.5))
        controls.addWidget(btn_slow)

        btn_normal = QPushButton("1.0x")
        btn_normal.clicked.connect(lambda: self.video.set_speed(1.0))
        controls.addWidget(btn_normal)

        btn_fast = QPushButton("2.0x")
        btn_fast.clicked.connect(lambda: self.video.set_speed(2.0))
        controls.addWidget(btn_fast)

        layout.addLayout(controls)

        # Connect signals
        self.video.position_changed.connect(self._on_position)
        self.video.duration_changed.connect(self._on_duration)
        self.video.playback_finished.connect(self._on_finished)

        self._duration: float = 0.0

    def _on_position(self, pos: float) -> None:
        """Handle position updates.

        Args:
            pos: Current position in seconds
        """
        frame = self.video.get_position_frame()
        self.position_label.setText(
            f"Position: {pos:.2f}s / {self._duration:.2f}s (Frame {frame})"
        )

    def _on_duration(self, dur: float) -> None:
        """Handle duration update.

        Args:
            dur: Video duration in seconds
        """
        self._duration = dur
        print(f"Duration: {dur:.2f}s @ {self.video.fps} FPS")

    def _on_finished(self) -> None:
        """Handle playback finished."""
        print("Playback finished")

    def load_video(self, path: str, fps: float = 60.0) -> None:
        """Load a video file.

        Args:
            path: Path to video file
            fps: Frame rate for frame calculations
        """
        self.video.load(path, fps=fps)

    def closeEvent(self, event) -> None:
        """Handle window close.

        Args:
            event: Close event from Qt
        """
        self.video.cleanup()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # CRITICAL: Qt resets locale during init - must restore for MPV.
    # Use both environment variable AND locale.setlocale for robustness.
    import os
    import locale
    os.environ["LC_NUMERIC"] = "C"
    locale.setlocale(locale.LC_NUMERIC, "C")

    win = PlayerDemoWindow()
    win.show()

    # Load test video if provided
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        # Try to detect FPS (default to 60)
        fps = 60.0
        if len(sys.argv) > 2:
            fps = float(sys.argv[2])

        win.load_video(video_path, fps=fps)
        print(f"Loaded: {video_path}")
        print("Controls:")
        print("  - Play/Pause: Toggle playback")
        print("  - << Frame / Frame >>: Step by frame")
        print("  - 0.5x / 1.0x / 2.0x: Change speed")
    else:
        print("Usage: python test_player.py <video_file> [fps]")
        print("Example: python test_player.py video.mp4 60.0")

    sys.exit(app.exec())
