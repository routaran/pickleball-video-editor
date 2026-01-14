"""MPV video player widget for PyQt6.

This module provides a VideoWidget class that embeds the MPV media player
into a PyQt6 application. It handles:
- Video loading and playback control
- Frame-accurate seeking
- Position/duration property observation
- OSD (On-Screen Display) messages

Requires:
- mpv library (system): sudo pacman -S mpv
- python-mpv package: pip install python-mpv

Critical MPV/Qt Integration:
- Must set WA_DontCreateNativeAncestors and WA_NativeWindow attributes
- Must set locale to 'C' BEFORE importing mpv to prevent numeric parsing issues
- Use wid=str(int(self.winId())) for embedding
"""

import locale
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget

# CRITICAL: Set locale BEFORE importing mpv to prevent numeric parsing issues
locale.setlocale(locale.LC_NUMERIC, "C")

import mpv  # noqa: E402 - must import after locale setup


__all__ = ["VideoWidget"]


class VideoWidget(QWidget):
    """Widget that embeds the MPV video player.

    This widget provides a Qt container for the MPV media player with
    full playback control and frame-accurate seeking for video editing.

    Signals:
        position_changed: Emitted when playback position changes (seconds: float)
        duration_changed: Emitted when video duration is known (seconds: float)
        playback_finished: Emitted when video reaches the end

    Attributes:
        fps: Video frame rate (set after loading, used for frame calculations)
    """

    # Signals
    position_changed = pyqtSignal(float)  # Current position in seconds
    duration_changed = pyqtSignal(float)  # Video duration in seconds
    playback_finished = pyqtSignal()  # Video ended

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the video widget.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)

        # Required for proper MPV embedding in Qt
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

        # Initialize state
        self._player: mpv.MPV | None = None
        self._duration: float = 0.0
        self._position: float = 0.0
        self.fps: float = 60.0  # Default, updated when video loads

        # Position update timer (more reliable than property observer in Qt)
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._update_position)
        self._position_timer.setInterval(50)  # 20 FPS updates

    def _create_player(self) -> None:
        """Create the MPV player instance with embedding configuration."""
        if self._player is not None:
            return

        self._player = mpv.MPV(
            wid=str(int(self.winId())),
            vo="gpu",
            hwdec="auto-safe",
            input_default_bindings=True,
            input_vo_keyboard=True,  # Allow arrow keys for seeking
            osd_level=1,
            keep_open=True,  # Don't close when video ends
            idle=True,
        )

        # Observe duration property
        self._player.observe_property("duration", self._on_duration_change)

        # Handle end of file
        @self._player.event_callback("end-file")
        def on_end_file(event: dict[str, Any]) -> None:
            if event.get("reason") == "eof":
                self.playback_finished.emit()

    def _on_duration_change(self, name: str, value: float | None) -> None:
        """Handle duration property changes from MPV.

        Args:
            name: Property name (always "duration")
            value: New duration value in seconds, or None if unknown
        """
        if value is not None and value > 0:
            self._duration = value
            # Emit signal in main thread via timer to avoid threading issues
            QTimer.singleShot(0, lambda: self.duration_changed.emit(value))

    def _update_position(self) -> None:
        """Update position from MPV (called by timer)."""
        if self._player is not None:
            pos = self._player.time_pos
            if pos is not None and pos != self._position:
                self._position = pos
                self.position_changed.emit(pos)

    def load(self, path: str | Path, fps: float = 60.0) -> None:
        """Load a video file.

        Args:
            path: Path to the video file
            fps: Video frame rate (for frame-to-seconds calculations)
        """
        self._create_player()
        self.fps = fps
        if self._player is not None:
            self._player.play(str(path))
            self._position_timer.start()

    def play(self) -> None:
        """Start or resume playback."""
        if self._player is not None:
            self._player.pause = False

    def pause(self) -> None:
        """Pause playback."""
        if self._player is not None:
            self._player.pause = True

    def toggle_pause(self) -> None:
        """Toggle between play and pause."""
        if self._player is not None:
            self._player.pause = not self._player.pause

    @property
    def is_paused(self) -> bool:
        """Check if playback is paused.

        Returns:
            True if paused or no player, False if playing
        """
        if self._player is not None:
            return self._player.pause
        return True

    def seek(self, seconds: float, absolute: bool = True) -> None:
        """Seek to a position in seconds.

        Args:
            seconds: Target position (absolute) or offset (relative)
            absolute: If True, seek to absolute position; if False, seek relative
        """
        if self._player is not None:
            if absolute:
                self._player.seek(seconds, reference="absolute")
            else:
                self._player.seek(seconds, reference="relative")

    def seek_frame(self, frame: int) -> None:
        """Seek to a specific frame number.

        Args:
            frame: Target frame number (0-based)
        """
        if self.fps > 0:
            seconds = frame / self.fps
            self.seek(seconds, absolute=True)

    def frame_step(self) -> None:
        """Step forward one frame (pauses if playing)."""
        if self._player is not None:
            self._player.frame_step()

    def frame_back_step(self) -> None:
        """Step backward one frame (pauses if playing)."""
        if self._player is not None:
            self._player.frame_back_step()

    def set_speed(self, speed: float) -> None:
        """Set playback speed.

        Args:
            speed: Playback speed multiplier (e.g., 0.5=half, 1.0=normal, 2.0=double)
        """
        if self._player is not None:
            self._player.speed = speed

    def get_position(self) -> float:
        """Get current playback position in seconds.

        Returns:
            Current position in seconds, or 0.0 if not playing
        """
        if self._player is not None:
            pos = self._player.time_pos
            return pos if pos is not None else 0.0
        return 0.0

    def get_position_frame(self) -> int:
        """Get current playback position as frame number.

        Returns:
            Current frame number (0-based)
        """
        return int(self.get_position() * self.fps)

    def get_duration(self) -> float:
        """Get video duration in seconds.

        Returns:
            Video duration in seconds, or 0.0 if unknown
        """
        return self._duration

    def show_osd(self, message: str, duration: float = 2.0) -> None:
        """Show an on-screen display message.

        Args:
            message: Text to display
            duration: Display duration in seconds
        """
        if self._player is not None:
            self._player.show_text(message, int(duration * 1000))

    def cleanup(self) -> None:
        """Clean up MPV resources. Call before destroying widget."""
        self._position_timer.stop()
        if self._player is not None:
            self._player.terminate()
            self._player = None

    def closeEvent(self, event) -> None:
        """Handle widget close event.

        Args:
            event: Close event from Qt
        """
        self.cleanup()
        super().closeEvent(event)
