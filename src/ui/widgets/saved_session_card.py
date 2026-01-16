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
- Optional context menu or delete button
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    PRIMARY_ACTION,
    RADIUS_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
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
    - Missing Video: Grayed out with warning icon

    Signals:
        clicked(SavedSessionInfo): Emitted when card is clicked
        delete_requested(SavedSessionInfo): Emitted when delete action triggered
    """

    clicked = pyqtSignal(SavedSessionInfo)
    delete_requested = pyqtSignal(SavedSessionInfo)

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
        self._init_ui()
        self._apply_styling()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Header: Video name + delete button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACE_SM)

        # Video name with truncation
        video_name_label = QLabel(self._truncate_filename(self._session_info.video_name))
        video_name_label.setFont(Fonts.body(size=14, weight=600))
        video_name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        video_name_label.setToolTip(self._session_info.video_name)
        header_layout.addWidget(video_name_label, stretch=1)

        # Delete button (small X button)
        delete_btn = QPushButton("×")
        delete_btn.setFont(Fonts.body(size=18, weight=700))
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(self._on_delete_clicked)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {BG_BORDER};
                color: {TEXT_PRIMARY};
            }}
        """)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setToolTip("Delete session")
        header_layout.addWidget(delete_btn)

        layout.addLayout(header_layout)

        # Score display (prominent, center-aligned)
        score_label = QLabel(self._session_info.current_score)
        score_label.setFont(Fonts.display(size=28, weight=700))
        score_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(score_label)

        # Metadata row: rally count + game type
        metadata_layout = QHBoxLayout()
        metadata_layout.setSpacing(SPACE_XS)

        rally_count_label = QLabel(
            f"{self._session_info.rally_count} {'rally' if self._session_info.rally_count == 1 else 'rallies'}"
        )
        rally_count_label.setFont(Fonts.secondary())
        rally_count_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        metadata_layout.addWidget(rally_count_label)

        # Bullet separator
        bullet = QLabel("•")
        bullet.setFont(Fonts.secondary())
        bullet.setStyleSheet(f"color: {TEXT_SECONDARY};")
        metadata_layout.addWidget(bullet)

        game_type_label = QLabel(self._session_info.game_type)
        game_type_label.setFont(Fonts.secondary())
        game_type_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        metadata_layout.addWidget(game_type_label)

        metadata_layout.addStretch()

        layout.addLayout(metadata_layout)

        # Last modified with warning if video missing
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(SPACE_XS)

        if not self._session_info.video_exists:
            warning_icon = QLabel("⚠")
            warning_icon.setFont(Fonts.body(size=12))
            warning_icon.setStyleSheet(f"color: {TEXT_WARNING};")
            warning_icon.setToolTip("Video file not found")
            footer_layout.addWidget(warning_icon)

        time_label = QLabel(_format_relative_time(self._session_info.last_modified))
        time_label.setFont(Fonts.secondary())
        time_label.setStyleSheet(
            f"color: {TEXT_DISABLED if not self._session_info.video_exists else TEXT_SECONDARY};"
        )
        footer_layout.addWidget(time_label)

        footer_layout.addStretch()

        layout.addLayout(footer_layout)

        # Make entire card clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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
        self.setMinimumSize(240, 160)
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
        # Clear and rebuild UI
        layout = self.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._init_ui()
        self._apply_styling()
