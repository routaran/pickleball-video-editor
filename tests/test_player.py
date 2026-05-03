#!/usr/bin/env python3
"""MPV VideoWidget tests and manual demo.

Sections
--------
1. Pytest unit tests (collected automatically by pytest) — cover
   ``VideoWidget.get_current_frame_pixmap`` with three mock states:
   - ``_player`` is ``None`` (no video loaded)
   - ``screenshot_raw`` returns a well-formed RGB dict
   - ``screenshot_raw`` returns ``None`` (mpv not ready)

2. Manual integration demo (only runs under ``if __name__ == "__main__"``) —
   creates a window with embedded VideoWidget and basic playback controls for
   live smoke-testing on a real video file.

   Usage:
       python tests/test_player.py <video_file>
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.video.player import VideoWidget


# ===========================================================================
# Pytest unit tests — VideoWidget.get_current_frame_pixmap
# ===========================================================================


# ---------------------------------------------------------------------------
# Session-scoped QApplication fixture (same pattern as test_court_calibrator)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the singleton QApplication, creating it if necessary."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helper: build a VideoWidget whose _player is NOT initialised (avoids real MPV)
# ---------------------------------------------------------------------------


def _make_widget(qapp: QApplication) -> VideoWidget:
    """Return a VideoWidget with ``_player`` left at ``None``.

    ``_create_player`` is replaced with a no-op so that calling ``load()``
    or any method that guards on ``self._player is not None`` behaves safely
    without a live MPV instance.

    Args:
        qapp: Active QApplication (ensures Qt is live).

    Returns:
        VideoWidget instance with ``_player == None``.
    """
    widget = VideoWidget()
    # Prevent accidental real MPV creation during tests.
    widget._create_player = MagicMock()  # type: ignore[method-assign]
    return widget


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestGetCurrentFramePixmap:
    """Unit tests for ``VideoWidget.get_current_frame_pixmap``."""

    # ------------------------------------------------------------------
    # State 1 — no player initialised
    # ------------------------------------------------------------------

    def test_returns_none_when_player_is_none(self, qapp: QApplication) -> None:
        """Must return ``None`` when ``_player`` has never been created."""
        widget = _make_widget(qapp)
        assert widget._player is None

        result = widget.get_current_frame_pixmap()

        assert result is None

    # ------------------------------------------------------------------
    # State 2 — screenshot_raw returns a well-formed RGB dict
    # ------------------------------------------------------------------

    def test_returns_pixmap_for_valid_rgb_dict(self, qapp: QApplication) -> None:
        """Must return a non-null ``QPixmap`` when ``screenshot_raw`` succeeds."""
        width = 16
        height = 9
        stride = width * 3
        raw_bytes = bytes(width * height * 3)  # all-black pixels

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
            "stride": stride,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is not None
        assert isinstance(result, QPixmap)

    def test_pixmap_dimensions_round_trip(self, qapp: QApplication) -> None:
        """The returned ``QPixmap`` must have the same width/height as the dict."""
        width = 32
        height = 18
        stride = width * 3
        raw_bytes = bytes(width * height * 3)

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
            "stride": stride,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is not None
        assert result.width() == width
        assert result.height() == height

    def test_uses_format_rgb888(self, qapp: QApplication) -> None:
        """Must build the intermediate ``QImage`` with ``Format_RGB888``."""
        width = 4
        height = 4
        stride = width * 3
        raw_bytes = bytes(width * height * 3)

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
            "stride": stride,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        # Capture the QImage before it is converted to QPixmap by patching
        # QPixmap.fromImage and inspecting the argument.
        captured_images: list[QImage] = []
        original_from_image = QPixmap.fromImage

        def _spy_from_image(img: QImage, *args, **kwargs) -> QPixmap:
            captured_images.append(img)
            return original_from_image(img, *args, **kwargs)

        QPixmap.fromImage = staticmethod(_spy_from_image)  # type: ignore[assignment]
        try:
            widget.get_current_frame_pixmap()
        finally:
            QPixmap.fromImage = staticmethod(original_from_image)  # type: ignore[assignment]

        assert len(captured_images) == 1
        assert captured_images[0].format() == QImage.Format.Format_RGB888

    def test_uses_stride_from_dict_when_present(self, qapp: QApplication) -> None:
        """When ``stride`` is in the dict it must be used (not recomputed as w*3)."""
        # Use a padded stride (common in YUV/packed frames) — 20 instead of 12
        # for a 4-wide image.  The pixmap must still report the correct width.
        width = 4
        height = 2
        stride = 20  # padded — wider than width * 3 (= 12)
        raw_bytes = bytes(stride * height)

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
            "stride": stride,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is not None
        assert result.width() == width

    def test_stride_defaults_to_width_times_3_when_absent(
        self, qapp: QApplication
    ) -> None:
        """When ``stride`` key is absent the method must infer it as ``w * 3``."""
        width = 8
        height = 4
        raw_bytes = bytes(width * height * 3)

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
            # "stride" deliberately omitted
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is not None
        assert result.width() == width
        assert result.height() == height

    # ------------------------------------------------------------------
    # State 3 — screenshot_raw returns None
    # ------------------------------------------------------------------

    def test_returns_none_when_screenshot_raw_returns_none(
        self, qapp: QApplication
    ) -> None:
        """Must return ``None`` when ``screenshot_raw()`` itself returns ``None``."""
        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = None

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is None

    # ------------------------------------------------------------------
    # Malformed dict — missing required keys
    # ------------------------------------------------------------------

    def test_returns_none_when_data_key_missing(self, qapp: QApplication) -> None:
        """Must return ``None`` when ``data`` key is absent from the raw dict."""
        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {"w": 16, "h": 9}

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is None

    def test_returns_none_when_w_key_missing(self, qapp: QApplication) -> None:
        """Must return ``None`` when ``w`` key is absent from the raw dict."""
        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": bytes(16 * 9 * 3),
            "h": 9,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is None

    def test_returns_none_when_h_key_missing(self, qapp: QApplication) -> None:
        """Must return ``None`` when ``h`` key is absent from the raw dict."""
        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": bytes(16 * 9 * 3),
            "w": 16,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        result = widget.get_current_frame_pixmap()

        assert result is None

    def test_screenshot_raw_called_exactly_once_per_invocation(
        self, qapp: QApplication
    ) -> None:
        """``screenshot_raw`` must be called exactly once per method call."""
        width = 8
        height = 6
        raw_bytes = bytes(width * height * 3)

        mock_player = MagicMock()
        mock_player.screenshot_raw.return_value = {
            "data": raw_bytes,
            "w": width,
            "h": height,
        }

        widget = _make_widget(qapp)
        widget._player = mock_player

        widget.get_current_frame_pixmap()

        mock_player.screenshot_raw.assert_called_once()


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
