"""SavedSessionCard widget for displaying saved session information.

This module provides a clickable card widget that displays saved session metadata
including video name, score, rally count, and last modified time. Cards can be
arranged in grids for session selection interfaces.

Components:
- SavedSessionInfo: Dataclass holding session metadata
- SavedSessionCard: Clickable card widget with hover effects and visual states

Visual Features:
- Truncated video filename with ellipsis
- Prominent score display using monospace font
- Rally count and last modified time
- Warning indicator for missing video files
- Hover state with accent border
- Absolutely positioned delete button (bottom-left) and load hint (bottom-right)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QEnterEvent, QMouseEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import (
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    PRIMARY_ACTION,
    RADIUS_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_ACCENT,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_WARNING,
    Fonts,
)

__all__ = ["SavedSessionInfo", "SavedSessionCard"]


@dataclass
class SavedSessionInfo:
    """Metadata for a saved session.

    Attributes:
        session_path: Path to the session JSON file
        session_hash: Video file hash for re-linking validation
        video_name: Display name of the video file
        video_path: Full original video path from session
        rally_count: Number of rallies in the session
        current_score: Current score string (e.g., "5-3-1")
        last_modified: ISO timestamp of last modification
        game_type: Game type ("singles" or "doubles")
        video_exists: Whether the original video file still exists
    """

    session_path: Path
    session_hash: str
    video_name: str
    video_path: str
    rally_count: int
    current_score: str
    last_modified: str
    game_type: str
    video_exists: bool


def _format_relative_time(iso_timestamp: str) -> str:
    """Convert ISO timestamp to relative time string.

    Args:
        iso_timestamp: ISO 8601 timestamp string

    Returns:
        Relative time string (e.g., "2h ago", "yesterday", "3 days ago")

    Example:
        >>> _format_relative_time("2026-01-15T10:30:00")
        "2h ago"
    """
    try:
        timestamp = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        return "unknown"

    now = datetime.now()
    delta = now - timestamp

    # Less than 1 minute
    if delta.total_seconds() < 60:
        return "just now"

    # Less than 1 hour
    minutes = int(delta.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}m ago"

    # Less than 24 hours
    hours = int(delta.total_seconds() / 3600)
    if hours < 24:
        return f"{hours}h ago"

    # Less than 48 hours
    days = delta.days
    if days == 1:
        return "yesterday"

    # Less than 7 days
    if days < 7:
        return f"{days} days ago"

    # Less than 30 days
    if days < 30:
        weeks = days // 7
        if weeks == 1:
            return "1 week ago"
        return f"{weeks} weeks ago"

    # Less than 365 days
    if days < 365:
        months = days // 30
        if months == 1:
            return "1 month ago"
        return f"{months} months ago"

    # Over a year
    years = days // 365
    if years == 1:
        return "1 year ago"
    return f"{years} years ago"


class SavedSessionCard(QFrame):
    """Clickable card displaying saved session information.

    Displays session metadata in a visually appealing card format with
    hover effects and visual indicators for missing video files.

    Visual States:
    - Normal: Dark background with border
    - Hover: Accent-colored border with slight background change
    - Missing Video: Grayed out with warning icon, yellow border on hover

    Layout Structure:
    - Header: Video name + timestamp (top-right)
    - Score: Prominent center display
    - Meta row: Rally count • game type (with warning icon if video missing)
    - Overlays (absolutely positioned, shown on hover):
      - Delete button: Bottom-left corner with red background
      - Load hint: Bottom-right corner "Click to load →"

    Signals:
        clicked(SavedSessionInfo): Emitted when card is clicked
        delete_requested(SavedSessionInfo): Emitted when delete action triggered
    """

    clicked = pyqtSignal(SavedSessionInfo)
    delete_requested = pyqtSignal(SavedSessionInfo)

    # Delete button dimensions
    DELETE_BTN_SIZE = 0

    def __init__(
        self,
        session_info: SavedSessionInfo,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize a saved session card.

        Args:
            session_info: Session metadata to display
            parent: Optional parent widget
        """
        super().__init__(parent)
        self._session_info = session_info
        self._delete_btn: QPushButton | None = None
        self._load_hint: QLabel | None = None
        self._init_ui()
        self._init_overlays()
        self._apply_styling()
        # Ensure card has minimum height to display all content
        self.setMinimumHeight(140)

    def _init_ui(self) -> None:
        """Initialize main UI components (not overlays)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Header: Video name + timestamp
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACE_SM)

        # Video name with truncation
        video_name_label = QLabel(self._truncate_filename(self._session_info.video_name))
        video_name_label.setFont(Fonts.body(size=14, weight=600))
        video_name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        video_name_label.setToolTip(self._session_info.video_name)
        header_layout.addWidget(video_name_label, stretch=1)

        # Timestamp (right side of header)
        time_label = QLabel(_format_relative_time(self._session_info.last_modified))
        time_label.setFont(Fonts.secondary())
        time_label.setStyleSheet(
            f"color: {TEXT_DISABLED if not self._session_info.video_exists else TEXT_SECONDARY};"
        )
        header_layout.addWidget(time_label)

        layout.addLayout(header_layout)

        # Score display (prominent, center-aligned)
        score_label = QLabel(self._session_info.current_score)
        score_label.setFont(Fonts.display(size=28, weight=700))
        score_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(score_label)

        # Meta row: rally count • game type (with optional warning)
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(SPACE_SM)

        # Warning icon for missing video (at start of meta row)
        if not self._session_info.video_exists:
            warning_icon = QLabel("⚠")
            warning_icon.setFont(Fonts.body(size=12))
            warning_icon.setStyleSheet(f"color: {TEXT_WARNING};")
            warning_icon.setToolTip("Video file not found")
            meta_layout.addWidget(warning_icon)

        # Rally count
        rally_count_label = QLabel(
            f"{self._session_info.rally_count} {'rally' if self._session_info.rally_count == 1 else 'rallies'}"
        )
        rally_count_label.setFont(Fonts.secondary())
        rally_count_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        meta_layout.addWidget(rally_count_label)

        # Bullet separator
        bullet = QLabel("•")
        bullet.setFont(Fonts.secondary())
        bullet.setStyleSheet(f"color: {TEXT_SECONDARY};")
        meta_layout.addWidget(bullet)

        # Game type
        game_type_label = QLabel(self._session_info.game_type)
        game_type_label.setFont(Fonts.secondary())
        game_type_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        meta_layout.addWidget(game_type_label)

        meta_layout.addStretch()
        layout.addLayout(meta_layout)

        # Add bottom padding to make room for overlays
        layout.addSpacing(SPACE_MD)

        # Make entire card clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _init_overlays(self) -> None:
        """Initialize absolutely positioned overlay widgets.

        Creates the delete button (bottom-left) and load hint (bottom-right)
        as direct children of the card, positioned manually in resizeEvent.
        """
        # Delete button (direct child, positioned at bottom-left corner)
        self._delete_btn = QPushButton("🗑", self)
        self._delete_btn.setFixedSize(self.DELETE_BTN_SIZE, self.DELETE_BTN_SIZE)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover { background-color: #dc2626; }
            QPushButton:pressed { background-color: #b91c1c; }
        """)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setToolTip("Delete session")
        self._delete_btn.setVisible(False)

        # Load hint (bottom-right corner)
        self._load_hint = QLabel("Click to load →", self)
        self._load_hint.setFont(Fonts.secondary())
        self._load_hint.setStyleSheet(f"color: {PRIMARY_ACTION};")
        self._load_hint.adjustSize()
        self._load_hint.setVisible(False)

    def _apply_styling(self) -> None:
        """Apply card styling with hover effects."""
        # Adjust colors for missing video
        border_color = BORDER_COLOR
        bg_color = BG_SECONDARY

        if not self._session_info.video_exists:
            # Gray out missing video cards
            self.setStyleSheet(f"""
                SavedSessionCard {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: {RADIUS_LG}px;
                    opacity: 0.6;
                }}
                SavedSessionCard:hover {{
                    border-color: {TEXT_WARNING};
                    background-color: {BG_TERTIARY};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                SavedSessionCard {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: {RADIUS_LG}px;
                }}
                SavedSessionCard:hover {{
                    border-color: {PRIMARY_ACTION};
                    background-color: {BG_TERTIARY};
                }}
            """)

        # Set minimum size for consistent card layout
        self.setMinimumSize(240, 140)
        self.setMaximumWidth(320)

    def _truncate_filename(self, filename: str, max_length: int = 30) -> str:
        """Truncate filename with ellipsis if too long.

        Args:
            filename: Full filename
            max_length: Maximum character length before truncation

        Returns:
            Truncated filename with ellipsis if needed
        """
        if len(filename) <= max_length:
            return filename

        # Keep extension visible
        if "." in filename:
            name, ext = filename.rsplit(".", 1)
            available_length = max_length - len(ext) - 4  # 4 for "..." + "."
            if available_length > 0:
                return f"{name[:available_length]}...{ext}"

        # No extension or too short
        return f"{filename[:max_length-3]}..."

    @pyqtSlot()
    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        self.delete_requested.emit(self._session_info)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Position overlay widgets when card is resized.

        Args:
            event: Resize event
        """
        super().resizeEvent(event)
        self._position_overlays()

    def _position_overlays(self) -> None:
        """Position the delete button and load hint overlays."""
        # Position delete button at bottom-left corner with margin inside card
        if self._delete_btn is not None:
            self._delete_btn.move(8, self.height() - self._delete_btn.height() - 8)

        # Position load hint at bottom-right corner
        if self._load_hint is not None:
            hint_x = self.width() - self._load_hint.width() - SPACE_MD
            hint_y = self.height() - self._load_hint.height() - SPACE_SM
            self._load_hint.move(hint_x, hint_y)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Show hover overlays when mouse enters card.

        Args:
            event: Enter event
        """
        if self._delete_btn is not None:
            self._delete_btn.setVisible(True)
        if self._load_hint is not None:
            self._load_hint.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Hide hover overlays when mouse leaves card.

        Args:
            event: Leave event
        """
        if self._delete_btn is not None:
            self._delete_btn.setVisible(False)
        if self._load_hint is not None:
            self._load_hint.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to emit clicked signal.

        Args:
            event: Mouse event containing button and position info
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._session_info)
        super().mousePressEvent(event)

    def get_session_info(self) -> SavedSessionInfo:
        """Get the session info for this card.

        Returns:
            SavedSessionInfo dataclass
        """
        return self._session_info

    def update_session_info(self, session_info: SavedSessionInfo) -> None:
        """Update the displayed session information.

        Args:
            session_info: New session metadata
        """
        self._session_info = session_info

        # Clean up old overlays
        if self._delete_btn is not None:
            self._delete_btn.deleteLater()
            self._delete_btn = None
        if self._load_hint is not None:
            self._load_hint.deleteLater()
            self._load_hint = None

        # Clear and rebuild main layout
        layout = self.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        self._init_ui()
        self._init_overlays()
        self._apply_styling()
        self._position_overlays()
