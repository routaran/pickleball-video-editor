"""Playback controls widget for video transport and speed control.

This module provides the PlaybackControls widget, which displays:
- Transport controls (skip back/forward, play/pause)
- Playback speed toggles (0.5x, 1x, 2x)
- Time display (current/total in MM:SS format)

Layout:
    |◀   ◀◀   [  ▶  ]   ▶▶   ▶|      0.5x  1x  2x    03:45/09:15
   -5s  -1s    play     +1s  +5s      speed          timecode

The widget uses the "Court Green" design system with monospace fonts for
timecodes to prevent layout shifts during playback.
"""

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from src.ui.styles import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    RADIUS_MD,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    Fonts,
)

__all__ = ["PlaybackControls"]


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS.

    Args:
        seconds: Time in seconds (can be fractional)

    Returns:
        Formatted time string in MM:SS format

    Examples:
        >>> _format_time(0.0)
        '00:00'
        >>> _format_time(65.5)
        '01:05'
        >>> _format_time(3725.8)
        '62:05'
    """
    if seconds < 0:
        seconds = 0

    minutes = int(seconds) // 60
    secs = int(seconds) % 60

    return f"{minutes:02d}:{secs:02d}"


class PlaybackControls(QFrame):
    """Video playback transport controls with speed toggles and time display.

    This widget provides a horizontal control bar with:
    - Navigation buttons: -5s, -1s, play/pause, +1s, +5s
    - Speed toggles: 0.5x, 1x, 2x (mutually exclusive)
    - Time display: MM:SS / MM:SS (current/total)

    Signals:
        skip_back_5s: User clicked |◀ button (skip back 5 seconds)
        skip_back_1s: User clicked ◀◀ button (skip back 1 second)
        play_pause: User clicked ▶/❚❚ button (toggle playback)
        skip_forward_1s: User clicked ▶▶ button (skip forward 1 second)
        skip_forward_5s: User clicked ▶| button (skip forward 5 seconds)
        speed_changed: User changed playback speed (emits 0.5, 1.0, or 2.0)

    Example:
        ```python
        controls = PlaybackControls()

        # Connect to video player
        controls.play_pause.connect(player.toggle_pause)
        controls.skip_forward_1s.connect(lambda: player.seek(1.0, 'relative'))
        controls.speed_changed.connect(player.set_speed)

        # Update UI from player state
        player.position_changed.connect(
            lambda pos: controls.set_time(pos, player.duration)
        )
        player.playing_changed.connect(controls.set_playing)
        ```
    """

    # Navigation signals
    skip_back_5s = pyqtSignal()
    skip_back_1s = pyqtSignal()
    play_pause = pyqtSignal()
    skip_forward_1s = pyqtSignal()
    skip_forward_5s = pyqtSignal()

    # Speed signal
    speed_changed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize playback controls.

        Args:
            parent: Parent widget (default: None)
        """
        super().__init__(parent)

        self._is_playing = False
        self._current_speed = 1.0

        self._init_ui()
        self._apply_styles()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Initialize the UI layout and widgets."""
        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_LG)

        # Left section: Transport controls
        transport_layout = QHBoxLayout()
        transport_layout.setSpacing(SPACE_SM)

        self._btn_skip_back_5s = QPushButton("|◀")
        self._btn_skip_back_1s = QPushButton("◀◀")
        self._btn_play_pause = QPushButton("▶")
        self._btn_skip_forward_1s = QPushButton("▶▶")
        self._btn_skip_forward_5s = QPushButton("▶|")

        # Set object names for styling
        self._btn_skip_back_5s.setObjectName("transport_button")
        self._btn_skip_back_1s.setObjectName("transport_button")
        self._btn_play_pause.setObjectName("play_button")
        self._btn_skip_forward_1s.setObjectName("transport_button")
        self._btn_skip_forward_5s.setObjectName("transport_button")

        # Set tooltips
        self._btn_skip_back_5s.setToolTip("Skip back 5 seconds")
        self._btn_skip_back_1s.setToolTip("Skip back 1 second")
        self._btn_play_pause.setToolTip("Play / Pause")
        self._btn_skip_forward_1s.setToolTip("Skip forward 1 second")
        self._btn_skip_forward_5s.setToolTip("Skip forward 5 seconds")

        # Make play button slightly larger
        self._btn_play_pause.setMinimumWidth(80)

        transport_layout.addWidget(self._btn_skip_back_5s)
        transport_layout.addWidget(self._btn_skip_back_1s)
        transport_layout.addWidget(self._btn_play_pause)
        transport_layout.addWidget(self._btn_skip_forward_1s)
        transport_layout.addWidget(self._btn_skip_forward_5s)

        # Center section: Speed toggles
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(SPACE_SM)

        self._btn_speed_half = QPushButton("0.5x")
        self._btn_speed_normal = QPushButton("1x")
        self._btn_speed_double = QPushButton("2x")

        # Set object names for styling
        self._btn_speed_half.setObjectName("speed_button")
        self._btn_speed_normal.setObjectName("speed_button")
        self._btn_speed_double.setObjectName("speed_button")

        # Make speed buttons checkable
        self._btn_speed_half.setCheckable(True)
        self._btn_speed_normal.setCheckable(True)
        self._btn_speed_double.setCheckable(True)

        # Set tooltips
        self._btn_speed_half.setToolTip("Half speed (0.5x)")
        self._btn_speed_normal.setToolTip("Normal speed (1x)")
        self._btn_speed_double.setToolTip("Double speed (2x)")

        # Create button group for mutually exclusive selection
        self._speed_button_group = QButtonGroup(self)
        self._speed_button_group.setExclusive(True)
        self._speed_button_group.addButton(self._btn_speed_half, 0)
        self._speed_button_group.addButton(self._btn_speed_normal, 1)
        self._speed_button_group.addButton(self._btn_speed_double, 2)

        # Default to normal speed
        self._btn_speed_normal.setChecked(True)

        speed_layout.addWidget(self._btn_speed_half)
        speed_layout.addWidget(self._btn_speed_normal)
        speed_layout.addWidget(self._btn_speed_double)

        # Right section: Time display
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("time_display")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setFont(Fonts.timestamp())
        self._time_label.setMinimumWidth(120)

        # Add all sections to main layout
        layout.addLayout(transport_layout)
        layout.addStretch()
        layout.addLayout(speed_layout)
        layout.addStretch()
        layout.addWidget(self._time_label)

    def _apply_styles(self) -> None:
        """Apply QSS styles to the widget."""
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
            }}

            QPushButton#transport_button,
            QPushButton#play_button {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 2px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 8px 16px;
                font-size: 16px;
            }}

            QPushButton#transport_button:hover,
            QPushButton#play_button:hover {{
                border-color: {TEXT_ACCENT};
                background-color: {BG_TERTIARY};
            }}

            QPushButton#transport_button:pressed,
            QPushButton#play_button:pressed {{
                background-color: {BG_BORDER};
            }}

            QPushButton#play_button {{
                padding: 8px 24px;
                font-weight: 600;
            }}

            QPushButton#speed_button {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: 2px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 6px 16px;
                font-size: 14px;
                min-width: 50px;
            }}

            QPushButton#speed_button:hover {{
                border-color: {TEXT_ACCENT};
                color: {TEXT_PRIMARY};
            }}

            QPushButton#speed_button:checked {{
                background-color: {TEXT_ACCENT};
                color: {BG_SECONDARY};
                border-color: {TEXT_ACCENT};
                font-weight: 600;
            }}

            QLabel#time_display {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 8px 16px;
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect internal button signals to external signals."""
        # Transport buttons
        self._btn_skip_back_5s.clicked.connect(self.skip_back_5s.emit)
        self._btn_skip_back_1s.clicked.connect(self.skip_back_1s.emit)
        self._btn_play_pause.clicked.connect(self.play_pause.emit)
        self._btn_skip_forward_1s.clicked.connect(self.skip_forward_1s.emit)
        self._btn_skip_forward_5s.clicked.connect(self.skip_forward_5s.emit)

        # Speed buttons
        self._btn_speed_half.clicked.connect(lambda: self._on_speed_changed(0.5))
        self._btn_speed_normal.clicked.connect(lambda: self._on_speed_changed(1.0))
        self._btn_speed_double.clicked.connect(lambda: self._on_speed_changed(2.0))

    @pyqtSlot(float)
    def _on_speed_changed(self, speed: float) -> None:
        """Handle speed button click.

        Args:
            speed: New playback speed (0.5, 1.0, or 2.0)
        """
        if self._current_speed != speed:
            self._current_speed = speed
            self.speed_changed.emit(speed)

    @pyqtSlot(bool)
    def set_playing(self, playing: bool) -> None:
        """Update play/pause button icon based on playback state.

        Args:
            playing: True if video is playing, False if paused

        Example:
            ```python
            player.playing_changed.connect(controls.set_playing)
            ```
        """
        self._is_playing = playing

        if playing:
            self._btn_play_pause.setText("❚❚")
            self._btn_play_pause.setToolTip("Pause")
        else:
            self._btn_play_pause.setText("▶")
            self._btn_play_pause.setToolTip("Play")

    @pyqtSlot(float, float)
    def set_time(self, current_seconds: float, total_seconds: float) -> None:
        """Update time display with current and total duration.

        Args:
            current_seconds: Current playback position in seconds
            total_seconds: Total video duration in seconds

        Example:
            ```python
            # Update every 100ms during playback
            player.position_changed.connect(
                lambda pos: controls.set_time(pos, player.duration)
            )
            ```
        """
        current_str = _format_time(current_seconds)
        total_str = _format_time(total_seconds)
        self._time_label.setText(f"{current_str} / {total_str}")

    @pyqtSlot(float)
    def set_speed(self, speed: float) -> None:
        """Update speed toggle selection programmatically.

        Args:
            speed: Playback speed to select (0.5, 1.0, or 2.0)

        Note:
            This method updates the UI without emitting speed_changed signal.
            Use this when synchronizing with external speed changes.

        Example:
            ```python
            # Sync with external speed change
            player.speed = 0.5
            controls.set_speed(0.5)
            ```
        """
        self._current_speed = speed

        # Block signals to prevent recursive emission
        self._speed_button_group.blockSignals(True)

        if speed == 0.5:
            self._btn_speed_half.setChecked(True)
        elif speed == 2.0:
            self._btn_speed_double.setChecked(True)
        else:
            self._btn_speed_normal.setChecked(True)

        self._speed_button_group.blockSignals(False)

    def get_speed(self) -> float:
        """Get current playback speed selection.

        Returns:
            Current speed value (0.5, 1.0, or 2.0)

        Example:
            ```python
            current_speed = controls.get_speed()
            print(f"Playing at {current_speed}x speed")
            ```
        """
        return self._current_speed
