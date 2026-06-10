"""Final Review Mode UI for Pickleball Video Editor.

This module provides the ReviewModeWidget and its sub-components for verifying
and adjusting rally timings before generating Kdenlive output.

Components:
- RallyHeaderWidget: Shows "RALLY X OF Y" with progress indicator
- TimingControlWidget: Adjust rally start/end times with +/- buttons
- ScoreEditWidget: Edit rally score with cascade option
- RallyCardWidget: Individual rally card for rally list
- RallyListWidget: Responsive wrapping grid of rally cards (uses QListWidget IconMode)
- ReviewModeWidget: Main container composing all components

The Review Mode replaces the Rally Controls and Toolbar sections when activated
from the Main Window's "Final Review" button.
"""

from PyQt6.QtCore import Qt, QSize, QTimer, QRegularExpression, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QRegularExpressionValidator, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.core.app_config import AppSettings

from src.core.models import Rally
from src.ui.styles.components import ButtonStyles, InputStyles, set_class, set_label_role
from src.ui.widgets.toast import ToastManager
from src.ui.styles import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    PRIMARY_ACTION,
    RADIUS_LG,
    RADIUS_MD,
    RECEIVER_WINS,
    SERVER_WINS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_WARNING,
    DANGER_TEXT,
    Fonts,
    icon as make_icon,
    pixmap as make_pixmap,
)
from src.ui.styles.fonts import ASPECT_ULTRAWIDE

__all__ = [
    "RallyHeaderWidget",
    "TimingControlWidget",
    "ScoreEditWidget",
    "RallyListWidget",
    "ReviewModeWidget",
]


def _format_time(seconds: float) -> str:
    """Format seconds to MM:SS.s format for display.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string (e.g., "03:45.2")
    """
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:04.1f}"


