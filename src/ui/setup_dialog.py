"""Setup dialog for Pickleball Video Editor.

This module provides the initial configuration dialog that users see when
starting the application. It provides:
- Recent Sessions: Display of saved sessions with click-to-resume functionality
- New Session: Form for starting a new editing session

For new sessions, it collects:
- Source video file path
- Game type (Singles or Doubles)
- Victory rules (Game to 11, 9, or Timed)
- Player names for both teams

The dialog validates all inputs and provides visual feedback for errors.
Team 1 is highlighted with an accent border to indicate the first server.

Recent Sessions features:
- Horizontal scrollable card layout
- Click to resume or start fresh
- Delete session with confirmation
- Missing video detection with re-link capability
"""

import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog
from src.video.frame_extract import extract_frame_at

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QKeyEvent,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.app_config import AppSettings
from src.ui.styles.geometry import fit_to_screen
from src.core.models import SessionState, generate_export_basename
from src.core.session_manager import SessionManager
from src.ui.dialogs import ResumeSessionDialog, ResumeSessionResult, SessionDetails
from src.ui.dialogs.config_dialog import ConfigDialog
from src.ui.styles.colors import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    DANGER_TEXT,
    GLOW_GREEN,
    PRIMARY_ACTION,
    RALLY_START,
    TEXT_ACCENT,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_WARNING,
    UNDO,
)
from src.ui.styles.fonts import RADIUS_MD, SPACE_MD, SPACE_SM, Fonts
from src.ui.widgets.court_calibrator import CourtCalibratorWidget
from src.ui.widgets.saved_session_card import SavedSessionCard, SavedSessionInfo
from src.video.probe import ProbeError, probe_video


_VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v",
    ".webm", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts",
})


__all__ = ["GameConfig", "SetupDialog"]


@dataclass
class GameConfig:
    """Configuration for a new game session.

    Attributes:
        video_path: Path to the source video file
        game_type: Type of game ("singles" or "doubles")
        victory_rule: Victory condition ("11", "9", or "timed")
        team1_players: List of player names for Team 1 (optional, can be set later)
        team2_players: List of player names for Team 2 (optional, can be set later)
        session_state: Optional loaded session state for resuming
    """

    video_path: Path
    game_type: str
    victory_rule: str
    team1_players: list[str] = field(default_factory=list)
    team2_players: list[str] = field(default_factory=list)
    session_state: SessionState | None = None
    court_corners: list[list[int]] | None = None
    auto_mode: bool = False

    def has_player_names(self) -> bool:
        """Check if player names have been configured.

        Returns:
            True if both teams have at least one player name
        """
        return len(self.team1_players) > 0 and len(self.team2_players) > 0

    def export_base_filename(self) -> str:
        """Generate a formatted export basename from video and game info.

        Returns:
            Formatted basename like "2025-03-08_AliceCharlie_vs_BobDave"
        """
        return generate_export_basename(
            self.video_path.stem,
            self.game_type,
            self.team1_players,
            self.team2_players,
        )


