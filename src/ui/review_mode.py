"""Final Review Mode UI for Pickleball Video Editor.

This module provides the ReviewModeWidget and its sub-components for verifying
and adjusting rally timings before generating Kdenlive output.

Components:
- RallyHeaderWidget: Shows "RALLY X OF Y" with progress indicator
- TimingControlWidget: Adjust rally start/end times with configurable-step nudge
  buttons and direct numeric entry fields
- WinnerControlWidget: Explicit serving-team / returning-team winner selection
- StateAnchorWidget: Set serving team and score at start of rally (always cascades)
- RallyListWidget: Horizontal scrolling list of rally cards (QListWidget IconMode)
- ReviewModeWidget: Main container composing all components

The Review Mode replaces the Rally Controls and Toolbar sections when activated
from the Main Window's "Final Review" button.
"""

import re

from PyQt6.QtCore import Qt, QSize, QTimer, QRegularExpression, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QRegularExpressionValidator, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    BG_BORDER_HOVER,
    BG_HOVER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    FOCUS_RING,
    PRIMARY_ACTION,
    PRIMARY_ACTION_TINT,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    RECEIVER_WINS,
    SERVER_WINS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_ACCENT,
    TEXT_DISABLED,
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
    "WinnerControlWidget",
    "StateAnchorWidget",
    "RallyListWidget",
    "ReviewModeWidget",
]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

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


# Module-level compiled regexes for _parse_time_input (LBYL — no try/except for flow).
# _COLON_TIME_RE: "digits:digits[.digits]" — MM:SS or MM:SS.s format.
# _PLAIN_NUM_RE:  non-negative integer or decimal — plain seconds.
_COLON_TIME_RE = re.compile(r'^\d+:(\d*\.?\d+)$')
_PLAIN_NUM_RE = re.compile(r'^\d+(?:\.\d+)?$')


def _parse_time_input(text: str) -> float | None:
    """Parse a user-entered time string into seconds.

    Accepts:
    - Plain float seconds: ``"42.5"`` → 42.5
    - MM:SS or MM:SS.s: ``"00:42.5"`` → 42.5, ``"1:23"`` → 83.0
    - Returns ``None`` on empty input, non-numeric input, negative values,
      or colon-format with seconds >= 60.
    """
    text = text.strip()
    if not text:
        return None
    m = _COLON_TIME_RE.match(text)
    if m:
        secs = float(m.group(1))
        if secs >= 60:
            return None
        minutes = int(text.split(":", 1)[0])
        return minutes * 60 + secs
    if _PLAIN_NUM_RE.match(text):
        return float(text)
    return None


# ---------------------------------------------------------------------------
# Step-selector QSS (used by TimingControlWidget combo)
# ---------------------------------------------------------------------------
_COMBO_QSS = f"""
QComboBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: {RADIUS_SM}px;
    padding: 4px 8px;
    min-height: 26px;
    min-width: 72px;
}}
QComboBox:hover {{
    border-color: {BG_BORDER_HOVER};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER_COLOR};
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
    color: {TEXT_PRIMARY};
    outline: none;
}}
"""

# QSS for the mutually-exclusive team-selector buttons in StateAnchorWidget
_TEAM_BTN_QSS = f"""
QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: {RADIUS_SM}px;
    padding: 5px 10px;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {BG_BORDER_HOVER};
}}
QPushButton:checked {{
    background-color: transparent;
    color: {PRIMARY_ACTION};
    border: 2px solid {PRIMARY_ACTION};
}}
QPushButton:checked:hover {{
    background-color: {PRIMARY_ACTION};
    color: {BG_PRIMARY};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER_COLOR};
    background-color: {BG_TERTIARY};
}}
"""


# ===========================================================================
# RallyHeaderWidget
# ===========================================================================

class RallyHeaderWidget(QWidget):
    """Header showing current rally progress with "RALLY X OF Y" display.

    Displays:
    - Large "FINAL REVIEW MODE" title and rally counter
    - Exit Review button and Return to Main Menu button

    Signals:
        exit_requested(): User clicked Exit Review button
        return_to_menu_requested(): User clicked Return to Main Menu button
    """

    exit_requested = pyqtSignal()
    return_to_menu_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_rally = 0
        self._total_rallies = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.setSpacing(SPACE_MD)

        self._title_label = QLabel("FINAL REVIEW MODE")
        self._title_label.setFont(Fonts.dialog_title())
        self._title_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        layout.addWidget(self._title_label)

        self._counter_label = QLabel("Rally 0 of 0")
        self._counter_label.setFont(Fonts.body(size=16, weight=600))
        layout.addWidget(self._counter_label)

        layout.addStretch()

        self._return_to_menu_button = QPushButton("Main Menu")
        self._return_to_menu_button.setFont(Fonts.button_other())
        self._return_to_menu_button.clicked.connect(self.return_to_menu_requested.emit)
        set_class(self._return_to_menu_button, "secondary")
        layout.addWidget(self._return_to_menu_button)

        self._exit_button = QPushButton("Exit Review")
        self._exit_button.setFont(Fonts.button_other())
        self._exit_button.clicked.connect(self.exit_requested.emit)
        set_class(self._exit_button, "secondary")
        layout.addWidget(self._exit_button)

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
        suffix = " (post-game)" if is_post_game else ""
        self._counter_label.setText(f"Rally {current + 1} of {total}{suffix}")


# ===========================================================================
# TimingControlWidget
# ===========================================================================