class RallyHeaderWidget(QWidget):
    """Header showing current rally progress with "RALLY X OF Y" display.

    Displays:
    - Large "RALLY X OF Y" text
    - Exit Review button on the right
    - Visual progress indicator bar

    Signals:
        exit_requested(): User clicked Exit Review button
        return_to_menu_requested(): User clicked Return to Main Menu button
    """

    exit_requested = pyqtSignal()
    return_to_menu_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the rally header widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._current_rally = 0
        self._total_rallies = 0
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.setSpacing(SPACE_MD)

        # Title label
        self._title_label = QLabel("FINAL REVIEW MODE")
        self._title_label.setFont(Fonts.dialog_title())
        self._title_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        layout.addWidget(self._title_label)

        # Rally counter label
        self._counter_label = QLabel("Rally 0 of 0")
        self._counter_label.setFont(Fonts.body(size=16, weight=600))
        layout.addWidget(self._counter_label)

        layout.addStretch()

        # Return to Main Menu button
        self._return_to_menu_button = QPushButton("Main Menu")
        self._return_to_menu_button.setFont(Fonts.button_other())
        self._return_to_menu_button.clicked.connect(self.return_to_menu_requested.emit)
        set_class(self._return_to_menu_button, "secondary")
        layout.addWidget(self._return_to_menu_button)

        # Exit button
        self._exit_button = QPushButton("Exit Review")
        self._exit_button.setFont(Fonts.button_other())
        self._exit_button.clicked.connect(self.exit_requested.emit)
        set_class(self._exit_button, "secondary")
        layout.addWidget(self._exit_button)

        # Container styling
        self.setStyleSheet(f"""
            RallyHeaderWidget {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)

    def set_rally(self, current: int, total: int, is_post_game: bool = False) -> None:
        """Update the displayed rally count.

        Args:
            current: Current rally index (0-based)
            total: Total number of rallies
            is_post_game: When True, appends " (post-game)" to the counter label
        """
        self._current_rally = current
        self._total_rallies = total
        # Display as 1-based for user
        suffix = " (post-game)" if is_post_game else ""
        self._counter_label.setText(f"Rally {current + 1} of {total}{suffix}")


class TimingControlWidget(QWidget):
    """Widget for adjusting rally start/end times with +/- 0.1s buttons.

    Displays:
    - Start time with -0.1s and +0.1s adjustment buttons
    - End time with -0.1s and +0.1s adjustment buttons
    - Duration (read-only, calculated)

    Signals:
        timing_adjusted(str, float): Emitted when timing is adjusted
            - field: "start" or "end"
            - delta: Change in seconds (e.g., 0.1 or -0.1)
    """

    timing_adjusted = pyqtSignal(str, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the timing control widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._start_time = 0.0
        self._end_time = 0.0
        self._orig_start = 0.0
        self._orig_end = 0.0
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section title
        title = QLabel("TIMING")
        title.setFont(Fonts.section_label())
        title.setText(title.text().upper())
        set_label_role(title, "sectionLabel")
        layout.addWidget(title)

        # Controls grid
        controls_layout = QGridLayout()
        controls_layout.setSpacing(SPACE_MD)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(4, 1)

        # Start time controls — row 0
        start_label = QLabel("START")
        start_label.setFont(Fonts.label())
        set_label_role(start_label, "body")
        controls_layout.addWidget(start_label, 0, 0)

        self._start_time_label = QLabel("00:00.0")
        self._start_time_label.setFont(Fonts.timestamp())
        controls_layout.addWidget(self._start_time_label, 0, 1)

        # End time controls — row 0
        end_label = QLabel("END")
        end_label.setFont(Fonts.label())
        set_label_role(end_label, "body")
        controls_layout.addWidget(end_label, 0, 3)

        self._end_time_label = QLabel("00:00.0")
        self._end_time_label.setFont(Fonts.timestamp())
        controls_layout.addWidget(self._end_time_label, 0, 4)

        # Offset captions — row 1, hidden until timing is modified
        _offset_style = (
            f"color: {TEXT_TERTIARY}; font-size: 12px;"
            " background: transparent; border: none;"
        )
        self._start_offset_label = QLabel("")
        self._start_offset_label.setStyleSheet(_offset_style)
        self._start_offset_label.hide()
        controls_layout.addWidget(self._start_offset_label, 1, 0, 1, 2)

        self._end_offset_label = QLabel("")
        self._end_offset_label.setStyleSheet(_offset_style)
        self._end_offset_label.hide()
        controls_layout.addWidget(self._end_offset_label, 1, 3, 1, 2)

        # Adjustment buttons — row 2
        start_minus_btn = QPushButton("-0.1s")
        start_minus_btn.setFont(Fonts.button_other())
        start_minus_btn.clicked.connect(lambda: self._adjust_start(-0.1))
        self._style_adjust_button(start_minus_btn)
        controls_layout.addWidget(start_minus_btn, 2, 0)

        start_plus_btn = QPushButton("+0.1s")
        start_plus_btn.setFont(Fonts.button_other())
        start_plus_btn.clicked.connect(lambda: self._adjust_start(0.1))
        self._style_adjust_button(start_plus_btn)
        controls_layout.addWidget(start_plus_btn, 2, 1)

        end_minus_btn = QPushButton("-0.1s")
        end_minus_btn.setFont(Fonts.button_other())
        end_minus_btn.clicked.connect(lambda: self._adjust_end(-0.1))
        self._style_adjust_button(end_minus_btn)
        controls_layout.addWidget(end_minus_btn, 2, 3)

        end_plus_btn = QPushButton("+0.1s")
        end_plus_btn.setFont(Fonts.button_other())
        end_plus_btn.clicked.connect(lambda: self._adjust_end(0.1))
        self._style_adjust_button(end_plus_btn)
        controls_layout.addWidget(end_plus_btn, 2, 4)

        # Duration display — row 3 cols 0-1; Reset button — row 3 cols 3-4
        duration_label = QLabel("DURATION")
        duration_label.setFont(Fonts.label())
        set_label_role(duration_label, "body")
        controls_layout.addWidget(duration_label, 3, 0)

        self._duration_label = QLabel("00:00.0")
        self._duration_label.setFont(Fonts.timestamp())
        controls_layout.addWidget(self._duration_label, 3, 1)

        self._reset_button = QPushButton("Reset")
        self._reset_button.setFont(Fonts.button_other())
        self._reset_button.setToolTip("Restore original timing")
        self._reset_button.clicked.connect(self._on_reset_clicked)
        self._reset_button.setStyleSheet(ButtonStyles.compact())
        self._reset_button.setEnabled(False)
        controls_layout.addWidget(self._reset_button, 3, 3, 1, 2)

        layout.addLayout(controls_layout)

        # Container styling
        self.setStyleSheet(f"""
            TimingControlWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    def _style_adjust_button(self, button: QPushButton) -> None:
        """Apply consistent styling to adjustment buttons.

        Args:
            button: Button to style
        """
        button.setStyleSheet(ButtonStyles.compact())

    def _adjust_start(self, delta: float) -> None:
        """Handle start time adjustment.

        Args:
            delta: Time change in seconds
        """
        self._start_time += delta
        if self._start_time < 0:
            self._start_time = 0.0
        self._update_display()
        self._check_modified()
        self.timing_adjusted.emit("start", delta)

    def _adjust_end(self, delta: float) -> None:
        """Handle end time adjustment.

        Args:
            delta: Time change in seconds
        """
        self._end_time += delta
        if self._end_time < self._start_time:
            self._end_time = self._start_time
        self._update_display()
        self._check_modified()
        self.timing_adjusted.emit("end", delta)

    def _check_modified(self) -> None:
        """Update Reset button state and offset captions based on delta from originals."""
        start_delta = round(self._start_time - self._orig_start, 1)
        end_delta = round(self._end_time - self._orig_end, 1)

        is_modified = start_delta != 0.0 or end_delta != 0.0
        self._reset_button.setEnabled(is_modified)

        if start_delta != 0.0:
            sign = "+" if start_delta > 0 else ""
            self._start_offset_label.setText(f"{sign}{start_delta:.1f}s from original")
            self._start_offset_label.show()
        else:
            self._start_offset_label.hide()

        if end_delta != 0.0:
            sign = "+" if end_delta > 0 else ""
            self._end_offset_label.setText(f"{sign}{end_delta:.1f}s from original")
            self._end_offset_label.show()
        else:
            self._end_offset_label.hide()

    @pyqtSlot()
    def _on_reset_clicked(self) -> None:
        """Restore start/end to the originals stored when the rally was loaded.

        Emits corrective ``timing_adjusted`` deltas so the parent widget and
        model stay in sync.
        """
        start_corrective = self._orig_start - self._start_time
        end_corrective = self._orig_end - self._end_time

        self._start_time = self._orig_start
        self._end_time = self._orig_end
        self._update_display()
        self._check_modified()

        if start_corrective != 0.0:
            self.timing_adjusted.emit("start", start_corrective)
        if end_corrective != 0.0:
            self.timing_adjusted.emit("end", end_corrective)

    def _update_display(self) -> None:
        """Update all time displays."""
        self._start_time_label.setText(_format_time(self._start_time))
        self._end_time_label.setText(_format_time(self._end_time))
        duration = max(0.0, self._end_time - self._start_time)
        self._duration_label.setText(_format_time(duration))

    def set_times(self, start_seconds: float, end_seconds: float) -> None:
        """Set the displayed start and end times.

        Also stores the provided values as the originals for the current rally
        so the Reset button and offset captions have a reference point.

        Args:
            start_seconds: Rally start time in seconds
            end_seconds: Rally end time in seconds
        """
        self._start_time = start_seconds
        self._end_time = end_seconds
        self._orig_start = start_seconds
        self._orig_end = end_seconds
        self._update_display()
        self._check_modified()


class ScoreEditWidget(QWidget):
    """Widget for editing rally score with optional cascade.

    Displays:
    - Current score (read-only)
    - Arrow indicator
    - New score input field with inline format validation
    - Cascade checkbox

    Signals:
        score_changed(str, bool): Emitted when score is changed
            - new_score: New score string (validated)
            - cascade: Whether to cascade to later rallies
    """

    score_changed = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the score edit widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._game_mode = "doubles"
        self._validator: QRegularExpressionValidator | None = None
        self._init_ui()
        self._update_validator()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section title
        title = QLabel("SCORE")
        title.setFont(Fonts.section_label())
        title.setText(title.text().upper())
        set_label_role(title, "sectionLabel")
        layout.addWidget(title)

        # Score edit layout
        score_layout = QHBoxLayout()
        score_layout.setSpacing(SPACE_MD)

        # Current score display
        current_layout = QVBoxLayout()
        current_layout.setSpacing(SPACE_SM // 2)

        current_label = QLabel("CURRENT")
        current_label.setFont(Fonts.secondary())
        current_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        current_layout.addWidget(current_label)

        self._current_score_label = QLabel("0-0-2")
        self._current_score_label.setFont(Fonts.display(size=20, weight=700))
        self._current_score_label.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_TERTIARY};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
            }}
        """)
        self._current_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        current_layout.addWidget(self._current_score_label)

        score_layout.addLayout(current_layout)

        # Arrow indicator — Lucide arrow-right
        arrow_label = QLabel()
        arrow_label.setPixmap(make_pixmap("arrow-right", TEXT_SECONDARY, 24))
        arrow_label.setFixedSize(24, 24)
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(arrow_label)

        # New score input
        new_layout = QVBoxLayout()
        new_layout.setSpacing(SPACE_SM // 2)

        new_label = QLabel("NEW SCORE")
        new_label.setFont(Fonts.secondary())
        new_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        new_layout.addWidget(new_label)

        self._new_score_input = QLineEdit()
        self._new_score_input.setFont(Fonts.display(size=20, weight=700))
        self._new_score_input.setPlaceholderText("X-Y-Z")
        self._new_score_input.editingFinished.connect(self._on_editing_finished)
        self._new_score_input.setStyleSheet(InputStyles.line_edit())
        new_layout.addWidget(self._new_score_input)

        score_layout.addLayout(new_layout)

        layout.addLayout(score_layout)

        # Inline error label — shown when the entered score does not match the
        # expected format (e.g. "7-5-2" for doubles, "7-5" for singles).
        self._error_label = QLabel("Use the format 7-5-2")
        self._error_label.setStyleSheet(
            f"color: {DANGER_TEXT}; font-size: 12px; background: transparent; border: none;"
        )
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Cascade checkbox
        self._cascade_checkbox = QCheckBox("Cascade to later rallies")
        self._cascade_checkbox.setFont(Fonts.label())
        self._cascade_checkbox.setStyleSheet(InputStyles.checkbox())
        layout.addWidget(self._cascade_checkbox)

        # Container styling
        self.setStyleSheet(f"""
            ScoreEditWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    @pyqtSlot()
    def _on_editing_finished(self) -> None:
        """Handle editingFinished — validate the format then emit score_changed.

        Uses the regex for the current game mode:
        - doubles:          ``^\\d{1,2}-\\d{1,2}-[12]$``  (e.g. "7-5-2")
        - singles/highlights: ``^\\d{1,2}-\\d{1,2}$``   (e.g. "7-5")

        Emits ``score_changed`` only when the format is Acceptable; shows the
        inline error label and activates the ``[error="true"]`` border otherwise.
        """
        text = self._new_score_input.text().strip()
        if not text:
            self._set_error_state(False)
            return
        rx = QRegularExpression(self._current_pattern())
        if rx.match(text).hasMatch():
            self._set_error_state(False)
            cascade = self._cascade_checkbox.isChecked()
            self.score_changed.emit(text, cascade)
        else:
            self._set_error_state(True)

    def _current_pattern(self) -> str:
        """Return the validation regex pattern for the current game mode.

        Returns:
            Anchored regex string for full-string matching.
        """
        if self._game_mode == "doubles":
            return r"^\d{1,2}-\d{1,2}-[12]$"
        return r"^\d{1,2}-\d{1,2}$"

    def _set_error_state(self, error: bool) -> None:
        """Toggle the error visual state on the score input and inline label.

        Sets the ``error`` dynamic property on the QLineEdit so the
        ``QLineEdit[error="true"]`` rule in InputStyles.line_edit() activates
        the red border.

        Args:
            error: True to show error state; False to clear it.
        """
        self._new_score_input.setProperty("error", "true" if error else "false")
        self._new_score_input.style().unpolish(self._new_score_input)
        self._new_score_input.style().polish(self._new_score_input)
        if error:
            self._error_label.show()
        else:
            self._error_label.hide()

    def set_mode(self, mode: str) -> None:
        """Set the game mode and rebuild the score input validator.

        Args:
            mode: One of ``"doubles"``, ``"singles"``, or ``"highlights"``.
                  Doubles expects X-Y-Z; singles / highlights expect X-Y.
        """
        self._game_mode = mode
        self._update_validator()

    def _update_validator(self) -> None:
        """Rebuild the QRegularExpressionValidator for the current mode.

        A reference is kept in ``self._validator`` so Python's garbage collector
        does not free it — ``QLineEdit.setValidator`` does not take ownership
        in the PyQt6 bindings.
        """
        pattern = self._current_pattern()
        self._validator = QRegularExpressionValidator(QRegularExpression(pattern))
        self._new_score_input.setValidator(self._validator)
        if self._game_mode == "doubles":
            self._new_score_input.setPlaceholderText("X-Y-Z")
        else:
            self._new_score_input.setPlaceholderText("X-Y")

    def set_current_score(self, score: str) -> None:
        """Set the displayed current score.

        Also clears the new-score input and any active error state so the
        widget is in a clean state when switching between rallies.

        Args:
            score: Score string (e.g., "3-2-1")
        """
        self._current_score_label.setText(score)
        self._new_score_input.clear()
        self._set_error_state(False)

    def get_new_score(self) -> str:
        """Get the entered new score.

        Returns:
            New score string from input field
        """
        return self._new_score_input.text()

    def get_cascade(self) -> bool:
        """Get the cascade checkbox state.

        Returns:
            True if cascade is checked
        """
        return self._cascade_checkbox.isChecked()