class SetupDialog(QDialog):
    """Initial setup dialog for configuring editing sessions.

    This dialog serves as the entry point for the application, providing:
    1. Recent Sessions: Horizontal scrollable cards showing saved sessions
       - Click to resume or start fresh
       - Delete with confirmation
       - Missing video handling with hash validation
    2. New Session Form: Input fields for starting new editing session

    The dialog uses a vertical layout with sections for:
    - Recent Sessions (hidden if no sessions exist)
    - Video file selection
    - Game configuration (type and victory rules)
    - Team 1 player names (highlighted as first server)
    - Team 2 player names

    Dynamic behavior:
    - Recent Sessions section hidden when no saved sessions
    - Singles mode hides Player 2 fields
    - Doubles mode shows all 4 player fields
    - Start Editing button disabled until all validation passes
    - Automatic session detection when browsing for video
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        app_settings: AppSettings | None = None,
    ) -> None:
        """Initialize the setup dialog.

        Args:
            parent: Parent widget (optional)
            app_settings: Application settings instance (optional, will load if not provided)
        """
        super().__init__(parent)
        self.setObjectName("setupDialog")
        self.setWindowTitle("Pickleball Video Editor")
        self.setModal(True)
        self.setAcceptDrops(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(520)  # Content is in a QScrollArea; 520 is enough to show controls

        # Configuration result (set when accepted)
        self._config: GameConfig | None = None

        # Court corners captured by the calibration step (optional)
        self._court_corners: list[list[int]] | None = None

        # Session manager for checking existing sessions
        self._session_manager = SessionManager()

        # Session state to resume (if user chooses to resume)
        self._session_state: SessionState | None = None

        # Application settings
        self._app_settings = app_settings or AppSettings.load()

        # Create UI components
        self._create_widgets()
        self._create_layout()
        self._apply_styles()
        self._connect_signals()

        # Explicit keyboard Tab order
        self._setup_tab_order()

        # Initial validation state
        self._validate()

        # Load saved sessions
        self._load_saved_sessions()

        # Size and center relative to available screen area:
        # width  = clamp(30% of available, 700, 1000)
        # height = clamp(85% of available, 520, 900)
        fit_to_screen(self, 0.30, 0.85, 700, 520, 1000, 900)

    @contextmanager
    def _native_file_dialog(self):
        """Temporarily clear app stylesheet for native file dialog appearance.

        Qt applies app-level stylesheets to ALL widgets including QFileDialog.
        Global selectors like QLabel{}, QPushButton{}, QScrollBar{} cannot be
        scoped and will style file dialog internals. The only way to get native
        appearance is to temporarily clear the stylesheet.
        """
        app = QApplication.instance()
        if app:
            saved_stylesheet = app.styleSheet()
            app.setStyleSheet("")
            try:
                yield
            finally:
                app.setStyleSheet(saved_stylesheet)
        else:
            yield

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Enter key to start editing if form is valid.

        Behavior:
        - If Browse button or video path field is focused: open file browser
        - If form is valid: start editing
        - Otherwise: do nothing (don't close dialog)
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = self.focusWidget()

            # If browse button or video path field is focused, open file browser
            if focused in (self.browse_button, self.video_path_edit):
                self._browse_video()
                return

            # If form is valid, start editing
            if self.start_button.isEnabled():
                self._on_start_editing()
                return

            # Otherwise, do nothing (ignore Enter)
            return

        # Let parent handle other keys
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the drag-and-drop overlay sized to the full dialog."""
        super().resizeEvent(event)
        if hasattr(self, "_drop_overlay"):
            self._drop_overlay.setGeometry(self.rect())

    # ------------------------------------------------------------------
    # Drag-and-drop support
    # ------------------------------------------------------------------

    def _show_drop_overlay(self) -> None:
        """Show the drop-feedback overlay, sized to the current dialog rect."""
        self._drop_overlay.setGeometry(self.rect())
        self._drop_overlay.show()
        self._drop_overlay.raise_()

    def _hide_drop_overlay(self) -> None:
        """Hide the drop-feedback overlay."""
        self._drop_overlay.hide()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept a drag that contains exactly one local video file URL.

        Shows a dashed overlay with "Drop video to load" during the drag.
        """
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in _VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    self._show_drop_overlay()
                    return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Hide the overlay when the drag leaves the dialog boundary."""
        self._hide_drop_overlay()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Load the dropped video path into the video path field."""
        self._hide_drop_overlay()
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in _VIDEO_EXTENSIONS:
                    self.video_path_edit.setText(str(path))
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _load_saved_sessions(self) -> None:
        """Load and display saved session cards.

        Fetches session metadata from SessionManager and creates SavedSessionCard
        widgets for each session. Hides the entire section if no sessions exist.
        """
        # Get all sessions from SessionManager
        sessions = self._session_manager.list_all_sessions(limit=6)

        # Hide section if no sessions
        if not sessions:
            self.sessions_section.setVisible(False)
            return

        # Show section and update count label
        self.sessions_section.setVisible(True)
        total_count = len(self._session_manager.list_all_sessions(limit=100))
        displayed_count = len(sessions)

        if displayed_count < total_count:
            self.sessions_count_label.setText(f"(showing {displayed_count} of {total_count})")
        else:
            self.sessions_count_label.setText(f"({displayed_count})")

        # Create cards for each session
        for session_dict in sessions:
            session_info = SavedSessionInfo(
                session_path=session_dict["session_path"],
                session_hash=session_dict["session_hash"],
                video_name=session_dict["video_name"],
                video_path=session_dict["video_path"],
                rally_count=session_dict["rally_count"],
                current_score=session_dict["current_score"],
                last_modified=session_dict["last_modified"],
                game_type=session_dict["game_type"],
                video_exists=session_dict["video_exists"],
            )

            card = SavedSessionCard(session_info)
            card.clicked.connect(self._on_session_card_clicked)
            card.delete_requested.connect(self._on_session_delete_requested)
            self.sessions_layout.addWidget(card)

        # Add stretch to push cards to the left
        self.sessions_layout.addStretch()

    @pyqtSlot(SavedSessionInfo)
    def _on_session_card_clicked(self, info: SavedSessionInfo) -> None:
        """Handle session card click.

        If video exists, show ResumeSessionDialog.
        If video missing, show MissingVideoDialog with options to browse, delete, or cancel.

        Args:
            info: Session metadata from the clicked card
        """
        if info.video_exists:
            # Video exists - show existing resume dialog flow
            self._handle_existing_session_from_card(info)
        else:
            # Video missing - show missing video dialog
            self._handle_missing_video(info)

    def _handle_existing_session_from_card(self, info: SavedSessionInfo) -> None:
        """Handle session card click when video exists.

        Shows ResumeSessionDialog and handles user's choice.

        Args:
            info: Session metadata
        """
        # Load full session state from session file
        state = self._session_manager.load_from_session_file(info.session_path)
        if state is None:
            QMessageBox.warning(
                self,
                "Session Load Error",
                "Failed to load session data. The session file may be corrupted."
            )
            return

        # Extract video path from session state
        video_path = state.video_path

        # Map victory_rules to display format
        victory_map = {
            "11": "Game to 11",
            "9": "Game to 9",
            "timed": "Timed"
        }
        victory_display = victory_map.get(state.victory_rules, state.victory_rules)

        # Format game type for display
        game_type_display = state.game_type.capitalize()

        # Create SessionDetails for dialog
        details = SessionDetails(
            video_name=info.video_name,
            rally_count=info.rally_count,
            current_score=info.current_score,
            last_position=state.last_position,
            game_type=game_type_display,
            victory_rule=victory_display
        )

        # Show resume dialog
        dialog = ResumeSessionDialog(details, self)
        dialog.exec()
        result = dialog.get_result()

        if result == ResumeSessionResult.RESUME:
            # User chose to resume - populate form and set session state
            self._session_state = state
            self.video_path_edit.setText(video_path)
            self._populate_from_session(state)
            # Automatically start editing instead of waiting for user to click button
            self._on_start_editing()
        else:  # START_FRESH
            # User chose to start fresh - delete session and populate video path
            self._session_manager.delete_session_file(info.session_path)
            self._session_state = None
            self.video_path_edit.setText(video_path)
            # Reload sessions to update UI
            self._reload_sessions()

    def _handle_missing_video(self, info: SavedSessionInfo) -> None:
        """Handle session card click when video is missing.

        Shows dialog with options to browse for video, delete session, or cancel.

        Args:
            info: Session metadata
        """
        # Create custom message box
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Video Not Found")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(f"The video file for this session could not be found.")
        msg_box.setInformativeText(
            f"Original path:\n{info.video_path}\n\n"
            "What would you like to do?"
        )

        # Add custom buttons
        browse_btn = msg_box.addButton("Browse for Video", QMessageBox.ButtonRole.ActionRole)
        delete_btn = msg_box.addButton("Delete Session", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()

        if clicked_button == browse_btn:
            # User wants to browse for video
            self._browse_for_missing_video(info)
        elif clicked_button == delete_btn:
            # User wants to delete session
            self._delete_session(info)

    def _browse_for_missing_video(self, info: SavedSessionInfo) -> None:
        """Browse for missing video file and validate hash.

        Args:
            info: Session metadata
        """
        with self._native_file_dialog():
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Locate Video File",
                str(Path.home() / "Videos"),
                "Video Files (*.mp4 *.MP4);;All Files (*)"
            )

        if not file_path:
            return

        # Validate that the selected file matches the session hash
        selected_hash = self._session_manager.get_video_hash(file_path)

        if selected_hash != info.session_hash:
            QMessageBox.critical(
                self,
                "Video Mismatch",
                "The selected video doesn't match this session.\n\n"
                "Please select the correct video file, or delete this session."
            )
            return

        # Hash matches - load session and populate form
        state = self._session_manager.load_from_session_file(info.session_path)
        if state is None:
            QMessageBox.warning(
                self,
                "Session Load Error",
                "Failed to load session data. The session file may be corrupted."
            )
            return

        # Update session with new video path and save
        state.video_path = file_path
        saved_path = self._session_manager.save(state, file_path)

        # Delete old session file ONLY if it's different from the new one
        # (same-hash relinks save to the same file, so no deletion needed)
        if saved_path and saved_path != info.session_path and info.session_path.exists():
            info.session_path.unlink()

        # Show resume dialog
        self._handle_existing_session_from_card(info)

        # Reload sessions to update UI
        self._reload_sessions()

    @pyqtSlot(SavedSessionInfo)
    def _on_session_delete_requested(self, info: SavedSessionInfo) -> None:
        """Handle delete button click on session card.

        Shows confirmation dialog before deleting.

        Args:
            info: Session metadata for the session to delete
        """
        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Are you sure you want to delete this session?\n\n"
            f"Video: {info.video_name}\n"
            f"Score: {info.current_score}\n"
            f"Rallies: {info.rally_count}\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._delete_session(info)

    def _delete_session(self, info: SavedSessionInfo) -> None:
        """Delete a session and refresh the UI.

        Args:
            info: Session metadata for the session to delete
        """
        # Delete the session file
        success = self._session_manager.delete_session_file(info.session_path)

        if not success:
            QMessageBox.warning(
                self,
                "Delete Failed",
                "Failed to delete session file."
            )
            return

        # Reload sessions to update UI
        self._reload_sessions()

    def _reload_sessions(self) -> None:
        """Reload and redisplay all saved sessions.

        Clears existing cards and repopulates from SessionManager.
        """
        # Clear existing cards
        while self.sessions_layout.count():
            item = self.sessions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reload sessions
        self._load_saved_sessions()

    def _create_widgets(self) -> None:
        """Create all dialog widgets."""
        # Settings button (appears at top)
        self._settings_button = QPushButton("Settings")
        self._settings_button.setFont(Fonts.button_other())
        self._settings_button.setObjectName("settings_button")
        self._settings_button.setToolTip("Configure application settings")

        # Recent Sessions section
        self.sessions_label = QLabel("RECENT SESSIONS")
        self.sessions_count_label = QLabel("")  # Will be populated later
        self.sessions_scroll = QScrollArea()
        self.sessions_scroll.setObjectName("sessions-scroll")
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sessions_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sessions_scroll.setMinimumHeight(200)
        self.sessions_container = QWidget()
        self.sessions_container.setObjectName("sessions-container")
        self.sessions_layout = QHBoxLayout(self.sessions_container)
        self.sessions_layout.setContentsMargins(0, 0, 0, 0)
        self.sessions_layout.setSpacing(16)
        self.sessions_scroll.setWidget(self.sessions_container)

        # Mode selector
        self.mode_label = QLabel("PROCESSING MODE")
        self.mode_label.setObjectName("section-label")

        self.mode_manual_radio = QRadioButton("Manual editing")
        self.mode_manual_radio.setChecked(True)
        self.mode_manual_radio.setObjectName("mode-radio")

        self.mode_auto_radio = QRadioButton("Auto-process (experimental)")
        self.mode_auto_radio.setObjectName("mode-radio")

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.mode_manual_radio, 0)
        self._mode_group.addButton(self.mode_auto_radio, 1)

        # Warning label shown when auto mode requires corner calibration
        self.auto_mode_warning_label = QLabel(
            "Court corner calibration is required for auto-process mode."
        )
        self.auto_mode_warning_label.setObjectName("auto-mode-warning")
        self.auto_mode_warning_label.setVisible(False)

        # Video source section
        self.video_label = QLabel("SOURCE VIDEO *")
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setPlaceholderText("Select a video file...")
        self.browse_button = QPushButton("Browse")

        # Error label shown when a non-empty path does not resolve to an existing file.
        # Red border alone is insufficient — this provides an accessible text cue.
        self._video_error_label = QLabel(
            "Video file not found — check the path or click Browse"
        )
        self._video_error_label.setObjectName("video-error-label")
        self._video_error_label.setVisible(False)

        # Court calibration row (optional step for ML auto-process mode)
        self.calibrate_button = QPushButton("Calibrate Court Corners")
        self.calibrate_button.setObjectName("calibrate-button")
        self.calibrate_button.setToolTip(
            "Optional: mark the 4 court corners for ML-assisted auto-processing"
        )
        self.calibrate_button.setEnabled(False)

        self.calibrate_status_label = QLabel("Not calibrated")
        self.calibrate_status_label.setObjectName("calibrate-status-uncalibrated")

        # Game configuration section
        self.game_type_label = QLabel("GAME TYPE")
        self.game_type_combo = QComboBox()
        self.game_type_combo.addItems(["Doubles", "Singles", "Highlights"])

        self.victory_label = QLabel("VICTORY RULES")
        self.victory_combo = QComboBox()
        self.victory_combo.addItems(["Game to 11", "Game to 9", "Timed"])

        # Team 1 section (first server - highlighted)
        self.team1_group = QGroupBox("TEAM 1 (First Server) (optional)")
        self.team1_player1_label = QLabel("Player 1")
        self.team1_player1_edit = QLineEdit()
        self.team1_player1_edit.setPlaceholderText("Optional - Serving player")
        self.team1_player2_label = QLabel("Player 2")
        self.team1_player2_edit = QLineEdit()
        self.team1_player2_edit.setPlaceholderText("Optional - Non-serving player")

        # Team 2 section
        self.team2_group = QGroupBox("TEAM 2 (optional)")
        self.team2_player1_label = QLabel("Player 1")
        self.team2_player1_edit = QLineEdit()
        self.team2_player1_edit.setPlaceholderText("Optional - Receiving player")
        self.team2_player2_label = QLabel("Player 2")
        self.team2_player2_edit = QLineEdit()
        self.team2_player2_edit.setPlaceholderText("Optional - Non-receiving player")

        # Dialog buttons
        self.cancel_button = QPushButton("Cancel")
        self.start_button = QPushButton("Start Editing")

        # Set object names for stylesheet targeting
        self.sessions_label.setObjectName("section-label")
        self.sessions_count_label.setObjectName("count-label")
        self.sessions_scroll.setObjectName("sessions-scroll")
        self.video_label.setObjectName("section-label")
        self.game_type_label.setObjectName("section-label")
        self.victory_label.setObjectName("section-label")
        self.team1_group.setObjectName("team1-group")
        self.team2_group.setObjectName("team2-group")
        self.start_button.setObjectName("primary-button")

    def _create_layout(self) -> None:
        """Create and configure the dialog layout.

        Layout structure:
            main_layout (QVBoxLayout)
              ├─ header_layout (Settings button - stays fixed at top)
              └─ QScrollArea (scrolls when needed)
                  └─ content_widget
                      ├─ sessions_section
                      ├─ video_section
                      ├─ config_layout
                      ├─ team1_group
                      ├─ team2_group
                      └─ button_layout
        """
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Top header with Settings button (stays fixed at top)
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(24, 24, 24, 12)
        header_layout.addStretch()
        header_layout.addWidget(self._settings_button)
        main_layout.addWidget(header_widget)

        # Create scrollable content area
        self._content_scroll = QScrollArea()
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content_scroll.setObjectName("content-scroll")

        # Content widget inside scroll area
        content_widget = QWidget()
        content_widget.setObjectName("content-widget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(24)
        content_layout.setContentsMargins(24, 12, 24, 24)

        # Recent Sessions section (conditionally visible)
        sessions_header_layout = QHBoxLayout()
        sessions_header_layout.addWidget(self.sessions_label)
        sessions_header_layout.addWidget(self.sessions_count_label)
        sessions_header_layout.addStretch()

        self.sessions_section = QWidget()
        sessions_section_layout = QVBoxLayout(self.sessions_section)
        sessions_section_layout.setContentsMargins(0, 0, 0, 0)
        sessions_section_layout.setSpacing(12)
        sessions_section_layout.addLayout(sessions_header_layout)
        sessions_section_layout.addWidget(self.sessions_scroll)

        content_layout.addWidget(self.sessions_section)

        # Mode selector section
        mode_section = QWidget()
        mode_section.setObjectName("mode-section")
        mode_section_layout = QVBoxLayout(mode_section)
        mode_section_layout.setContentsMargins(16, 16, 16, 16)
        mode_section_layout.setSpacing(SPACE_SM)
        mode_section_layout.addWidget(self.mode_label)

        mode_radios_layout = QHBoxLayout()
        mode_radios_layout.setSpacing(SPACE_MD)
        mode_radios_layout.addWidget(self.mode_manual_radio)
        mode_radios_layout.addWidget(self.mode_auto_radio)
        mode_radios_layout.addStretch()
        mode_section_layout.addLayout(mode_radios_layout)
        mode_section_layout.addWidget(self.auto_mode_warning_label)

        content_layout.addWidget(mode_section)

        # Video source section
        video_section = QWidget()
        video_section.setMinimumHeight(100)  # Label + input row with comfortable padding
        video_layout = QVBoxLayout(video_section)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(SPACE_SM)
        video_layout.addWidget(self.video_label)

        video_input_layout = QHBoxLayout()
        video_input_layout.addWidget(self.video_path_edit, stretch=1)
        video_input_layout.addWidget(self.browse_button)
        video_layout.addLayout(video_input_layout)

        # Error label — appears when a non-empty path does not exist
        video_layout.addWidget(self._video_error_label)

        # Calibration row — button + status label side by side
        calibrate_row = QHBoxLayout()
        calibrate_row.setSpacing(SPACE_SM)
        calibrate_row.addWidget(self.calibrate_button)
        calibrate_row.addWidget(self.calibrate_status_label)
        calibrate_row.addStretch()
        video_layout.addLayout(calibrate_row)

        content_layout.addWidget(video_section)

        # Game configuration section (side by side)
        config_layout = QHBoxLayout()
        config_layout.setSpacing(SPACE_MD)

        # Game type container
        game_type_container = QWidget()
        game_type_container.setMinimumHeight(110)  # Label + combo with 16px padding each side
        game_type_layout = QVBoxLayout(game_type_container)
        game_type_layout.setContentsMargins(16, 16, 16, 16)
        game_type_layout.setSpacing(8)
        game_type_layout.addWidget(self.game_type_label)
        game_type_layout.addWidget(self.game_type_combo)
        game_type_container.setObjectName("config-container")

        # Victory rules container
        self._victory_container = QWidget()
        self._victory_container.setMinimumHeight(110)  # Label + combo with 16px padding each side
        victory_layout = QVBoxLayout(self._victory_container)
        victory_layout.setContentsMargins(16, 16, 16, 16)
        victory_layout.setSpacing(8)
        victory_layout.addWidget(self.victory_label)
        victory_layout.addWidget(self.victory_combo)
        self._victory_container.setObjectName("config-container")

        config_layout.addWidget(game_type_container)
        config_layout.addWidget(self._victory_container)

        content_layout.addLayout(config_layout)

        # Team 1 section (first server)
        self.team1_group.setMinimumHeight(160)  # Two rows at ~52px each + 16px margins top/bottom
        team1_layout = QFormLayout()
        team1_layout.setSpacing(SPACE_SM)
        team1_layout.setContentsMargins(16, 16, 16, 16)
        team1_layout.addRow(self.team1_player1_label, self.team1_player1_edit)
        team1_layout.addRow(self.team1_player2_label, self.team1_player2_edit)
        self.team1_group.setLayout(team1_layout)

        content_layout.addWidget(self.team1_group)

        # Team 2 section
        self.team2_group.setMinimumHeight(160)  # Two rows at ~52px each + 16px margins top/bottom
        team2_layout = QFormLayout()
        team2_layout.setSpacing(SPACE_SM)
        team2_layout.setContentsMargins(16, 16, 16, 16)
        team2_layout.addRow(self.team2_player1_label, self.team2_player1_edit)
        team2_layout.addRow(self.team2_player2_label, self.team2_player2_edit)
        self.team2_group.setLayout(team2_layout)

        content_layout.addWidget(self.team2_group)

        # Dialog buttons
        button_widget = QWidget()
        button_widget.setMinimumHeight(60)  # Touch-friendly button height
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.start_button)

        content_layout.addWidget(button_widget)

        # Add stretch to push content to top when window is larger
        content_layout.addStretch()

        # Set the content widget in the scroll area
        self._content_scroll.setWidget(content_widget)
        main_layout.addWidget(self._content_scroll)

        self.setLayout(main_layout)

        # Drag-and-drop overlay: a full-dialog label that floats on top when a
        # video file is dragged over the window.  Positioned/sized in resizeEvent.
        self._drop_overlay = QLabel("Drop video to load", self)
        self._drop_overlay.setObjectName("drop-overlay")
        self._drop_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_overlay.setGeometry(self.rect())
        self._drop_overlay.hide()
        # Overlay must not consume mouse events — drag events go to the dialog.
        self._drop_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _apply_styles(self) -> None:
        """Apply QSS styling to the dialog."""
        self.setStyleSheet(f"""
            #setupDialog {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
            }}

            #setupDialog QPushButton#settings_button {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
                min-width: 80px;
            }}

            #setupDialog QPushButton#settings_button:hover {{
                background-color: {BG_BORDER};
                border-color: {TEXT_ACCENT};
            }}

            #setupDialog QLabel#section-label {{
                color: {TEXT_SECONDARY};
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }}

            #setupDialog QLabel#count-label {{
                color: {TEXT_TERTIARY};
                font-size: 12px;
                font-weight: 500;
            }}

            #setupDialog QScrollArea#sessions-scroll {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
            }}

            #setupDialog QScrollArea#sessions-scroll > QWidget {{
                background-color: {BG_SECONDARY};
            }}

            #setupDialog QWidget#sessions-container {{
                background-color: {BG_SECONDARY};
            }}

            #setupDialog QScrollArea#content-scroll {{
                background-color: {BG_SECONDARY};
                border: none;
            }}

            #setupDialog QScrollArea#content-scroll > QWidget {{
                background-color: {BG_SECONDARY};
            }}

            #setupDialog QWidget#content-widget {{
                background-color: {BG_SECONDARY};
            }}

            #setupDialog QScrollBar:horizontal {{
                height: 10px;
                background-color: {BG_TERTIARY};
                border-radius: 5px;
                margin: 2px;
            }}

            #setupDialog QScrollBar::handle:horizontal {{
                background-color: {TEXT_SECONDARY};
                border-radius: 4px;
                min-width: 30px;
            }}

            #setupDialog QScrollBar::handle:horizontal:hover {{
                background-color: {PRIMARY_ACTION};
            }}

            #setupDialog QScrollBar::add-line:horizontal,
            #setupDialog QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}

            #setupDialog QScrollBar:vertical {{
                width: 10px;
                background-color: {BG_TERTIARY};
                border-radius: 5px;
                margin: 2px;
            }}

            #setupDialog QScrollBar::handle:vertical {{
                background-color: {TEXT_SECONDARY};
                border-radius: 4px;
                min-height: 30px;
            }}

            #setupDialog QScrollBar::handle:vertical:hover {{
                background-color: {PRIMARY_ACTION};
            }}

            #setupDialog QScrollBar::add-line:vertical,
            #setupDialog QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            #setupDialog QLineEdit {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                min-height: 36px;   /* Prevents vertical squishing */
                min-width: 200px;   /* Prevents horizontal squishing */
            }}

            #setupDialog QLineEdit:focus {{
                border-color: {TEXT_ACCENT};
            }}

            #setupDialog QLineEdit[invalid="true"] {{
                border-color: {UNDO};
            }}

            #setupDialog QComboBox {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                min-width: 150px;
            }}

            #setupDialog QComboBox:hover {{
                border-color: {TEXT_ACCENT};
            }}

            #setupDialog QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}

            #setupDialog QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {TEXT_PRIMARY};
                margin-right: 8px;
            }}

            #setupDialog QComboBox QAbstractItemView {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: {TEXT_ACCENT};
                selection-color: {BG_PRIMARY};
            }}

            #setupDialog QWidget#config-container {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
            }}

            #setupDialog QGroupBox {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                color: {TEXT_PRIMARY};
                margin-top: 12px;
                padding-top: 16px;
            }}

            #setupDialog QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 0 8px;
            }}

            #setupDialog QGroupBox#team1-group {{
                border-color: {TEXT_ACCENT};
                border-width: 2px;
            }}

            #setupDialog QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                min-width: 100px;
            }}

            #setupDialog QPushButton:hover:!disabled {{
                border-color: {TEXT_ACCENT};
            }}

            #setupDialog QPushButton:disabled {{
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}

            #setupDialog QPushButton#primary-button {{
                background-color: {PRIMARY_ACTION};
                color: {BG_PRIMARY};
                border: 2px solid {PRIMARY_ACTION};
                font-weight: 600;
            }}

            #setupDialog QPushButton#primary-button:hover:!disabled {{
                background-color: {TEXT_ACCENT};
            }}

            #setupDialog QPushButton#primary-button:disabled {{
                background-color: {BG_TERTIARY};
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}

            #setupDialog QPushButton#calibrate-button {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BG_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 180px;
            }}

            #setupDialog QPushButton#calibrate-button:hover:!disabled {{
                border-color: {TEXT_WARNING};
                color: {TEXT_WARNING};
            }}

            #setupDialog QPushButton#calibrate-button:disabled {{
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}

            #setupDialog QLabel#calibrate-status-uncalibrated {{
                color: {TEXT_WARNING};
                font-size: 13px;
                font-weight: 500;
            }}

            #setupDialog QLabel#calibrate-status-calibrated {{
                color: {TEXT_ACCENT};
                font-size: 13px;
                font-weight: 500;
            }}

            #setupDialog QWidget#mode-section {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
            }}

            #setupDialog QRadioButton#mode-radio {{
                color: {TEXT_PRIMARY};
                font-size: 14px;
                spacing: 8px;
            }}

            #setupDialog QRadioButton#mode-radio::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid {BORDER_COLOR};
                background-color: {BG_TERTIARY};
            }}

            #setupDialog QRadioButton#mode-radio::indicator:checked {{
                border-color: {TEXT_ACCENT};
                background-color: {TEXT_ACCENT};
            }}

            #setupDialog QRadioButton#mode-radio:hover {{
                color: {TEXT_ACCENT};
            }}

            #setupDialog QLabel#auto-mode-warning {{
                color: {TEXT_WARNING};
                font-size: 12px;
                font-weight: 500;
            }}

            #setupDialog QLabel#video-error-label {{
                color: {DANGER_TEXT};
                font-size: 12px;
                font-weight: 400;
            }}

            QLabel#drop-overlay {{
                background-color: rgba(37, 42, 51, 0.90);
                border: 3px dashed {RALLY_START};
                border-radius: 8px;
                color: {RALLY_START};
                font-size: 20px;
                font-weight: 600;
            }}
        """)

    def _setup_tab_order(self) -> None:
        """Set explicit keyboard Tab order for the setup form.

        Order: video path → browse → game-type combo → victory combo
               → Team 1 player 1 → Team 1 player 2 → Team 2 player 1
               → Team 2 player 2 → manual-mode radio → auto-mode radio
               → start button.

        Qt skips hidden/disabled widgets automatically, so doubles-only fields
        (player 2 inputs) and timed/highlights fields are handled transparently.
        """
        QWidget.setTabOrder(self.video_path_edit, self.browse_button)
        QWidget.setTabOrder(self.browse_button, self.game_type_combo)
        QWidget.setTabOrder(self.game_type_combo, self.victory_combo)
        QWidget.setTabOrder(self.victory_combo, self.team1_player1_edit)
        QWidget.setTabOrder(self.team1_player1_edit, self.team1_player2_edit)
        QWidget.setTabOrder(self.team1_player2_edit, self.team2_player1_edit)
        QWidget.setTabOrder(self.team2_player1_edit, self.team2_player2_edit)
        QWidget.setTabOrder(self.team2_player2_edit, self.mode_manual_radio)
        QWidget.setTabOrder(self.mode_manual_radio, self.mode_auto_radio)
        QWidget.setTabOrder(self.mode_auto_radio, self.start_button)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        # Settings button
        self._settings_button.clicked.connect(self._on_settings_clicked)

        self.browse_button.clicked.connect(self._browse_video)
        self.calibrate_button.clicked.connect(self._open_calibrator)
        self.game_type_combo.currentIndexChanged.connect(self._on_game_type_changed)

        # Mode selector
        self.mode_manual_radio.toggled.connect(self._on_mode_changed)
        self.mode_auto_radio.toggled.connect(self._on_mode_changed)

        # Validation triggers
        self.video_path_edit.textChanged.connect(self._validate)
        self.video_path_edit.textChanged.connect(self._update_calibrate_button_state)
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
        # Resolve the starting directory from DisplayConfig (added by Task 1),
        # falling back to ~/Videos when the field is absent or empty.
        _display = getattr(self._app_settings, "display", None)
        _last_browse = getattr(_display, "last_browse_dir", "") if _display is not None else ""
        _browse_dir = _last_browse if _last_browse else str(Path.home() / "Videos")

        with self._native_file_dialog():
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Video File",
                _browse_dir,
                "Video Files (*.mp4 *.MP4);;All Files (*)"
            )

        if not file_path:
            return

        # Persist the directory for the next browse session.
        if _display is not None and hasattr(_display, "last_browse_dir"):
            _display.last_browse_dir = str(Path(file_path).parent)
            self._app_settings.save()

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
                # Automatically start editing instead of waiting for user to click button
                self._on_start_editing()
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
        game_type_index_map = {
            "doubles": 0,
            "singles": 1,
            "highlights": 2
        }
        game_type_index = game_type_index_map.get(state.game_type, 1)  # default to singles
        self.game_type_combo.setCurrentIndex(game_type_index)

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
        """Show or hide fields based on game type.

        Args:
            index: Index of selected game type (0=Doubles, 1=Singles, 2=Highlights)
        """
        is_doubles = (index == 0)
        is_highlights = (index == 2)

        # Show/hide Player 2 fields (visible only for doubles)
        self.team1_player2_label.setVisible(is_doubles)
        self.team1_player2_edit.setVisible(is_doubles)
        self.team2_player2_label.setVisible(is_doubles)
        self.team2_player2_edit.setVisible(is_doubles)

        # For highlights mode, hide victory rules and all player fields
        self.victory_label.setVisible(not is_highlights)
        self.victory_combo.setVisible(not is_highlights)
        self.team1_group.setVisible(not is_highlights)
        self.team2_group.setVisible(not is_highlights)

        # Find the victory container and hide it too
        # Victory container is the second child of config_layout
        if hasattr(self, '_victory_container'):
            self._victory_container.setVisible(not is_highlights)

        # Auto-process is incompatible with highlights (no scoring to simulate).
        # Disable the radio when highlights is selected and force back to manual;
        # re-enable it when switching away (leave user's prior choice intact).
        self.mode_auto_radio.setEnabled(not is_highlights)
        if is_highlights and self.mode_auto_radio.isChecked():
            self.mode_manual_radio.setChecked(True)

        # Revalidate after visibility change
        self._validate()

    def _validate(self) -> bool:
        """Validate all fields and update UI state.

        Player names are optional and can be added anytime during editing.
        In auto-process mode, court corner calibration is additionally required.

        Returns:
            True if all validation passes, False otherwise
        """
        is_valid = True

        # Validate video path (required for all game types).
        # Show the error label only when a non-empty path cannot be resolved —
        # an empty field is simply incomplete, not an erroneous entry.
        video_path = self.video_path_edit.text().strip()
        if not video_path:
            self.video_path_edit.setProperty("invalid", "false")
            self._video_error_label.setVisible(False)
            is_valid = False
        elif not Path(video_path).exists():
            self.video_path_edit.setProperty("invalid", "true")
            self._video_error_label.setVisible(True)
            is_valid = False
        else:
            self.video_path_edit.setProperty("invalid", "false")
            self._video_error_label.setVisible(False)

        # Player names are now optional - no validation required
        # Clear any invalid states on player fields
        self.team1_player1_edit.setProperty("invalid", "false")
        self.team1_player2_edit.setProperty("invalid", "false")
        self.team2_player1_edit.setProperty("invalid", "false")
        self.team2_player2_edit.setProperty("invalid", "false")

        # In auto-process mode, court corners are required
        auto_mode_active = self.mode_auto_radio.isChecked()
        if auto_mode_active and self._court_corners is None:
            is_valid = False

        # Update Start Editing button state
        self.start_button.setEnabled(is_valid)

        # Force style refresh for video path field
        self._refresh_style(self.video_path_edit)

        return is_valid

    def _refresh_style(self, widget: QWidget) -> None:
        """Force style refresh on a widget.

        Args:
            widget: Widget to refresh
        """
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    @pyqtSlot()
    def _on_start_editing(self) -> None:
        """Handle Start Editing / Auto-process button click or auto-start from session resume."""
        auto_mode_active = self.mode_auto_radio.isChecked()

        # Skip validation when resuming a session - the session data is authoritative
        if self._session_state is None:
            if not self._validate():
                return

        # Auto-process mode: additional pre-flight checks
        if auto_mode_active:
            # Corners must be calibrated
            if self._court_corners is None:
                self.auto_mode_warning_label.setVisible(True)
                QMessageBox.warning(
                    self,
                    "Calibration Required",
                    "Auto-process mode requires court corner calibration.\n\n"
                    "Please click 'Calibrate Court Corners' and mark the four "
                    "corners of the court before continuing.",
                )
                return

            # Trained model checkpoint must exist
            checkpoint_path = self._default_winner_checkpoint()
            if not checkpoint_path.exists():
                QMessageBox.warning(
                    self,
                    "Model Not Found",
                    "Auto-process requires a trained model. "
                    "Please run 'python -m ml train-winner' first.",
                )
                return

        # Collect configuration
        game_type_index = self.game_type_combo.currentIndex()
        if game_type_index == 0:
            game_type = "doubles"
        elif game_type_index == 1:
            game_type = "singles"
        else:
            game_type = "highlights"

        # Map victory combo index to rule string (not used for highlights)
        victory_map = {
            0: "11",  # Game to 11
            1: "9",   # Game to 9
            2: "timed"
        }
        # For highlights, use empty string as victory rule doesn't apply
        victory_rule = "" if game_type == "highlights" else victory_map[self.victory_combo.currentIndex()]

        # Collect player names based on source
        if game_type == "highlights":
            # Highlights mode: no player names
            team1_players = []
            team2_players = []
        elif self._session_state is not None:
            # Resuming session: use session player names, filtering empty strings
            team1_players = [n for n in self._session_state.player_names.get("team1", []) if n]
            team2_players = [n for n in self._session_state.player_names.get("team2", []) if n]
        else:
            # New session: collect from form fields, filtering empty strings
            team1_inputs = [self.team1_player1_edit.text().strip()]
            team2_inputs = [self.team2_player1_edit.text().strip()]

            if game_type == "doubles":
                team1_inputs.append(self.team1_player2_edit.text().strip())
                team2_inputs.append(self.team2_player2_edit.text().strip())

            # Filter empty strings to prevent [""] propagation
            team1_players = [n for n in team1_inputs if n]
            team2_players = [n for n in team2_inputs if n]

        # Create configuration
        self._config = GameConfig(
            video_path=Path(self.video_path_edit.text().strip()),
            game_type=game_type,
            victory_rule=victory_rule,
            team1_players=team1_players,
            team2_players=team2_players,
            session_state=self._session_state,  # Include loaded session state
            court_corners=self._court_corners,
            auto_mode=auto_mode_active,
        )

        # Accept the dialog
        self.accept()

    def get_config(self) -> GameConfig | None:
        """Get configuration if dialog was accepted, None if cancelled.

        Returns:
            GameConfig if dialog was accepted, None otherwise
        """
        return self._config

    def get_app_settings(self) -> AppSettings:
        """Get the current application settings.

        Returns:
            Current application settings instance
        """
        return self._app_settings

    @pyqtSlot()
    def _on_settings_clicked(self) -> None:
        """Open the configuration dialog.

        When the user applies changes, the settings are saved and
        the internal app_settings instance is updated.
        """
        dialog = ConfigDialog(self._app_settings, self)
        if dialog.exec():
            result = dialog.get_result()
            if result is not None:
                self._app_settings = result.settings
                self._app_settings.save()

    @pyqtSlot(str)
    def _update_calibrate_button_state(self, text: str) -> None:
        """Enable the calibrate button only when a valid video path is set.

        Args:
            text: Current text in the video path field.
        """
        video_path = Path(text.strip())
        self.calibrate_button.setEnabled(video_path.exists() and video_path.is_file())

    @pyqtSlot(bool)
    def _on_mode_changed(self, _checked: bool) -> None:
        """React to a mode radio button toggle.

        Updates the Start button label, shows/hides the auto-mode warning, and
        re-runs validation so the Start button enable state is correct.
        """
        auto_mode_active = self.mode_auto_radio.isChecked()

        if auto_mode_active:
            self.start_button.setText("Auto-process")
            # Show warning if corners not yet set; hide once they are
            corners_missing = self._court_corners is None
            self.auto_mode_warning_label.setVisible(corners_missing)
        else:
            self.start_button.setText("Start Editing")
            self.auto_mode_warning_label.setVisible(False)

        self._validate()

    @staticmethod
    def _default_winner_checkpoint() -> Path:
        """Return the absolute path of the default WinnerClassifier checkpoint.

        The path is computed relative to this source file so it works regardless
        of the current working directory.  setup_dialog.py lives at
        src/ui/setup_dialog.py; the checkpoint is at ml/checkpoints/best_winner.pt.
        """
        project_root = Path(__file__).parent.parent.parent
        return project_root / "ml" / "checkpoints" / "best_winner.pt"

    def _extract_calibration_frame_pixmap(
        self, video_path: Path, offset_s: float
    ) -> QPixmap | None:
        """Thin shim over :func:`~src.video.frame_extract.extract_frame_at`.

        Delegates to the module-level helper so any existing callers continue
        to work.  Error dialogs are anchored to *self* via ``parent_widget``.

        Args:
            video_path: Absolute path to the source video file.
            offset_s: Seek position in seconds (must be >= 0).

        Returns:
            A valid QPixmap on success, or None on any failure.
        """
        return extract_frame_at(video_path, offset_s, parent_widget=self)

    @pyqtSlot()
    def _open_calibrator(self, frame_pixmap: QPixmap | None = None) -> None:
        """Open the court calibration dialog, optionally with a pre-supplied frame.

        When *frame_pixmap* is None (the default — including the no-arg call from
        the calibrate button's ``clicked`` signal), the method probes the selected
        video for its duration, then calls
        :meth:`_extract_calibration_frame_pixmap` to extract the frame at the
        5 % mark via ffmpeg.  When a QPixmap is passed in explicitly the
        extraction step is skipped and that pixmap is used directly.

        In both cases the frame is shown inside :class:`CourtCalibratorWidget`
        in a modal QDialog.  On success the corners are stored in
        ``self._court_corners`` and the status label is updated.
        """
        if frame_pixmap is None:
            video_path_str = self.video_path_edit.text().strip()
            video_path = Path(video_path_str)

            if not video_path.exists():
                QMessageBox.warning(
                    self,
                    "No Video Selected",
                    "Please select a video file before calibrating court corners.",
                )
                return

            # Get video duration via ffprobe
            try:
                info = probe_video(video_path)
                duration = info.duration
            except ProbeError as exc:
                QMessageBox.critical(
                    self,
                    "ffprobe Error",
                    f"Could not read video metadata:\n{exc}",
                )
                return

            if duration <= 0:
                QMessageBox.warning(
                    self,
                    "Invalid Duration",
                    "The video reports a zero or negative duration.  "
                    "Cannot extract a frame for calibration.",
                )
                return

            selector = FrameSelectorDialog(
                video_path=video_path,
                video_duration_s=duration,
                initial_offset_s=duration * 0.05,
                parent=self,
            )
            if selector.exec() != QDialog.DialogCode.Accepted:
                return  # user cancelled — abort calibration entirely
            frame_pixmap = selector.get_result()
            if frame_pixmap is None:
                QMessageBox.warning(
                    self,
                    "No Frame Selected",
                    "No frame was selected for calibration.",
                )
                return

        # Build modal dialog containing the calibrator widget.
        # Size proportionally to the screen so court corners are clearly visible
        # on both 1080p and 4K/ultrawide displays.
        calibrator_dialog = QDialog(self)
        calibrator_dialog.setWindowTitle("Calibrate Court Corners")
        calibrator_dialog.setModal(True)
        fit_to_screen(calibrator_dialog, 0.50, 0.70, 700, 520, 1400, 1000)

        dialog_layout = QVBoxLayout(calibrator_dialog)
        dialog_layout.setContentsMargins(0, 0, 0, 0)

        calibrator = CourtCalibratorWidget(frame_pixmap, calibrator_dialog)
        dialog_layout.addWidget(calibrator)

        # Connect signal: on confirmation close dialog and store corners
        calibrator.cornersCaptured.connect(
            lambda corners: self._on_corners_captured(corners, calibrator_dialog)
        )

        calibrator_dialog.exec()

    def _on_corners_captured(
        self,
        corners: list[tuple[int, int]],
        dialog: QDialog,
    ) -> None:
        """Store captured court corners and update the status label.

        Args:
            corners: List of 4 (x, y) tuples in original-image pixel coordinates.
            dialog: The calibration dialog to close after storing the result.
        """
        # Convert tuples to lists for JSON-serialisation compatibility
        self._court_corners = [[x, y] for x, y in corners]

        # Update status label to calibrated appearance
        self.calibrate_status_label.setObjectName("calibrate-status-calibrated")
        self.calibrate_status_label.setText("4 corners set")
        self._refresh_style(self.calibrate_status_label)

        # In auto mode, hide the "calibration required" warning now that it is done
        if self.mode_auto_radio.isChecked():
            self.auto_mode_warning_label.setVisible(False)

        # Re-run validation — auto mode start button can now be enabled
        self._validate()

        dialog.accept()
