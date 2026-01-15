"""MainWindow for the Pickleball Video Editor - primary editing interface.

This module provides the main editing interface where users mark rallies,
track scores, and control video playback. The window integrates:
- VideoWidget for embedded MPV playback
- StatusOverlay showing rally state and score
- Rally control buttons (Start, Server Wins, Receiver Wins, Undo)
- Playback controls with speed adjustment
- Toolbar with intervention and session management buttons

The window follows a vertical layout as specified in UI_SPEC.md Section 4:
1. Video player area with status overlay
2. Playback controls (transport + speed + timecode)
3. Rally controls panel (primary action buttons)
4. Toolbar (intervention and session management)

State Management:
- WAITING: No rally in progress
  - Rally Start button is active (green glow)
  - Server/Receiver Wins buttons are disabled
- IN_RALLY: Rally in progress
  - Server/Receiver Wins buttons are active (blue/orange glow)
  - Rally Start button is disabled

All actions trigger score state updates and rally manager tracking.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.models import ScoreSnapshot, SessionState
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState
from src.core.session_manager import SessionManager
from src.ui.dialogs import (
    AddCommentDialog,
    AddCommentResult,
    EditScoreDialog,
    EditScoreResult,
    ForceSideOutDialog,
    ForceSideOutResult,
    GameOverDialog,
    GameOverResult,
    UnsavedWarningDialog,
    UnsavedWarningResult,
)
from src.ui.setup_dialog import GameConfig
from src.ui.styles import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BORDER_COLOR,
    RADIUS_LG,
    SPACE_LG,
    SPACE_MD,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    Fonts,
)
from src.ui.widgets import (
    BUTTON_TYPE_RALLY_START,
    BUTTON_TYPE_RECEIVER_WINS,
    BUTTON_TYPE_SERVER_WINS,
    BUTTON_TYPE_UNDO,
    PlaybackControls,
    RallyButton,
    StatusOverlay,
    ToastManager,
)
from src.video.player import VideoWidget
from src.video.probe import probe_video, ProbeError


__all__ = ["MainWindow"]


class MainWindow(QMainWindow):
    """Primary editing interface with rally marking controls.

    This is the main window where users spend most of their time marking rallies,
    tracking scores, and editing video. It provides real-time feedback through
    the status overlay and toast notifications.

    Signals:
        session_saved: Emitted when the session is saved
        review_requested: Emitted when user clicks Final Review button
        quit_requested: Emitted when user wants to quit

    Example:
        ```python
        # Create configuration from setup dialog
        config = GameConfig(
            video_path=Path("match.mp4"),
            game_type="doubles",
            victory_rule="11",
            team1_players=["Alice", "Bob"],
            team2_players=["Carol", "Dave"]
        )

        # Create and show main window
        window = MainWindow(config)
        window.show()
        ```
    """

    # Signals
    session_saved = pyqtSignal()
    review_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(
        self,
        config: GameConfig,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize main window with game configuration.

        Args:
            config: Game configuration from SetupDialog (may include session_state for resuming)
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.config = config

        # Session manager for saving/loading
        self._session_manager = SessionManager()

        # Dirty state tracking
        self._dirty = False

        # Position to restore after video loads (for session resumption)
        self._restore_position: float | None = None

        # Initialize core components (may restore from session)
        self._init_core_components()

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Load video
        self._load_video()

        # Initial state update
        self._update_display()

    def _init_core_components(self) -> None:
        """Initialize ScoreState and RallyManager.

        Creates the core business logic components that manage scoring
        and rally tracking throughout the editing session. If a session_state
        is provided in the config, restores from that state.
        """
        # Check if we're restoring from a session
        session_state = self.config.session_state

        if session_state is not None:
            # Restore from session
            # Create player names dict for ScoreState
            player_names = session_state.player_names

            # Initialize score state machine
            self.score_state = ScoreState(
                game_type=session_state.game_type,
                victory_rules=session_state.victory_rules,
                player_names=player_names
            )

            # Restore score state from session
            score_snapshot_dict = {
                "score": session_state.current_score,
                "serving_team": session_state.serving_team,
                "server_number": session_state.server_number
            }
            score_snapshot = ScoreSnapshot.from_dict(score_snapshot_dict)
            self.score_state.restore_snapshot(score_snapshot)

            # Initialize rally manager with session rallies (fps will be updated after video probe)
            self.rally_manager = RallyManager(fps=60.0)

            # Restore rally manager state
            rally_manager_dict = {
                "rallies": [r.to_dict() for r in session_state.rallies],
                "undo_stack": [],  # Start with empty undo stack
                "fps": 60.0  # Will be updated after probe
            }
            self.rally_manager = RallyManager.from_dict(rally_manager_dict)

            # Store position to restore after video loads
            self._restore_position = session_state.last_position
        else:
            # New session - initialize from scratch
            # Create player names dict for ScoreState
            player_names = {
                "team1": self.config.team1_players,
                "team2": self.config.team2_players,
            }

            # Initialize score state machine
            self.score_state = ScoreState(
                game_type=self.config.game_type,
                victory_rules=self.config.victory_rule,
                player_names=player_names
            )

            # Initialize rally manager (fps will be updated after video probe)
            self.rally_manager = RallyManager(fps=60.0)

            self._restore_position = None

        # Track video info (set after probing)
        self.video_fps = 60.0
        self.video_duration = 0.0

    def _setup_ui(self) -> None:
        """Create the main window layout.

        Builds the complete UI hierarchy following the vertical layout
        specified in UI_SPEC.md Section 4.
        """
        # Window properties
        self.setWindowTitle(f"Pickleball Video Editor - {self.config.video_path.name}")
        self.setMinimumSize(1024, 768)
        self.resize(1280, 900)

        # Central widget with main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(SPACE_MD)
        main_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)

        # Video area (player + overlay)
        video_area = self._create_video_area()
        main_layout.addWidget(video_area, stretch=1)

        # Playback controls
        self.playback_controls = PlaybackControls()
        main_layout.addWidget(self.playback_controls)

        # Rally controls panel
        rally_controls = self._create_rally_controls()
        main_layout.addWidget(rally_controls)

        # Toolbar (intervention + session buttons)
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Apply global stylesheet
        self._apply_styles()

    def _create_video_area(self) -> QWidget:
        """Create video player with status overlay.

        Returns:
            Container widget with video player and overlay
        """
        container = QWidget()
        container.setObjectName("video_container")

        # Use absolute positioning for overlay on top of video
        # VideoWidget will be the background, StatusOverlay floats on top
        self.video_widget = VideoWidget(container)
        self.video_widget.setGeometry(0, 0, 800, 600)  # Will resize with container

        # Status overlay positioned at top of video
        self.status_overlay = StatusOverlay(container)
        self.status_overlay.move(SPACE_MD, SPACE_MD)
        self.status_overlay.raise_()  # Ensure overlay is on top

        # Set minimum size for video container
        container.setMinimumSize(640, 480)

        return container

    def _create_rally_controls(self) -> QFrame:
        """Create rally control buttons panel.

        Returns:
            Frame containing rally action buttons and counter
        """
        panel = QFrame()
        panel.setObjectName("rally_panel")
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)

        # Section label
        label = QLabel("RALLY CONTROLS")
        label.setObjectName("section_label")
        label.setFont(Fonts.body(12, 600))
        layout.addWidget(label)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        # Create rally buttons
        self.btn_rally_start = RallyButton("RALLY START", BUTTON_TYPE_RALLY_START)
        self.btn_server_wins = RallyButton("SERVER WINS", BUTTON_TYPE_SERVER_WINS)
        self.btn_receiver_wins = RallyButton("RECEIVER WINS", BUTTON_TYPE_RECEIVER_WINS)
        self.btn_undo = RallyButton("UNDO", BUTTON_TYPE_UNDO)

        button_layout.addWidget(self.btn_rally_start)
        button_layout.addWidget(self.btn_server_wins)
        button_layout.addWidget(self.btn_receiver_wins)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_undo)

        layout.addLayout(button_layout)

        # Rally counter
        self.rally_counter_label = QLabel("Rally: 0")
        self.rally_counter_label.setObjectName("rally_counter")
        self.rally_counter_label.setFont(Fonts.body(14, 500))
        layout.addWidget(self.rally_counter_label)

        return panel

    def _create_toolbar(self) -> QFrame:
        """Create intervention and session buttons.

        Returns:
            Frame containing toolbar buttons
        """
        panel = QFrame()
        panel.setObjectName("toolbar_panel")
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(panel)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)

        # Intervention buttons (left side)
        self.btn_edit_score = QPushButton("Edit Score")
        self.btn_force_sideout = QPushButton("Force Side-Out")
        self.btn_add_comment = QPushButton("Add Comment")
        self.btn_time_expired = QPushButton("Time Expired*")

        # Set object names for styling
        for btn in [self.btn_edit_score, self.btn_force_sideout,
                    self.btn_add_comment, self.btn_time_expired]:
            btn.setObjectName("toolbar_button")
            btn.setFont(Fonts.button_other())

        # Time Expired only for timed games
        if self.config.victory_rule != "timed":
            self.btn_time_expired.setVisible(False)

        layout.addWidget(self.btn_edit_score)
        layout.addWidget(self.btn_force_sideout)
        layout.addWidget(self.btn_add_comment)
        layout.addWidget(self.btn_time_expired)

        layout.addStretch()

        # Session buttons (right side)
        self.btn_save_session = QPushButton("Save Session")
        self.btn_final_review = QPushButton("Final Review")

        for btn in [self.btn_save_session, self.btn_final_review]:
            btn.setObjectName("toolbar_button")
            btn.setFont(Fonts.button_other())

        layout.addWidget(self.btn_save_session)
        layout.addWidget(self.btn_final_review)

        return panel

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the window."""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG_PRIMARY};
            }}

            QWidget#video_container {{
                background-color: #000000;
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}

            QFrame#rally_panel,
            QFrame#toolbar_panel {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_LG}px;
            }}

            QLabel#section_label {{
                color: {TEXT_SECONDARY};
                letter-spacing: 0.5px;
            }}

            QLabel#rally_counter {{
                color: {TEXT_PRIMARY};
            }}

            QPushButton#toolbar_button {{
                background-color: {BG_SECONDARY};
                color: {TEXT_PRIMARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 8px 16px;
                min-width: 100px;
            }}

            QPushButton#toolbar_button:hover {{
                border-color: {TEXT_PRIMARY};
            }}

            QPushButton#toolbar_button:pressed {{
                background-color: {BG_BORDER};
            }}

            QPushButton#toolbar_button:disabled {{
                opacity: 0.4;
                color: {TEXT_SECONDARY};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to handler slots.

        Sets up all signal/slot connections for UI interactions and
        video playback synchronization.
        """
        # Rally control buttons
        self.btn_rally_start.clicked.connect(self.on_rally_start)
        self.btn_server_wins.clicked.connect(self.on_server_wins)
        self.btn_receiver_wins.clicked.connect(self.on_receiver_wins)
        self.btn_undo.clicked.connect(self.on_undo)

        # Playback controls
        self.playback_controls.skip_back_5s.connect(lambda: self.video_widget.seek(-5.0, absolute=False))
        self.playback_controls.skip_back_1s.connect(lambda: self.video_widget.seek(-1.0, absolute=False))
        self.playback_controls.play_pause.connect(self.video_widget.toggle_pause)
        self.playback_controls.skip_forward_1s.connect(lambda: self.video_widget.seek(1.0, absolute=False))
        self.playback_controls.skip_forward_5s.connect(lambda: self.video_widget.seek(5.0, absolute=False))
        self.playback_controls.speed_changed.connect(self.video_widget.set_speed)

        # Video player signals
        self.video_widget.position_changed.connect(self._on_video_position_changed)
        self.video_widget.duration_changed.connect(self._on_video_duration_changed)

        # Toolbar buttons
        self.btn_edit_score.clicked.connect(self._on_edit_score)
        self.btn_force_sideout.clicked.connect(self._on_force_sideout)
        self.btn_add_comment.clicked.connect(self._on_add_comment)
        self.btn_time_expired.clicked.connect(self._on_time_expired)
        self.btn_save_session.clicked.connect(self._on_save_session)
        self.btn_final_review.clicked.connect(self._on_final_review)

    def _load_video(self) -> None:
        """Load the video file and probe metadata.

        Probes the video using ffprobe to extract fps and duration,
        then loads it into the MPV player widget. If restoring a session,
        seeks to the last saved position.
        """
        video_path = self.config.video_path

        # Check file exists before probing
        if not video_path.exists():
            ToastManager.show_error(
                self,
                f"Video file not found: {video_path.name}",
                duration_ms=5000
            )
            return

        # Probe video for metadata (external tool - ProbeError on failure)
        try:
            video_info = probe_video(video_path)
        except ProbeError as e:
            ToastManager.show_error(
                self,
                f"Failed to probe video: {e}",
                duration_ms=5000
            )
            return

        self.video_fps = video_info.fps
        self.video_duration = video_info.duration

        # Update rally manager with correct fps
        self.rally_manager.fps = self.video_fps

        # Load video into player
        self.video_widget.load(str(video_path), fps=self.video_fps)

        # If restoring session, seek to last position
        if self._restore_position is not None:
            self.video_widget.seek(self._restore_position, absolute=True)
            ToastManager.show_success(
                self,
                f"Resumed session at {self._restore_position:.1f}s",
                duration_ms=3000
            )
        else:
            ToastManager.show_success(
                self,
                f"Loaded video: {video_path.name} ({video_info.resolution})",
                duration_ms=3000
            )

    # Rally marking handlers

    @pyqtSlot()
    def on_rally_start(self) -> None:
        """Handle Rally Start button click.

        Marks the beginning of a rally at the current video position.
        Captures a score snapshot for undo functionality.
        """
        # LBYL: Check if rally is already in progress
        if self.rally_manager.is_rally_in_progress():
            ToastManager.show_warning(self, "Rally already in progress", duration_ms=3000)
            return

        # Get current video position
        timestamp = self.video_widget.get_position()

        # Save score snapshot for undo
        score_snapshot = self.score_state.save_snapshot()

        # Mark rally start (precondition checked above)
        start_frame = self.rally_manager.start_rally(timestamp, score_snapshot)

        # Mark session as dirty
        self._dirty = True

        # Pause video for precise marking
        self.video_widget.pause()

        # Update UI state
        self._update_display()

        # Show feedback
        self.video_widget.show_osd("Rally started", duration=1.5)

    @pyqtSlot()
    def on_server_wins(self) -> None:
        """Handle Server Wins button click.

        Marks the end of the current rally with the server as winner.
        Updates the score state and creates a rally record.
        """
        # Check if rally is in progress
        if not self.rally_manager.is_rally_in_progress():
            ToastManager.show_warning(self, "No rally in progress", duration_ms=3000)
            return

        # Get current video position
        timestamp = self.video_widget.get_position()

        # Get score before rally ends
        score_at_start = self.score_state.get_score_string()

        # Update score state (server wins = server's team scores)
        self.score_state.server_wins()

        # Save snapshot after score update
        score_snapshot = self.score_state.save_snapshot()

        # End rally (precondition checked above)
        rally = self.rally_manager.end_rally(
            timestamp=timestamp,
            winner="server",
            score_at_start=score_at_start,
            score_snapshot=score_snapshot
        )

        # Mark session as dirty
        self._dirty = True

        # Pause video
        self.video_widget.pause()

        # Update UI state
        self._update_display()

        # Show feedback with new score
        new_score = self.score_state.get_score_string()
        self.video_widget.show_osd(f"Server wins: {new_score}", duration=2.0)

        # Check if game is over
        self._check_game_over()

    @pyqtSlot()
    def on_receiver_wins(self) -> None:
        """Handle Receiver Wins button click.

        Marks the end of the current rally with the receiver as winner.
        Updates the score state (side-out if needed) and creates a rally record.
        """
        # LBYL: Check if rally is in progress
        if not self.rally_manager.is_rally_in_progress():
            ToastManager.show_warning(self, "No rally in progress", duration_ms=3000)
            return

        # Get current video position
        timestamp = self.video_widget.get_position()

        # Get score before rally ends
        score_at_start = self.score_state.get_score_string()

        # Update score state (receiver wins = side-out, no score change)
        self.score_state.receiver_wins()

        # Save snapshot after score update
        score_snapshot = self.score_state.save_snapshot()

        # End rally (precondition checked above)
        rally = self.rally_manager.end_rally(
            timestamp=timestamp,
            winner="receiver",
            score_at_start=score_at_start,
            score_snapshot=score_snapshot
        )

        # Mark session as dirty
        self._dirty = True

        # Pause video
        self.video_widget.pause()

        # Update UI state
        self._update_display()

        # Show feedback
        new_score = self.score_state.get_score_string()
        self.video_widget.show_osd(f"Receiver wins: {new_score}", duration=2.0)

    @pyqtSlot()
    def on_undo(self) -> None:
        """Handle Undo button click.

        Undoes the last action (rally start or rally end) and restores
        the previous score state. Seeks video to the position where the
        action occurred.
        """
        # Check if undo is available
        if not self.rally_manager.can_undo():
            ToastManager.show_info(self, "Nothing to undo", duration_ms=2000)
            return

        # Undo the last action (precondition checked above)
        action, seek_position = self.rally_manager.undo()

        # Restore score state from snapshot
        self.score_state.restore_snapshot(action.score_before)

        # Seek video to where action occurred
        self.video_widget.seek(seek_position, absolute=True)
        self.video_widget.pause()

        # Update UI state
        self._update_display()

        # Show feedback
        action_name = action.action_type.value.replace("_", " ").title()
        self.video_widget.show_osd(f"Undone: {action_name}", duration=2.0)
        ToastManager.show_info(self, f"Undone: {action_name}", duration_ms=2000)

    # State management

    def _update_display(self) -> None:
        """Update all UI elements based on current state.

        Refreshes:
        - Status overlay (rally status, score, server info)
        - Button states (active/disabled based on rally state)
        - Rally counter
        """
        # Update status overlay
        in_rally = self.rally_manager.is_rally_in_progress()
        score_string = self.score_state.get_score_string()
        server_info = self.score_state.get_server_info()

        # Format server info for display
        team_name = f"Team {server_info.serving_team + 1}"
        server_text = f"{team_name} ({server_info.player_name})"
        if server_info.server_number is not None:
            server_text += f" #{server_info.server_number}"

        self.status_overlay.update_display(
            in_rally=in_rally,
            score=score_string,
            server_info=server_text
        )

        # Update button states
        self._update_button_states()

        # Update rally counter
        rally_count = self.rally_manager.get_rally_count()
        self.rally_counter_label.setText(f"Rally: {rally_count}")

    def _update_button_states(self) -> None:
        """Update rally button active/disabled states.

        Button logic:
        - WAITING (no rally): Rally Start active, Server/Receiver disabled
        - IN_RALLY: Server/Receiver active, Rally Start disabled
        - Undo: Always enabled if can_undo() is True
        """
        in_rally = self.rally_manager.is_rally_in_progress()
        can_undo = self.rally_manager.can_undo()

        if in_rally:
            # Rally in progress: Server/Receiver active
            self.btn_rally_start.setEnabled(False)
            self.btn_rally_start.set_active(False)

            self.btn_server_wins.setEnabled(True)
            self.btn_server_wins.set_active(True)

            self.btn_receiver_wins.setEnabled(True)
            self.btn_receiver_wins.set_active(True)
        else:
            # Waiting: Rally Start active
            self.btn_rally_start.setEnabled(True)
            self.btn_rally_start.set_active(True)

            self.btn_server_wins.setEnabled(False)
            self.btn_server_wins.set_active(False)

            self.btn_receiver_wins.setEnabled(False)
            self.btn_receiver_wins.set_active(False)

        # Undo button
        self.btn_undo.setEnabled(can_undo)

    def _check_game_over(self) -> None:
        """Check if game is over and show dialog if needed.

        For standard games (11 or 9), checks win conditions and shows GameOverDialog.
        For timed games, the user must manually trigger via Time Expired button.
        """
        is_over, winner_team = self.score_state.is_game_over()

        if is_over:
            final_score = self.score_state.get_score_string()
            rally_count = self.rally_manager.get_rally_count()
            is_timed = self.config.victory_rule == "timed"

            dialog = GameOverDialog(winner_team, final_score, rally_count, is_timed, self)
            dialog.exec()
            result = dialog.get_result()

            if result == GameOverResult.FINISH_GAME:
                # Transition to review mode
                self.review_requested.emit()
            # else CONTINUE_EDITING - just close dialog and continue

    # Video player handlers

    @pyqtSlot(float)
    def _on_video_position_changed(self, position: float) -> None:
        """Handle video position changes.

        Updates the playback controls timecode display.

        Args:
            position: Current position in seconds
        """
        self.playback_controls.set_time(position, self.video_duration)

    @pyqtSlot(float)
    def _on_video_duration_changed(self, duration: float) -> None:
        """Handle video duration updates.

        Args:
            duration: Video duration in seconds
        """
        self.video_duration = duration

    # Toolbar button handlers (stubs for future implementation)

    @pyqtSlot()
    def _on_edit_score(self) -> None:
        """Handle Edit Score button click.

        Opens the EditScoreDialog to manually correct score errors.
        """
        current_score = self.score_state.get_score_string()
        is_doubles = self.config.game_type == "doubles"

        dialog = EditScoreDialog(current_score, is_doubles, self)
        if dialog.exec():
            result = dialog.get_result()
            if result is not None:
                # Parse and apply the new score
                self.score_state.set_score(result.new_score)
                self._dirty = True
                self._update_display()
                ToastManager.show_success(
                    self,
                    f"Score updated: {result.new_score}",
                    duration_ms=3000
                )

    @pyqtSlot()
    def _on_force_sideout(self) -> None:
        """Handle Force Side-Out button click.

        Opens the ForceSideOutDialog to force a side-out (for error correction).
        """
        # Get current server info
        server_info = self.score_state.get_server_info()
        current_server = f"Team {server_info.serving_team + 1} ({server_info.player_name})"
        if server_info.server_number is not None:
            current_server += f" - Server {server_info.server_number}"

        # Compute what "after" will look like
        next_team = 1 - server_info.serving_team
        next_player_names = self.config.team1_players if next_team == 0 else self.config.team2_players
        next_player = next_player_names[0] if next_player_names else "Unknown"
        next_server = f"Team {next_team + 1} ({next_player})"
        if self.config.game_type == "doubles":
            next_server += " - Server 1"

        current_score = self.score_state.get_score_string()
        is_doubles = self.config.game_type == "doubles"

        dialog = ForceSideOutDialog(current_server, next_server, current_score, is_doubles, self)
        if dialog.exec():
            result = dialog.get_result()
            if result is not None:
                # Apply new score if provided
                if result.new_score:
                    self.score_state.set_score(result.new_score)
                # Force side-out
                self.score_state.force_side_out()
                self._dirty = True
                self._update_display()
                ToastManager.show_warning(
                    self,
                    "Side-out forced",
                    duration_ms=3000
                )

    @pyqtSlot()
    def _on_add_comment(self) -> None:
        """Handle Add Comment button click.

        Opens the AddCommentDialog to add notes at current timestamp.
        """
        timestamp = self.video_widget.get_position()

        dialog = AddCommentDialog(timestamp, self)
        if dialog.exec():
            result = dialog.get_result()
            if result is not None:
                # Store the comment (for now, just show feedback)
                # TODO: Store in session/rally manager when persistence is implemented
                self._dirty = True
                ToastManager.show_success(
                    self,
                    f"Comment added at {result.timestamp:.2f}s",
                    duration_ms=3000
                )

    @pyqtSlot()
    def _on_time_expired(self) -> None:
        """Handle Time Expired button click.

        For timed games, manually marks the end of the game and
        determines the winner based on current score.
        """
        if self.config.victory_rule != "timed":
            return

        # Determine winner based on current score
        score = self.score_state.score
        if score[0] > score[1]:
            winner_team = 0
        elif score[1] > score[0]:
            winner_team = 1
        else:
            # Tie - show warning
            ToastManager.show_warning(
                self,
                "Game tied - cannot determine winner",
                duration_ms=4000
            )
            return

        # Show game over notification
        winner_name = f"Team {winner_team + 1}"
        final_score = self.score_state.get_score_string()

        ToastManager.show_success(
            self,
            f"Time Expired! {winner_name} wins: {final_score}",
            duration_ms=6000
        )

        self.video_widget.show_osd(f"Time Expired! {winner_name} wins", duration=5.0)

    def _build_session_state(self) -> SessionState:
        """Build SessionState from current state.

        Collects all current state information into a SessionState object
        for persistence.

        Returns:
            SessionState containing complete session information
        """
        # Get current score snapshot
        score_snapshot = self.score_state.save_snapshot()

        # Build player names dict
        player_names = {
            "team1": self.config.team1_players,
            "team2": self.config.team2_players,
        }

        # Get current video position
        last_position = self.video_widget.get_position()

        # Create session state
        session_state = SessionState(
            version="1.0",
            video_path=str(self.config.video_path),
            video_hash="",  # Will be set by SessionManager.save()
            game_type=self.config.game_type,
            victory_rules=self.config.victory_rule,
            player_names=player_names,
            rallies=self.rally_manager.get_rallies(),
            current_score=list(score_snapshot.score),
            serving_team=score_snapshot.serving_team,
            server_number=score_snapshot.server_number,
            last_position=last_position,
            created_at="",  # Will be set by SessionManager.save() if new
            modified_at="",  # Will be set by SessionManager.save()
            interventions=[],  # TODO: Implement interventions tracking
            comments=[],  # TODO: Implement comments tracking
        )

        return session_state

    @pyqtSlot()
    def _on_save_session(self) -> None:
        """Handle Save Session button click.

        Saves current session state to JSON file and clears dirty flag.
        """
        # Build session state from current state
        session_state = self._build_session_state()

        # Save to disk
        saved_path = self._session_manager.save(session_state, str(self.config.video_path))

        if saved_path is not None:
            # Clear dirty flag
            self._dirty = False

            # Show success feedback
            ToastManager.show_success(
                self,
                "Session saved successfully",
                duration_ms=3000
            )
            self.session_saved.emit()
        else:
            # Save failed
            ToastManager.show_error(
                self,
                "Failed to save session",
                duration_ms=3000
            )

    @pyqtSlot()
    def _on_final_review(self) -> None:
        """Handle Final Review button click.

        Switches to the final review mode where users can adjust
        rally timings and generate output files.
        """
        # Check if there are rallies to review
        if self.rally_manager.get_rally_count() == 0:
            ToastManager.show_warning(
                self,
                "No rallies to review. Mark at least one rally first.",
                duration_ms=3000
            )
            return

        # Emit signal to switch to review mode
        self.review_requested.emit()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.

        Checks for unsaved changes and prompts user before closing.

        Args:
            event: Close event from Qt
        """
        # Check if there are unsaved changes
        if self._dirty:
            # Show unsaved warning dialog
            dialog = UnsavedWarningDialog(self)
            dialog.exec()
            result = dialog.get_result()

            if result == UnsavedWarningResult.SAVE_AND_QUIT:
                # Save session before closing
                session_state = self._build_session_state()
                saved_path = self._session_manager.save(session_state, str(self.config.video_path))

                if saved_path is None:
                    # Save failed - show error and cancel close
                    ToastManager.show_error(
                        self,
                        "Failed to save session",
                        duration_ms=3000
                    )
                    event.ignore()
                    return

                # Save succeeded - continue with close
                self._dirty = False

            elif result == UnsavedWarningResult.CANCEL:
                # User cancelled - don't close
                event.ignore()
                return

            # DONT_SAVE - continue with close without saving

        # Clean up video player
        self.video_widget.cleanup()

        # Emit quit signal
        self.quit_requested.emit()

        super().closeEvent(event)
