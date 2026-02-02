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

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QResizeEvent, QShowEvent, QShortcut
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.app_config import AppSettings
from src.core.models import GameCompletionInfo, ScoreSnapshot, SessionState
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState
from src.core.session_manager import SessionManager
from src.output import KdenliveGenerator, FFmpegExporter
from src.ui.dialogs import (
    AddCommentDialog,
    AddCommentResult,
    EditScoreDialog,
    EditScoreResult,
    ExportCompleteDialog,
    ExportCompleteResult,
    ExportProgressDialog,
    ForceSideOutDialog,
    ForceSideOutResult,
    GameOverDialog,
    GameOverResult,
    NewGameConfirmDialog,
    NewGameResult,
    PlayerNamesDialog,
    UnsavedWarningDialog,
    UnsavedWarningResult,
)
from src.ui.review_mode import ReviewModeWidget
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
    ClipTimelineWidget,
    PlaybackControls,
    RallyButton,
    StatusOverlay,
    ToastManager,
)
from src.video.player import VideoWidget
from src.video.probe import probe_video, ProbeError


__all__ = ["MainWindow"]


class _VideoContainer(QWidget):
    """Container widget that manages VideoWidget and StatusOverlay layout.

    This container uses absolute positioning with proper resize handling
    to ensure the video widget fills the container while the status overlay
    remains positioned at the top-left corner.
    """

    def __init__(
        self,
        video_widget: "VideoWidget",
        status_overlay: "StatusOverlay",
        parent: QWidget | None = None
    ) -> None:
        """Initialize the video container.

        Args:
            video_widget: The VideoWidget to embed
            status_overlay: The StatusOverlay to position on top
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.setObjectName("video_container")

        # CRITICAL: Make this container a native window so MPV's X11 window
        # can be properly reparented when moving between editing/review modes.
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)

        # Store references and reparent widgets
        self._video_widget = video_widget
        self._status_overlay = status_overlay
        video_widget.setParent(self)
        status_overlay.setParent(self)

        # Ensure overlay is on top
        status_overlay.raise_()

        # Set minimum size for 16:9 video (user requirement: 870x490)
        self.setMinimumSize(870, 490)

        # Force native window creation
        self.winId()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize events to keep video widget filling the container.

        Args:
            event: Resize event from Qt
        """
        super().resizeEvent(event)

        # Video widget fills the entire container
        self._video_widget.setGeometry(0, 0, self.width(), self.height())

        # Status overlay stays at top-left with padding
        self._status_overlay.move(SPACE_MD, SPACE_MD)


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
    return_to_menu_requested = pyqtSignal()

    def __init__(
        self,
        config: GameConfig,
        app_settings: AppSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize main window with game configuration.

        Args:
            config: Game configuration from SetupDialog (may include session_state for resuming)
            app_settings: Application settings for shortcuts and window sizes
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.config = config
        self._app_settings = app_settings or AppSettings()

        # Track if we're in highlights mode (no scores, just cuts)
        self._is_highlights_mode = config.game_type == "highlights"

        # Session manager for saving/loading
        self._session_manager = SessionManager()

        # Dirty state tracking
        self._dirty = False

        # Position to restore after video loads (for session resumption)
        self._restore_position: float | None = None

        # Review mode state
        self._review_widget: ReviewModeWidget | None = None
        self._in_review_mode = False
        self._rally_playback_timer: QTimer | None = None

        # Video container reparenting state (for review mode)
        self._video_container_original_parent: QWidget | None = None
        self._video_container_original_index: int = 0

        # Flag to track if video has been loaded (deferred until showEvent)
        self._video_loaded = False

        # Compact mode state
        self._compact_mode = False

        # Active export dialog tracking (for non-blocking FFmpeg export)
        self._active_export_dialog: ExportProgressDialog | None = None

        # Initialize core components (may restore from session)
        self._init_core_components()

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Setup keyboard shortcuts (using QShortcut for window-level shortcuts)
        self._setup_shortcuts()

        # NOTE: Video loading is deferred to showEvent() to ensure
        # the widget has a valid native window ID for MPV embedding.

        # Initial state update
        self._update_display()

    def _init_core_components(self) -> None:
        """Initialize ScoreState and RallyManager.

        Creates the core business logic components that manage scoring
        and rally tracking throughout the editing session. If a session_state
        is provided in the config, restores from that state.

        For highlights mode, score_state is set to None as scoring is not tracked.
        """
        # Check if we're restoring from a session
        session_state = self.config.session_state

        if self._is_highlights_mode:
            # Highlights mode - no score tracking
            self.score_state = None

            if session_state is not None:
                # Restore rally manager from session
                rally_manager_dict = {
                    "rallies": [r.to_dict() for r in session_state.rallies],
                    "undo_stack": [],
                    "fps": 60.0
                }
                self.rally_manager = RallyManager.from_dict(rally_manager_dict)
                self._restore_position = session_state.last_position
            else:
                self.rally_manager = RallyManager(fps=60.0)
                self._restore_position = None

        elif session_state is not None:
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
        # Apply window size from config
        ws = self._app_settings.window_size
        self.setMinimumSize(ws.min_width, ws.min_height)
        if ws.max_width > 0 and ws.max_height > 0:
            self.setMaximumSize(ws.max_width, ws.max_height)
        self.resize(1600, 1100)

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
        self.rally_controls_panel = self._create_rally_controls()
        main_layout.addWidget(self.rally_controls_panel)

        # Toolbar (intervention + session buttons)
        self.toolbar_panel = self._create_toolbar()
        main_layout.addWidget(self.toolbar_panel)

        # Apply global stylesheet
        self._apply_styles()

    def _create_video_area(self) -> QWidget:
        """Create video player with status overlay.

        Returns:
            Container widget with video player and overlay
        """
        # Create video widget and status overlay
        self.video_widget = VideoWidget()
        self.status_overlay = StatusOverlay()

        # Use custom container that handles resize events
        # Store as instance variable for reparenting in review mode
        self._video_container = _VideoContainer(self.video_widget, self.status_overlay)

        return self._video_container

    def _create_rally_controls(self) -> QFrame:
        """Create rally control buttons panel.

        Returns:
            Frame containing rally action buttons and counter

        For highlights mode, shows simplified UI with just MARK START / MARK END buttons.
        """
        panel = QFrame()
        panel.setObjectName("rally_panel")
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)

        # Section label
        if self._is_highlights_mode:
            label = QLabel("HIGHLIGHT CONTROLS")
        else:
            label = QLabel("RALLY CONTROLS")
        label.setObjectName("section_label")
        label.setFont(Fonts.body(12, 600))
        layout.addWidget(label)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        if self._is_highlights_mode:
            # Highlights mode: just MARK START and MARK END
            self.btn_rally_start = RallyButton("MARK START", BUTTON_TYPE_RALLY_START)
            self.btn_mark_end = RallyButton("MARK END", BUTTON_TYPE_SERVER_WINS)
            self.btn_undo = RallyButton("UNDO", BUTTON_TYPE_UNDO)

            # Set btn_server_wins and btn_receiver_wins to None so we don't access them
            self.btn_server_wins = None
            self.btn_receiver_wins = None

            # Prevent buttons from taking focus
            for btn in [self.btn_rally_start, self.btn_mark_end, self.btn_undo]:
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            button_layout.addWidget(self.btn_rally_start)
            button_layout.addWidget(self.btn_mark_end)
            button_layout.addStretch()
            button_layout.addWidget(self.btn_undo)
        else:
            # Normal mode: RALLY START, SERVER WINS, RECEIVER WINS
            self.btn_rally_start = RallyButton("RALLY START", BUTTON_TYPE_RALLY_START)
            self.btn_server_wins = RallyButton("SERVER WINS", BUTTON_TYPE_SERVER_WINS)
            self.btn_receiver_wins = RallyButton("RECEIVER WINS", BUTTON_TYPE_RECEIVER_WINS)
            self.btn_undo = RallyButton("UNDO", BUTTON_TYPE_UNDO)
            self.btn_mark_end = None  # Not used in normal mode

            # Prevent buttons from taking focus (keyboard shortcuts handled by MainWindow)
            for btn in [self.btn_rally_start, self.btn_server_wins,
                        self.btn_receiver_wins, self.btn_undo]:
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            button_layout.addWidget(self.btn_rally_start)
            button_layout.addWidget(self.btn_server_wins)
            button_layout.addWidget(self.btn_receiver_wins)
            button_layout.addStretch()
            button_layout.addWidget(self.btn_undo)

        layout.addLayout(button_layout)

        # Visual clip timeline for ALL match types
        self.clip_timeline = ClipTimelineWidget()
        self.clip_timeline.clip_clicked.connect(self._on_clip_clicked)
        self.clip_timeline.clip_play_requested.connect(self._on_clip_play_requested)
        layout.addWidget(self.clip_timeline)

        return panel

    def _create_toolbar(self) -> QFrame:
        """Create intervention and session buttons.

        Returns:
            Frame containing toolbar buttons

        For highlights mode, hides score-related buttons (Edit Score, Force Side-Out, Time Expired,
        Player Names, New Game).
        """
        panel = QFrame()
        panel.setObjectName("toolbar_panel")
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(panel)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)

        # Intervention buttons (left side) - not all shown in highlights mode
        self.btn_edit_score = QPushButton("Edit Score")
        self.btn_force_sideout = QPushButton("Force Side-Out")
        self.btn_add_comment = QPushButton("Add Comment")
        self.btn_time_expired = QPushButton("Time Expired*")

        # NEW: Player Names button
        self.btn_update_names = QPushButton("Names")
        self.btn_update_names.setToolTip("Set or update player names")

        # NEW: Start New Game button
        self.btn_new_game = QPushButton("New Game")
        self.btn_new_game.setToolTip("Start a new game (clears all rallies)")

        # Set object names for styling and prevent focus stealing
        for btn in [self.btn_edit_score, self.btn_force_sideout,
                    self.btn_add_comment, self.btn_time_expired,
                    self.btn_update_names, self.btn_new_game]:
            btn.setObjectName("toolbar_button")
            btn.setFont(Fonts.button_other())
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Hide score-related buttons in highlights mode
        if self._is_highlights_mode:
            self.btn_edit_score.setVisible(False)
            self.btn_force_sideout.setVisible(False)
            self.btn_time_expired.setVisible(False)
            self.btn_update_names.setVisible(False)
            self.btn_new_game.setVisible(False)
        else:
            # Time Expired only for timed games
            if self.config.victory_rule != "timed":
                self.btn_time_expired.setVisible(False)

        layout.addWidget(self.btn_edit_score)
        layout.addWidget(self.btn_force_sideout)
        layout.addWidget(self.btn_add_comment)
        layout.addWidget(self.btn_time_expired)
        layout.addWidget(self.btn_update_names)
        layout.addWidget(self.btn_new_game)

        layout.addStretch()

        # Session buttons (right side)
        self.btn_return_to_menu = QPushButton("Main Menu")
        self.btn_save_session = QPushButton("Save Session")
        self.btn_final_review = QPushButton("Final Review")

        for btn in [self.btn_return_to_menu, self.btn_save_session, self.btn_final_review]:
            btn.setObjectName("toolbar_button")
            btn.setFont(Fonts.button_other())
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.btn_return_to_menu.setToolTip("Return to main menu")

        layout.addWidget(self.btn_return_to_menu)
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
        if self._is_highlights_mode:
            # Highlights mode: MARK END button
            self.btn_mark_end.clicked.connect(self.on_mark_end)
        else:
            # Normal mode: SERVER/RECEIVER WINS buttons
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
        self.btn_update_names.clicked.connect(self._on_update_player_names)
        self.btn_new_game.clicked.connect(self._on_start_new_game)
        self.btn_return_to_menu.clicked.connect(self._on_return_to_menu)
        self.btn_save_session.clicked.connect(self._on_save_session)
        self.btn_final_review.clicked.connect(self._on_final_review)

    def _key_from_char(self, char: str) -> Qt.Key:
        """Convert single character to Qt.Key.

        Args:
            char: Single character string (case-insensitive)

        Returns:
            Qt.Key enum value
        """
        return getattr(Qt.Key, f"Key_{char.upper()}")

    def _setup_shortcuts(self) -> None:
        """Set up global keyboard shortcuts using QShortcut.

        Uses QShortcut instead of keyPressEvent() because QShortcut has higher
        priority than widget-level key handling. This ensures shortcuts work
        regardless of which widget currently has focus.

        Shortcuts are loaded from AppSettings for customization.
        """
        shortcuts = self._app_settings.shortcuts
        skip_durations = self._app_settings.skip_durations

        # Video control shortcuts (always active)
        self._shortcut_pause = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._shortcut_pause.activated.connect(self._on_shortcut_pause)

        self._shortcut_seek_back = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self._shortcut_seek_back.activated.connect(
            lambda: self.video_widget.seek(skip_durations.arrow_left, absolute=False)
        )

        self._shortcut_seek_forward = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self._shortcut_seek_forward.activated.connect(
            lambda: self.video_widget.seek(skip_durations.arrow_right, absolute=False)
        )

        self._shortcut_seek_back_long = QShortcut(QKeySequence(Qt.Key.Key_Down), self)
        self._shortcut_seek_back_long.activated.connect(
            lambda: self.video_widget.seek(skip_durations.arrow_down, absolute=False)
        )

        self._shortcut_seek_forward_long = QShortcut(QKeySequence(Qt.Key.Key_Up), self)
        self._shortcut_seek_forward_long.activated.connect(
            lambda: self.video_widget.seek(skip_durations.arrow_up, absolute=False)
        )

        # Rally control shortcuts (only when not in review mode)
        self._shortcut_rally_start = QShortcut(QKeySequence(self._key_from_char(shortcuts.rally_start)), self)
        self._shortcut_rally_start.activated.connect(self._on_shortcut_rally_start)

        self._shortcut_server_wins = QShortcut(QKeySequence(self._key_from_char(shortcuts.server_wins)), self)
        self._shortcut_server_wins.activated.connect(self._on_shortcut_server_wins)

        self._shortcut_receiver_wins = QShortcut(QKeySequence(self._key_from_char(shortcuts.receiver_wins)), self)
        self._shortcut_receiver_wins.activated.connect(self._on_shortcut_receiver_wins)

        self._shortcut_undo = QShortcut(QKeySequence(self._key_from_char(shortcuts.undo)), self)
        self._shortcut_undo.activated.connect(self._on_shortcut_undo)

    def _on_shortcut_pause(self) -> None:
        """Handle Space shortcut for pause/unpause."""
        self.video_widget.toggle_pause()

    def _on_shortcut_rally_start(self) -> None:
        """Handle C shortcut for rally start / mark start."""
        if not self._in_review_mode and self.btn_rally_start.isEnabled():
            self.on_rally_start()

    def _on_shortcut_server_wins(self) -> None:
        """Handle S shortcut for server wins / mark end (highlights mode)."""
        if self._in_review_mode:
            return
        if self._is_highlights_mode:
            # In highlights mode, S key triggers MARK END
            if self.btn_mark_end is not None and self.btn_mark_end.isEnabled():
                self.on_mark_end()
        else:
            # Normal mode: server wins
            if self.btn_server_wins is not None and self.btn_server_wins.isEnabled():
                self.on_server_wins()

    def _on_shortcut_receiver_wins(self) -> None:
        """Handle R shortcut for receiver wins (disabled in highlights mode)."""
        if self._in_review_mode:
            return
        # In highlights mode, R key does nothing (no receiver concept)
        if not self._is_highlights_mode:
            if self.btn_receiver_wins is not None and self.btn_receiver_wins.isEnabled():
                self.on_receiver_wins()

    def _on_shortcut_undo(self) -> None:
        """Handle U shortcut for undo."""
        if not self._in_review_mode and self.btn_undo.isEnabled():
            self.on_undo()

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

        # If restoring session, seek to last position after MPV has loaded
        # Use a timer because MPV needs time to initialize before seeking works
        if self._restore_position is not None:
            # Try to get the last rally end position (last cut location)
            last_cut_info = self.rally_manager.get_last_rally_end_position()

            if last_cut_info is not None:
                # Resume at end of last rally (last cut)
                end_frame, restore_pos = last_cut_info
                rally_count = self.rally_manager.get_rally_count()
                if self._is_highlights_mode:
                    toast_msg = f"Resumed at last cut (Clip {rally_count} end) - paused"
                else:
                    toast_msg = f"Resumed at last cut (Rally {rally_count} end) - paused"
            else:
                # No rallies - fall back to saved position
                restore_pos = self._restore_position
                toast_msg = f"Resumed session at {restore_pos:.1f}s - paused"

            def _do_restore_seek() -> None:
                self.video_widget.seek(restore_pos, absolute=True)
                # Ensure video is paused so user can see where they left off
                self.video_widget.pause()
                ToastManager.show_success(self, toast_msg, duration_ms=3000)

            # Wait 500ms for MPV to initialize before seeking
            QTimer.singleShot(500, _do_restore_seek)
        else:
            ToastManager.show_success(
                self,
                f"Loaded video: {video_path.name} ({video_info.resolution})",
                duration_ms=3000
            )

    # Rally marking handlers

    def _get_dummy_score_snapshot(self) -> ScoreSnapshot:
        """Create a dummy score snapshot for highlights mode.

        Returns:
            A ScoreSnapshot with zeroed values (used for undo stack structure)
        """
        return ScoreSnapshot(score=(0, 0), serving_team=0, server_number=None)

    @pyqtSlot()
    def on_rally_start(self) -> None:
        """Handle Rally Start / Mark Start button click.

        Marks the beginning of a rally/clip at the current video position.
        Captures a score snapshot for undo functionality.
        """
        # LBYL: Check if rally is already in progress
        if self.rally_manager.is_rally_in_progress():
            msg = "Clip already in progress" if self._is_highlights_mode else "Rally already in progress"
            ToastManager.show_warning(self, msg, duration_ms=3000)
            return

        # Get current video position
        timestamp = self.video_widget.get_position()

        # Save score snapshot for undo (use dummy for highlights mode)
        if self._is_highlights_mode:
            score_snapshot = self._get_dummy_score_snapshot()
        else:
            score_snapshot = self.score_state.save_snapshot()

        # Mark rally start (precondition checked above)
        start_frame = self.rally_manager.start_rally(timestamp, score_snapshot)

        # Mark session as dirty
        self._dirty = True

        # Update UI state
        self._update_display()

        # Show feedback
        msg = f"Clip started at {timestamp:.1f}s" if self._is_highlights_mode else f"Rally started at {timestamp:.1f}s"
        self.video_widget.show_osd(msg, duration=2.0)

    @pyqtSlot()
    def on_mark_end(self) -> None:
        """Handle Mark End button click (highlights mode only).

        Marks the end of the current clip without score tracking.
        """
        # Check if clip is in progress
        if not self.rally_manager.is_rally_in_progress():
            ToastManager.show_warning(self, "No clip in progress", duration_ms=3000)
            return

        # Get current video position
        timestamp = self.video_widget.get_position()

        # End rally with no score (empty string)
        rally = self.rally_manager.end_rally(
            timestamp=timestamp,
            winner="",  # No winner in highlights mode
            score_at_start="",  # No score in highlights mode
            score_snapshot=self._get_dummy_score_snapshot()
        )

        # Mark session as dirty
        self._dirty = True

        # Update UI state
        self._update_display()

        # Show feedback
        clip_count = self.rally_manager.get_rally_count()
        self.video_widget.show_osd(f"Clip {clip_count} marked", duration=2.0)

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

        # Restore score state from snapshot (only in normal mode)
        if not self._is_highlights_mode and self.score_state is not None:
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

        if self._is_highlights_mode:
            # Highlights mode: no score or server info
            self.status_overlay.update_display(
                in_rally=in_rally,
                score="",  # No score display
                server_info=""  # No server info
            )
        else:
            # Normal mode: full score and server info
            score_string = self.score_state.get_score_string()
            server_info = self.score_state.get_server_info()

            # Format server info for display with placeholder for missing names
            team_label = f"Team {server_info.serving_team + 1}"

            if server_info.player_name:  # Non-empty = name is set
                server_text = f"{team_label} ({server_info.player_name})"
            else:  # Empty = name not set, show just team
                server_text = team_label

            if server_info.server_number is not None:
                server_text += f" #{server_info.server_number}"

            self.status_overlay.update_display(
                in_rally=in_rally,
                score=score_string,
                server_info=server_text
            )

        # Update button states
        self._update_button_states()

        # Update clip timeline for ALL match types
        rally_count = self.rally_manager.get_rally_count()
        if self.clip_timeline is not None:
            self.clip_timeline.set_clips(
                self.rally_manager.get_rallies(),
                self.rally_manager.fps,
                game_type=self.config.game_type,
            )

            # Generate in-progress label based on game type
            if in_rally:
                if self._is_highlights_mode:
                    in_progress_label = str(rally_count + 1)
                else:
                    # Singles/doubles: show current score as in-progress label
                    in_progress_label = self.score_state.get_score_string()
                self.clip_timeline.set_in_progress(True, label=in_progress_label)
            else:
                self.clip_timeline.set_in_progress(False)

    def _update_button_states(self) -> None:
        """Update rally button active/disabled states.

        Button logic:
        - WAITING (no rally): Rally Start active, Server/Receiver (or Mark End) disabled
        - IN_RALLY: Server/Receiver (or Mark End) active, Rally Start disabled
        - Undo: Always enabled if can_undo() is True
        """
        in_rally = self.rally_manager.is_rally_in_progress()
        can_undo = self.rally_manager.can_undo()

        if self._is_highlights_mode:
            # Highlights mode: MARK START / MARK END buttons
            if in_rally:
                self.btn_rally_start.setEnabled(False)
                self.btn_rally_start.set_active(False)

                self.btn_mark_end.setEnabled(True)
                self.btn_mark_end.set_active(True)
            else:
                self.btn_rally_start.setEnabled(True)
                self.btn_rally_start.set_active(True)

                self.btn_mark_end.setEnabled(False)
                self.btn_mark_end.set_active(False)
        else:
            # Normal mode: RALLY START / SERVER WINS / RECEIVER WINS buttons
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

    def _calculate_final_score(self) -> str:
        """Calculate final score for display.

        Returns formatted score like "11-9" (team scores, not server-perspective).
        """
        score = self.score_state.score
        return f"{score[0]}-{score[1]}"

    def _get_winning_team_names(self) -> list[str]:
        """Get the names of the winning team based on current score.

        Returns:
            List of player names for the winning team
        """
        score = self.score_state.score
        if score[0] > score[1]:
            return self.config.team1_players
        elif score[1] > score[0]:
            return self.config.team2_players
        else:
            # Tie - return empty (shouldn't happen in completed game)
            return []

    # Video player handlers

    @pyqtSlot(float)
    def _on_video_position_changed(self, position: float) -> None:
        """Handle video position changes.

        Updates the playback controls timecode display and clip timeline
        highlighting (in highlights mode).

        Args:
            position: Current position in seconds
        """
        self.playback_controls.set_time(position, self.video_duration)

        # Update clip timeline highlighting for ALL match types
        if self.clip_timeline is not None:
            self.clip_timeline.update_position(position)

    @pyqtSlot(float)
    def _on_video_duration_changed(self, duration: float) -> None:
        """Handle video duration updates.

        Args:
            duration: Video duration in seconds
        """
        self.video_duration = duration

    # Clip timeline handlers (all match types)

    @pyqtSlot(int)
    def _on_clip_clicked(self, index: int) -> None:
        """Handle single click on a clip cell in the timeline.

        Seeks video to the clip's start time.

        Args:
            index: 0-based clip index
        """
        rallies = self.rally_manager.get_rallies()
        if not (0 <= index < len(rallies)):
            return

        rally = rallies[index]
        start_sec = rally.start_frame / self.rally_manager.fps
        self.video_widget.seek(start_sec, absolute=True)

        # Appropriate OSD label for match type
        if self._is_highlights_mode:
            osd_label = f"Clip {index + 1}"
        else:
            osd_label = f"Rally {index + 1} ({rally.score_at_start})"
        self.video_widget.show_osd(osd_label, duration=1.5)

    @pyqtSlot(int)
    def _on_clip_play_requested(self, index: int) -> None:
        """Handle double-click on a clip cell in the timeline.

        Plays the clip from start to end, then auto-pauses.

        Args:
            index: 0-based clip index
        """
        rallies = self.rally_manager.get_rallies()
        if not (0 <= index < len(rallies)):
            return

        rally = rallies[index]
        start_sec = rally.start_frame / self.rally_manager.fps
        end_sec = rally.end_frame / self.rally_manager.fps
        duration_ms = int((end_sec - start_sec) * 1000)

        # Seek to start
        self.video_widget.seek(start_sec, absolute=True)

        # Start playback
        self.video_widget.play()

        # Set up timer to pause at end (reuse review mode timer pattern)
        if self._rally_playback_timer is not None:
            self._rally_playback_timer.stop()
            self._rally_playback_timer.deleteLater()

        self._rally_playback_timer = QTimer(self)
        self._rally_playback_timer.setSingleShot(True)
        self._rally_playback_timer.timeout.connect(lambda: self.video_widget.pause())
        self._rally_playback_timer.start(duration_ms)

        # Show feedback with appropriate label for match type
        if self._is_highlights_mode:
            self.video_widget.show_osd(f"Playing Clip {index + 1}", duration=2.0)
        else:
            self.video_widget.show_osd(f"Playing Rally {index + 1}", duration=2.0)

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

    @pyqtSlot()
    def _on_return_to_menu(self) -> None:
        """Handle Return to Main Menu button click.

        Shows unsaved warning if there are unsaved changes, then
        emits return_to_menu_requested signal.
        """
        if self._dirty:
            dialog = UnsavedWarningDialog(self)
            if dialog.exec():
                result = dialog.get_result()
                if result == UnsavedWarningResult.CANCEL:
                    return
                if result == UnsavedWarningResult.SAVE_AND_QUIT:
                    self._on_save_session()

        self.return_to_menu_requested.emit()

    @pyqtSlot()
    def _on_update_player_names(self) -> None:
        """Handle Update Player Names button click.

        Opens the PlayerNamesDialog to set or update player names.
        Updates both config and score_state when names are changed.
        """
        dialog = PlayerNamesDialog(
            game_type=self.config.game_type,
            current_team1=self.config.team1_players,
            current_team2=self.config.team2_players,
            parent=self
        )

        if dialog.exec():
            result = dialog.get_result()
            if result is not None:
                # Update config
                self.config.team1_players = result.team1_players
                self.config.team2_players = result.team2_players

                # Update ScoreState
                if self.score_state is not None:
                    self.score_state.set_player_names({
                        "team1": result.team1_players,
                        "team2": result.team2_players,
                    })

                self._dirty = True
                self._update_display()

                # Refresh review widget if active
                if self._in_review_mode and self._review_widget is not None:
                    self._refresh_review_widget_names()

                ToastManager.show_success(self, "Player names updated", duration_ms=3000)

    def _refresh_review_widget_names(self) -> None:
        """Update review widget with new player names.

        Refreshes the rally list display when player names are updated
        while in review mode.
        """
        if self._review_widget is not None:
            # Re-populate rallies to refresh any player name displays
            rallies = self.rally_manager.get_rallies()
            self._review_widget.set_rallies(rallies, fps=self.video_fps, is_highlights=self._is_highlights_mode)

            # Update game completion info if applicable
            if not self._is_highlights_mode:
                final_score = self._calculate_final_score()
                winning_team_names = self._get_winning_team_names()
                self._review_widget.set_game_completion_info(final_score, winning_team_names)

    @pyqtSlot()
    def _on_start_new_game(self) -> None:
        """Handle Start New Game button click.

        Shows confirmation dialog, then clears all rallies and resets score.
        Optionally allows changing game settings (game type, victory rule).
        """
        rally_count = self.rally_manager.get_rally_count()

        dialog = NewGameConfirmDialog(
            current_game_type=self.config.game_type,
            current_victory_rule=self.config.victory_rule,
            rally_count=rally_count,
            parent=self
        )

        if dialog.exec():
            result, new_settings = dialog.get_result()

            if result == NewGameResult.START_NEW:
                # Clear all rallies
                self.rally_manager.clear_all()

                # Update game settings if changed
                if new_settings is not None:
                    self.config.game_type = new_settings.game_type
                    self.config.victory_rule = new_settings.victory_rule

                # Full reset of score state (preserves player names)
                if self.score_state is not None:
                    self.score_state = ScoreState(
                        game_type=self.config.game_type,
                        victory_rules=self.config.victory_rule,
                        player_names={
                            "team1": self.config.team1_players,
                            "team2": self.config.team2_players,
                        }
                    )

                self._dirty = True
                self._update_display()
                ToastManager.show_success(self, "New game started", duration_ms=3000)

    def _build_session_state(self) -> SessionState:
        """Build SessionState from current state.

        Collects all current state information into a SessionState object
        for persistence.

        Returns:
            SessionState containing complete session information
        """
        # Get current video position
        last_position = self.video_widget.get_position()

        if self._is_highlights_mode:
            # Highlights mode: no score state
            session_state = SessionState(
                version="1.0",
                video_path=str(self.config.video_path),
                video_hash="",  # Will be set by SessionManager.save()
                game_type=self.config.game_type,
                victory_rules=self.config.victory_rule,
                player_names={"team1": [], "team2": []},
                rallies=self.rally_manager.get_rallies(),
                current_score=[0, 0],
                serving_team=0,
                server_number=None,
                last_position=last_position,
                created_at="",
                modified_at="",
                interventions=[],
                comments=[],
            )
        else:
            # Normal mode: get current score snapshot
            score_snapshot = self.score_state.save_snapshot()

            # Build player names dict
            player_names = {
                "team1": self.config.team1_players,
                "team2": self.config.team2_players,
            }

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

        # Enter review mode
        self.enter_review_mode()

    # Review mode methods

    def _get_widget_index(self, widget: QWidget) -> int:
        """Get the index of a widget in its parent's layout.

        Args:
            widget: Widget to find index for

        Returns:
            Index of widget in parent layout, or 0 if not found
        """
        parent = widget.parent()
        if parent and parent.layout():
            for i in range(parent.layout().count()):
                item = parent.layout().itemAt(i)
                # Check for spacer items (item.widget() returns None for spacers)
                if item is not None and item.widget() is not None and item.widget() == widget:
                    return i
        return 0

    def enter_review_mode(self) -> None:
        """Switch to review mode with video in splitter layout.

        Hides rally controls and toolbar, creates ReviewModeWidget if needed,
        reparents video container into the review widget's placeholder,
        populates it with rallies, and connects signals.
        """
        if self._in_review_mode:
            return

        # Set flag early to prevent race condition from multiple calls
        self._in_review_mode = True

        # Hide editing mode panels
        self.rally_controls_panel.hide()
        self.toolbar_panel.hide()

        # Create review widget if it doesn't exist
        if self._review_widget is None:
            self._review_widget = ReviewModeWidget(self)
            # Insert after playback controls
            central_widget = self.centralWidget()
            if central_widget is not None:
                layout = central_widget.layout()
                if layout is not None:
                    layout.insertWidget(2, self._review_widget)

            # Connect review widget signals
            self._review_widget.rally_changed.connect(self._on_review_rally_changed)
            self._review_widget.timing_adjusted.connect(self._on_review_timing_adjusted)
            self._review_widget.score_changed.connect(self._on_review_score_changed)
            self._review_widget.play_rally_requested.connect(self._on_review_play_rally)
            self._review_widget.exit_requested.connect(self.exit_review_mode)
            self._review_widget.generate_requested.connect(self._on_review_generate)
            self._review_widget.export_ffmpeg_requested.connect(self._on_export_ffmpeg)
            self._review_widget.game_completed_toggled.connect(self._on_game_completed_toggled)
            self._review_widget.return_to_menu_requested.connect(self.return_to_menu_requested.emit)

        # === Move video container into review widget's video placeholder ===
        video_placeholder = self._review_widget.get_video_placeholder()
        if video_placeholder is not None:
            # Store original parent for restoration
            central = self.centralWidget()
            if central is not None:
                self._video_container_original_parent = central
                main_layout = central.layout()
                if main_layout is not None:
                    self._video_container_original_index = main_layout.indexOf(self._video_container)
                    # Remove from main layout
                    main_layout.removeWidget(self._video_container)

            # Reparent video container directly to placeholder (no layout)
            # This matches how _VideoContainer handles its children
            self._video_container.setParent(video_placeholder)
            self._video_container.setGeometry(0, 0, video_placeholder.width(), video_placeholder.height())
            self._video_container.show()
            self._video_container.raise_()

            # Install resize handler on placeholder to keep video container sized correctly
            self._placeholder_original_resize_event = video_placeholder.resizeEvent
            def _placeholder_resize(event: QResizeEvent) -> None:
                self._placeholder_original_resize_event(event)
                self._video_container.setGeometry(0, 0, video_placeholder.width(), video_placeholder.height())
            video_placeholder.resizeEvent = _placeholder_resize

        # Populate with current rallies
        rallies = self.rally_manager.get_rallies()
        self._review_widget.set_rallies(rallies, fps=self.video_fps, is_highlights=self._is_highlights_mode)

        # Set default export path suggestion
        default_path = str(self.config.video_path.parent / f"{self.config.video_path.stem}.kdenlive")
        self._review_widget.set_export_path(default_path)

        if self._is_highlights_mode:
            # Highlights mode: no game completion info needed
            self._review_widget.set_game_completion_info("", [])
            self._review_widget.hide_game_completion_controls()
        else:
            # Normal mode: calculate and set game completion info
            final_score = self._calculate_final_score()
            winning_team_names = self._get_winning_team_names()
            self._review_widget.set_game_completion_info(final_score, winning_team_names)

            # Auto-detect if game is already over based on current score
            is_over, winner = self.score_state.is_game_over()
            if is_over:
                self._review_widget._mark_complete_checkbox.setChecked(True)

        # Show review widget
        self._review_widget.show()

        # Show feedback
        if self._is_highlights_mode:
            msg = "Entered review mode - adjust timings as needed"
        else:
            msg = "Entered review mode - adjust timings and scores as needed"
        ToastManager.show_success(self, msg, duration_ms=3000)

    def exit_review_mode(self) -> None:
        """Exit review mode and restore video to original location.

        Restores video container to its original parent, hides review widget,
        and shows rally controls and toolbar.
        """
        if not self._in_review_mode:
            return

        # Set flag early to prevent race condition from multiple calls
        self._in_review_mode = False

        # === Restore video container to original parent ===
        if self._video_container_original_parent is not None:
            # Restore placeholder's original resize event if we replaced it
            if self._review_widget is not None:
                video_placeholder = self._review_widget.get_video_placeholder()
                if video_placeholder is not None and hasattr(self, '_placeholder_original_resize_event'):
                    video_placeholder.resizeEvent = self._placeholder_original_resize_event

            # Restore to original layout at original position
            original_layout = self._video_container_original_parent.layout()
            if original_layout is not None:
                # Insert at original index with stretch=1 (as it was originally)
                original_layout.insertWidget(self._video_container_original_index, self._video_container, stretch=1)

            self._video_container.show()

        # Hide review widget
        if self._review_widget is not None:
            self._review_widget.hide()

        # Show editing mode panels
        self.rally_controls_panel.show()
        self.toolbar_panel.show()

        # Show feedback
        ToastManager.show_info(
            self,
            "Returned to editing mode",
            duration_ms=2000
        )

    @pyqtSlot(int)
    def _on_review_rally_changed(self, index: int) -> None:
        """Handle rally selection change in review mode.

        Seeks to and auto-plays the selected rally.

        Args:
            index: Rally index (0-based)
        """
        # Delegate to play rally method which handles seeking, playing, and auto-pause
        self._on_review_play_rally(index)

    @pyqtSlot(int, str, float)
    def _on_review_timing_adjusted(self, index: int, which: str, delta: float) -> None:
        """Handle timing adjustment in review mode.

        Updates rally timing based on the adjustment made in the review widget.

        Args:
            index: Rally index (0-based)
            which: "start" or "end"
            delta: Time change in seconds (can be negative)
        """
        # Check if index is valid
        if not (0 <= index < self.rally_manager.get_rally_count()):
            return

        # Update rally timing
        if which == "start":
            rally = self.rally_manager.update_rally_timing(
                index=index,
                start_delta=delta,
                end_delta=0.0
            )
        elif which == "end":
            rally = self.rally_manager.update_rally_timing(
                index=index,
                start_delta=0.0,
                end_delta=delta
            )
        else:
            return

        # Mark session as dirty
        self._dirty = True

        # Show feedback
        direction = "earlier" if delta < 0 else "later"
        self.video_widget.show_osd(
            f"{which.title()} adjusted {abs(delta):.1f}s {direction}",
            duration=1.5
        )

    def _refresh_game_completion_info(self) -> None:
        """Recompute game completion info after score changes.

        Updates the final score and winning team based on current score state
        and refreshes the review widget if in review mode.
        """
        if not self._in_review_mode or self._review_widget is None:
            return

        # Recalculate final score from score_state
        final_score = self._calculate_final_score()

        # Determine winner based on current scores
        t1_score, t2_score = self.score_state.score[0], self.score_state.score[1]
        if t1_score > t2_score:
            winning_team_names = self.config.team1_players
        elif t2_score > t1_score:
            winning_team_names = self.config.team2_players
        else:
            # Tie - use empty list
            winning_team_names = []

        # Update review widget with new completion info
        self._review_widget.set_game_completion_info(final_score, winning_team_names)

    @pyqtSlot(int, str, bool)
    def _on_review_score_changed(self, index: int, new_score: str, cascade: bool) -> None:
        """Handle score change in review mode.

        Updates the rally's score_at_start and optionally cascades to later rallies.

        Args:
            index: Rally index (0-based)
            new_score: New score string
            cascade: If True, recalculate subsequent rally scores
        """
        # Check if index is valid
        if not (0 <= index < self.rally_manager.get_rally_count()):
            return

        # Check if new score is non-empty
        if not new_score:
            return

        # Update rally score
        self.rally_manager.update_rally_score(
            index=index,
            new_score=new_score,
            cascade=cascade
        )

        # If cascade is enabled, replay score state for subsequent rallies
        if cascade:
            # Parse new score and set as starting point
            try:
                self.score_state.set_score(new_score)

                # Replay all rallies from index onwards
                for i in range(index, self.rally_manager.get_rally_count()):
                    rally = self.rally_manager.get_rally(i)

                    # Update score at start for this rally
                    if i > index:
                        rally.score_at_start = self.score_state.get_score_string()

                    # Apply winner to score state for next rally
                    if rally.winner == "server":
                        self.score_state.server_wins()
                    elif rally.winner == "receiver":
                        self.score_state.receiver_wins()

                # Update review widget with new rally data
                if self._review_widget is not None:
                    rallies = self.rally_manager.get_rallies()
                    self._review_widget.set_rallies(rallies, fps=self.video_fps)
                    self._review_widget.set_current_rally(index)

                ToastManager.show_success(
                    self,
                    f"Score updated and cascaded to {self.rally_manager.get_rally_count() - index} rallies",
                    duration_ms=3000
                )
            except (ValueError, IndexError) as e:
                ToastManager.show_error(
                    self,
                    f"Invalid score format: {e}",
                    duration_ms=3000
                )
                return
        else:
            # Just show success for single update
            ToastManager.show_success(
                self,
                f"Score updated for rally {index + 1}",
                duration_ms=2000
            )

        # Mark session as dirty
        self._dirty = True

        # Refresh game completion info after any score edit
        self._refresh_game_completion_info()

    @pyqtSlot(int)
    def _on_review_play_rally(self, index: int) -> None:
        """Play the selected rally from start to end.

        Sets up a timer to automatically pause when the rally ends.

        Args:
            index: Rally index (0-based)
        """
        # Check if index is valid
        if not (0 <= index < self.rally_manager.get_rally_count()):
            return

        # Get rally
        rally = self.rally_manager.get_rally(index)

        # Convert frames to seconds
        start_seconds = rally.start_frame / self.video_fps
        end_seconds = rally.end_frame / self.video_fps
        duration_ms = int((end_seconds - start_seconds) * 1000)

        # Seek to start
        self.video_widget.seek(start_seconds, absolute=True)

        # Start playback
        self.video_widget.play()

        # Set up timer to pause at end
        if self._rally_playback_timer is not None:
            self._rally_playback_timer.stop()
            self._rally_playback_timer.deleteLater()

        self._rally_playback_timer = QTimer(self)
        self._rally_playback_timer.setSingleShot(True)
        self._rally_playback_timer.timeout.connect(lambda: self.video_widget.pause())
        self._rally_playback_timer.start(duration_ms)

        # Show feedback
        self.video_widget.show_osd(
            f"Playing Rally {index + 1}",
            duration=2.0
        )

    @pyqtSlot(bool)
    def _on_game_completed_toggled(self, completed: bool) -> None:
        """Handle game completed toggle from review widget.

        Args:
            completed: Whether game is now marked as completed
        """
        self._dirty = True

    @pyqtSlot()
    def _on_review_generate(self) -> None:
        """Handle generate Kdenlive project request.

        Generates Kdenlive project and SRT subtitle files from current rallies.
        Shows ExportCompleteDialog with options to delete session and open folder.
        """
        # Get segments from rally manager
        segments = self.rally_manager.to_segments()

        # Check if there are segments to export
        if not segments:
            msg = "No clips to export" if self._is_highlights_mode else "No rallies to export"
            ToastManager.show_warning(self, msg, duration_ms=3000)
            return

        # Warn if game appears incomplete and not marked as completed (only for normal mode)
        if not self._is_highlights_mode:
            is_over, _ = self.score_state.is_game_over()
            if not is_over and (self._review_widget is None or not self._review_widget.is_game_completed()):
                ToastManager.show_warning(
                    self,
                    "Game appears incomplete - final score subtitle will not be added",
                    duration_ms=3000
                )

        # Check if export path was preset in review widget
        preset_path = ""
        if self._review_widget is not None:
            preset_path = self._review_widget.get_export_path()

        if preset_path:
            # Use preset path
            selected_path = Path(preset_path)
            # Ensure .kdenlive extension
            if selected_path.suffix.lower() != '.kdenlive':
                selected_path = selected_path.with_suffix('.kdenlive')
        else:
            # Show file save dialog for export path
            default_dir = str(Path.home() / "Videos")
            default_filename = f"{self.config.video_path.stem}.kdenlive"
            selected_path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export Kdenlive Project",
                str(Path(default_dir) / default_filename),
                "Kdenlive Project (*.kdenlive);;All Files (*)"
            )

            # Check if user cancelled
            if not selected_path_str:
                return

            selected_path = Path(selected_path_str)

        # Get video resolution from probe
        # We need to re-probe because we only stored fps/duration, not resolution
        try:
            video_info = probe_video(self.config.video_path)
            resolution = (video_info.width, video_info.height)
        except ProbeError:
            # Fall back to default HD resolution if probe fails
            resolution = (1920, 1080)
            ToastManager.show_warning(
                self,
                "Could not detect video resolution, using 1920x1080",
                duration_ms=3000
            )

        # Check if game is marked as completed (only for normal mode)
        game_completion_info = None
        if not self._is_highlights_mode and self._review_widget is not None and self._review_widget.is_game_completed():
            final_score, winning_names = self._review_widget.get_game_completion_info()
            winning_team = 0 if self.score_state.score[0] > self.score_state.score[1] else 1
            game_completion_info = GameCompletionInfo(
                is_completed=True,
                final_score=final_score,
                winning_team=winning_team,
                winning_team_names=winning_names,
                extension_seconds=8.0
            )

        # Create generator with player names for intro subtitle
        generator = KdenliveGenerator(
            video_path=str(self.config.video_path),
            segments=segments,
            fps=self.video_fps,
            resolution=resolution,
            team1_players=self.config.team1_players,
            team2_players=self.config.team2_players,
            game_type=self.config.game_type,
            game_completion=game_completion_info
        )

        # Generate files with selected path
        try:
            kdenlive_path, srt_path = generator.generate(output_path=selected_path)

            # Check if session exists
            session_exists = self._session_manager.find_existing(
                str(self.config.video_path)
            ) is not None

            # Show export complete dialog
            dialog = ExportCompleteDialog(
                kdenlive_path=kdenlive_path,
                show_delete_option=session_exists,
                parent=self
            )
            result = dialog.exec_and_get_result()

            if result.delete_session:
                # CRITICAL: Handle unsaved changes before deletion
                should_delete = True
                if self._dirty:
                    confirm = QMessageBox.question(
                        self,
                        "Unsaved Changes",
                        "You have unsaved changes. Delete session anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if confirm != QMessageBox.StandardButton.Yes:
                        should_delete = False

                if should_delete:
                    self._session_manager.delete(str(self.config.video_path))
                    self._dirty = False  # Only clear after confirmed deletion
                    ToastManager.show_success(
                        self,
                        "Session deleted successfully",
                        duration_ms=3000
                    )

            if result.open_folder:
                # Open file manager to output directory
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(kdenlive_path.parent)))

        except Exception as e:
            ToastManager.show_error(
                self,
                f"Generation failed: {e}",
                duration_ms=5000
            )

    @pyqtSlot()
    def _on_export_ffmpeg(self) -> None:
        """Handle FFmpeg MP4 export request.

        Exports rally segments directly to MP4 using FFmpeg with hardware encoding.
        Uses a non-blocking progress dialog with background threading.
        Shows toast notifications on completion.
        """
        # Check if export already in progress
        if self._active_export_dialog is not None:
            ToastManager.show_warning(
                self,
                "Export already in progress",
                duration_ms=3000
            )
            self._active_export_dialog.raise_()
            self._active_export_dialog.activateWindow()
            return

        # Get segments from rally manager
        segments = self.rally_manager.to_segments()

        # Check if there are segments to export
        if not segments:
            msg = "No clips to export" if self._is_highlights_mode else "No rallies to export"
            ToastManager.show_warning(self, msg, duration_ms=3000)
            return

        # Show file save dialog for MP4 output
        default_dir = str(Path.home() / "Videos")
        default_filename = f"{self.config.video_path.stem}.mp4"
        selected_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export to MP4",
            str(Path(default_dir) / default_filename),
            "MP4 Video (*.mp4);;All Files (*)"
        )

        # Check if user cancelled
        if not selected_path_str:
            return

        selected_path = Path(selected_path_str)

        # Build player_names dict
        player_names = {
            "team1": self.config.team1_players,
            "team2": self.config.team2_players,
            "game_type": self.config.game_type
        }

        # Check if game is marked as completed (only for normal mode)
        game_completion_info = None
        if not self._is_highlights_mode and self._review_widget is not None and self._review_widget.is_game_completed():
            final_score, winning_names = self._review_widget.get_game_completion_info()
            winning_team = 0 if self.score_state.score[0] > self.score_state.score[1] else 1
            game_completion_info = GameCompletionInfo(
                is_completed=True,
                final_score=final_score,
                winning_team=winning_team,
                winning_team_names=winning_names,
                extension_seconds=8.0
            )

        # Create FFmpeg exporter
        exporter = FFmpegExporter(
            video_path=self.config.video_path,
            segments=segments,
            fps=self.video_fps,
            player_names=player_names,
            game_completion=game_completion_info
        )

        # Create and show non-blocking progress dialog
        dialog = ExportProgressDialog(
            exporter=exporter,
            output_path=selected_path,
            parent=self
        )
        dialog.export_finished.connect(self._on_export_finished)
        dialog.export_cancelled_signal.connect(self._on_export_cancelled)

        self._active_export_dialog = dialog
        dialog.show()  # Non-blocking

    @pyqtSlot(bool, Path, str)
    def _on_export_finished(self, success: bool, output_path: Path, error_message: str) -> None:
        """Handle export completion signal.

        Args:
            success: True if export succeeded
            output_path: Path to exported file if successful
            error_message: Error description if failed
        """
        self._active_export_dialog = None

        if success:
            ToastManager.show_success(
                self,
                f"MP4 exported to {output_path.name}",
                duration_ms=5000
            )
            # Open file manager to output directory
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path.parent)))
        else:
            ToastManager.show_error(
                self,
                f"Export failed: {error_message}",
                duration_ms=5000
            )

    @pyqtSlot()
    def _on_export_cancelled(self) -> None:
        """Handle export cancellation signal."""
        self._active_export_dialog = None
        ToastManager.show_warning(
            self,
            "Export cancelled",
            duration_ms=3000
        )

    def _check_compact_mode(self) -> None:
        """Check if compact mode should be toggled based on window width."""
        width = self.width()
        new_compact = width < 950
        if new_compact != self._compact_mode:
            self._compact_mode = new_compact
            self._apply_compact_styles()

    def _apply_compact_styles(self) -> None:
        """Apply or remove compact mode styles."""
        from PyQt6.QtGui import QFont

        if self._compact_mode:
            # Smaller fonts for compact mode
            for btn in [self.btn_rally_start, self.btn_server_wins,
                        self.btn_receiver_wins, self.btn_undo]:
                if btn:
                    btn.setFont(QFont("IBM Plex Sans", 14))
            # Notify status overlay
            if hasattr(self, 'status_overlay') and self.status_overlay:
                self.status_overlay.set_compact_mode(True)
        else:
            # Restore normal fonts
            for btn in [self.btn_rally_start, self.btn_server_wins,
                        self.btn_receiver_wins]:
                if btn:
                    btn.setFont(QFont("IBM Plex Sans", 18, QFont.Weight.DemiBold))
            if self.btn_undo:
                self.btn_undo.setFont(QFont("IBM Plex Sans", 14, QFont.Weight.Medium))
            # Notify status overlay
            if hasattr(self, 'status_overlay') and self.status_overlay:
                self.status_overlay.set_compact_mode(False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle window resize - check compact mode threshold."""
        super().resizeEvent(event)
        self._check_compact_mode()

    def showEvent(self, event: QShowEvent) -> None:
        """Handle window show event.

        Loads the video after the window is shown to ensure the VideoWidget
        has a valid native window ID for MPV embedding.

        Args:
            event: Show event from Qt
        """
        super().showEvent(event)

        # Only load video once, on first show
        if not self._video_loaded:
            self._video_loaded = True
            # Use a timer to ensure the window is fully realized
            # 100ms gives Qt time to create native windows and process events
            QTimer.singleShot(100, self._load_video)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.

        Checks for active export and unsaved changes before closing.

        Args:
            event: Close event from Qt
        """
        # Check if export is in progress
        if self._active_export_dialog is not None:
            reply = QMessageBox.question(
                self,
                "Export in Progress",
                "Video export is still in progress. Cancel export and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            # Cancel the export via close() which triggers cancellation
            self._active_export_dialog.close()
            self._active_export_dialog = None

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
