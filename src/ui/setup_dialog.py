"""Setup dialog for Pickleball Video Editor.

This module provides the initial configuration dialog that users see when
starting a new editing session. It collects:
- Source video file path
- Game type (Singles or Doubles)
- Victory rules (Game to 11, 9, or Timed)
- Player names for both teams

The dialog validates all inputs and provides visual feedback for errors.
Team 1 is highlighted with an accent border to indicate the first server.
"""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models import SessionState
from src.core.session_manager import SessionManager
from src.ui.dialogs import ResumeSessionDialog, ResumeSessionResult, SessionDetails
from src.ui.styles.colors import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    GLOW_GREEN,
    PRIMARY_ACTION,
    TEXT_ACCENT,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


__all__ = ["GameConfig", "SetupDialog"]


@dataclass
class GameConfig:
    """Configuration for a new game session.

    Attributes:
        video_path: Path to the source video file
        game_type: Type of game ("singles" or "doubles")
        victory_rule: Victory condition ("11", "9", or "timed")
        team1_players: List of player names for Team 1
        team2_players: List of player names for Team 2
        session_state: Optional loaded session state for resuming
    """

    video_path: Path
    game_type: str
    victory_rule: str
    team1_players: list[str]
    team2_players: list[str]
    session_state: SessionState | None = None


