"""New Game Confirmation Dialog for the Pickleball Video Editor.

This module provides a confirmation dialog for the "Start New Game" action.
The dialog warns about data loss (clearing all rallies) and offers options
to keep or change game settings before starting fresh.

Visual Design:
- Warning icon/color to indicate destructive action
- Clear explanation of what will be cleared
- Option to keep or change game settings
- Destructive button with amber/warning styling
"""

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import (
    RADIUS_XL,
    SPACE_LG,
    SPACE_MD,
    Fonts,
)


# Amber/warning color for destructive action
WARNING_COLOR = "#FFB300"
WARNING_HOVER = "#FFC940"


class NewGameResult(Enum):
    """Result options from the New Game dialog.

    Attributes:
        START_NEW: User confirmed to start a new game
        CANCEL: User cancelled the action
    """

    START_NEW = "start_new"
    CANCEL = "cancel"


@dataclass
class NewGameSettings:
    """Optional new game settings if user chose to change them.

    Attributes:
        game_type: New game type ("singles" or "doubles")
        victory_rule: New victory rule ("11", "9", or "timed")
    """

    game_type: str
    victory_rule: str


class NewGameConfirmDialog(QDialog):
    """Confirmation dialog for starting a new game.

    This dialog is shown when the user clicks "Start New Game". It warns
    about the destructive nature of the action (clearing all rallies) and
    offers the option to keep or change game settings.

    Example:
        ```python
        dialog = NewGameConfirmDialog(
            current_game_type="doubles",
            current_victory_rule="11",
            rally_count=15,
            parent=main_window
        )

        if dialog.exec():
            result, new_settings = dialog.get_result()
            if result == NewGameResult.START_NEW:
                # Clear rallies and optionally apply new settings
                if new_settings is not None:
                    config.game_type = new_settings.game_type
                    config.victory_rule = new_settings.victory_rule
        ```
    """

    def __init__(
        self,
        current_game_type: str,
        current_victory_rule: str,
        rally_count: int,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the New Game Confirmation dialog.

        Args:
            current_game_type: Current game type ("singles" or "doubles")
            current_victory_rule: Current victory rule ("11", "9", or "timed")
            rally_count: Number of rallies that will be cleared
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)
        self.setObjectName("newGameConfirmDialog")

        self._current_game_type = current_game_type
        self._current_victory_rule = current_victory_rule
        self._rally_count = rally_count
        self._result = NewGameResult.CANCEL
        self._new_settings: NewGameSettings | None = None

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        self.setWindowTitle("Start New Game")
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Warning icon and title
        title_label = QLabel("⚠ Start New Game")
        title_label.setFont(Fonts.dialog_title())
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("warning_title")
        layout.addWidget(title_label)

        # Warning message with rally count
        if self._rally_count > 0:
            warning_text = (
                f"This will clear all {self._rally_count} rallies and reset the score to 0-0.\n\n"
                "This action cannot be undone."
            )
        else:
            warning_text = "This will reset the score to 0-0.\n\nThis action cannot be undone."

        warning_label = QLabel(warning_text)
        warning_label.setFont(Fonts.label())
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_label.setWordWrap(True)
        warning_label.setObjectName("warning_message")
        layout.addWidget(warning_label)

        # Settings options
        settings_label = QLabel("Game Settings:")
        settings_label.setFont(Fonts.secondary())
        layout.addWidget(settings_label)

        # Radio buttons for keep/change settings
        self._keep_settings_radio = QRadioButton("Keep current settings")
        self._change_settings_radio = QRadioButton("Change settings")
        self._keep_settings_radio.setChecked(True)

        self._settings_group = QButtonGroup(self)
        self._settings_group.addButton(self._keep_settings_radio, 0)
        self._settings_group.addButton(self._change_settings_radio, 1)

        radio_layout = QVBoxLayout()
        radio_layout.addWidget(self._keep_settings_radio)
        radio_layout.addWidget(self._change_settings_radio)
        layout.addLayout(radio_layout)

        # Settings dropdowns (initially hidden)
        self._settings_container = QWidget()
        settings_form_layout = QVBoxLayout(self._settings_container)
        settings_form_layout.setContentsMargins(SPACE_MD, 0, 0, 0)
        settings_form_layout.setSpacing(SPACE_MD)

        # Game type dropdown
        game_type_layout = QHBoxLayout()
        game_type_label = QLabel("Game Type:")
        game_type_label.setFont(Fonts.secondary())
        self._game_type_combo = QComboBox()
        self._game_type_combo.addItems(["Doubles", "Singles"])
        # Set current selection
        if self._current_game_type == "singles":
            self._game_type_combo.setCurrentIndex(1)
        else:
            self._game_type_combo.setCurrentIndex(0)
        game_type_layout.addWidget(game_type_label)
        game_type_layout.addWidget(self._game_type_combo)
        game_type_layout.addStretch()
        settings_form_layout.addLayout(game_type_layout)

        # Victory rule dropdown
        victory_layout = QHBoxLayout()
        victory_label = QLabel("Victory Rule:")
        victory_label.setFont(Fonts.secondary())
        self._victory_combo = QComboBox()
        self._victory_combo.addItems(["Game to 11", "Game to 9", "Timed"])
        # Set current selection
        victory_map = {"11": 0, "9": 1, "timed": 2}
        self._victory_combo.setCurrentIndex(victory_map.get(self._current_victory_rule, 0))
        victory_layout.addWidget(victory_label)
        victory_layout.addWidget(self._victory_combo)
        victory_layout.addStretch()
        settings_form_layout.addLayout(victory_layout)

        self._settings_container.setVisible(False)
        layout.addWidget(self._settings_container)

        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setFont(Fonts.button_other())
        self._cancel_button.setMinimumHeight(40)
        self._cancel_button.setObjectName("secondary_button")

        self._start_new_button = QPushButton("Start New Game")
        self._start_new_button.setFont(Fonts.button_other())
        self._start_new_button.setMinimumHeight(40)
        self._start_new_button.setObjectName("warning_button")

        button_layout.addWidget(self._cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self._start_new_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QLabel {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
            }}

            QLabel#warning_title {{
                color: {WARNING_COLOR};
            }}

            QLabel#warning_message {{
                color: {TEXT_SECONDARY};
                padding: 8px;
            }}

            QRadioButton {{
                color: {TEXT_PRIMARY};
                spacing: 8px;
            }}

            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
            }}

            QComboBox {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 120px;
            }}

            QComboBox:hover {{
                border-color: {TEXT_PRIMARY};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {TEXT_PRIMARY};
                margin-right: 8px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BG_BORDER};
                selection-background-color: {WARNING_COLOR};
                selection-color: {BG_SECONDARY};
            }}

            QPushButton#secondary_button {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: 8px 16px;
                min-width: 100px;
            }}

            QPushButton#secondary_button:hover {{
                border-color: {TEXT_PRIMARY};
            }}

            QPushButton#warning_button {{
                background-color: {WARNING_COLOR};
                border: 2px solid {WARNING_COLOR};
                border-radius: 6px;
                color: {BG_SECONDARY};
                padding: 8px 16px;
                font-weight: 600;
                min-width: 130px;
            }}

            QPushButton#warning_button:hover {{
                background-color: {WARNING_HOVER};
                border-color: {WARNING_HOVER};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._cancel_button.clicked.connect(self._on_cancel)
        self._start_new_button.clicked.connect(self._on_start_new)
        self._settings_group.buttonClicked.connect(self._on_settings_option_changed)

    def _on_settings_option_changed(self) -> None:
        """Handle settings option radio button change."""
        show_settings = self._change_settings_radio.isChecked()
        self._settings_container.setVisible(show_settings)
        self.adjustSize()

    def _on_cancel(self) -> None:
        """Handle Cancel button click."""
        self._result = NewGameResult.CANCEL
        self._new_settings = None
        self.reject()

    def _on_start_new(self) -> None:
        """Handle Start New Game button click."""
        self._result = NewGameResult.START_NEW

        if self._change_settings_radio.isChecked():
            # Map combo indices to values
            game_type = "doubles" if self._game_type_combo.currentIndex() == 0 else "singles"
            victory_map = {0: "11", 1: "9", 2: "timed"}
            victory_rule = victory_map[self._victory_combo.currentIndex()]

            self._new_settings = NewGameSettings(
                game_type=game_type,
                victory_rule=victory_rule,
            )
        else:
            self._new_settings = None

        self.accept()

    def get_result(self) -> tuple[NewGameResult, NewGameSettings | None]:
        """Get the user's choice after dialog is closed.

        Returns:
            Tuple of (result, new_settings) where:
            - result: NewGameResult indicating user's choice
            - new_settings: NewGameSettings if user chose to change settings, None otherwise
        """
        return self._result, self._new_settings

    def keyPressEvent(self, event) -> None:
        """Handle keyboard events, specifically Escape key.

        Args:
            event: QKeyEvent from Qt
        """
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)


__all__ = [
    "NewGameConfirmDialog",
    "NewGameResult",
    "NewGameSettings",
]
