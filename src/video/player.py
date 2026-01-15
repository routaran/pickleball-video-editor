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

import ctypes
import locale
import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget

# CRITICAL: Set locale BEFORE importing mpv to prevent numeric parsing issues.
# Use ctypes to call C library setlocale directly.
import sys as _sys
os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")
_libc = ctypes.CDLL("libc.so.6")
_libc.setlocale.restype = ctypes.c_char_p
_result = _libc.setlocale(1, b"C")  # LC_NUMERIC = 1 on Linux
_current = _libc.setlocale(1, None)
print(f"\n{'='*60}")
print(f"LOCALE FIX APPLIED: setlocale={_result}, current={_current}")
print(f"{'='*60}\n")
_sys.stdout.flush()

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

        # CRITICAL: Re-enforce LC_NUMERIC immediately before MPV creation.
        import ctypes
        import sys
        from pathlib import Path
        libc = ctypes.CDLL("libc.so.6")
        libc.setlocale.restype = ctypes.c_char_p
        LC_NUMERIC = 1

        # Force set and verify locale
        libc.setlocale(LC_NUMERIC, b"C")
        current = libc.setlocale(LC_NUMERIC, None)

        # Write to stdout, stderr AND file to guarantee visibility
        msg = f">>> LOCALE CHECK: LC_NUMERIC = {current} <<<"
        print(msg)
        print(msg, file=sys.stderr)
        Path("/tmp/mpv_locale_check.txt").write_text(msg + "\n")

        if current != b"C":
            raise RuntimeError(f"LOCALE NOT SET! Got {current}, expected b'C'")

        # Ensure the widget has a valid native window ID
        # Force creation of native window if not already done
        from PyQt6.QtWidgets import QApplication
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.winId()  # Force window ID creation
        QApplication.processEvents()  # Process pending events

        wid = int(self.winId())

        # Detect display server
        display_server = os.environ.get("XDG_SESSION_TYPE", "unknown")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        print(f">>> MPV EMBEDDING: winId = {wid}, display = {display_server}, wayland = {wayland_display} <<<")

        if wid == 0:
            raise RuntimeError("VideoWidget has invalid winId (0). Widget must be shown first.")

        # Use x11 video output for reliable embedding
        # gpu/libmpv can have issues with window embedding on some systems
        self._player = mpv.MPV(
            wid=str(wid),
            vo="x11",  # x11 is most reliable for embedding
            hwdec="auto-safe",
            input_default_bindings=False,  # Disable MPV keyboard shortcuts
            input_vo_keyboard=False,  # Let Qt handle all keyboard input
            osd_level=1,
            keep_open=True,  # Don't close when video ends
            idle=True,
        )

        # Observe duration property
        self._player.observe_property("duration", self._on_duration_change)

        # Handle end of file
        @self._player.event_callback("end-file")
        def on_end_file(event: Any) -> None:
            # MpvEvent.data returns MpvEventEndFile with reason as int
            # EOF = 0, RESTARTED = 1, ABORTED = 2
            if event.data is not None and event.data.reason == 0:  # EOF
                QTimer.singleShot(0, self.playback_finished.emit)

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
