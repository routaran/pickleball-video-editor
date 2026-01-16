"""Resume Session dialog for continuing saved editing sessions.

This module provides the ResumeSessionDialog class, which is shown when the application
detects a saved session for the selected video file. It displays session details including
progress, current score, last position, game type, and victory rules.

Visual Design:
- Video filename display
- Session details in bulleted list format
- Two action buttons: Start Fresh (clears session) and Resume Session (continues)
- Clear separation between session info and action buttons

Dialog Dimensions:
- Max width: 500px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.6)
"""

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    PRIMARY_ACTION,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import (
    RADIUS_XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_XL,
    Fonts,
)


@dataclass
class SessionDetails:
    """Details about a saved editing session.

    Attributes:
        video_name: Name of the video file (e.g., "match_2026-01-14.mp4")
        rally_count: Number of rallies marked so far
        current_score: Current score string (e.g., "8-6-1" or "7-5")
        last_position: Last video position in seconds
        game_type: Game type string ("Singles" or "Doubles")
        victory_rule: Victory condition string (e.g., "Game to 11", "Timed")
    """
    video_name: str
    rally_count: int
    current_score: str
    last_position: float
    game_type: str
    victory_rule: str


class ResumeSessionResult(Enum):
    """Result options from the Resume Session dialog.

    Attributes:
        START_FRESH: User chose to discard saved session and start new
        RESUME: User chose to continue from saved session
    """
    START_FRESH = "fresh"
    RESUME = "resume"