class TimingControlWidget(QWidget):
    """Widget for adjusting rally start/end times.

    Features:
    - Configurable nudge step (0.1 / 0.25 / 0.5 / 1.0 s) via combo selector
    - ±step nudge buttons (labels update when step changes)
    - Direct numeric entry QLineEdits for start, end, and duration
      (duration edits adjust end = start + duration)
    - Offset captions and Reset button (unchanged behaviour)

    Signals:
        timing_adjusted(str, float): Nudge applied — (field "start"|"end", delta)
        timing_set(str, float): Direct entry committed — (field "start"|"end",
            absolute_seconds)
    """

    timing_adjusted = pyqtSignal(str, float)
    timing_set = pyqtSignal(str, float)

    _STEP_OPTIONS: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0)
    _STEP_LABELS: tuple[str, ...] = ("0.1 s", "0.25 s", "0.5 s", "1.0 s")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_time = 0.0
        self._end_time = 0.0
        self._orig_start = 0.0
        self._orig_end = 0.0
        self._step = self._STEP_OPTIONS[0]
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # -- Section title ---------------------------------------------------
        title = QLabel("TIMING")
        title.setFont(Fonts.section_label())
        title.setText(title.text().upper())
        set_label_role(title, "sectionLabel")
        layout.addWidget(title)

        # -- Step selector row -----------------------------------------------
        step_row = QHBoxLayout()
        step_row.setSpacing(SPACE_SM)
        step_row.addStretch()
        step_label = QLabel("Step:")
        step_label.setFont(Fonts.label())
        set_label_role(step_label, "body")
        step_row.addWidget(step_label)

        self._step_combo = QComboBox()
        self._step_combo.addItems(list(self._STEP_LABELS))
        self._step_combo.setFont(Fonts.label())
        self._step_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._step_combo.setStyleSheet(_COMBO_QSS)
        self._step_combo.currentIndexChanged.connect(self._on_step_changed)
        step_row.addWidget(self._step_combo)
        layout.addLayout(step_row)

        # -- Main controls grid ----------------------------------------------
        controls_layout = QGridLayout()
        controls_layout.setSpacing(SPACE_MD)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(4, 1)

        # Row 0 — labels + direct-entry fields
        start_label = QLabel("START")
        start_label.setFont(Fonts.label())
        set_label_role(start_label, "body")
        controls_layout.addWidget(start_label, 0, 0)

        self._start_entry = QLineEdit("00:00.0")
        self._start_entry.setFont(Fonts.timestamp())
        self._start_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._start_entry.setToolTip("Enter time as MM:SS.s or raw seconds")
        self._start_entry.setStyleSheet(InputStyles.line_edit())
        self._start_entry.editingFinished.connect(self._on_start_entry_committed)
        controls_layout.addWidget(self._start_entry, 0, 1)

        end_label = QLabel("END")
        end_label.setFont(Fonts.label())
        set_label_role(end_label, "body")
        controls_layout.addWidget(end_label, 0, 3)

        self._end_entry = QLineEdit("00:00.0")
        self._end_entry.setFont(Fonts.timestamp())
        self._end_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._end_entry.setToolTip("Enter time as MM:SS.s or raw seconds")
        self._end_entry.setStyleSheet(InputStyles.line_edit())
        self._end_entry.editingFinished.connect(self._on_end_entry_committed)
        controls_layout.addWidget(self._end_entry, 0, 4)

        # Row 1 — offset captions (hidden until timing is modified)
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

        # Row 2 — nudge buttons (labels update with step)
        self._start_minus_btn = QPushButton("-0.1 s")
        self._start_minus_btn.setFont(Fonts.button_other())
        self._start_minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._start_minus_btn.clicked.connect(lambda: self._adjust_start(-1))
        self._style_adjust_button(self._start_minus_btn)
        controls_layout.addWidget(self._start_minus_btn, 2, 0)

        self._start_plus_btn = QPushButton("+0.1 s")
        self._start_plus_btn.setFont(Fonts.button_other())
        self._start_plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._start_plus_btn.clicked.connect(lambda: self._adjust_start(1))
        self._style_adjust_button(self._start_plus_btn)
        controls_layout.addWidget(self._start_plus_btn, 2, 1)

        self._end_minus_btn = QPushButton("-0.1 s")
        self._end_minus_btn.setFont(Fonts.button_other())
        self._end_minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._end_minus_btn.clicked.connect(lambda: self._adjust_end(-1))
        self._style_adjust_button(self._end_minus_btn)
        controls_layout.addWidget(self._end_minus_btn, 2, 3)

        self._end_plus_btn = QPushButton("+0.1 s")
        self._end_plus_btn.setFont(Fonts.button_other())
        self._end_plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._end_plus_btn.clicked.connect(lambda: self._adjust_end(1))
        self._style_adjust_button(self._end_plus_btn)
        controls_layout.addWidget(self._end_plus_btn, 2, 4)

        # Row 3 — duration entry + reset
        duration_label = QLabel("DURATION")
        duration_label.setFont(Fonts.label())
        set_label_role(duration_label, "body")
        controls_layout.addWidget(duration_label, 3, 0)

        self._duration_entry = QLineEdit("00:00.0")
        self._duration_entry.setFont(Fonts.timestamp())
        self._duration_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._duration_entry.setToolTip("Edit duration to move end time (end = start + duration)")
        self._duration_entry.setStyleSheet(InputStyles.line_edit())
        self._duration_entry.editingFinished.connect(self._on_duration_entry_committed)
        controls_layout.addWidget(self._duration_entry, 3, 1)

        self._reset_button = QPushButton("Reset")
        self._reset_button.setFont(Fonts.button_other())
        self._reset_button.setToolTip("Restore original timing")
        self._reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reset_button.clicked.connect(self._on_reset_clicked)
        self._reset_button.setStyleSheet(ButtonStyles.compact())
        self._reset_button.setEnabled(False)
        controls_layout.addWidget(self._reset_button, 3, 3, 1, 2)

        layout.addLayout(controls_layout)

        self.setStyleSheet(f"""
            TimingControlWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    def _style_adjust_button(self, button: QPushButton) -> None:
        button.setStyleSheet(ButtonStyles.compact())

    # -- Step selector -------------------------------------------------------

    @pyqtSlot(int)
    def _on_step_changed(self, index: int) -> None:
        """Update step value and nudge-button labels when combo selection changes."""
        if 0 <= index < len(self._STEP_OPTIONS):
            self._step = self._STEP_OPTIONS[index]
            lbl = self._STEP_LABELS[index]
            self._start_minus_btn.setText(f"-{lbl}")
            self._start_plus_btn.setText(f"+{lbl}")
            self._end_minus_btn.setText(f"-{lbl}")
            self._end_plus_btn.setText(f"+{lbl}")

    # -- Nudge actions -------------------------------------------------------

    def _adjust_start(self, multiplier: float) -> None:
        """Apply a nudge to start time.  multiplier is +1 or -1."""
        delta = self._step * multiplier
        self._start_time += delta
        if self._start_time < 0.0:
            self._start_time = 0.0
        self._sync_entry_fields()
        self._check_modified()
        self.timing_adjusted.emit("start", delta)

    def _adjust_end(self, multiplier: float) -> None:
        """Apply a nudge to end time.  multiplier is +1 or -1."""
        delta = self._step * multiplier
        self._end_time += delta
        if self._end_time < self._start_time:
            self._end_time = self._start_time
        self._sync_entry_fields()
        self._check_modified()
        self.timing_adjusted.emit("end", delta)

    # -- Direct-entry handlers -----------------------------------------------

    @pyqtSlot()
    def _on_start_entry_committed(self) -> None:
        """Parse the start entry and emit timing_set if value changed."""
        text = self._start_entry.text().strip()
        value = _parse_time_input(text)
        if value is None:
            # Restore display to the current internal value
            self._sync_entry_fields()
            return
        value = max(0.0, min(value, self._end_time))
        if abs(value - self._start_time) < 1e-6:
            self._sync_entry_fields()
            return
        self._start_time = value
        self._sync_entry_fields()
        self._check_modified()
        self.timing_set.emit("start", self._start_time)

    @pyqtSlot()
    def _on_end_entry_committed(self) -> None:
        """Parse the end entry and emit timing_set if value changed."""
        text = self._end_entry.text().strip()
        value = _parse_time_input(text)
        if value is None:
            self._sync_entry_fields()
            return
        value = max(self._start_time, value)
        if abs(value - self._end_time) < 1e-6:
            self._sync_entry_fields()
            return
        self._end_time = value
        self._sync_entry_fields()
        self._check_modified()
        self.timing_set.emit("end", self._end_time)

    @pyqtSlot()
    def _on_duration_entry_committed(self) -> None:
        """Parse the duration entry, translate to new end time, emit timing_set."""
        text = self._duration_entry.text().strip()
        value = _parse_time_input(text)
        if value is None or value < 0:
            self._sync_entry_fields()
            return
        new_end = self._start_time + value
        if abs(new_end - self._end_time) < 1e-6:
            self._sync_entry_fields()
            return
        self._end_time = new_end
        self._sync_entry_fields()
        self._check_modified()
        self.timing_set.emit("end", self._end_time)

    # -- Reset ---------------------------------------------------------------

    @pyqtSlot()
    def _on_reset_clicked(self) -> None:
        """Restore start/end to the originals stored when the rally was loaded.

        Emits corrective ``timing_adjusted`` deltas so the parent and model
        stay in sync.
        """
        start_corrective = self._orig_start - self._start_time
        end_corrective = self._orig_end - self._end_time

        self._start_time = self._orig_start
        self._end_time = self._orig_end
        self._sync_entry_fields()
        self._check_modified()

        if start_corrective != 0.0:
            self.timing_adjusted.emit("start", start_corrective)
        if end_corrective != 0.0:
            self.timing_adjusted.emit("end", end_corrective)

    # -- Display sync --------------------------------------------------------

    def _sync_entry_fields(self) -> None:
        """Update all three QLineEdit fields from _start_time/_end_time.

        Signals are blocked during the update to prevent recursive commits.
        """
        duration = max(0.0, self._end_time - self._start_time)
        for widget, value in (
            (self._start_entry, self._start_time),
            (self._end_entry, self._end_time),
            (self._duration_entry, duration),
        ):
            widget.blockSignals(True)
            widget.setText(_format_time(value))
            widget.blockSignals(False)

    def _check_modified(self) -> None:
        """Update Reset button state and offset captions based on delta from originals."""
        start_delta = round(self._start_time - self._orig_start, 3)
        end_delta = round(self._end_time - self._orig_end, 3)

        is_modified = start_delta != 0.0 or end_delta != 0.0
        self._reset_button.setEnabled(is_modified)

        if start_delta != 0.0:
            sign = "+" if start_delta > 0 else ""
            self._start_offset_label.setText(f"{sign}{start_delta:.2f}s from original")
            self._start_offset_label.show()
        else:
            self._start_offset_label.hide()

        if end_delta != 0.0:
            sign = "+" if end_delta > 0 else ""
            self._end_offset_label.setText(f"{sign}{end_delta:.2f}s from original")
            self._end_offset_label.show()
        else:
            self._end_offset_label.hide()

    # -- Public API ----------------------------------------------------------

    def set_times(self, start_seconds: float, end_seconds: float) -> None:
        """Set and display the start and end times.

        Stores the provided values as the originals for the current rally
        so Reset and offset captions have a reference point.

        Args:
            start_seconds: Rally start time in seconds
            end_seconds: Rally end time in seconds
        """
        self._start_time = start_seconds
        self._end_time = end_seconds
        self._orig_start = start_seconds
        self._orig_end = end_seconds
        self._sync_entry_fields()
        self._check_modified()


# ===========================================================================
# WinnerControlWidget
# ===========================================================================

class WinnerControlWidget(QWidget):
    """Explicit two-option winner selection control.

    Replaces the single "Flip Winner" button.  Displays two buttons labeled
    with the actual team names derived from the current rally's
    ``score_snapshot_at_start.serving_team`` field:

    - "Team X Won" → emits winner_selected("server")
    - "Team Y Won" → emits winner_selected("receiver")

    Low-confidence rallies are highlighted with an amber border on both
    buttons (amber = RECEIVER_WINS; normal = SERVER_WINS).

    Signals:
        winner_selected(str): ``"server"`` or ``"receiver"``
    """

    winner_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._low_confidence = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section label
        title = QLabel("WINNER")
        title.setFont(Fonts.section_label())
        title.setText(title.text().upper())
        set_label_role(title, "sectionLabel")
        layout.addWidget(title)

        # Read-only serving-team info line
        self._serving_info_label = QLabel("Serving: —")
        self._serving_info_label.setFont(Fonts.secondary())
        self._serving_info_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        layout.addWidget(self._serving_info_label)

        # Two winner buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_SM)

        self._server_btn = QPushButton("Serving Team Won")
        self._server_btn.setFont(Fonts.button_other())
        self._server_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._server_btn.setToolTip("Mark the currently serving team as the winner")
        self._server_btn.clicked.connect(lambda: self.winner_selected.emit("server"))
        btn_row.addWidget(self._server_btn)

        self._receiver_btn = QPushButton("Returning Team Won")
        self._receiver_btn.setFont(Fonts.button_other())
        self._receiver_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._receiver_btn.setToolTip("Mark the returning (non-serving) team as the winner")
        self._receiver_btn.clicked.connect(lambda: self.winner_selected.emit("receiver"))
        btn_row.addWidget(self._receiver_btn)

        layout.addLayout(btn_row)

        # Container styling
        self.setStyleSheet(f"""
            WinnerControlWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        # Apply initial button style (normal, not low-confidence)
        self._apply_button_style()

    def _apply_button_style(self) -> None:
        """Style both winner buttons based on the current low-confidence flag."""
        color = RECEIVER_WINS if self._low_confidence else SERVER_WINS
        self._server_btn.setStyleSheet(ButtonStyles.outline(color))
        self._receiver_btn.setStyleSheet(ButtonStyles.outline(color))

    # -- Public API ----------------------------------------------------------

    def set_teams(self, serving_name: str, returning_name: str) -> None:
        """Update button labels and info display for the current rally.

        Args:
            serving_name: Display name for the serving team (e.g. "Alice & Bob")
            returning_name: Display name for the returning team
        """
        self._server_btn.setText(f"{serving_name} Won")
        self._receiver_btn.setText(f"{returning_name} Won")
        self._serving_info_label.setText(f"Serving: {serving_name}")

    def set_low_confidence(self, low: bool) -> None:
        """Toggle amber / blue styling for low-confidence rally classifications.

        Args:
            low: True → amber RECEIVER_WINS border; False → blue SERVER_WINS border
        """
        self._low_confidence = low
        self._apply_button_style()


# ===========================================================================
# StateAnchorWidget  (replaces ScoreEditWidget)
# ===========================================================================

class StateAnchorWidget(QWidget):
    """Control for setting the game state (serving team + score) at rally start.

    Always cascades to later rallies — the cascade checkbox from the previous
    ScoreEditWidget has been removed.  MainWindow is responsible for cascade logic.

    Validation follows the same regex patterns as the old ScoreEditWidget:
    - doubles:  ``^\\d{1,2}-\\d{1,2}-[12]$``
    - singles / highlights: ``^\\d{1,2}-\\d{1,2}$``

    The Apply button is disabled until the score field contains a valid value.
    An inline error label appears for invalid (non-empty) input.

    Signals:
        state_anchor_applied(int, str): (serving_team 0|1, score_string)
            Emitted when the user clicks Apply with a valid score.
    """

    state_anchor_applied = pyqtSignal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game_mode = "doubles"
        self._serving_team = 0
        self._team1_name = "Team 1"
        self._team2_name = "Team 2"
        self._validator: QRegularExpressionValidator | None = None
        self._init_ui()
        self._update_validator()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section label
        title = QLabel("GAME STATE")
        title.setFont(Fonts.section_label())
        title.setText(title.text().upper())
        set_label_role(title, "sectionLabel")
        layout.addWidget(title)

        # Sub-heading clarifying the action
        subtitle = QLabel("Set score and serving team at start of rally")
        subtitle.setFont(Fonts.secondary())
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        layout.addWidget(subtitle)

        # Serving-team selector
        team_header = QLabel("Serving team:")
        team_header.setFont(Fonts.label())
        set_label_role(team_header, "body")
        layout.addWidget(team_header)

        team_btn_row = QHBoxLayout()
        team_btn_row.setSpacing(SPACE_SM)

        self._team1_btn = QPushButton("Team 1")
        self._team1_btn.setCheckable(True)
        self._team1_btn.setChecked(True)
        self._team1_btn.setFont(Fonts.button_other())
        self._team1_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._team1_btn.setStyleSheet(_TEAM_BTN_QSS)
        self._team1_btn.clicked.connect(lambda: self._set_serving_team(0))
        team_btn_row.addWidget(self._team1_btn)

        self._team2_btn = QPushButton("Team 2")
        self._team2_btn.setCheckable(True)
        self._team2_btn.setChecked(False)
        self._team2_btn.setFont(Fonts.button_other())
        self._team2_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._team2_btn.setStyleSheet(_TEAM_BTN_QSS)
        self._team2_btn.clicked.connect(lambda: self._set_serving_team(1))
        team_btn_row.addWidget(self._team2_btn)

        team_btn_row.addStretch()
        layout.addLayout(team_btn_row)

        # Score entry row
        score_row = QHBoxLayout()
        score_row.setSpacing(SPACE_SM)

        score_label = QLabel("Score:")
        score_label.setFont(Fonts.label())
        set_label_role(score_label, "body")
        score_row.addWidget(score_label)

        self._score_input = QLineEdit()
        self._score_input.setFont(Fonts.display(size=18, weight=700))
        self._score_input.setPlaceholderText("X-Y-Z")
        self._score_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_input.setStyleSheet(InputStyles.line_edit())
        self._score_input.textChanged.connect(self._on_score_text_changed)
        score_row.addWidget(self._score_input, 1)

        layout.addLayout(score_row)

        # Inline error label
        self._error_label = QLabel("Use format X-Y-Z (doubles) or X-Y (singles)")
        self._error_label.setStyleSheet(
            f"color: {DANGER_TEXT}; font-size: 12px; background: transparent; border: none;"
        )
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Apply button — disabled until score is valid
        self._apply_btn = QPushButton("Apply to Rally")
        self._apply_btn.setFont(Fonts.button_other())
        self._apply_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._apply_btn.setEnabled(False)
        self._apply_btn.setStyleSheet(ButtonStyles.outline(PRIMARY_ACTION))
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        layout.addWidget(self._apply_btn)

        self.setStyleSheet(f"""
            StateAnchorWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    # -- Internal helpers ----------------------------------------------------

    def _current_pattern(self) -> str:
        if self._game_mode == "doubles":
            return r"^\d{1,2}-\d{1,2}-[12]$"
        return r"^\d{1,2}-\d{1,2}$"

    def _is_valid_score(self, text: str) -> bool:
        rx = QRegularExpression(self._current_pattern())
        return rx.match(text.strip()).hasMatch()

    def _set_error_state(self, error: bool) -> None:
        self._score_input.setProperty("error", "true" if error else "false")
        self._score_input.style().unpolish(self._score_input)
        self._score_input.style().polish(self._score_input)
        if error:
            self._error_label.show()
        else:
            self._error_label.hide()

    def _set_serving_team(self, team: int) -> None:
        """Mutually-exclusive toggle for the two team buttons."""
        self._serving_team = team
        self._team1_btn.setChecked(team == 0)
        self._team2_btn.setChecked(team == 1)

    def _update_validator(self) -> None:
        """Rebuild QRegularExpressionValidator for the current game mode.

        Reference kept in ``self._validator`` to prevent GC under PyQt6.
        """
        pattern = self._current_pattern()
        self._validator = QRegularExpressionValidator(QRegularExpression(pattern))
        self._score_input.setValidator(self._validator)
        if self._game_mode == "doubles":
            self._score_input.setPlaceholderText("X-Y-Z")
        else:
            self._score_input.setPlaceholderText("X-Y")

    # -- Signal handlers -----------------------------------------------------

    @pyqtSlot(str)
    def _on_score_text_changed(self, text: str) -> None:
        is_valid = self._is_valid_score(text)
        self._apply_btn.setEnabled(is_valid)
        # Only show error for non-empty invalid input
        self._set_error_state(bool(text) and not is_valid)

    @pyqtSlot()
    def _on_apply_clicked(self) -> None:
        text = self._score_input.text().strip()
        if self._is_valid_score(text):
            self.state_anchor_applied.emit(self._serving_team, text)

    # -- Public API ----------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Set the game mode and rebuild the score validator.

        Args:
            mode: ``"doubles"``, ``"singles"``, or ``"highlights"``
        """
        self._game_mode = mode
        self._update_validator()

    def set_state(self, score: str, serving_team: int) -> None:
        """Prefill the widget for the current rally.

        Args:
            score: Score string at rally start (e.g., "3-2-1")
            serving_team: Serving team index (0 or 1)
        """
        self._score_input.blockSignals(True)
        self._score_input.setText(score)
        self._score_input.blockSignals(False)
        self._set_serving_team(serving_team)
        is_valid = self._is_valid_score(score)
        self._apply_btn.setEnabled(is_valid)
        self._set_error_state(False)

    def set_team_names(self, team1_name: str, team2_name: str) -> None:
        """Update the labels on the serving-team toggle buttons.

        Args:
            team1_name: Display name for team 1 (e.g., "Alice & Bob")
            team2_name: Display name for team 2
        """
        self._team1_name = team1_name
        self._team2_name = team2_name
        self._team1_btn.setText(team1_name)
        self._team2_btn.setText(team2_name)


# ===========================================================================
# RallyListWidget
# ===========================================================================

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
        super().__init__(parent)
        self._rallies: list[Rally] = []
        self._current_index = 0
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        self._list_widget = QListWidget()
        self._list_widget.setObjectName("rallyList")
        self._list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self._list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self._list_widget.setWrapping(False)  # Single row; control panel needs full vertical height
        self._list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list_widget.setSpacing(4)
        self._list_widget.setGridSize(QSize(70, 50))
        self._list_widget.setUniformItemSizes(True)
        self._list_widget.setMovement(QListWidget.Movement.Static)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        _grid_h = self._list_widget.gridSize().height()
        _spacing = self._list_widget.spacing()
        _scrollbar_h = self._list_widget.horizontalScrollBar().sizeHint().height()
        _frame_h = self._list_widget.frameWidth() * 2
        _derived_h = _grid_h + 2 * _spacing + _scrollbar_h + _frame_h
        self._list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._list_widget.setFixedHeight(_derived_h)

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
                background: {PRIMARY_ACTION_TINT};
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
        """Create a card widget for a rally item."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        num_label = QLabel(str(rally_num))
        num_label.setFont(Fonts.display(size=14, weight=600))
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

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
        widget.setStyleSheet("background: transparent;")
        return widget

    def set_rallies(self, rallies: list[Rally]) -> None:
        """Populate the rally list with cards."""
        self._rallies = rallies
        self._list_widget.clear()

        for idx, rally in enumerate(rallies):
            item = QListWidgetItem()
            widget = self._create_card_widget(idx + 1, rally.score_at_start, rally.is_post_game)
            item.setSizeHint(QSize(62, 42))
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

        if rallies:
            self.set_current_rally(0)

    @pyqtSlot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.rally_selected.emit(idx)

    def set_current_rally(self, index: int) -> None:
        """Set the currently selected rally."""
        if 0 <= index < self._list_widget.count():
            self._current_index = index
            self._list_widget.setCurrentRow(index)
            self._list_widget.scrollToItem(
                self._list_widget.item(index),
                QListWidget.ScrollHint.EnsureVisible,
            )


# ===========================================================================
# ReviewModeWidget
# ===========================================================================

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
    NEVER placed inside a QScrollArea in either arrangement.

    Signals:
        rally_changed(int): Current rally index changed
        timing_adjusted(int, str, float): Nudge applied
            - rally_idx, field "start"|"end", delta
        timing_set(int, str, float): Direct entry committed
            - rally_idx, field "start"|"end", absolute_seconds
        winner_set(int, str): Winner explicitly set
            - rally_idx, "server"|"receiver"
        state_anchor_set(int, int, str): Game state anchor applied
            - rally_idx, serving_team 0|1, score_string
        delete_rally_requested(int): User requested rally deletion
        insert_rally_requested(int): User requested rally insertion after index
        exit_requested(): Exit review mode
        return_to_menu_requested(): Return to main menu
        generate_requested(): Generate Kdenlive project
        export_ffmpeg_requested(): Export MP4 via FFmpeg
        play_rally_requested(int): Play the specified rally
        navigate_previous(): Navigate to previous rally
        navigate_next(): Navigate to next rally
        game_completed_toggled(bool): Mark Game Completed toggled
        export_path_changed(str): Export path field changed
    """

    rally_changed = pyqtSignal(int)
    timing_adjusted = pyqtSignal(int, str, float)
    timing_set = pyqtSignal(int, str, float)
    winner_set = pyqtSignal(int, str)
    state_anchor_set = pyqtSignal(int, int, str)
    delete_rally_requested = pyqtSignal(int)
    insert_rally_requested = pyqtSignal(int)
    exit_requested = pyqtSignal()
    return_to_menu_requested = pyqtSignal()
    generate_requested = pyqtSignal()
    export_ffmpeg_requested = pyqtSignal()
    play_rally_requested = pyqtSignal(int)
    navigate_previous = pyqtSignal()
    navigate_next = pyqtSignal()
    game_completed_toggled = pyqtSignal(bool)
    export_path_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rallies: list[Rally] = []
        self._current_index = 0
        self._fps = 60.0
        self._game_completed = False
        self._final_score = ""
        self._winning_team_names: list[str] = []
        self._export_path: str = ""
        self._low_confidence_indices: set[int] = set()

        # Team name state (set via set_team_names)
        self._team1_players: list[str] = []
        self._team2_players: list[str] = []
        self._team1_name: str = "Team 1"
        self._team2_name: str = "Team 2"

        self._app_settings = AppSettings.load()

        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(500)
        self._splitter_save_timer.timeout.connect(self._save_splitter_sizes)

        self._init_ui()

    def _init_ui(self) -> None:
        """Create stable leaf widgets and the arrangement host.

        Full layout is deferred to _arrange_tall / _arrange_wide, called once
        from showEvent.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        main_layout.setSpacing(SPACE_MD)

        # Header
        self._header = RallyHeaderWidget()
        self._header.exit_requested.connect(self.exit_requested.emit)
        self._header.return_to_menu_requested.connect(self.return_to_menu_requested.emit)
        main_layout.addWidget(self._header)

        # Arrangement host
        self._arrangement_host = QWidget(self)
        self._arrangement_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _host_layout = QVBoxLayout(self._arrangement_host)
        _host_layout.setContentsMargins(0, 0, 0, 0)
        _host_layout.setSpacing(0)
        main_layout.addWidget(self._arrangement_host, stretch=1)

        # Video placeholder (MPV reparenting target — NEVER inside a QScrollArea)
        self._video_placeholder = QWidget()
        self._video_placeholder.setObjectName("video_placeholder")
        self._video_placeholder.setMinimumSize(320, 180)
        self._video_placeholder.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_placeholder.setStyleSheet("")
        self._video_placeholder.winId()

        # Control panel content widget
        self._control_panel_widget = QWidget()
        self._control_panel_widget.setStyleSheet("background-color: transparent;")
        self._build_control_panel()

        # Rally strip (nav row + rally list)
        self._rally_strip_widget = QWidget()
        self._build_rally_strip()

        # Export / generate widget
        self._export_widget = QWidget()
        self._export_widget.setObjectName("generateContainer")
        self._build_export_widget()

        # Splitter references — assigned in _arrange_*
        self._outer_splitter: QSplitter | None = None
        self._inner_splitter: QSplitter | None = None
        self._master_splitter: QSplitter | None = None

        self._arrangement: str = ""  # "tall" | "wide"

        self.setStyleSheet(f"ReviewModeWidget {{ background-color: {BG_PRIMARY}; }}")

    # =========================================================================
    # Section-widget builders
    # =========================================================================

    def _build_control_panel(self) -> None:
        """Populate _control_panel_widget with play / winner / timing / anchor controls."""
        cp_layout = QVBoxLayout(self._control_panel_widget)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(SPACE_MD)

        # Play Rally button (prominent green outline)
        play_rally_button = QPushButton("PLAY RALLY")
        play_rally_button.setIcon(make_icon("play", PRIMARY_ACTION, 16))
        play_rally_button.setIconSize(QSize(16, 16))
        play_rally_button.setFont(Fonts.button_rally())
        play_rally_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        play_rally_button.clicked.connect(self._on_play_clicked)
        play_rally_button.setStyleSheet(ButtonStyles.outline(PRIMARY_ACTION, rally_tier=True))
        cp_layout.addWidget(play_rally_button)

        # Explicit winner control (replaces the old "Flip Winner" button)
        self._winner_control = WinnerControlWidget()
        self._winner_control.winner_selected.connect(self._on_winner_set)
        cp_layout.addWidget(self._winner_control)

        # Delete / Insert row
        edit_row = QHBoxLayout()
        edit_row.setSpacing(SPACE_SM)

        self._delete_rally_button = QPushButton("Delete Rally")
        self._delete_rally_button.setFont(Fonts.button_other())
        self._delete_rally_button.setObjectName("deleteRallyButton")
        self._delete_rally_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._delete_rally_button.clicked.connect(self._on_delete_rally_clicked)
        self._delete_rally_button.setToolTip(
            "Remove this rally and recalculate all subsequent scores"
        )
        self._delete_rally_button.setStyleSheet(ButtonStyles.outline(DANGER_TEXT))
        edit_row.addWidget(self._delete_rally_button)

        self._insert_rally_button = QPushButton("Insert Rally After")
        self._insert_rally_button.setFont(Fonts.button_other())
        self._insert_rally_button.setObjectName("insertRallyButton")
        self._insert_rally_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._insert_rally_button.clicked.connect(self._on_insert_rally_clicked)
        self._insert_rally_button.setToolTip(
            "Insert a new rally after this one with a placeholder timing and score"
        )
        self._insert_rally_button.setStyleSheet(ButtonStyles.compact())
        edit_row.addWidget(self._insert_rally_button)

        cp_layout.addLayout(edit_row)

        # Timing controls (with configurable step + direct entry)
        self._timing_widget = TimingControlWidget()
        self._timing_widget.timing_adjusted.connect(self._on_timing_adjusted)
        self._timing_widget.timing_set.connect(self._on_timing_set)
        cp_layout.addWidget(self._timing_widget)

        # Game-state anchor (replaces ScoreEditWidget; always cascades)
        self._state_anchor = StateAnchorWidget()
        self._state_anchor.state_anchor_applied.connect(self._on_state_anchor_applied)
        cp_layout.addWidget(self._state_anchor)

        cp_layout.addStretch()

    def _build_rally_strip(self) -> None:
        """Populate _rally_strip_widget with the navigation row and rally list."""
        rs_layout = QVBoxLayout(self._rally_strip_widget)
        rs_layout.setContentsMargins(0, 0, 0, 0)
        rs_layout.setSpacing(SPACE_SM)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(SPACE_MD)

        list_title = QLabel("RALLY LIST (click to navigate)")
        list_title.setFont(Fonts.body(size=12, weight=600))
        list_title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        nav_row.addWidget(list_title)
        nav_row.addStretch()

        self._prev_button = QPushButton("Prev")
        self._prev_button.setIcon(make_icon("chevron-left", TEXT_PRIMARY, 16))
        self._prev_button.setIconSize(QSize(16, 16))
        self._prev_button.setFont(Fonts.button_other())
        self._prev_button.clicked.connect(self._on_previous_clicked)
        self._prev_button.setEnabled(False)
        self._style_nav_button(self._prev_button)
        nav_row.addWidget(self._prev_button)

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

        self._rally_list = RallyListWidget()
        self._rally_list.rally_selected.connect(self._on_rally_selected)
        rs_layout.addWidget(self._rally_list)

    def _build_export_widget(self) -> None:
        """Populate _export_widget with the generate/export container content."""
        ex_layout = QVBoxLayout(self._export_widget)
        ex_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        ex_layout.setSpacing(SPACE_SM)

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

        self._mark_complete_checkbox = QCheckBox("Mark Game Completed")
        self._mark_complete_checkbox.setFont(Fonts.button_other())
        self._mark_complete_checkbox.toggled.connect(self._on_mark_complete_toggled)
        ex_layout.addWidget(self._mark_complete_checkbox)

        self._final_score_label = QLabel("")
        self._final_score_label.setFont(Fonts.display(size=16, weight=600))
        self._final_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._final_score_label.hide()
        ex_layout.addWidget(self._final_score_label)

        export_header = QLabel("Export Options")
        export_header.setFont(Fonts.body(size=14, weight=600))
        export_header.setStyleSheet(f"color: {TEXT_SECONDARY};")
        ex_layout.addWidget(export_header)

        export_cards_layout = QHBoxLayout()
        export_cards_layout.setSpacing(SPACE_MD)

        # Kdenlive Card
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

        # FFmpeg Card
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

        Structure (_video_placeholder is NOT inside any QScrollArea)::

            _outer_splitter (Vertical, childrenCollapsible=False):
              top_section (min 200 px):
                _inner_splitter (Horizontal):
                  _video_placeholder          ← NOT in scroll
                  control_panel_scroll        → _control_panel_widget
              bottom_scroll (QScrollArea, min 330 px):
                bottom_content:
                  _rally_strip_widget
                  _export_widget
        """
        host_layout = self._arrangement_host.layout()

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

        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._inner_splitter.setChildrenCollapsible(False)
        self._inner_splitter.addWidget(self._video_placeholder)
        self._inner_splitter.addWidget(control_panel_scroll)
        self._inner_splitter.setSizes([600, 320])
        self._inner_splitter.setStretchFactor(0, 1)
        self._inner_splitter.setStretchFactor(1, 0)

        top_section = QWidget()
        top_section.setMinimumHeight(200)
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(self._inner_splitter)

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

        Structure (_video_placeholder is NOT inside any QScrollArea)::

            _master_splitter (Horizontal, childrenCollapsible=False):
              left_panel (NOT in scroll, stretchFactor=1):
                _video_placeholder          ← NOT in scroll
                _rally_strip_widget
              right_scroll (QScrollArea, min 460 px):
                right_panel:
                  _control_panel_widget
                  _export_widget
        """
        host_layout = self._arrangement_host.layout()

        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {BG_PRIMARY};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACE_SM)
        left_layout.addWidget(self._video_placeholder, stretch=1)
        left_layout.addWidget(self._rally_strip_widget)

        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(SPACE_MD, 0, 0, 0)
        right_layout.setSpacing(SPACE_MD)
        right_layout.addWidget(self._control_panel_widget)
        right_layout.addWidget(self._export_widget)
        right_layout.addStretch()

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

        self._master_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._master_splitter.setChildrenCollapsible(False)
        self._master_splitter.addWidget(left_panel)
        self._master_splitter.addWidget(right_scroll)
        self._master_splitter.setStretchFactor(0, 1)
        self._master_splitter.setStretchFactor(1, 0)
        self._master_splitter.splitterMoved.connect(self._on_splitter_moved)

        host_layout.addWidget(self._master_splitter)

    # =========================================================================
    # Navigation button styling
    # =========================================================================

    def _style_nav_button(self, button: QPushButton) -> None:
        set_class(button, "nav")

    # =========================================================================
    # Show event — decides and freezes the arrangement
    # =========================================================================

    def showEvent(self, event: QShowEvent) -> None:
        """Choose and build the arrangement ONCE at review entry."""
        super().showEvent(event)

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

        _display = getattr(self._app_settings, "display", None)

        if self._arrangement == "wide" and self._master_splitter is not None:
            _h_sizes = getattr(_display, "review_splitter_h", []) if _display else []
            if _h_sizes and len(_h_sizes) == 2 and sum(_h_sizes) > 0:
                self._master_splitter.setSizes(list(_h_sizes))
                return
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
            _avail_h = self._arrangement_host.height()
            if _avail_h > 0:
                _top_h = max(200, int(_avail_h * 0.65))
                _bot_h = max(330, _avail_h - _top_h)
                self._outer_splitter.setSizes([_top_h, _bot_h])

    @pyqtSlot(int, int)
    def _on_splitter_moved(self, pos: int, index: int) -> None:
        self._splitter_save_timer.start()

    def _save_splitter_sizes(self) -> None:
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

    # =========================================================================
    # Signal bridge slots
    # =========================================================================

    @pyqtSlot(str, float)
    def _on_timing_adjusted(self, field: str, delta: float) -> None:
        """Forward TimingControlWidget nudge to the outer timing_adjusted signal."""
        self.timing_adjusted.emit(self._current_index, field, delta)

    @pyqtSlot(str, float)
    def _on_timing_set(self, field: str, abs_seconds: float) -> None:
        """Forward TimingControlWidget direct-entry commit to timing_set."""
        self.timing_set.emit(self._current_index, field, abs_seconds)

    @pyqtSlot(str)
    def _on_winner_set(self, winner: str) -> None:
        """Forward WinnerControlWidget selection to winner_set."""
        self.winner_set.emit(self._current_index, winner)

    @pyqtSlot(int, str)
    def _on_state_anchor_applied(self, serving_team: int, score: str) -> None:
        """Forward StateAnchorWidget apply to state_anchor_set."""
        self.state_anchor_set.emit(self._current_index, serving_team, score)

    @pyqtSlot()
    def _on_delete_rally_clicked(self) -> None:
        self.delete_rally_requested.emit(self._current_index)

    @pyqtSlot()
    def _on_insert_rally_clicked(self) -> None:
        self.insert_rally_requested.emit(self._current_index)

    @pyqtSlot(int)
    def _on_rally_selected(self, index: int) -> None:
        self.set_current_rally(index)

    @pyqtSlot()
    def _on_previous_clicked(self) -> None:
        if self._current_index > 0:
            self.set_current_rally(self._current_index - 1)
            self.navigate_previous.emit()

    @pyqtSlot()
    def _on_next_clicked(self) -> None:
        if self._current_index < len(self._rallies) - 1:
            self.set_current_rally(self._current_index + 1)
            self.navigate_next.emit()

    @pyqtSlot()
    def _on_play_clicked(self) -> None:
        self.play_rally_requested.emit(self._current_index)

    # =========================================================================
    # Winner-control label helper
    # =========================================================================

    def _update_winner_control(self, index: int) -> None:
        """Refresh WinnerControlWidget labels for the rally at *index*.

        Derives serving/returning team names from
        ``rally.score_snapshot_at_start.serving_team``.  Falls back to
        ``"unknown"`` when the snapshot is missing.
        """
        rally = self._rallies[index]
        snapshot = rally.score_snapshot_at_start
        if snapshot is None:
            self._winner_control.set_teams("unknown", "unknown")
            return
        serving_idx = snapshot.serving_team          # 0 or 1
        returning_idx = 1 - serving_idx
        serving_name = self._team1_name if serving_idx == 0 else self._team2_name
        returning_name = self._team1_name if returning_idx == 0 else self._team2_name
        self._winner_control.set_teams(serving_name, returning_name)

    # =========================================================================
    # Public API — rally population and navigation
    # =========================================================================

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
            is_highlights: If True, hide winner / score controls.
            game_mode: Score format — ``"doubles"`` (X-Y-Z), ``"singles"``
                       (X-Y), or ``"highlights"`` (no score).
        """
        self._rallies = rallies
        self._fps = fps

        if is_highlights:
            self._state_anchor.hide()
            self._winner_control.hide()
        else:
            self._state_anchor.show()
            self._state_anchor.set_mode(game_mode)
            self._winner_control.show()

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
        """Set the currently displayed rally and refresh all child controls.

        Args:
            index: Rally index (0-based)
        """
        if not (0 <= index < len(self._rallies)):
            return

        self._current_index = index
        rally = self._rallies[index]

        # Header
        self._header.set_rally(index, len(self._rallies), is_post_game=rally.is_post_game)

        # Timing controls — convert frames to seconds
        start_seconds = rally.start_frame / self._fps
        end_seconds = rally.end_frame / self._fps
        self._timing_widget.set_times(start_seconds, end_seconds)

        # Winner control — derive serving/returning team names from snapshot
        self._update_winner_control(index)
        low_conf = index in self._low_confidence_indices
        self._winner_control.set_low_confidence(low_conf)

        # State anchor — prefill score and serving team
        snapshot = rally.score_snapshot_at_start
        serving_team = snapshot.serving_team if snapshot is not None else 0
        self._state_anchor.set_state(rally.score_at_start, serving_team)

        # Rally list
        self._rally_list.set_current_rally(index)

        # Prev / Next boundary guards
        self._prev_button.setEnabled(index > 0)
        self._next_button.setEnabled(index < len(self._rallies) - 1)

        # Notify observers
        self.rally_changed.emit(index)

    def set_team_names(self, team1: list[str], team2: list[str]) -> None:
        """Supply player names for both teams.

        Used to label the winner buttons and state-anchor team selector with
        human-readable names.  Fallback when a list is empty: "Team 1"/"Team 2".
        The "unknown" label is reserved for missing snapshot data only.

        Args:
            team1: Player names for team 1 (e.g. ``["Alice", "Bob"]``)
            team2: Player names for team 2
        """
        self._team1_players = list(team1)
        self._team2_players = list(team2)
        self._team1_name = " & ".join(team1) if team1 else "Team 1"
        self._team2_name = " & ".join(team2) if team2 else "Team 2"

        self._state_anchor.set_team_names(self._team1_name, self._team2_name)

        # Refresh winner control if a rally is already loaded
        if self._rallies and 0 <= self._current_index < len(self._rallies):
            self._update_winner_control(self._current_index)

    def get_current_rally_index(self) -> int:
        """Return the current rally index (0-based)."""
        return self._current_index

    def navigate_to_previous(self) -> None:
        """Navigate to the previous rally (programmatic, no signal)."""
        if self._current_index > 0:
            self.set_current_rally(self._current_index - 1)

    def navigate_to_next(self) -> None:
        """Navigate to the next rally (programmatic, no signal)."""
        if self._current_index < len(self._rallies) - 1:
            self.set_current_rally(self._current_index + 1)

    def get_video_placeholder(self) -> QWidget:
        """Return the video placeholder widget for MPV embedding."""
        return self._video_placeholder

    def get_inner_splitter(self) -> QSplitter | None:
        """Return the inner horizontal splitter (tall arrangement only)."""
        return self._inner_splitter

    def get_outer_splitter(self) -> QSplitter | None:
        """Return the outer vertical splitter (tall arrangement only)."""
        return self._outer_splitter

    # =========================================================================
    # Low-confidence indices
    # =========================================================================

    def set_low_confidence_indices(self, indices: set[int]) -> None:
        """Mark specific rally indices as having low-confidence winner classifications.

        The winner control is styled with amber when the current rally is in this set.

        Args:
            indices: Set of rally indices (0-based) with low confidence
        """
        self._low_confidence_indices = indices
        low_conf = self._current_index in self._low_confidence_indices
        self._winner_control.set_low_confidence(low_conf)

    def get_low_confidence_indices(self) -> set[int]:
        """Return a copy of the low-confidence rally index set."""
        return set(self._low_confidence_indices)

    # =========================================================================
    # Game-completion controls
    # =========================================================================

    @pyqtSlot(bool)
    def _on_mark_complete_toggled(self, checked: bool) -> None:
        self._game_completed = checked
        if checked:
            self._final_score_label.show()
        else:
            self._final_score_label.hide()
        self.game_completed_toggled.emit(checked)

    def set_game_completion_info(
        self,
        final_score: str,
        winning_team_names: list[str],
    ) -> None:
        """Set the game completion display info."""
        self._final_score = final_score
        self._winning_team_names = winning_team_names

        if winning_team_names:
            winner_str = " & ".join(winning_team_names) + " Win"
        else:
            winner_str = ""

        display_text = final_score
        if winner_str:
            display_text += f"\n{winner_str}"
        self._final_score_label.setText(display_text)

    def is_game_completed(self) -> bool:
        """Return whether the game has been marked as completed."""
        return self._game_completed

    def get_game_completion_info(self) -> tuple[str, list[str]]:
        """Return (final_score, winning_team_names) for export."""
        return self._final_score, self._winning_team_names

    def hide_game_completion_controls(self) -> None:
        """Hide game-completion controls (highlights mode)."""
        self._mark_complete_checkbox.hide()
        self._final_score_label.hide()

    def set_game_completed(self, checked: bool, announce: bool = False) -> None:
        """Set the mark-complete checkbox state.

        Args:
            checked: Whether the game should be marked as completed.
            announce: When True and checked is True, show an info toast.
        """
        self._mark_complete_checkbox.setChecked(checked)
        if announce and checked and self._final_score:
            message = (
                f"Game complete detected — final score {self._final_score}. "
                "Uncheck 'Mark Game Completed' if this is wrong."
            )
            ToastManager.show_info(self, message)

    # =========================================================================
    # Export path
    # =========================================================================

    @pyqtSlot()
    def _on_browse_clicked(self) -> None:
        from pathlib import Path

        default_dir = str(Path.home() / "Videos")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Export Location",
            default_dir,
            "Kdenlive Project (*.kdenlive);;All Files (*)",
        )
        if file_path:
            self._export_path_edit.setText(file_path)

    @pyqtSlot(str)
    def _on_export_path_changed(self, path: str) -> None:
        self._export_path = path
        self.export_path_changed.emit(path)

    def get_export_path(self) -> str:
        """Return the currently set export path (empty string = use dialog)."""
        return self._export_path

    def set_export_path(self, path: str) -> None:
        """Set the export path display field.

        Args:
            path: Path string to display
        """
        self._export_path = path
        self._export_path_edit.setText(path)
