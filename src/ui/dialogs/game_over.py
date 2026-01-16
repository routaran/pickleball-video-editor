"""Game Over dialog for announcing match completion.

This module provides the GameOverDialog class, which displays when a game ends
either by reaching the victory condition (e.g., first to 11) or when time expires
in a timed game. The dialog shows the winner, final score, rally count, and offers
options to continue editing (for miscounts) or finish the game.

Visual Design:
- Large winner announcement in accent-colored box
- Final score and rally count display
- Two action buttons: Continue Editing (secondary) and Finish Game (primary)
- Variant for timed games with "Time Expired" title and "(Highest score wins)" subtitle

Dialog Dimensions:
- Max width: 500px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.1)
"""

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
    TEXT_ACCENT,
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


class GameOverResult(Enum):
    """Result options from the Game Over dialog.

    Attributes:
        CONTINUE_EDITING: User chose to continue editing (in case of miscount)
        FINISH_GAME: User chose to finish the game and proceed to review
    """
    CONTINUE_EDITING = "continue"
    FINISH_GAME = "finish"


class GameOverDialog(QDialog):
    """Modal dialog announcing game completion with winner and final statistics.

    This dialog is shown when a game reaches its victory condition or when time
    expires in a timed game. It displays:
    - Winner announcement (TEAM X WINS!)
    - Final score
    - Total rally count
    - Options to continue editing or finish

    For timed games, adds contextual subtitle "(Highest score wins)".

    Example:
        >>> dialog = GameOverDialog(
        ...     winner_team=1,
        ...     final_score="11-9-2",
        ...     rally_count=23,
        ...     parent=main_window
        ... )
        >>> result = dialog.get_result()
        >>> if result == GameOverResult.FINISH_GAME:
        ...     proceed_to_review()
    """

    def __init__(
        self,
        winner_team: int,
        final_score: str,
        rally_count: int,
        is_timed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Game Over dialog.

        Args:
            winner_team: Winning team number (1 or 2)
            final_score: Final score string (e.g., "11-9-2" for doubles, "11-9" for singles)
            rally_count: Total number of rallies marked
            is_timed: Whether this is a timed game (adds subtitle and title variant)
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)

        self._winner_team = winner_team
        self._final_score = final_score
        self._rally_count = rally_count
        self._is_timed = is_timed
        self._result = GameOverResult.CONTINUE_EDITING

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        # Configure dialog window
        title = "Time Expired - Game Over" if self._is_timed else "Game Over"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Title
        title_label = QLabel(title)
        title_label.setFont(Fonts.dialog_title())
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(title_label)

        # Spacer above winner announcement
        layout.addSpacing(SPACE_MD)

        # Winner announcement (large accent box)
        winner_container = self._create_winner_announcement()
        layout.addWidget(winner_container)

        # Timed game subtitle
        if self._is_timed:
            subtitle = QLabel("(Highest score wins)")
            subtitle.setFont(Fonts.label())
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle.setStyleSheet(f"color: {TEXT_SECONDARY};")
            layout.addWidget(subtitle)

        layout.addSpacing(SPACE_MD)

        # Final score
        score_label = QLabel(f"Final Score: {self._final_score}")
        score_label.setFont(Fonts.display(size=24))
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(score_label)

        # Rally count
        rally_label = QLabel(f"{self._rally_count} rallies")
        rally_label.setFont(Fonts.label())
        rally_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rally_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(rally_label)

        layout.addSpacing(SPACE_XL)

        # Action buttons
        button_layout = self._create_button_row()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _create_winner_announcement(self) -> QWidget:
        """Create the winner announcement box.

        Returns:
            Widget containing the winner announcement with accent styling
        """
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Winner text
        winner_text = f"TEAM {self._winner_team} WINS!"
        winner_label = QLabel(winner_text)
        winner_label.setFont(Fonts.body(size=28, weight=700))
        winner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        winner_label.setStyleSheet(f"color: {TEXT_ACCENT};")

        container_layout.addWidget(winner_label)
        container.setLayout(container_layout)

        # Apply accent box styling
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_TERTIARY};
                border: 2px solid {TEXT_ACCENT};
                border-radius: {RADIUS_XL}px;
            }}
        """)

        return container

    def _create_button_row(self) -> QHBoxLayout:
        """Create the button row with Continue Editing and Finish Game buttons.

        Returns:
            Horizontal layout containing both action buttons
        """
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        # Continue Editing (secondary) - left aligned
        continue_btn = QPushButton("Continue Editing")
        continue_btn.setFont(Fonts.button_other())
        continue_btn.setMinimumHeight(40)
        continue_btn.setObjectName("secondary_button")
        continue_btn.clicked.connect(self._on_continue_editing)

        # Finish Game (primary) - right aligned
        finish_btn = QPushButton("Finish Game")
        finish_btn.setFont(Fonts.button_other())
        finish_btn.setMinimumHeight(40)
        finish_btn.setObjectName("primary_button")
        finish_btn.clicked.connect(self._on_finish_game)
        finish_btn.setDefault(True)  # Enter key triggers this

        button_layout.addWidget(continue_btn)
        button_layout.addStretch()
        button_layout.addWidget(finish_btn)

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
                border-color: {TEXT_ACCENT};
            }}

            QPushButton#primary_button {{
                background-color: {PRIMARY_ACTION};
                border: 2px solid {PRIMARY_ACTION};
                border-radius: 6px;
                color: {BG_SECONDARY};
                padding: 8px 16px;
                font-weight: 600;
                min-width: 140px;
            }}

            QPushButton#primary_button:hover {{
                background-color: #4FE695;
            }}
        """)

    def _on_continue_editing(self) -> None:
        """Handle Continue Editing button click."""
        self._result = GameOverResult.CONTINUE_EDITING
        self.accept()

    def _on_finish_game(self) -> None:
        """Handle Finish Game button click."""
        self._result = GameOverResult.FINISH_GAME
        self.accept()

    def get_result(self) -> GameOverResult:
        """Get the user's choice after dialog is closed.

        This method should be called after exec() or show() has completed.

        Returns:
            GameOverResult.CONTINUE_EDITING or GameOverResult.FINISH_GAME

        Example:
            >>> dialog = GameOverDialog(1, "11-9", 23, parent=self)
            >>> dialog.exec()
            >>> if dialog.get_result() == GameOverResult.FINISH_GAME:
            ...     self.enter_review_mode()
        """
        return self._result


__all__ = [
    "GameOverDialog",
    "GameOverResult",
]