class RallyListWidget(QWidget):
    """Horizontal scrolling list of rally cards using QListWidget IconMode.

    Displays all rallies as cards in a single horizontal row with
    horizontal scrolling when there are more cards than can fit.

    Signals:
        rally_selected(int): Emitted when a rally card is clicked
            - rally_index: Index of selected rally (0-based)
    """

    rally_selected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the rally list widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._rallies: list[Rally] = []
        self._current_index = 0
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Use QListWidget in IconMode - single horizontal row with scroll
        self._list_widget = QListWidget()
        self._list_widget.setObjectName("rallyList")  # Set object name for theme targeting
        self._list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self._list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self._list_widget.setWrapping(False)  # Single row, no wrapping
        self._list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list_widget.setSpacing(4)
        self._list_widget.setGridSize(QSize(70, 50))  # Grid cell size
        self._list_widget.setUniformItemSizes(True)
        self._list_widget.setMovement(QListWidget.Movement.Static)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Derive height from the grid cell size, inter-item spacing, the
        # horizontal scrollbar, and the frame border so the value stays correct
        # if those dimensions change rather than using a magic constant.
        _grid_h = self._list_widget.gridSize().height()   # 50 px
        _spacing = self._list_widget.spacing()             # 4 px
        _scrollbar_h = self._list_widget.horizontalScrollBar().sizeHint().height()
        _frame_h = self._list_widget.frameWidth() * 2
        _derived_h = _grid_h + 2 * _spacing + _scrollbar_h + _frame_h
        self._list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._list_widget.setFixedHeight(_derived_h)

        # Style the list widget with object-scoped selectors
        self._list_widget.setStyleSheet(f"""
            QListWidget#rallyList {{
                background: {BG_PRIMARY};
                border: none;
                padding: {SPACE_SM}px;
            }}
            QListWidget#rallyList::item {{
                background: {BG_TERTIARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px;
            }}
            QListWidget#rallyList::item:selected {{
                background: rgba(74, 222, 128, 0.15);
                border: 2px solid {PRIMARY_ACTION};
                            }}
            QListWidget#rallyList::item:hover {{
                background: {BG_BORDER};
                border-color: {PRIMARY_ACTION};
            }}
            QScrollBar:horizontal {{
                background-color: {BG_TERTIARY};
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {BORDER_COLOR};
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {PRIMARY_ACTION};
            }}
        """)

        self._list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list_widget)

        # Container styling
        self.setStyleSheet(f"""
            RallyListWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    def _create_card_widget(
        self, rally_num: int, score: str, is_post_game: bool = False
    ) -> QWidget:
        """Create a card widget for a rally item.

        Args:
            rally_num: Rally number (1-based for display)
            score: Score string
            is_post_game: When True, shows a muted "PG" indicator on the card

        Returns:
            QWidget containing rally card content
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        num_label = QLabel(str(rally_num))
        num_label.setFont(Fonts.display(size=14, weight=600))
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

        # Post-game label replaces the score string with a "PG" tag
        if is_post_game:
            score_label = QLabel("PG")
            score_label.setFont(Fonts.display(size=9))
            score_label.setStyleSheet(
                f"color: {TEXT_WARNING}; background: transparent; border: none;"
            )
        else:
            score_label = QLabel(score)
            score_label.setFont(Fonts.display(size=9))
            score_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
            )
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(num_label)
        layout.addWidget(score_label)

        # Make the widget transparent so item styling shows through
        widget.setStyleSheet("background: transparent;")
        return widget

    def set_rallies(self, rallies: list[Rally]) -> None:
        """Populate the rally list with cards.

        Args:
            rallies: List of Rally objects
        """
        self._rallies = rallies
        self._list_widget.clear()

        for idx, rally in enumerate(rallies):
            item = QListWidgetItem()
            # Create custom widget for the item
            widget = self._create_card_widget(idx + 1, rally.score_at_start, rally.is_post_game)
            item.setSizeHint(QSize(62, 42))
            item.setData(Qt.ItemDataRole.UserRole, idx)  # Store index
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

        if rallies:
            self.set_current_rally(0)

    @pyqtSlot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle rally item click.

        Args:
            item: Clicked list widget item
        """
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.rally_selected.emit(idx)

    def set_current_rally(self, index: int) -> None:
        """Set the currently selected rally.

        Args:
            index: Rally index (0-based)
        """
        if 0 <= index < self._list_widget.count():
            self._current_index = index
            self._list_widget.setCurrentRow(index)
            # Ensure selected item is visible
            self._list_widget.scrollToItem(
                self._list_widget.item(index),
                QListWidget.ScrollHint.EnsureVisible
            )


class ReviewModeWidget(QWidget):
    """Main container for Final Review Mode with tall or wide arrangement.

    Composites all review components:
    - Rally header with progress (top, outside arrangement area)
    - Video placeholder + control panel
    - Rally list + navigation + generate

    The layout is chosen ONCE when the widget is first shown, based on the
    window aspect ratio at that moment:

    - **Tall** (default): outer vertical splitter — video+controls on top,
      rally-list+export on the bottom (scrollable).
    - **Wide** (aspect >= 2.0): horizontal master splitter — video+rally-list
      on the left (not scrolled), controls+export column on the right
      (scrollable, min 460 px).

    The arrangement is FROZEN for the review session.  Re-arrangement on
    subsequent resizes is deliberately not supported: mpv native-window
    reparenting is fragile and switching while the video is embedded causes
    native-window regressions on repeated enter→exit→enter cycles.

    mpv Safety Contract
    -------------------
    ``_video_placeholder`` is the X11 native-window target for mpv.  It is
    NEVER placed inside a QScrollArea in either arrangement.  MainWindow
    reparents ``_video_container`` into ``_video_placeholder`` via the
    enter_review_mode / exit_review_mode paths; those paths must not be
    changed by this module.

    Signals:
        rally_changed(int): Current rally index changed
        timing_adjusted(int, str, float): Rally timing adjusted
            - rally_idx: Rally index
            - field: "start" or "end"
            - delta: Time change in seconds
        score_changed(int, str, bool): Rally score changed
            - rally_idx: Rally index
            - new_score: New score string
            - cascade: Cascade to later rallies
        exit_requested(): Exit review mode
        generate_requested(): Generate Kdenlive project
        play_rally_requested(int): Play the specified rally
        navigate_previous(): Navigate to previous rally
        navigate_next(): Navigate to next rally
    """

    rally_changed = pyqtSignal(int)
    timing_adjusted = pyqtSignal(int, str, float)
    score_changed = pyqtSignal(int, str, bool)
    winner_flipped = pyqtSignal(int)  # rally index — emitted when user flips the rally winner
    delete_rally_requested = pyqtSignal(int)  # rally index — emitted when user requests deletion
    insert_rally_requested = pyqtSignal(int)  # rally index — emitted when user requests insert after
    exit_requested = pyqtSignal()
    return_to_menu_requested = pyqtSignal()
    generate_requested = pyqtSignal()
    export_ffmpeg_requested = pyqtSignal()
    play_rally_requested = pyqtSignal(int)
    navigate_previous = pyqtSignal()
    navigate_next = pyqtSignal()
    game_completed_toggled = pyqtSignal(bool)  # Emitted when Mark Game Completed is toggled
    export_path_changed = pyqtSignal(str)  # Emitted when export path is set

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the review mode widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._rallies: list[Rally] = []
        self._current_index = 0
        self._fps = 60.0  # Default fps, should be set by parent
        self._game_completed = False
        self._final_score = ""
        self._winning_team_names: list[str] = []
        self._export_path: str = ""  # Custom export path, empty means use dialog
        self._low_confidence_indices: set[int] = set()

        # Load settings for geometry persistence (DisplayConfig added by Task 1).
        self._app_settings = AppSettings.load()

        # Debounce timer so splitter moves are not saved on every pixel drag.
        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(500)
        self._splitter_save_timer.timeout.connect(self._save_splitter_sizes)

        self._init_ui()
        # Note: splitter signal connections are made inside _arrange_tall() /
        # _arrange_wide(), which are called from showEvent().  Do NOT connect
        # _outer_splitter.splitterMoved here — the splitter is None at this point.

    def _init_ui(self) -> None:
        """Create stable leaf widgets and the arrangement host.

        The full layout is deferred to :meth:`_arrange_tall` or
        :meth:`_arrange_wide`, called once from :meth:`showEvent`.  Splitting
        construction from arrangement means the section widgets are stable
        across repeated enter→exit→enter review cycles, and
        ``_video_placeholder`` is placed in its final parent (outside any
        QScrollArea) before mpv reparents its native X11 window into it.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        main_layout.setSpacing(SPACE_MD)

        # ── Header ───────────────────────────────────────────────────────────
        self._header = RallyHeaderWidget()
        self._header.exit_requested.connect(self.exit_requested.emit)
        self._header.return_to_menu_requested.connect(self.return_to_menu_requested.emit)
        main_layout.addWidget(self._header)

        # ── Arrangement host ─────────────────────────────────────────────────
        # _arrange_tall() or _arrange_wide() adds its root widget here exactly
        # once.  Subsequent showEvent calls are no-ops for the layout.
        self._arrangement_host = QWidget(self)
        self._arrangement_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _host_layout = QVBoxLayout(self._arrangement_host)
        _host_layout.setContentsMargins(0, 0, 0, 0)
        _host_layout.setSpacing(0)
        main_layout.addWidget(self._arrangement_host, stretch=1)

        # ── Video placeholder ────────────────────────────────────────────────
        # MPV reparenting target.  WA_NativeWindow gives this widget its own
        # X11 window ID.  winId() is called immediately so the X11 window is
        # created now, before any parent assignment.  On X11, XReparentWindow
        # preserves the window ID, so the value returned here remains valid
        # after _arrange_tall/_arrange_wide reparents the widget into a splitter.
        #
        # CRITICAL: This widget must NEVER be placed inside a QScrollArea in
        # either the tall or wide arrangement.
        self._video_placeholder = QWidget()
        self._video_placeholder.setObjectName("video_placeholder")
        self._video_placeholder.setMinimumSize(320, 180)
        self._video_placeholder.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_placeholder.setStyleSheet("")
        self._video_placeholder.winId()  # Force native X11 window creation NOW

        # ── Control panel content widget ─────────────────────────────────────
        # Plain widget with no scroll.  _arrange_* wraps it in a QScrollArea.
        self._control_panel_widget = QWidget()
        self._control_panel_widget.setStyleSheet("background-color: transparent;")
        self._build_control_panel()

        # ── Rally strip (nav row + rally list) ───────────────────────────────
        self._rally_strip_widget = QWidget()
        self._build_rally_strip()

        # ── Export / generate widget ─────────────────────────────────────────
        self._export_widget = QWidget()
        self._export_widget.setObjectName("generateContainer")
        self._build_export_widget()

        # ── Splitter references — assigned in _arrange_* ─────────────────────
        self._outer_splitter: QSplitter | None = None
        self._inner_splitter: QSplitter | None = None
        self._master_splitter: QSplitter | None = None

        # Arrangement token — set once in showEvent; guards against re-arrangement.
        self._arrangement: str = ""  # "tall" | "wide"

        # Main widget background
        self.setStyleSheet(f"ReviewModeWidget {{ background-color: {BG_PRIMARY}; }}")

    # =========================================================================
    # Section-widget builders — called once from _init_ui
    # =========================================================================

    def _build_control_panel(self) -> None:
        """Populate ``_control_panel_widget`` with play/flip/timing/score controls."""
        cp_layout = QVBoxLayout(self._control_panel_widget)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(SPACE_MD)

        # Play Rally button (prominent green outline)
        play_rally_button = QPushButton("PLAY RALLY")
        play_rally_button.setIcon(make_icon("play", PRIMARY_ACTION, 16))
        play_rally_button.setIconSize(QSize(16, 16))
        play_rally_button.setFont(Fonts.button_rally())
        play_rally_button.clicked.connect(self._on_play_clicked)
        play_rally_button.setStyleSheet(ButtonStyles.outline(PRIMARY_ACTION, rally_tier=True))
        cp_layout.addWidget(play_rally_button)

        # Flip Winner button
        self._flip_winner_button = QPushButton("Flip Winner")
        self._flip_winner_button.setFont(Fonts.button_other())
        self._flip_winner_button.setObjectName("flipWinnerButton")
        self._flip_winner_button.clicked.connect(self._on_flip_winner_clicked)
        self._flip_winner_button.setToolTip(
            "Swap server/receiver for this rally and recalculate all subsequent scores"
        )
        self._apply_flip_button_style(low_confidence=False)
        cp_layout.addWidget(self._flip_winner_button)

        # Delete / Insert row
        edit_row = QHBoxLayout()
        edit_row.setSpacing(SPACE_SM)

        self._delete_rally_button = QPushButton("Delete Rally")
        self._delete_rally_button.setFont(Fonts.button_other())
        self._delete_rally_button.setObjectName("deleteRallyButton")
        self._delete_rally_button.clicked.connect(self._on_delete_rally_clicked)
        self._delete_rally_button.setToolTip(
            "Remove this rally and recalculate all subsequent scores"
        )
        self._delete_rally_button.setStyleSheet(ButtonStyles.outline(DANGER_TEXT))
        edit_row.addWidget(self._delete_rally_button)

        self._insert_rally_button = QPushButton("Insert Rally After")
        self._insert_rally_button.setFont(Fonts.button_other())
        self._insert_rally_button.setObjectName("insertRallyButton")
        self._insert_rally_button.clicked.connect(self._on_insert_rally_clicked)
        self._insert_rally_button.setToolTip(
            "Insert a new rally after this one with a placeholder timing and score"
        )
        self._insert_rally_button.setStyleSheet(ButtonStyles.compact())
        edit_row.addWidget(self._insert_rally_button)

        cp_layout.addLayout(edit_row)

        # Timing controls
        self._timing_widget = TimingControlWidget()
        self._timing_widget.timing_adjusted.connect(self._on_timing_adjusted)
        cp_layout.addWidget(self._timing_widget)

        # Score editing
        self._score_widget = ScoreEditWidget()
        self._score_widget.score_changed.connect(self._on_score_changed)
        cp_layout.addWidget(self._score_widget)

        cp_layout.addStretch()

    def _build_rally_strip(self) -> None:
        """Populate ``_rally_strip_widget`` with the navigation row and rally list."""
        rs_layout = QVBoxLayout(self._rally_strip_widget)
        rs_layout.setContentsMargins(0, 0, 0, 0)
        rs_layout.setSpacing(SPACE_SM)

        # Navigation header row
        nav_row = QHBoxLayout()
        nav_row.setSpacing(SPACE_MD)

        list_title = QLabel("RALLY LIST (click to navigate)")
        list_title.setFont(Fonts.body(size=12, weight=600))
        list_title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        nav_row.addWidget(list_title)
        nav_row.addStretch()

        # Prev button — promoted to attribute so set_current_rally can disable it.
        self._prev_button = QPushButton("Prev")
        self._prev_button.setIcon(make_icon("chevron-left", TEXT_PRIMARY, 16))
        self._prev_button.setIconSize(QSize(16, 16))
        self._prev_button.setFont(Fonts.button_other())
        self._prev_button.clicked.connect(self._on_previous_clicked)
        self._prev_button.setEnabled(False)
        self._style_nav_button(self._prev_button)
        nav_row.addWidget(self._prev_button)

        # Next button — promoted to attribute so set_current_rally can disable it.
        self._next_button = QPushButton("Next")
        self._next_button.setIcon(make_icon("chevron-right", TEXT_PRIMARY, 16))
        self._next_button.setIconSize(QSize(16, 16))
        self._next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._next_button.setFont(Fonts.button_other())
        self._next_button.clicked.connect(self._on_next_clicked)
        self._next_button.setEnabled(False)
        self._style_nav_button(self._next_button)
        nav_row.addWidget(self._next_button)

        rs_layout.addLayout(nav_row)

        # Rally list widget
        self._rally_list = RallyListWidget()
        self._rally_list.rally_selected.connect(self._on_rally_selected)
        rs_layout.addWidget(self._rally_list)

    def _build_export_widget(self) -> None:
        """Populate ``_export_widget`` with the generate/export container content."""
        ex_layout = QVBoxLayout(self._export_widget)
        ex_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        ex_layout.setSpacing(SPACE_SM)

        # Summary row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(SPACE_SM)
        summary_icon = QLabel()
        summary_icon.setPixmap(make_pixmap("circle-check", TEXT_ACCENT, 16))
        summary_icon.setFixedSize(16, 16)
        summary_row.addWidget(summary_icon)
        summary_label = QLabel("Ready to generate output")
        summary_label.setFont(Fonts.body(size=14, weight=500))
        summary_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        summary_row.addWidget(summary_label)
        summary_row.addStretch()
        ex_layout.addLayout(summary_row)

        # Mark Game Completed checkbox
        self._mark_complete_checkbox = QCheckBox("Mark Game Completed")
        self._mark_complete_checkbox.setFont(Fonts.button_other())
        self._mark_complete_checkbox.toggled.connect(self._on_mark_complete_toggled)
        ex_layout.addWidget(self._mark_complete_checkbox)

        # Final score display (hidden until checkbox checked)
        self._final_score_label = QLabel("")
        self._final_score_label.setFont(Fonts.display(size=16, weight=600))
        self._final_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._final_score_label.hide()
        ex_layout.addWidget(self._final_score_label)

        # Export Options header
        export_header = QLabel("Export Options")
        export_header.setFont(Fonts.body(size=14, weight=600))
        export_header.setStyleSheet(f"color: {TEXT_SECONDARY};")
        ex_layout.addWidget(export_header)

        # Two export cards side by side
        export_cards_layout = QHBoxLayout()
        export_cards_layout.setSpacing(SPACE_MD)

        # === Kdenlive Card ===
        kdenlive_card = QWidget()
        kdenlive_card.setObjectName("kdenliveCard")
        kdenlive_layout = QVBoxLayout(kdenlive_card)
        kdenlive_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        kdenlive_layout.setSpacing(SPACE_SM)

        kdenlive_title = QLabel("Kdenlive Project")
        kdenlive_title.setFont(Fonts.body(size=14, weight=600))
        kdenlive_title.setStyleSheet(f"color: {PRIMARY_ACTION};")
        kdenlive_layout.addWidget(kdenlive_title)

        export_label = QLabel("Export to:")
        export_label.setFont(Fonts.label())
        set_label_role(export_label, "body")
        kdenlive_layout.addWidget(export_label)

        self._export_path_edit = QLineEdit()
        self._export_path_edit.setPlaceholderText("Click Browse or use default...")
        self._export_path_edit.setReadOnly(False)
        self._export_path_edit.textChanged.connect(self._on_export_path_changed)
        self._export_path_edit.setStyleSheet(InputStyles.line_edit())
        kdenlive_layout.addWidget(self._export_path_edit)

        self._browse_button = QPushButton("Browse")
        self._browse_button.setFont(Fonts.button_other())
        self._browse_button.clicked.connect(self._on_browse_clicked)
        self._browse_button.setStyleSheet(ButtonStyles.compact())
        kdenlive_layout.addWidget(self._browse_button)

        kdenlive_layout.addStretch()

        # Generate button — the lone filled-green primary action in this view.
        # Disabled until at least one rally is present (set_rallies enables it).
        self._generate_button = QPushButton("GENERATE PROJECT")
        self._generate_button.setFont(Fonts.button_rally())
        self._generate_button.clicked.connect(self.generate_requested.emit)
        self._generate_button.setStyleSheet(ButtonStyles.primary())
        self._generate_button.setEnabled(False)
        kdenlive_layout.addWidget(self._generate_button)

        kdenlive_card.setStyleSheet(f"""
            QWidget#kdenliveCard {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        kdenlive_card.setMinimumHeight(180)
        export_cards_layout.addWidget(kdenlive_card, 1)

        # === FFmpeg Card ===
        ffmpeg_card = QWidget()
        ffmpeg_card.setObjectName("ffmpegCard")
        ffmpeg_layout = QVBoxLayout(ffmpeg_card)
        ffmpeg_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        ffmpeg_layout.setSpacing(SPACE_SM)

        ffmpeg_title = QLabel("MP4 Video")
        ffmpeg_title.setFont(Fonts.body(size=14, weight=600))
        ffmpeg_title.setStyleSheet(f"color: {SERVER_WINS};")
        ffmpeg_layout.addWidget(ffmpeg_title)

        ffmpeg_desc = QLabel("Ready-to-share output\nwith hardware encoding")
        ffmpeg_desc.setFont(Fonts.label())
        set_label_role(ffmpeg_desc, "body")
        ffmpeg_desc.setWordWrap(True)
        ffmpeg_layout.addWidget(ffmpeg_desc)

        ffmpeg_layout.addStretch()

        # FFmpeg export button — blue outline secondary (not the primary action).
        # Disabled until at least one rally is present (set_rallies enables it).
        self._ffmpeg_button = QPushButton("EXPORT MP4")
        self._ffmpeg_button.setFont(Fonts.button_rally())
        self._ffmpeg_button.clicked.connect(self.export_ffmpeg_requested.emit)
        self._ffmpeg_button.setStyleSheet(ButtonStyles.outline(SERVER_WINS))
        self._ffmpeg_button.setEnabled(False)
        ffmpeg_layout.addWidget(self._ffmpeg_button)

        ffmpeg_card.setStyleSheet(f"""
            QWidget#ffmpegCard {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        ffmpeg_card.setMinimumHeight(140)
        export_cards_layout.addWidget(ffmpeg_card, 1)

        ex_layout.addLayout(export_cards_layout)

        self._export_widget.setStyleSheet(f"""
            QWidget#generateContainer {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self._export_widget.setMinimumHeight(160)

    # =========================================================================
    # Arrangement builders — each called at most ONCE from showEvent
    # =========================================================================

    def _arrange_tall(self) -> None:
        """Assemble the default vertical (tall) arrangement.

        Structure (``_video_placeholder`` is NOT inside any QScrollArea)::

            _outer_splitter (Vertical, childrenCollapsible=False):
              top_section (min 200 px):
                _inner_splitter (Horizontal):
                  _video_placeholder          ← NOT in scroll
                  control_panel_scroll        → _control_panel_widget
              bottom_scroll (QScrollArea, min 330 px):
                bottom_content:
                  _rally_strip_widget
                  _export_widget

        Splitter signal is connected here (not in __init__) because the
        splitter is created here.
        """
        host_layout = self._arrangement_host.layout()

        # Control panel scroll (right of video in the inner splitter)
        control_panel_scroll = QScrollArea()
        control_panel_scroll.setWidgetResizable(True)
        control_panel_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        control_panel_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        control_panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        control_panel_scroll.setMinimumWidth(420)
        control_panel_scroll.setMaximumWidth(720)
        control_panel_scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )
        control_panel_scroll.setWidget(self._control_panel_widget)

        # Inner horizontal splitter: video | controls
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._inner_splitter.setChildrenCollapsible(False)
        self._inner_splitter.addWidget(self._video_placeholder)  # NOT in scroll
        self._inner_splitter.addWidget(control_panel_scroll)
        self._inner_splitter.setSizes([600, 320])
        self._inner_splitter.setStretchFactor(0, 1)  # video stretches
        self._inner_splitter.setStretchFactor(1, 0)  # controls stay

        # Top section wrapper
        top_section = QWidget()
        top_section.setMinimumHeight(200)
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(self._inner_splitter)

        # Bottom scroll area: rally strip + export.
        # Only the bottom section scrolls; the video in the top section stays fixed.
        bottom_content = QWidget()
        bottom_content.setStyleSheet(f"background-color: {BG_PRIMARY};")
        bottom_content_layout = QVBoxLayout(bottom_content)
        bottom_content_layout.setContentsMargins(0, 0, 0, 0)
        bottom_content_layout.setSpacing(SPACE_MD)
        bottom_content_layout.addWidget(self._rally_strip_widget)
        bottom_content_layout.addWidget(self._export_widget)

        bottom_scroll = QScrollArea()
        bottom_scroll.setWidgetResizable(True)
        bottom_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        bottom_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        bottom_scroll.setFrameShape(QFrame.Shape.NoFrame)
        bottom_scroll.setMinimumHeight(330)
        bottom_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {BG_PRIMARY}; border: none; }}"
        )
        bottom_scroll.setWidget(bottom_content)

        # Outer vertical splitter: top section | bottom scroll
        self._outer_splitter = QSplitter(Qt.Orientation.Vertical)
        self._outer_splitter.setChildrenCollapsible(False)
        self._outer_splitter.addWidget(top_section)
        self._outer_splitter.addWidget(bottom_scroll)
        self._outer_splitter.setSizes([300, 400])
        self._outer_splitter.setStretchFactor(0, 1)
        self._outer_splitter.setStretchFactor(1, 0)
        self._outer_splitter.splitterMoved.connect(self._on_splitter_moved)

        host_layout.addWidget(self._outer_splitter)

    def _arrange_wide(self) -> None:
        """Assemble the ultrawide horizontal arrangement.

        Structure (``_video_placeholder`` is NOT inside any QScrollArea)::

            _master_splitter (Horizontal, childrenCollapsible=False):
              left_panel (NOT in scroll, stretchFactor=1):
                _video_placeholder          ← NOT in scroll
                _rally_strip_widget
              right_scroll (QScrollArea, min 460 px):
                right_panel:
                  _control_panel_widget
                  _export_widget

        Only the right column (controls + export) is scrollable.
        The video and rally-list strip are never placed inside a QScrollArea.

        Splitter signal is connected here (not in __init__) because the
        splitter is created here.
        """
        host_layout = self._arrangement_host.layout()

        # Left panel: video (stretch) + rally strip below.
        # Neither widget is inside a scroll area.
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {BG_PRIMARY};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACE_SM)
        left_layout.addWidget(self._video_placeholder, stretch=1)  # NOT in scroll
        left_layout.addWidget(self._rally_strip_widget)

        # Right panel content (placed inside right_scroll below)
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(SPACE_MD, 0, 0, 0)
        right_layout.setSpacing(SPACE_MD)
        right_layout.addWidget(self._control_panel_widget)
        right_layout.addWidget(self._export_widget)
        right_layout.addStretch()

        # Right scroll area — the ONLY scrollable region in wide mode
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setMinimumWidth(460)
        right_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {BG_SECONDARY}; border: none; }}"
        )
        right_scroll.setWidget(right_panel)

        # Master horizontal splitter: left panel | right scroll
        self._master_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._master_splitter.setChildrenCollapsible(False)
        self._master_splitter.addWidget(left_panel)
        self._master_splitter.addWidget(right_scroll)
        self._master_splitter.setStretchFactor(0, 1)  # video side stretches
        self._master_splitter.setStretchFactor(1, 0)  # controls column fixed
        self._master_splitter.splitterMoved.connect(self._on_splitter_moved)

        host_layout.addWidget(self._master_splitter)

    # =========================================================================
    # Navigation button styling
    # =========================================================================

    def _style_nav_button(self, button: QPushButton) -> None:
        """Apply consistent styling to navigation buttons.

        Uses the ``nav`` property class from theme.qss
        (QPushButton[buttonClass="nav"]) which provides min-width 100px,
        36px height, and green focus ring.

        Args:
            button: Button to style
        """
        set_class(button, "nav")

    # =========================================================================
    # Show event — decides and freezes the arrangement
    # =========================================================================

    def showEvent(self, event: QShowEvent) -> None:
        """Choose and build the arrangement ONCE at review entry.

        The arrangement is frozen for the remainder of the review session.
        Re-arrangement is deliberately not supported across resizes within a
        review session: mpv native-window reparenting is fragile and repeated
        enter→exit→enter cycles may cause native-window regressions.

        The window aspect ratio at the moment ``showEvent`` fires determines
        which arrangement is built.  If ``width / height >= ASPECT_ULTRAWIDE``
        (2.0), the wide horizontal arrangement is used; otherwise the tall
        vertical arrangement is used.

        Splitter sizes are applied after the arrangement is built: persisted
        sizes from DisplayConfig take precedence; proportional defaults are
        used otherwise.
        """
        super().showEvent(event)

        # Build the arrangement exactly once.
        if not self._arrangement:
            window = self.window()
            w = window.width()
            h = window.height()
            if h > 0 and (w / h) >= ASPECT_ULTRAWIDE:
                self._arrange_wide()
                self._arrangement = "wide"
            else:
                self._arrange_tall()
                self._arrangement = "tall"

        # Apply splitter sizes (persisted → proportional default).
        _display = getattr(self._app_settings, "display", None)

        if self._arrangement == "wide" and self._master_splitter is not None:
            _h_sizes = getattr(_display, "review_splitter_h", []) if _display else []
            if _h_sizes and len(_h_sizes) == 2 and sum(_h_sizes) > 0:
                self._master_splitter.setSizes(list(_h_sizes))
                return
            # Default: video side ~60%, controls column ~40% (min 460 px).
            _avail_w = self._arrangement_host.width()
            if _avail_w > 0:
                _right_w = max(460, int(_avail_w * 0.40))
                _left_w = max(400, _avail_w - _right_w)
                self._master_splitter.setSizes([_left_w, _right_w])

        elif self._arrangement == "tall" and self._outer_splitter is not None:
            _v_sizes = getattr(_display, "review_splitter_v", []) if _display else []
            if _v_sizes and len(_v_sizes) == 2 and sum(_v_sizes) > 0:
                self._outer_splitter.setSizes(list(_v_sizes))
                return
            # Default: 65 / 35 top/bottom proportional split.
            _avail_h = self._arrangement_host.height()
            if _avail_h > 0:
                _top_h = max(200, int(_avail_h * 0.65))
                _bot_h = max(330, _avail_h - _top_h)
                self._outer_splitter.setSizes([_top_h, _bot_h])

    @pyqtSlot(int, int)
    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Restart the save-debounce timer when any active splitter is dragged."""
        self._splitter_save_timer.start()

    def _save_splitter_sizes(self) -> None:
        """Write the active splitter sizes to DisplayConfig and persist."""
        _display = getattr(self._app_settings, "display", None)
        if _display is None:
            return
        if self._arrangement == "tall" and self._outer_splitter is not None:
            if hasattr(_display, "review_splitter_v"):
                _display.review_splitter_v = self._outer_splitter.sizes()
                self._app_settings.save()
        elif self._arrangement == "wide" and self._master_splitter is not None:
            if hasattr(_display, "review_splitter_h"):
                _display.review_splitter_h = self._master_splitter.sizes()
                self._app_settings.save()

    @pyqtSlot(str, float)
    def _on_timing_adjusted(self, field: str, delta: float) -> None:
        """Handle timing adjustment from TimingControlWidget.

        Args:
            field: "start" or "end"
            delta: Time change in seconds
        """
        self.timing_adjusted.emit(self._current_index, field, delta)

    @pyqtSlot(str, bool)
    def _on_score_changed(self, new_score: str, cascade: bool) -> None:
        """Handle score change from ScoreEditWidget.

        Args:
            new_score: New score string
            cascade: Whether to cascade changes
        """
        self.score_changed.emit(self._current_index, new_score, cascade)

    @pyqtSlot()
    def _on_flip_winner_clicked(self) -> None:
        """Handle Flip Winner button click.

        Emits winner_flipped with the current rally index so MainWindow can
        update rally_manager and cascade scores.
        """
        self.winner_flipped.emit(self._current_index)

    @pyqtSlot()
    def _on_delete_rally_clicked(self) -> None:
        """Handle Delete Rally button click.

        Emits delete_rally_requested with the current rally index so MainWindow
        can confirm, delete from rally_manager, and cascade scores.
        """
        self.delete_rally_requested.emit(self._current_index)

    @pyqtSlot()
    def _on_insert_rally_clicked(self) -> None:
        """Handle Insert Rally After button click.

        Emits insert_rally_requested with the current rally index so MainWindow
        can build a placeholder rally, insert it, and cascade scores.
        """
        self.insert_rally_requested.emit(self._current_index)

    def _apply_flip_button_style(self, low_confidence: bool) -> None:
        """Apply styling to the Flip Winner button.

        When low_confidence is True the button uses the orange/amber palette
        to draw the user's attention to an uncertain classification.

        Args:
            low_confidence: Whether the current rally has a low-confidence winner
        """
        if low_confidence:
            border_color = RECEIVER_WINS      # orange — draws attention to uncertain call
        else:
            border_color = SERVER_WINS        # blue — neutral / informational

        # ButtonStyles.outline rules scope to this widget; QPushButton {} inside
        # the factory string matches only _flip_winner_button itself.
        self._flip_winner_button.setStyleSheet(ButtonStyles.outline(border_color))

    def set_low_confidence_indices(self, indices: set[int]) -> None:
        """Mark specific rally indices as having low-confidence winner classifications.

        The Flip Winner button will be shown with a more prominent orange style
        when the currently displayed rally is in this set.

        Args:
            indices: Set of rally indices (0-based) that have low confidence
        """
        self._low_confidence_indices = indices
        # Re-style button if the current rally is affected
        low_conf = self._current_index in self._low_confidence_indices
        self._apply_flip_button_style(low_confidence=low_conf)

    def get_low_confidence_indices(self) -> set[int]:
        """Return the current set of low-confidence rally indices.

        Returns:
            Copy of the set so callers cannot accidentally mutate internal state.
        """
        return set(self._low_confidence_indices)

    @pyqtSlot(int)
    def _on_rally_selected(self, index: int) -> None:
        """Handle rally selection from RallyListWidget.

        Args:
            index: Rally index (0-based)
        """
        self.set_current_rally(index)

    @pyqtSlot()
    def _on_previous_clicked(self) -> None:
        """Handle previous button click."""
        if self._current_index > 0:
            self.set_current_rally(self._current_index - 1)
            self.navigate_previous.emit()

    @pyqtSlot()
    def _on_next_clicked(self) -> None:
        """Handle next button click."""
        if self._current_index < len(self._rallies) - 1:
            self.set_current_rally(self._current_index + 1)
            self.navigate_next.emit()

    @pyqtSlot()
    def _on_play_clicked(self) -> None:
        """Handle play rally button click."""
        self.play_rally_requested.emit(self._current_index)

    def set_rallies(
        self,
        rallies: list[Rally],
        fps: float = 60.0,
        is_highlights: bool = False,
        game_mode: str = "doubles",
    ) -> None:
        """Populate the review mode with rallies.

        Args:
            rallies: List of Rally objects.
            fps: Video frames per second for time calculations.
            is_highlights: If True, hide score-related controls.
            game_mode: Score format — ``"doubles"`` (X-Y-Z), ``"singles"``
                       (X-Y), or ``"highlights"`` (no score).  Controls which
                       regex pattern the ScoreEditWidget validator uses.
        """
        self._rallies = rallies
        self._fps = fps
        self._is_highlights = is_highlights

        # Hide score widget in highlights mode; otherwise update the validator.
        if is_highlights:
            self._score_widget.hide()
        else:
            self._score_widget.show()
            self._score_widget.set_mode(game_mode)

        # Enable export buttons and delete button only when there is at least one rally.
        has_rallies = len(rallies) > 0
        self._generate_button.setEnabled(has_rallies)
        self._ffmpeg_button.setEnabled(has_rallies)
        self._delete_rally_button.setEnabled(has_rallies)
        _no_rallies_tip = "Add at least one rally to export"
        self._generate_button.setToolTip("" if has_rallies else _no_rallies_tip)
        self._ffmpeg_button.setToolTip("" if has_rallies else _no_rallies_tip)

        self._rally_list.set_rallies(rallies)
        if rallies:
            self.set_current_rally(0)

    def set_current_rally(self, index: int) -> None:
        """Set the currently displayed rally.

        Args:
            index: Rally index (0-based)
        """
        if not (0 <= index < len(self._rallies)):
            return

        self._current_index = index
        rally = self._rallies[index]

        # Update header (pass post-game flag for visual indicator)
        self._header.set_rally(index, len(self._rallies), is_post_game=rally.is_post_game)

        # Update timing controls (convert frames to seconds using actual fps)
        start_seconds = rally.start_frame / self._fps
        end_seconds = rally.end_frame / self._fps
        self._timing_widget.set_times(start_seconds, end_seconds)

        # Update score widget
        self._score_widget.set_current_score(rally.score_at_start)

        # Update rally list selection
        self._rally_list.set_current_rally(index)

        # Refresh Flip Winner button styling based on low-confidence flag
        low_conf = index in self._low_confidence_indices
        self._apply_flip_button_style(low_confidence=low_conf)

        # Disable Prev/Next at list boundaries so keyboard/click never navigates
        # past the first or last rally.
        self._prev_button.setEnabled(index > 0)
        self._next_button.setEnabled(index < len(self._rallies) - 1)

        # Emit signal
        self.rally_changed.emit(index)

    def get_current_rally_index(self) -> int:
        """Get the current rally index.

        Returns:
            Current rally index (0-based)
        """
        return self._current_index

    def navigate_to_previous(self) -> None:
        """Navigate to the previous rally."""
        if self._current_index > 0:
            self.set_current_rally(self._current_index - 1)

    def navigate_to_next(self) -> None:
        """Navigate to the next rally."""
        if self._current_index < len(self._rallies) - 1:
            self.set_current_rally(self._current_index + 1)

    def get_video_placeholder(self) -> QWidget:
        """Get the video placeholder widget for external embedding.

        MainWindow can use this to parent the video widget inside the review mode.

        Returns:
            Video placeholder widget
        """
        return self._video_placeholder

    def get_inner_splitter(self) -> QSplitter | None:
        """Get the inner horizontal splitter (tall arrangement only).

        Returns:
            Inner QSplitter (horizontal) in tall mode; None in wide mode or
            before the first showEvent.
        """
        return self._inner_splitter

    def get_outer_splitter(self) -> QSplitter | None:
        """Get the outer vertical splitter (tall arrangement only).

        Returns:
            Outer QSplitter (vertical) in tall mode; None in wide mode or
            before the first showEvent.
        """
        return self._outer_splitter

    @pyqtSlot(bool)
    def _on_mark_complete_toggled(self, checked: bool) -> None:
        """Handle Mark Game Completed checkbox toggle."""
        self._game_completed = checked
        if checked:
            self._final_score_label.show()
        else:
            self._final_score_label.hide()
        self.game_completed_toggled.emit(checked)

    def set_game_completion_info(
        self,
        final_score: str,
        winning_team_names: list[str]
    ) -> None:
        """Set the game completion display info."""
        self._final_score = final_score
        self._winning_team_names = winning_team_names

        # Format display: "11-9\nJane/Joe Win"
        if winning_team_names:
            winner_str = " & ".join(winning_team_names) + " Win"
        else:
            winner_str = ""

        display_text = final_score
        if winner_str:
            display_text += f"\n{winner_str}"
        self._final_score_label.setText(display_text)

    def is_game_completed(self) -> bool:
        """Check if game is marked as completed."""
        return self._game_completed

    def get_game_completion_info(self) -> tuple[str, list[str]]:
        """Get game completion info for export."""
        return self._final_score, self._winning_team_names

    def hide_game_completion_controls(self) -> None:
        """Hide game completion controls (for highlights mode)."""
        self._mark_complete_checkbox.hide()
        self._final_score_label.hide()

    def set_game_completed(self, checked: bool, announce: bool = False) -> None:
        """Set the mark-complete checkbox state and optionally announce via a toast.

        This is the public API for external callers (e.g. MainWindow auto-detecting
        a game-over score).  Prefer this over reaching into ``_mark_complete_checkbox``
        directly.

        When ``announce`` is ``True`` and the game is being marked complete, an
        info toast is shown prompting the user to verify the detected result.

        Args:
            checked: Whether the game should be marked as completed.
            announce: When ``True`` and ``checked`` is ``True``, show an info
                      toast with the final score detected.
        """
        self._mark_complete_checkbox.setChecked(checked)
        if announce and checked and self._final_score:
            message = (
                f"Game complete detected — final score {self._final_score}. "
                "Uncheck 'Mark Game Completed' if this is wrong."
            )
            ToastManager.show_info(self, message)

    @pyqtSlot()
    def _on_browse_clicked(self) -> None:
        """Handle Browse button click - open file dialog for export path."""
        from pathlib import Path

        default_dir = str(Path.home() / "Videos")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Export Location",
            default_dir,
            "Kdenlive Project (*.kdenlive);;All Files (*)"
        )

        if file_path:
            self._export_path_edit.setText(file_path)

    @pyqtSlot(str)
    def _on_export_path_changed(self, path: str) -> None:
        """Handle export path text changes."""
        self._export_path = path
        self.export_path_changed.emit(path)

    def get_export_path(self) -> str:
        """Get the currently set export path.

        Returns:
            Export path string, or empty string if not set
        """
        return self._export_path

    def set_export_path(self, path: str) -> None:
        """Set the export path display.

        Args:
            path: Path to display in the export path field
        """
        self._export_path = path
        self._export_path_edit.setText(path)
