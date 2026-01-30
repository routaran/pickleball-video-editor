"""Visual clip timeline widget with clickable numbered cells.

This module provides a visual timeline showing clickable clip cells that
highlight when the current playback position is within that clip's time range.
Replaces the simple "Clips: N" counter in highlights mode.

Features:
- Numbered cells (1, 2, 3...) for each clip
- Active cell highlighting with green glow when playback is inside clip
- Single click to seek to clip start
- Double click to play clip from start to end
- Hover tooltip showing time range (e.g., "0:45 - 0:48")
- In-progress indicator (pulsing amber) when clip is started but not ended
- Horizontal scrolling for many clips with auto-scroll to active clip
"""

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from src.core.models import Rally
from src.ui.styles.colors import (
    BG_BORDER,
    BG_PRIMARY,
    BG_TERTIARY,
    RALLY_START,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    Colors,
)


__all__ = ["ClipTimelineWidget"]


# Cell styling constants (from plan)
CELL_BG_NORMAL = "#2a2a2a"
CELL_BORDER_NORMAL = "#3a3a3a"
CELL_TEXT_NORMAL = "#888888"

CELL_BG_HOVER = "#2a2a2a"
CELL_BORDER_HOVER = "#4ade80"
CELL_TEXT_HOVER = "#ffffff"

CELL_BG_ACTIVE = "#22c55e"
CELL_BORDER_ACTIVE = "#22c55e"
CELL_TEXT_ACTIVE = "#1a1a1a"

CELL_BG_IN_PROGRESS = "#f59e0b"
CELL_BORDER_IN_PROGRESS = "#f59e0b"
CELL_TEXT_IN_PROGRESS = "#1a1a1a"

# Cell dimensions
CELL_WIDTH = 28
CELL_HEIGHT = 24
CELL_SPACING = 4
CELL_BORDER_RADIUS = 4
CELL_FONT_SIZE = 11
CELL_FONT_WEIGHT = 500


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


class _ClipCell(QPushButton):
    """Individual clickable cell in the clip timeline."""

    def __init__(
        self,
        index: int,
        start_seconds: float,
        end_seconds: float,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize a clip cell.

        Args:
            index: 0-based clip index
            start_seconds: Clip start time in seconds
            end_seconds: Clip end time in seconds
            parent: Parent widget
        """
        super().__init__(str(index + 1), parent)
        self._index = index
        self._start_seconds = start_seconds
        self._end_seconds = end_seconds
        self._is_active = False

        # Set fixed size
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)

        # Set cursor
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Set font
        font = QFont("IBM Plex Sans", CELL_FONT_SIZE)
        font.setWeight(QFont.Weight.Medium)
        self.setFont(font)

        # Set tooltip
        time_range = f"{_format_time(start_seconds)} - {_format_time(end_seconds)}"
        self.setToolTip(time_range)

        # Apply styling
        self._apply_style()

    @property
    def index(self) -> int:
        """Get the 0-based clip index."""
        return self._index

    @property
    def start_seconds(self) -> float:
        """Get the clip start time in seconds."""
        return self._start_seconds

    @property
    def end_seconds(self) -> float:
        """Get the clip end time in seconds."""
        return self._end_seconds

    def is_active(self) -> bool:
        """Check if cell is in active state."""
        return self._is_active

    def set_active(self, active: bool) -> None:
        """Set the active state.

        Args:
            active: True to highlight as active
        """
        if self._is_active == active:
            return
        self._is_active = active
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply QSS styling based on current state."""
        if self._is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {CELL_BG_ACTIVE};
                    border: 1px solid {CELL_BORDER_ACTIVE};
                    border-radius: {CELL_BORDER_RADIUS}px;
                    color: {CELL_TEXT_ACTIVE};
                    font-weight: {CELL_FONT_WEIGHT};
                    padding: 0;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {CELL_BG_NORMAL};
                    border: 1px solid {CELL_BORDER_NORMAL};
                    border-radius: {CELL_BORDER_RADIUS}px;
                    color: {CELL_TEXT_NORMAL};
                    font-weight: {CELL_FONT_WEIGHT};
                    padding: 0;
                }}
                QPushButton:hover {{
                    border-color: {CELL_BORDER_HOVER};
                    color: {CELL_TEXT_HOVER};
                }}
            """)


class _InProgressCell(QWidget):
    """Pulsing amber cell indicating a clip in progress."""

    def __init__(self, next_index: int, parent: QWidget | None = None) -> None:
        """Initialize the in-progress cell.

        Args:
            next_index: The next clip number (1-based)
            parent: Parent widget
        """
        super().__init__(parent)
        self._next_index = next_index
        self._pulse_opacity = 1.0

        # Set fixed size
        self.setFixedSize(CELL_WIDTH, CELL_HEIGHT)

        # Setup pulse animation
        self._pulse_animation = QPropertyAnimation(self, b"pulse_opacity")
        self._pulse_animation.setDuration(1000)  # 1 second per cycle
        self._pulse_animation.setStartValue(1.0)
        self._pulse_animation.setEndValue(0.4)
        self._pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_animation.setLoopCount(-1)  # Infinite loop

        # Start animation
        self._pulse_animation.start()

    def set_index(self, index: int) -> None:
        """Update the displayed index.

        Args:
            index: Next clip number (1-based)
        """
        self._next_index = index
        self.update()

    @pyqtProperty(float)
    def pulse_opacity(self) -> float:
        """Get current pulse opacity."""
        return self._pulse_opacity

    @pulse_opacity.setter
    def pulse_opacity(self, value: float) -> None:
        """Set pulse opacity and trigger repaint."""
        self._pulse_opacity = value
        self.update()

    def paintEvent(self, event) -> None:
        """Custom paint for pulsing effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        # Set opacity for pulsing
        painter.setOpacity(self._pulse_opacity)

        # Draw background
        bg_color = Colors.to_qcolor(CELL_BG_IN_PROGRESS)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, CELL_BORDER_RADIUS, CELL_BORDER_RADIUS)

        # Draw border
        border_color = Colors.to_qcolor(CELL_BORDER_IN_PROGRESS)
        border_pen = QPen(border_color, 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(0, 0, -1, -1), CELL_BORDER_RADIUS, CELL_BORDER_RADIUS
        )

        # Draw text
        painter.setOpacity(1.0)  # Full opacity for text
        painter.setPen(Colors.to_qcolor(CELL_TEXT_IN_PROGRESS))
        font = QFont("IBM Plex Sans", CELL_FONT_SIZE)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._next_index))


