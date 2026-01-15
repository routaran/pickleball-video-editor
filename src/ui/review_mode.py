"""Final Review Mode UI for Pickleball Video Editor.

This module provides the ReviewModeWidget and its sub-components for verifying
and adjusting rally timings before generating Kdenlive output.

Components:
- RallyHeaderWidget: Shows "RALLY X OF Y" with progress indicator
- TimingControlWidget: Adjust rally start/end times with +/- buttons
- ScoreEditWidget: Edit rally score with cascade option
- RallyCardWidget: Individual rally card for rally list
- RallyListWidget: Horizontal scrollable grid of rally cards
- ReviewModeWidget: Main container composing all components

The Review Mode replaces the Rally Controls and Toolbar sections when activated
from the Main Window's "Final Review" button.
"""

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.core.models import Rally
from src.ui.styles import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BORDER_COLOR,
    GLOW_GREEN,
    PRIMARY_ACTION,
    RADIUS_LG,
    RADIUS_MD,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    Fonts,
)

__all__ = [
    "RallyHeaderWidget",
    "TimingControlWidget",
    "ScoreEditWidget",
    "RallyCardWidget",
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
    """

    exit_requested = pyqtSignal()

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
        self._counter_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(self._counter_label)

        layout.addStretch()

        # Exit button
        self._exit_button = QPushButton("Exit Review")
        self._exit_button.setFont(Fonts.button_other())
        self._exit_button.clicked.connect(self.exit_requested.emit)
        self._exit_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
            }}
            QPushButton:hover {{
                background-color: {BG_BORDER};
            }}
        """)
        layout.addWidget(self._exit_button)

        # Container styling
        self.setStyleSheet(f"""
            RallyHeaderWidget {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)

    def set_rally(self, current: int, total: int) -> None:
        """Update the displayed rally count.

        Args:
            current: Current rally index (0-based)
            total: Total number of rallies
        """
        self._current_rally = current
        self._total_rallies = total
        # Display as 1-based for user
        self._counter_label.setText(f"Rally {current + 1} of {total}")


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
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section title
        title = QLabel("TIMING")
        title.setFont(Fonts.body(size=12, weight=600))
        title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(title)

        # Controls grid
        controls_layout = QGridLayout()
        controls_layout.setSpacing(SPACE_MD)
        controls_layout.setColumnStretch(1, 1)
        controls_layout.setColumnStretch(4, 1)

        # Start time controls
        start_label = QLabel("START")
        start_label.setFont(Fonts.label())
        start_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        controls_layout.addWidget(start_label, 0, 0)

        self._start_time_label = QLabel("00:00.0")
        self._start_time_label.setFont(Fonts.timestamp())
        self._start_time_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        controls_layout.addWidget(self._start_time_label, 0, 1)

        start_minus_btn = QPushButton("-0.1s")
        start_minus_btn.setFont(Fonts.button_other())
        start_minus_btn.clicked.connect(lambda: self._adjust_start(-0.1))
        self._style_adjust_button(start_minus_btn)
        controls_layout.addWidget(start_minus_btn, 1, 0)

        start_plus_btn = QPushButton("+0.1s")
        start_plus_btn.setFont(Fonts.button_other())
        start_plus_btn.clicked.connect(lambda: self._adjust_start(0.1))
        self._style_adjust_button(start_plus_btn)
        controls_layout.addWidget(start_plus_btn, 1, 1)

        # End time controls
        end_label = QLabel("END")
        end_label.setFont(Fonts.label())
        end_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        controls_layout.addWidget(end_label, 0, 3)

        self._end_time_label = QLabel("00:00.0")
        self._end_time_label.setFont(Fonts.timestamp())
        self._end_time_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        controls_layout.addWidget(self._end_time_label, 0, 4)

        end_minus_btn = QPushButton("-0.1s")
        end_minus_btn.setFont(Fonts.button_other())
        end_minus_btn.clicked.connect(lambda: self._adjust_end(-0.1))
        self._style_adjust_button(end_minus_btn)
        controls_layout.addWidget(end_minus_btn, 1, 3)

        end_plus_btn = QPushButton("+0.1s")
        end_plus_btn.setFont(Fonts.button_other())
        end_plus_btn.clicked.connect(lambda: self._adjust_end(0.1))
        self._style_adjust_button(end_plus_btn)
        controls_layout.addWidget(end_plus_btn, 1, 4)

        layout.addLayout(controls_layout)

        # Duration display
        duration_layout = QHBoxLayout()
        duration_layout.setSpacing(SPACE_SM)

        duration_label = QLabel("DURATION")
        duration_label.setFont(Fonts.label())
        duration_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        duration_layout.addWidget(duration_label)

        self._duration_label = QLabel("00:00.0")
        self._duration_label.setFont(Fonts.timestamp())
        self._duration_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        duration_layout.addWidget(self._duration_label)
        duration_layout.addStretch()

        layout.addLayout(duration_layout)

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
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
                min-width: 60px;
            }}
            QPushButton:hover {{
                background-color: {BG_BORDER};
                border-color: {PRIMARY_ACTION};
            }}
        """)

    def _adjust_start(self, delta: float) -> None:
        """Handle start time adjustment.

        Args:
            delta: Time change in seconds
        """
        self._start_time += delta
        if self._start_time < 0:
            self._start_time = 0.0
        self._update_display()
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
        self.timing_adjusted.emit("end", delta)

    def _update_display(self) -> None:
        """Update all time displays."""
        self._start_time_label.setText(_format_time(self._start_time))
        self._end_time_label.setText(_format_time(self._end_time))
        duration = max(0.0, self._end_time - self._start_time)
        self._duration_label.setText(_format_time(duration))

    def set_times(self, start_seconds: float, end_seconds: float) -> None:
        """Set the displayed start and end times.

        Args:
            start_seconds: Rally start time in seconds
            end_seconds: Rally end time in seconds
        """
        self._start_time = start_seconds
        self._end_time = end_seconds
        self._update_display()


