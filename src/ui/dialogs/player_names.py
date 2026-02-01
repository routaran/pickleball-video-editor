"""Player Names Dialog for the Pickleball Video Editor.

This module provides a modal dialog for setting or updating player names
at any time during editing. The dialog dynamically adjusts its fields
based on game type (singles vs doubles).

Team 1 is highlighted as "First Server" with accent styling to indicate
their serving priority at the start of the game.
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    Fonts,
)


@dataclass
class PlayerNamesResult:
    """Result of the Player Names dialog.

    Attributes:
        team1_players: List of Team 1 player names (filtered, non-empty)
        team2_players: List of Team 2 player names (filtered, non-empty)
    """

    team1_players: list[str]
    team2_players: list[str]


class PlayerNamesDialog(QDialog):
    """Modal dialog for setting or updating player names.

    Allows users to set or update player names at any time during editing.
    The number of input fields adjusts based on game type:
    - Singles: 1 player per team (2 total)
    - Doubles: 2 players per team (4 total)

    Team 1 is highlighted as "First Server" with accent styling.

    Example:
        ```python
        dialog = PlayerNamesDialog(
            game_type="doubles",
            current_team1=["Alice", "Bob"],
            current_team2=["Carol", "Dave"],
            parent=main_window
        )

        if dialog.exec():
            result = dialog.get_result()
            if result:
                score_state.set_player_names({
                    "team1": result.team1_players,
                    "team2": result.team2_players,
                })
        ```
    """

    def __init__(
        self,
        game_type: str,
        current_team1: list[str] | None = None,
        current_team2: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Player Names dialog.

        Args:
            game_type: "singles" or "doubles"
            current_team1: Current Team 1 player names (optional, for pre-population)
            current_team2: Current Team 2 player names (optional, for pre-population)
            parent: Parent widget for modal behavior
        """
        super().__init__(parent)
        self.setObjectName("playerNamesDialog")

        self.game_type = game_type
        self.current_team1 = current_team1 or []
        self.current_team2 = current_team2 or []
        self._result: PlayerNamesResult | None = None

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()
        self._populate_fields()

    def _setup_ui(self) -> None:
        """Create and layout the dialog widgets."""
        self.setWindowTitle("Player Names")
        self.setModal(True)
        self.setFixedWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Title
        title_label = QLabel("Player Names")
        title_label.setFont(Fonts.dialog_title())
        layout.addWidget(title_label)

        # Subtitle hint
        hint_label = QLabel("Player names will appear in score overlays and exports")
        hint_label.setFont(Fonts.secondary())
        hint_label.setObjectName("hint_label")
        layout.addWidget(hint_label)

        # Determine if doubles
        is_doubles = self.game_type == "doubles"

        # Team 1 section (First Server - highlighted)
        self._team1_group = QGroupBox("TEAM 1 (First Server)")
        self._team1_group.setObjectName("team1_group")
        team1_layout = QFormLayout()
        team1_layout.setSpacing(SPACE_MD)
        team1_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)

        self._team1_player1_edit = QLineEdit()
        self._team1_player1_edit.setPlaceholderText("Player 1 name")
        team1_layout.addRow("Player 1:", self._team1_player1_edit)

        if is_doubles:
            self._team1_player2_edit = QLineEdit()
            self._team1_player2_edit.setPlaceholderText("Player 2 name")
            team1_layout.addRow("Player 2:", self._team1_player2_edit)
        else:
            self._team1_player2_edit = None

        self._team1_group.setLayout(team1_layout)
        layout.addWidget(self._team1_group)

        # Team 2 section
        self._team2_group = QGroupBox("TEAM 2")
        self._team2_group.setObjectName("team2_group")
        team2_layout = QFormLayout()
        team2_layout.setSpacing(SPACE_MD)
        team2_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)

        self._team2_player1_edit = QLineEdit()
        self._team2_player1_edit.setPlaceholderText("Player 1 name")
        team2_layout.addRow("Player 1:", self._team2_player1_edit)

        if is_doubles:
            self._team2_player2_edit = QLineEdit()
            self._team2_player2_edit.setPlaceholderText("Player 2 name")
            team2_layout.addRow("Player 2:", self._team2_player2_edit)
        else:
            self._team2_player2_edit = None

        self._team2_group.setLayout(team2_layout)
        layout.addWidget(self._team2_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setFont(Fonts.button_other())
        self._cancel_button.setFixedHeight(40)
        self._cancel_button.setMinimumWidth(100)
        self._cancel_button.setObjectName("cancel_button")
        button_layout.addWidget(self._cancel_button)

        self._apply_button = QPushButton("Apply")
        self._apply_button.setFont(Fonts.button_other())
        self._apply_button.setFixedHeight(40)
        self._apply_button.setMinimumWidth(100)
        self._apply_button.setObjectName("apply_button")
        button_layout.addWidget(self._apply_button)

        layout.addLayout(button_layout)

    def _apply_styles(self) -> None:
        """Apply QSS styling to the dialog and its widgets."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QLabel {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
                border: none;
            }}

            QLabel#hint_label {{
                color: {TEXT_SECONDARY};
                margin-bottom: 8px;
            }}

            QGroupBox {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BG_BORDER};
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                color: {TEXT_PRIMARY};
                margin-top: 12px;
                padding-top: 16px;
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 0 8px;
            }}

            QGroupBox#team1_group {{
                border-color: {TEXT_ACCENT};
                border-width: 2px;
            }}

            QLineEdit {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
            }}

            QLineEdit:focus {{
                border-color: {TEXT_ACCENT};
            }}

            QPushButton {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                color: {TEXT_PRIMARY};
            }}

            QPushButton:hover:!disabled {{
                background-color: {BG_BORDER};
            }}

            QPushButton#apply_button {{
                background-color: {PRIMARY_ACTION};
                border-color: {PRIMARY_ACTION};
                color: {BG_SECONDARY};
                font-weight: 600;
            }}

            QPushButton#apply_button:hover:!disabled {{
                background-color: {TEXT_ACCENT};
                border-color: {TEXT_ACCENT};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._cancel_button.clicked.connect(self.reject)
        self._apply_button.clicked.connect(self._on_apply)

    def _populate_fields(self) -> None:
        """Pre-populate fields with current player names."""
        # Team 1
        if len(self.current_team1) >= 1:
            self._team1_player1_edit.setText(self.current_team1[0])
        if self._team1_player2_edit is not None and len(self.current_team1) >= 2:
            self._team1_player2_edit.setText(self.current_team1[1])

        # Team 2
        if len(self.current_team2) >= 1:
            self._team2_player1_edit.setText(self.current_team2[0])
        if self._team2_player2_edit is not None and len(self.current_team2) >= 2:
            self._team2_player2_edit.setText(self.current_team2[1])

    def _get_team1_inputs(self) -> list[str]:
        """Get Team 1 player name inputs.

        Returns:
            List of input values (may include empty strings)
        """
        inputs = [self._team1_player1_edit.text()]
        if self._team1_player2_edit is not None:
            inputs.append(self._team1_player2_edit.text())
        return inputs

    def _get_team2_inputs(self) -> list[str]:
        """Get Team 2 player name inputs.

        Returns:
            List of input values (may include empty strings)
        """
        inputs = [self._team2_player1_edit.text()]
        if self._team2_player2_edit is not None:
            inputs.append(self._team2_player2_edit.text())
        return inputs

    def _on_apply(self) -> None:
        """Handle Apply button click.

        CRITICAL: Filters empty/whitespace-only entries to prevent [""] propagation.
        """
        # Filter empty strings - CRITICAL to prevent [""] propagation
        team1 = [n.strip() for n in self._get_team1_inputs() if n.strip()]
        team2 = [n.strip() for n in self._get_team2_inputs() if n.strip()]

        self._result = PlayerNamesResult(
            team1_players=team1,
            team2_players=team2,
        )
        self.accept()

    def get_result(self) -> PlayerNamesResult | None:
        """Get the dialog result after execution.

        Returns:
            PlayerNamesResult if the dialog was accepted, None if cancelled
        """
        return self._result


__all__ = ["PlayerNamesDialog", "PlayerNamesResult"]