class ResumeSessionDialog(QDialog):
    """Modal dialog for resuming or discarding a saved editing session.

    This dialog is shown when a saved session is found for the selected video.
    It presents the session details and allows the user to either resume where
    they left off or start fresh (discarding the saved progress).

    Session details displayed:
    - Progress: Number of rallies marked
    - Current Score: Last recorded score
    - Last Position: Video timestamp of last edit
    - Game Type: Singles or Doubles
    - Victory Rules: Game to 11, Game to 9, or Timed

    Example:
        >>> details = SessionDetails(
        ...     video_name="match.mp4",
        ...     rally_count=15,
        ...     current_score="8-6-1",
        ...     last_position=323.45,
        ...     game_type="Doubles",
        ...     victory_rule="Game to 11"
        ... )
        >>> dialog = ResumeSessionDialog(details, parent=main_window)
        >>> result = dialog.get_result()
        >>> if result == ResumeSessionResult.RESUME:
        ...     load_session()
    """

    def __init__(
        self,
        details: SessionDetails,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Resume Session dialog.

        Args:
            details: SessionDetails object with saved session information
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)

        self._details = details
        self._result = ResumeSessionResult.RESUME

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        # Configure dialog window
        self.setWindowTitle("Resume Session?")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Title
        title_label = QLabel("Resume Session?")
        title_label.setFont(Fonts.dialog_title())
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(title_label)

        # "Found saved session for:" label
        found_label = QLabel("Found saved session for:")
        found_label.setFont(Fonts.label())
        found_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(found_label)

        # Video filename display box
        filename_box = self._create_filename_display()
        layout.addWidget(filename_box)

        layout.addSpacing(SPACE_MD)

        # Separator line
        separator = self._create_separator()
        layout.addWidget(separator)

        layout.addSpacing(SPACE_MD)

        # Session details section
        details_section = self._create_details_section()
        layout.addWidget(details_section)

        layout.addSpacing(SPACE_XL)

        # Action buttons
        button_layout = self._create_button_row()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _create_filename_display(self) -> QWidget:
        """Create the video filename display box.

        Returns:
            Widget containing the video filename in a styled box
        """
        filename_label = QLabel(self._details.video_name)
        filename_label.setFont(Fonts.input_text())
        filename_label.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                padding: 8px 12px;
            }}
        """)
        return filename_label

    def _create_separator(self) -> QWidget:
        """Create a horizontal separator line.

        Returns:
            Widget representing a visual divider
        """
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {BG_BORDER};")
        return separator

    def _create_details_section(self) -> QWidget:
        """Create the session details section with bulleted list.

        Returns:
            Widget containing all session details
        """
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_SM := 8)

        # Section title
        title = QLabel("SESSION DETAILS")
        title.setFont(Fonts.body(size=12, weight=600))
        title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(title)

        layout.addSpacing(SPACE_SM)

        # Format last position as MM:SS.ss
        minutes = int(self._details.last_position // 60)
        seconds = self._details.last_position % 60
        position_str = f"{minutes:02d}:{seconds:05.2f}"

        # Details list items
        details_items = [
            ("Progress:", f"{self._details.rally_count} rallies marked"),
            ("Current Score:", self._details.current_score),
            ("Last Position:", position_str),
            ("Game Type:", self._details.game_type),
            ("Victory Rules:", self._details.victory_rule),
        ]

        for label_text, value_text in details_items:
            item = self._create_detail_item(label_text, value_text)
            layout.addWidget(item)

        container.setLayout(layout)
        return container

    def _create_detail_item(self, label: str, value: str) -> QLabel:
        """Create a single detail list item.

        Args:
            label: Detail label (e.g., "Progress:")
            value: Detail value (e.g., "15 rallies marked")

        Returns:
            QLabel with formatted detail text
        """
        # Bullet point + label + value
        text = f"• {label:16} {value}"

        detail_label = QLabel(text)
        detail_label.setFont(Fonts.label())
        detail_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        return detail_label

    def _create_button_row(self) -> QHBoxLayout:
        """Create the button row with Start Fresh and Resume Session buttons.

        Returns:
            Horizontal layout containing both action buttons
        """
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        # Start Fresh (secondary) - left aligned
        fresh_btn = QPushButton("Start Fresh")
        fresh_btn.setFont(Fonts.button_other())
        fresh_btn.setMinimumHeight(40)
        fresh_btn.setObjectName("secondary_button")
        fresh_btn.clicked.connect(self._on_start_fresh)

        # Resume Session (primary) - right aligned
        resume_btn = QPushButton("Resume Session")
        resume_btn.setFont(Fonts.button_other())
        resume_btn.setMinimumHeight(40)
        resume_btn.setObjectName("primary_button")
        resume_btn.clicked.connect(self._on_resume_session)
        resume_btn.setDefault(True)  # Enter key triggers this

        button_layout.addWidget(fresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(resume_btn)

        return button_layout

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QPushButton#secondary_button {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: 8px 16px;
                min-width: 140px;
            }}

            QPushButton#secondary_button:hover {{
                border-color: {TEXT_PRIMARY};
            }}

            QPushButton#primary_button {{
                background-color: {PRIMARY_ACTION};
                border: 2px solid {PRIMARY_ACTION};
                border-radius: 6px;
                color: {BG_SECONDARY};
                padding: 8px 16px;
                font-weight: 600;
                min-width: 160px;
            }}

            QPushButton#primary_button:hover {{
                background-color: #4FE695;
            }}
        """)

    def _on_start_fresh(self) -> None:
        """Handle Start Fresh button click."""
        self._result = ResumeSessionResult.START_FRESH
        self.accept()

    def _on_resume_session(self) -> None:
        """Handle Resume Session button click."""
        self._result = ResumeSessionResult.RESUME
        self.accept()

    def get_result(self) -> ResumeSessionResult:
        """Get the user's choice after dialog is closed.

        This method should be called after exec() or show() has completed.

        Returns:
            ResumeSessionResult.START_FRESH or ResumeSessionResult.RESUME

        Example:
            >>> dialog = ResumeSessionDialog(session_details, parent=self)
            >>> dialog.exec()
            >>> if dialog.get_result() == ResumeSessionResult.RESUME:
            ...     self.load_saved_session()
            >>> else:
            ...     self.clear_saved_session()
        """
        return self._result


__all__ = [
    "ResumeSessionDialog",
    "ResumeSessionResult",
    "SessionDetails",
]