class SetupDialog(QDialog):
    """Initial setup dialog for configuring a new editing session.

    This dialog collects all necessary information before starting the main
    editing interface. It provides validation and visual feedback for all
    required fields.

    The dialog uses a vertical layout with sections for:
    - Video file selection
    - Game configuration (type and victory rules)
    - Team 1 player names (highlighted as first server)
    - Team 2 player names

    Dynamic behavior:
    - Singles mode hides Player 2 fields
    - Doubles mode shows all 4 player fields
    - Start Editing button disabled until all validation passes
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the setup dialog.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.setWindowTitle("New Editing Session")
        self.setModal(True)
        self.setMinimumWidth(600)

        # Configuration result (set when accepted)
        self._config: GameConfig | None = None

        # Session manager for checking existing sessions
        self._session_manager = SessionManager()

        # Session state to resume (if user chooses to resume)
        self._session_state: SessionState | None = None

        # Create UI components
        self._create_widgets()
        self._create_layout()
        self._apply_styles()
        self._connect_signals()

        # Initial validation state
        self._validate()

    def _create_widgets(self) -> None:
        """Create all dialog widgets."""
        # Video source section
        self.video_label = QLabel("SOURCE VIDEO")
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Select a video file...")
        self.browse_button = QPushButton("Browse")

        # Game configuration section
        self.game_type_label = QLabel("GAME TYPE")
        self.game_type_combo = QComboBox()
        self.game_type_combo.addItems(["Doubles", "Singles"])

        self.victory_label = QLabel("VICTORY RULES")
        self.victory_combo = QComboBox()
        self.victory_combo.addItems(["Game to 11", "Game to 9", "Timed"])

        # Team 1 section (first server - highlighted)
        self.team1_group = QGroupBox("TEAM 1 (First Server)")
        self.team1_player1_label = QLabel("Player 1 *")
        self.team1_player1_edit = QLineEdit()
        self.team1_player2_label = QLabel("Player 2 *")
        self.team1_player2_edit = QLineEdit()

        # Team 2 section
        self.team2_group = QGroupBox("TEAM 2")
        self.team2_player1_label = QLabel("Player 1 *")
        self.team2_player1_edit = QLineEdit()
        self.team2_player2_label = QLabel("Player 2 *")
        self.team2_player2_edit = QLineEdit()

        # Dialog buttons
        self.cancel_button = QPushButton("Cancel")
        self.start_button = QPushButton("Start Editing")

        # Set object names for stylesheet targeting
        self.video_label.setObjectName("section-label")
        self.game_type_label.setObjectName("section-label")
        self.victory_label.setObjectName("section-label")
        self.team1_group.setObjectName("team1-group")
        self.team2_group.setObjectName("team2-group")
        self.start_button.setObjectName("primary-button")

    def _create_layout(self) -> None:
        """Create and configure the dialog layout."""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # Video source section
        video_layout = QVBoxLayout()
        video_layout.setSpacing(8)
        video_layout.addWidget(self.video_label)

        video_input_layout = QHBoxLayout()
        video_input_layout.addWidget(self.video_path_edit, stretch=1)
        video_input_layout.addWidget(self.browse_button)
        video_layout.addLayout(video_input_layout)

        main_layout.addLayout(video_layout)

        # Game configuration section (side by side)
        config_layout = QHBoxLayout()
        config_layout.setSpacing(16)

        # Game type container
        game_type_container = QWidget()
        game_type_layout = QVBoxLayout(game_type_container)
        game_type_layout.setContentsMargins(16, 16, 16, 16)
        game_type_layout.setSpacing(8)
        game_type_layout.addWidget(self.game_type_label)
        game_type_layout.addWidget(self.game_type_combo)
        game_type_container.setObjectName("config-container")

        # Victory rules container
        victory_container = QWidget()
        victory_layout = QVBoxLayout(victory_container)
        victory_layout.setContentsMargins(16, 16, 16, 16)
        victory_layout.setSpacing(8)
        victory_layout.addWidget(self.victory_label)
        victory_layout.addWidget(self.victory_combo)
        victory_container.setObjectName("config-container")

        config_layout.addWidget(game_type_container)
        config_layout.addWidget(victory_container)

        main_layout.addLayout(config_layout)

        # Team 1 section (first server)
        team1_layout = QFormLayout()
        team1_layout.setSpacing(12)
        team1_layout.setContentsMargins(16, 16, 16, 16)
        team1_layout.addRow(self.team1_player1_label, self.team1_player1_edit)
        team1_layout.addRow(self.team1_player2_label, self.team1_player2_edit)
        self.team1_group.setLayout(team1_layout)

        main_layout.addWidget(self.team1_group)

        # Team 2 section
        team2_layout = QFormLayout()
        team2_layout.setSpacing(12)
        team2_layout.setContentsMargins(16, 16, 16, 16)
        team2_layout.addRow(self.team2_player1_label, self.team2_player1_edit)
        team2_layout.addRow(self.team2_player2_label, self.team2_player2_edit)
        self.team2_group.setLayout(team2_layout)

        main_layout.addWidget(self.team2_group)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.start_button)

        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def _apply_styles(self) -> None:
        """Apply QSS styling to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
            }}

            QLabel#section-label {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }}

            QLineEdit {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }}

            QLineEdit:focus {{
                border-color: {TEXT_ACCENT};
                outline: none;
            }}

            QLineEdit[invalid="true"] {{
                border-color: #EF5350;
            }}

            QComboBox {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                min-width: 150px;
            }}

            QComboBox:hover {{
                border-color: {TEXT_ACCENT};
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
                border: 1px solid {BORDER_COLOR};
                selection-background-color: {TEXT_ACCENT};
                selection-color: {BG_PRIMARY};
            }}

            QWidget#config-container {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
            }}

            QGroupBox {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: 8px;
                font-size: 14px;
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

            QGroupBox#team1-group {{
                border-color: {TEXT_ACCENT};
                border-width: 2px;
            }}

            QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                min-width: 100px;
            }}

            QPushButton:hover:!disabled {{
                border-color: {TEXT_ACCENT};
                transform: translateY(-1px);
            }}

            QPushButton:pressed:!disabled {{
                transform: translateY(0);
            }}

            QPushButton:disabled {{
                opacity: 0.4;
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}

            QPushButton#primary-button {{
                background-color: {PRIMARY_ACTION};
                color: {BG_PRIMARY};
                border: 2px solid {PRIMARY_ACTION};
                font-weight: 600;
            }}

            QPushButton#primary-button:hover:!disabled {{
                box-shadow: 0 0 20px {GLOW_GREEN};
            }}

            QPushButton#primary-button:disabled {{
                background-color: {BG_TERTIARY};
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.browse_button.clicked.connect(self._browse_video)
        self.game_type_combo.currentIndexChanged.connect(self._on_game_type_changed)

        # Validation triggers
        self.video_path_edit.textChanged.connect(self._validate)
        self.team1_player1_edit.textChanged.connect(self._validate)
        self.team1_player2_edit.textChanged.connect(self._validate)
        self.team2_player1_edit.textChanged.connect(self._validate)
        self.team2_player2_edit.textChanged.connect(self._validate)

        # Dialog buttons
        self.cancel_button.clicked.connect(self.reject)
        self.start_button.clicked.connect(self._on_start_editing)

    @pyqtSlot()
    def _browse_video(self) -> None:
        """Open file dialog to select video file.

        After selection, checks if a session exists for the video and
        prompts the user to resume or start fresh.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            "/home/rkalluri/Videos/pickleball",
            "Video Files (*.mp4 *.MP4);;All Files (*)"
        )

        if not file_path:
            return

        self.video_path_edit.setText(file_path)

        # Check if session exists for this video
        session_info = self._session_manager.get_session_info(file_path)

        if session_info is not None:
            # Session exists - show resume dialog
            self._handle_existing_session(file_path, session_info)

    def _handle_existing_session(self, video_path: str, session_info: dict) -> None:
        """Handle detection of an existing session.

        Shows ResumeSessionDialog and handles user's choice to resume or start fresh.

        Args:
            video_path: Path to the video file
            session_info: Session information dictionary from SessionManager
        """
        # Map victory_rules to display format
        victory_map = {
            "11": "Game to 11",
            "9": "Game to 9",
            "timed": "Timed"
        }
        victory_display = victory_map.get(session_info["victory_rules"], session_info["victory_rules"])

        # Format game type for display
        game_type_display = session_info["game_type"].capitalize()

        # Create SessionDetails for dialog
        details = SessionDetails(
            video_name=Path(video_path).name,
            rally_count=session_info["rally_count"],
            current_score=session_info["current_score"],
            last_position=session_info["last_position"],
            game_type=game_type_display,
            victory_rule=victory_display
        )

        # Show resume dialog
        dialog = ResumeSessionDialog(details, self)
        dialog.exec()
        result = dialog.get_result()

        if result == ResumeSessionResult.RESUME:
            # Load full session state
            state = self._session_manager.load(video_path)
            if state is not None:
                self._session_state = state
                # Pre-fill form fields from session
                self._populate_from_session(state)
        else:  # START_FRESH
            # Delete the old session
            self._session_manager.delete(video_path)
            self._session_state = None

    def _populate_from_session(self, state: SessionState) -> None:
        """Populate form fields from loaded session state.

        Args:
            state: Loaded session state
        """
        # Set game type
        if state.game_type == "doubles":
            self.game_type_combo.setCurrentIndex(0)
        else:  # singles
            self.game_type_combo.setCurrentIndex(1)

        # Set victory rules
        victory_index_map = {
            "11": 0,
            "9": 1,
            "timed": 2
        }
        victory_index = victory_index_map.get(state.victory_rules, 0)
        self.victory_combo.setCurrentIndex(victory_index)

        # Set player names
        team1_names = state.player_names.get("team1", [])
        team2_names = state.player_names.get("team2", [])

        if len(team1_names) >= 1:
            self.team1_player1_edit.setText(team1_names[0])
        if len(team1_names) >= 2:
            self.team1_player2_edit.setText(team1_names[1])

        if len(team2_names) >= 1:
            self.team2_player1_edit.setText(team2_names[0])
        if len(team2_names) >= 2:
            self.team2_player2_edit.setText(team2_names[1])

    @pyqtSlot(int)
    def _on_game_type_changed(self, index: int) -> None:
        """Show or hide Player 2 fields based on game type.

        Args:
            index: Index of selected game type (0=Doubles, 1=Singles)
        """
        is_doubles = (index == 0)

        # Show/hide Player 2 fields
        self.team1_player2_label.setVisible(is_doubles)
        self.team1_player2_edit.setVisible(is_doubles)
        self.team2_player2_label.setVisible(is_doubles)
        self.team2_player2_edit.setVisible(is_doubles)

        # Revalidate after visibility change
        self._validate()

    def _validate(self) -> bool:
        """Validate all fields and update UI state.

        Returns:
            True if all validation passes, False otherwise
        """
        is_valid = True

        # Validate video path
        video_path = self.video_path_edit.text().strip()
        if not video_path or not Path(video_path).exists():
            self.video_path_edit.setProperty("invalid", "true")
            is_valid = False
        else:
            self.video_path_edit.setProperty("invalid", "false")

        # Determine which fields are required based on game type
        is_doubles = (self.game_type_combo.currentIndex() == 0)

        # Validate Team 1 Player 1
        if not self.team1_player1_edit.text().strip():
            self.team1_player1_edit.setProperty("invalid", "true")
            is_valid = False
        else:
            self.team1_player1_edit.setProperty("invalid", "false")

        # Validate Team 1 Player 2 (only if doubles)
        if is_doubles:
            if not self.team1_player2_edit.text().strip():
                self.team1_player2_edit.setProperty("invalid", "true")
                is_valid = False
            else:
                self.team1_player2_edit.setProperty("invalid", "false")

        # Validate Team 2 Player 1
        if not self.team2_player1_edit.text().strip():
            self.team2_player1_edit.setProperty("invalid", "true")
            is_valid = False
        else:
            self.team2_player1_edit.setProperty("invalid", "false")

        # Validate Team 2 Player 2 (only if doubles)
        if is_doubles:
            if not self.team2_player2_edit.text().strip():
                self.team2_player2_edit.setProperty("invalid", "true")
                is_valid = False
            else:
                self.team2_player2_edit.setProperty("invalid", "false")

        # Update Start Editing button state
        self.start_button.setEnabled(is_valid)

        # Force style refresh
        self.video_path_edit.style().unpolish(self.video_path_edit)
        self.video_path_edit.style().polish(self.video_path_edit)
        self.team1_player1_edit.style().unpolish(self.team1_player1_edit)
        self.team1_player1_edit.style().polish(self.team1_player1_edit)
        self.team1_player2_edit.style().unpolish(self.team1_player2_edit)
        self.team1_player2_edit.style().polish(self.team1_player2_edit)
        self.team2_player1_edit.style().unpolish(self.team2_player1_edit)
        self.team2_player1_edit.style().polish(self.team2_player1_edit)
        self.team2_player2_edit.style().unpolish(self.team2_player2_edit)
        self.team2_player2_edit.style().polish(self.team2_player2_edit)

        return is_valid

    @pyqtSlot()
    def _on_start_editing(self) -> None:
        """Handle Start Editing button click."""
        if not self._validate():
            return

        # Collect configuration
        is_doubles = (self.game_type_combo.currentIndex() == 0)
        game_type = "doubles" if is_doubles else "singles"

        # Map victory combo index to rule string
        victory_map = {
            0: "11",  # Game to 11
            1: "9",   # Game to 9
            2: "timed"
        }
        victory_rule = victory_map[self.victory_combo.currentIndex()]

        # Collect player names
        team1_players = [self.team1_player1_edit.text().strip()]
        team2_players = [self.team2_player1_edit.text().strip()]

        if is_doubles:
            team1_players.append(self.team1_player2_edit.text().strip())
            team2_players.append(self.team2_player2_edit.text().strip())

        # Create configuration
        self._config = GameConfig(
            video_path=Path(self.video_path_edit.text().strip()),
            game_type=game_type,
            victory_rule=victory_rule,
            team1_players=team1_players,
            team2_players=team2_players,
            session_state=self._session_state,  # Include loaded session state
        )

        # Accept the dialog
        self.accept()

    def get_config(self) -> GameConfig | None:
        """Get configuration if dialog was accepted, None if cancelled.

        Returns:
            GameConfig if dialog was accepted, None otherwise
        """
        return self._config