class ClipTimelineWidget(QFrame):
    """Visual clip timeline with clickable numbered cells.

    This widget displays a horizontal row of numbered cells, one per clip.
    The active clip (containing the current playback position) is highlighted
    with a green glow. Clicking a cell seeks to that clip's start time.

    Signals:
        clip_clicked: Emitted when a clip cell is single-clicked (0-based index)
        clip_play_requested: Emitted when a clip cell is double-clicked (0-based index)

    Example:
        >>> timeline = ClipTimelineWidget()
        >>> timeline.set_clips(rallies, fps=60.0)
        >>> timeline.clip_clicked.connect(on_clip_clicked)
        >>> timeline.update_position(current_time)
    """

    clip_clicked = pyqtSignal(int)  # Single click - emits 0-based index
    clip_play_requested = pyqtSignal(int)  # Double click - play clip

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the clip timeline widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("clip_timeline")

        # State
        self._clips: list[tuple[float, float]] = []  # (start_seconds, end_seconds)
        self._cells: list[_ClipCell] = []
        self._active_index: int | None = None
        self._in_progress = False
        self._in_progress_cell: _InProgressCell | None = None

        # Double-click detection
        self._click_timer: QTimer | None = None
        self._pending_click_index: int | None = None

        # Setup UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the widget layout."""
        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area for horizontal scrolling
        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("clip_timeline_scroll")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setFixedHeight(CELL_HEIGHT + 8)  # Cell height + padding

        # Apply scroll area styling
        self._scroll_area.setStyleSheet(f"""
            QScrollArea#clip_timeline_scroll {{
                background-color: transparent;
                border: none;
            }}
            QScrollArea#clip_timeline_scroll > QWidget > QWidget {{
                background-color: transparent;
            }}
            QScrollBar:horizontal {{
                height: 6px;
                background-color: {BG_TERTIARY};
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {BG_BORDER};
                border-radius: 3px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {TEXT_DISABLED};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
                height: 0;
            }}
        """)

        # Container for cells
        self._cell_container = QWidget()
        self._cell_container.setObjectName("clip_timeline_container")
        self._cell_layout = QHBoxLayout(self._cell_container)
        self._cell_layout.setContentsMargins(0, 4, 0, 4)
        self._cell_layout.setSpacing(CELL_SPACING)
        self._cell_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._scroll_area.setWidget(self._cell_container)

        layout.addWidget(self._scroll_area)

        # Placeholder label for empty state
        self._placeholder = QLabel("No clips yet")
        self._placeholder.setObjectName("clip_timeline_placeholder")
        self._placeholder.setStyleSheet(f"""
            QLabel#clip_timeline_placeholder {{
                color: {TEXT_DISABLED};
                font-size: 12px;
            }}
        """)
        self._placeholder.hide()
        layout.addWidget(self._placeholder)

        # Show placeholder initially
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        """Update visibility based on whether there are clips."""
        has_clips = len(self._clips) > 0 or self._in_progress

        self._scroll_area.setVisible(has_clips)
        self._placeholder.setVisible(not has_clips)

    def _clear_layout(self) -> None:
        """Clear all items from the cell layout."""
        # Remove all items from layout (widgets and spacers)
        while self._cell_layout.count() > 0:
            item = self._cell_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                # Spacer items are automatically cleaned up

    def set_clips(self, rallies: list[Rally], fps: float) -> None:
        """Rebuild cells from rally list.

        Args:
            rallies: List of Rally objects
            fps: Video frames per second for time conversion
        """
        # Clear entire layout (cells, in-progress indicator, and stretches)
        self._clear_layout()
        self._cells.clear()
        self._in_progress_cell = None

        # Convert rallies to time ranges
        self._clips = []
        for rally in rallies:
            start_sec = rally.start_frame / fps
            end_sec = rally.end_frame / fps
            self._clips.append((start_sec, end_sec))

        # Create new cells
        for i, (start_sec, end_sec) in enumerate(self._clips):
            cell = _ClipCell(i, start_sec, end_sec, self._cell_container)
            cell.clicked.connect(lambda checked, idx=i: self._on_cell_clicked(idx))
            self._cell_layout.addWidget(cell)
            self._cells.append(cell)

        # Add stretch at end (must be before in-progress cell insertion)
        self._cell_layout.addStretch()

        # Add in-progress cell if needed (inserts before stretch)
        if self._in_progress:
            self._add_in_progress_cell()

        # Reset active state
        self._active_index = None

        # Update empty state
        self._update_empty_state()

    def set_in_progress(self, in_progress: bool, next_index: int = 0) -> None:
        """Show/hide pulsing in-progress indicator.

        Args:
            in_progress: True to show indicator, False to hide
            next_index: The next clip number (1-based) to display
        """
        if self._in_progress == in_progress:
            # Just update index if already showing
            if in_progress and self._in_progress_cell is not None:
                self._in_progress_cell.set_index(next_index)
            return

        self._in_progress = in_progress

        if in_progress:
            self._add_in_progress_cell(next_index)
        else:
            self._remove_in_progress_cell()

        self._update_empty_state()

    def _add_in_progress_cell(self, next_index: int = 0) -> None:
        """Add the in-progress cell to the layout."""
        if self._in_progress_cell is not None:
            return

        # Calculate next index if not provided
        if next_index == 0:
            next_index = len(self._clips) + 1

        self._in_progress_cell = _InProgressCell(next_index, self._cell_container)

        # Insert before the stretch (last item)
        count = self._cell_layout.count()
        if count > 0:
            # Insert at position before last item (the stretch)
            self._cell_layout.insertWidget(count - 1, self._in_progress_cell)
        else:
            # No items yet, just add
            self._cell_layout.addWidget(self._in_progress_cell)
            self._cell_layout.addStretch()

    def _remove_in_progress_cell(self) -> None:
        """Remove the in-progress cell from the layout."""
        if self._in_progress_cell is not None:
            self._in_progress_cell.deleteLater()
            self._in_progress_cell = None

    def update_position(self, position_seconds: float) -> None:
        """Update active cell highlighting based on playback position.

        Called at ~20 FPS during playback. Only updates styling if the
        active clip changes to avoid unnecessary repaints.

        Args:
            position_seconds: Current playback position in seconds
        """
        new_active = self._find_active_clip(position_seconds)

        if new_active == self._active_index:
            return  # No change

        # Update previous active cell
        if self._active_index is not None and self._active_index < len(self._cells):
            self._cells[self._active_index].set_active(False)

        # Update new active cell
        if new_active is not None and new_active < len(self._cells):
            self._cells[new_active].set_active(True)
            # Auto-scroll to keep active cell visible
            self._ensure_visible(new_active)

        self._active_index = new_active

    def _find_active_clip(self, pos: float) -> int | None:
        """Find the index of the clip containing the position.

        Args:
            pos: Current position in seconds

        Returns:
            0-based index of containing clip, or None if between/outside clips
        """
        for i, (start, end) in enumerate(self._clips):
            if start <= pos <= end:
                return i
        return None

    def _ensure_visible(self, index: int) -> None:
        """Ensure the cell at the given index is visible.

        Args:
            index: Cell index to scroll into view
        """
        if index < 0 or index >= len(self._cells):
            return

        cell = self._cells[index]
        self._scroll_area.ensureWidgetVisible(cell, xMargin=CELL_WIDTH, yMargin=0)

    def _on_cell_clicked(self, index: int) -> None:
        """Handle cell click with double-click detection.

        Args:
            index: 0-based clip index
        """
        if self._click_timer is not None and self._click_timer.isActive():
            # This is a double-click
            self._click_timer.stop()
            self._pending_click_index = None
            self.clip_play_requested.emit(index)
        else:
            # Start timer for single click
            self._pending_click_index = index
            if self._click_timer is None:
                self._click_timer = QTimer(self)
                self._click_timer.setSingleShot(True)
                self._click_timer.timeout.connect(self._on_click_timeout)
            self._click_timer.start(250)  # 250ms double-click window

    def _on_click_timeout(self) -> None:
        """Handle single click timeout."""
        if self._pending_click_index is not None:
            self.clip_clicked.emit(self._pending_click_index)
            self._pending_click_index = None

    def get_clip_count(self) -> int:
        """Get the number of clips.

        Returns:
            Number of clips in the timeline
        """
        return len(self._clips)