class ScoreEditWidget(QWidget):
    """Widget for editing rally score with optional cascade.

    Displays:
    - Current score (read-only)
    - Arrow indicator
    - New score input field
    - Cascade checkbox

    Signals:
        score_changed(str, bool): Emitted when score is changed
            - new_score: New score string
            - cascade: Whether to cascade to later rallies
    """

    score_changed = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the score edit widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section title
        title = QLabel("SCORE")
        title.setFont(Fonts.body(size=12, weight=600))
        title.setStyleSheet(f"color: {TEXT_SECONDARY};")
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

        # Arrow indicator
        arrow_label = QLabel("→")
        arrow_label.setFont(Fonts.display(size=24))
        arrow_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
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
        self._new_score_input.textChanged.connect(self._on_score_changed)
        self._new_score_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
            }}
            QLineEdit:focus {{
                border-color: {PRIMARY_ACTION};
            }}
        """)
        new_layout.addWidget(self._new_score_input)

        score_layout.addLayout(new_layout)

        layout.addLayout(score_layout)

        # Cascade checkbox
        self._cascade_checkbox = QCheckBox("Cascade to later rallies")
        self._cascade_checkbox.setFont(Fonts.label())
        self._cascade_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {BORDER_COLOR};
                border-radius: 3px;
                background-color: {BG_TERTIARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {PRIMARY_ACTION};
                border-color: {PRIMARY_ACTION};
            }}
        """)
        layout.addWidget(self._cascade_checkbox)

        # Container styling
        self.setStyleSheet(f"""
            ScoreEditWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    def _on_score_changed(self) -> None:
        """Handle score input changes."""
        new_score = self._new_score_input.text()
        cascade = self._cascade_checkbox.isChecked()
        if new_score:  # Only emit if non-empty
            self.score_changed.emit(new_score, cascade)

    def set_current_score(self, score: str) -> None:
        """Set the displayed current score.

        Args:
            score: Score string (e.g., "3-2-1")
        """
        self._current_score_label.setText(score)
        self._new_score_input.clear()

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


class RallyCardWidget(QWidget):
    """Individual rally card for the rally list.

    Displays:
    - Rally number (large)
    - Score at start (small)

    Supports selection state with visual highlighting.

    Signals:
        clicked(): Emitted when card is clicked
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        rally_number: int,
        score: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the rally card.

        Args:
            rally_number: Rally number (1-based for display)
            score: Score string
            parent: Parent widget
        """
        super().__init__(parent)
        self._rally_number = rally_number
        self._score = score
        self._selected = False
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        layout.setSpacing(SPACE_SM // 2)

        # Rally number
        number_label = QLabel(f"Rally {self._rally_number}")
        number_label.setFont(Fonts.body(size=14, weight=600))
        number_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(number_label)

        # Score
        score_label = QLabel(self._score)
        score_label.setFont(Fonts.display(size=12))
        score_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(score_label)

        self.setFixedSize(100, 60)
        self._update_style()

    def _update_style(self) -> None:
        """Update widget styling based on selection state."""
        if self._selected:
            self.setStyleSheet(f"""
                RallyCardWidget {{
                    background-color: {BG_SECONDARY};
                    border: 2px solid {PRIMARY_ACTION};
                    border-radius: {RADIUS_MD}px;
                    box-shadow: 0 0 8px {GLOW_GREEN};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                RallyCardWidget {{
                    background-color: {BG_TERTIARY};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: {RADIUS_MD}px;
                }}
                RallyCardWidget:hover {{
                    background-color: {BG_BORDER};
                    border-color: {PRIMARY_ACTION};
                }}
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events.

        Args:
            event: Mouse event from Qt
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        """Set the card's selection state.

        Args:
            selected: True if card should be selected
        """
        self._selected = selected
        self._update_style()


class RallyListWidget(QWidget):
    """Horizontal scrollable grid of rally cards.

    Displays all rallies as cards in a grid layout with horizontal scrolling.
    Clicking a card navigates to that rally.

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
        self._cards: list[RallyCardWidget] = []
        self._current_index = 0
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Section title
        title = QLabel("RALLY LIST (click to navigate)")
        title.setFont(Fonts.body(size=12, weight=600))
        title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(title)

        # Scroll area for rally cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BG_PRIMARY};
                border: none;
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

        # Container widget for cards
        self._cards_container = QWidget()
        self._cards_layout = QGridLayout(self._cards_container)
        self._cards_layout.setSpacing(SPACE_SM)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area.setWidget(self._cards_container)
        layout.addWidget(scroll_area)

        # Container styling
        self.setStyleSheet(f"""
            RallyListWidget {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}
        """)

    def set_rallies(self, rallies: list[Rally]) -> None:
        """Populate the rally list with cards.

        Args:
            rallies: List of Rally objects
        """
        # Clear existing cards
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # Create new cards
        cols = 6  # Number of cards per row
        for idx, rally in enumerate(rallies):
            card = RallyCardWidget(
                rally_number=idx + 1,
                score=rally.score_at_start,
            )
            card.clicked.connect(lambda i=idx: self._on_card_clicked(i))
            self._cards.append(card)

            row = idx // cols
            col = idx % cols
            self._cards_layout.addWidget(card, row, col)

        if self._cards:
            self.set_current_rally(0)

    def _on_card_clicked(self, index: int) -> None:
        """Handle rally card click.

        Args:
            index: Rally index (0-based)
        """
        self.set_current_rally(index)
        self.rally_selected.emit(index)

    def set_current_rally(self, index: int) -> None:
        """Set the currently selected rally.

        Args:
            index: Rally index (0-based)
        """
        if 0 <= index < len(self._cards):
            # Deselect previous
            if 0 <= self._current_index < len(self._cards):
                self._cards[self._current_index].set_selected(False)

            # Select new
            self._current_index = index
            self._cards[self._current_index].set_selected(True)

            # Scroll to make visible
            self._cards[self._current_index].ensurePolished()


class ReviewModeWidget(QWidget):
    """Main container for Final Review Mode.

    Composites all review components:
    - Rally header with progress
    - Timing adjustment controls
    - Score editing
    - Rally list navigation
    - Generate Kdenlive button

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
    exit_requested = pyqtSignal()
    generate_requested = pyqtSignal()
    play_rally_requested = pyqtSignal(int)
    navigate_previous = pyqtSignal()
    navigate_next = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the review mode widget.

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
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_MD)

        # Header with rally progress
        self._header = RallyHeaderWidget()
        self._header.exit_requested.connect(self.exit_requested.emit)
        layout.addWidget(self._header)

        # Timing controls
        self._timing_widget = TimingControlWidget()
        self._timing_widget.timing_adjusted.connect(self._on_timing_adjusted)
        layout.addWidget(self._timing_widget)

        # Score editing
        self._score_widget = ScoreEditWidget()
        self._score_widget.score_changed.connect(self._on_score_changed)
        layout.addWidget(self._score_widget)

        # Rally list
        self._rally_list = RallyListWidget()
        self._rally_list.rally_selected.connect(self._on_rally_selected)
        layout.addWidget(self._rally_list)

        # Navigation controls
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(SPACE_MD)

        prev_button = QPushButton("◀ Previous")
        prev_button.setFont(Fonts.button_other())
        prev_button.clicked.connect(self._on_previous_clicked)
        self._style_nav_button(prev_button)
        nav_layout.addWidget(prev_button)

        play_button = QPushButton("▶ Play Rally")
        play_button.setFont(Fonts.button_other())
        play_button.clicked.connect(self._on_play_clicked)
        self._style_nav_button(play_button)
        nav_layout.addWidget(play_button)

        next_button = QPushButton("Next ▶")
        next_button.setFont(Fonts.button_other())
        next_button.clicked.connect(self._on_next_clicked)
        self._style_nav_button(next_button)
        nav_layout.addWidget(next_button)

        layout.addLayout(nav_layout)

        # Generate section
        generate_container = QWidget()
        generate_layout = QVBoxLayout(generate_container)
        generate_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        generate_layout.setSpacing(SPACE_MD)

        summary_label = QLabel("✓ Ready to generate output")
        summary_label.setFont(Fonts.body(size=14, weight=500))
        summary_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        generate_layout.addWidget(summary_label)

        generate_button = QPushButton("GENERATE KDENLIVE PROJECT")
        generate_button.setFont(Fonts.button_rally())
        generate_button.clicked.connect(self.generate_requested.emit)
        generate_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {PRIMARY_ACTION};
                color: {BG_PRIMARY};
                border: 2px solid {PRIMARY_ACTION};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_MD}px {SPACE_XL}px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: {TEXT_ACCENT};
                box-shadow: 0 0 20px {GLOW_GREEN};
            }}
        """)
        generate_layout.addWidget(generate_button, alignment=Qt.AlignmentFlag.AlignCenter)

        generate_container.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_SECONDARY};
                border: 2px solid {BORDER_COLOR};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        layout.addWidget(generate_container)

        # Main container styling
        self.setStyleSheet(f"""
            ReviewModeWidget {{
                background-color: {BG_PRIMARY};
            }}
        """)

    def _style_nav_button(self, button: QPushButton) -> None:
        """Apply consistent styling to navigation buttons.

        Args:
            button: Button to style
        """
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_LG}px;
                min-width: 120px;
            }}
            QPushButton:hover {{
                background-color: {BG_BORDER};
                border-color: {PRIMARY_ACTION};
            }}
        """)

    def _on_timing_adjusted(self, field: str, delta: float) -> None:
        """Handle timing adjustment from TimingControlWidget.

        Args:
            field: "start" or "end"
            delta: Time change in seconds
        """
        self.timing_adjusted.emit(self._current_index, field, delta)

    def _on_score_changed(self, new_score: str, cascade: bool) -> None:
        """Handle score change from ScoreEditWidget.

        Args:
            new_score: New score string
            cascade: Whether to cascade changes
        """
        self.score_changed.emit(self._current_index, new_score, cascade)

    def _on_rally_selected(self, index: int) -> None:
        """Handle rally selection from RallyListWidget.

        Args:
            index: Rally index (0-based)
        """
        self.set_current_rally(index)

    def _on_previous_clicked(self) -> None:
        """Handle previous button click."""
        if self._current_index > 0:
            self.set_current_rally(self._current_index - 1)
            self.navigate_previous.emit()

    def _on_next_clicked(self) -> None:
        """Handle next button click."""
        if self._current_index < len(self._rallies) - 1:
            self.set_current_rally(self._current_index + 1)
            self.navigate_next.emit()

    def _on_play_clicked(self) -> None:
        """Handle play rally button click."""
        self.play_rally_requested.emit(self._current_index)

    def set_rallies(self, rallies: list[Rally]) -> None:
        """Populate the review mode with rallies.

        Args:
            rallies: List of Rally objects
        """
        self._rallies = rallies
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

        # Update header
        self._header.set_rally(index, len(self._rallies))

        # Update timing controls (convert frames to seconds assuming 30fps)
        fps = 30.0  # TODO: Get from video metadata
        start_seconds = rally.start_frame / fps
        end_seconds = rally.end_frame / fps
        self._timing_widget.set_times(start_seconds, end_seconds)

        # Update score widget
        self._score_widget.set_current_score(rally.score_at_start)

        # Update rally list selection
        self._rally_list.set_current_rally(index)

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
