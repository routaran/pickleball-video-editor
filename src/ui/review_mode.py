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

from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
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
        self._counter_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(self._counter_label)

        layout.addStretch()

        # Return to Main Menu button
        self._return_to_menu_button = QPushButton("Main Menu")
        self._return_to_menu_button.setFont(Fonts.button_other())
        self._return_to_menu_button.clicked.connect(self.return_to_menu_requested.emit)
        self._return_to_menu_button.setStyleSheet(f"""
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
        layout.addWidget(self._return_to_menu_button)

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

    @pyqtSlot()
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
        self._list_widget.setFixedHeight(66)  # Fixed height for single row + scrollbar

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

    def _create_card_widget(self, rally_num: int, score: str) -> QWidget:
        """Create a card widget for a rally item.

        Args:
            rally_num: Rally number (1-based for display)
            score: Score string

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

        score_label = QLabel(score)
        score_label.setFont(Fonts.display(size=9))
        score_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
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
            widget = self._create_card_widget(idx + 1, rally.score_at_start)
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
    """Main container for Final Review Mode with dual-splitter layout.

    Composites all review components:
    - Rally header with progress (top, outside splitters)
    - Video placeholder + control panel (top section, horizontal split)
    - Rally list + navigation + generate (bottom section)

    Layout structure:
    - Header (fixed top)
    - Outer QSplitter (Vertical):
      - Top section with Inner QSplitter (Horizontal):
        - Video placeholder (stretches)
        - Control panel (fixed ~320px width)
      - Bottom section:
        - Rally list header with nav buttons
        - Rally list widget
        - Generate section

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
    return_to_menu_requested = pyqtSignal()
    generate_requested = pyqtSignal()
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
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize UI components with dual-splitter layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        main_layout.setSpacing(SPACE_MD)

        # Header with rally progress (stays at top, outside splitters)
        self._header = RallyHeaderWidget()
        self._header.exit_requested.connect(self.exit_requested.emit)
        self._header.return_to_menu_requested.connect(self.return_to_menu_requested.emit)
        main_layout.addWidget(self._header)

        # ===================================================================
        # OUTER SPLITTER (Vertical) - separates top section from rally list
        # ===================================================================
        self._outer_splitter = QSplitter(Qt.Orientation.Vertical)
        self._outer_splitter.setChildrenCollapsible(False)
        self._outer_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background: {BG_BORDER};
                height: 6px;
                border-radius: 3px;
            }}
            QSplitter::handle:vertical:hover {{
                background: {PRIMARY_ACTION};
            }}
        """)

        # ===================================================================
        # TOP SECTION - contains inner splitter (video + controls)
        # ===================================================================
        top_section = QWidget()
        top_section_layout = QVBoxLayout(top_section)
        top_section_layout.setContentsMargins(0, 0, 0, 0)
        top_section_layout.setSpacing(0)

        # INNER SPLITTER (Horizontal) - splits video placeholder from control panel
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._inner_splitter.setChildrenCollapsible(False)
        self._inner_splitter.setStyleSheet(f"""
            QSplitter::handle:horizontal {{
                background: {BG_BORDER};
                width: 6px;
                border-radius: 3px;
            }}
            QSplitter::handle:horizontal:hover {{
                background: {PRIMARY_ACTION};
            }}
        """)

        # Video Placeholder (for main_window to embed video widget)
        # Minimum size enforces 16:9 video at 870x490 (user requirement)
        self._video_placeholder = QWidget()
        self._video_placeholder.setObjectName("video_placeholder")
        self._video_placeholder.setMinimumSize(870, 490)
        # CRITICAL: Make placeholder a native window so MPV's X11 window can be
        # properly reparented here. Without this, the video stays at (0,0) of main window.
        self._video_placeholder.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._video_placeholder.winId()  # Force native window creation
        # No background/border - the embedded video container provides its own styling
        self._video_placeholder.setStyleSheet("")

        # Control Panel (Play Rally + Timing + Score)
        control_panel = QWidget()
        control_panel.setMinimumWidth(280)
        control_panel.setMaximumWidth(400)
        control_panel_layout = QVBoxLayout(control_panel)
        control_panel_layout.setContentsMargins(0, 0, 0, 0)
        control_panel_layout.setSpacing(SPACE_MD)

        # Play Rally button (prominent with green border)
        play_rally_button = QPushButton("▶ PLAY RALLY")
        play_rally_button.setFont(Fonts.button_rally())
        play_rally_button.clicked.connect(self._on_play_clicked)
        play_rally_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {PRIMARY_ACTION};
                border: 2px solid {PRIMARY_ACTION};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_MD}px {SPACE_LG}px;
                min-height: 48px;
            }}
            QPushButton:hover {{
                background-color: {PRIMARY_ACTION};
                color: {BG_PRIMARY};
                            }}
        """)
        control_panel_layout.addWidget(play_rally_button)

        # Timing controls
        self._timing_widget = TimingControlWidget()
        self._timing_widget.timing_adjusted.connect(self._on_timing_adjusted)
        control_panel_layout.addWidget(self._timing_widget)

        # Score editing
        self._score_widget = ScoreEditWidget()
        self._score_widget.score_changed.connect(self._on_score_changed)
        control_panel_layout.addWidget(self._score_widget)

        control_panel_layout.addStretch()

        # Add widgets to inner splitter
        self._inner_splitter.addWidget(self._video_placeholder)
        self._inner_splitter.addWidget(control_panel)
        self._inner_splitter.setSizes([600, 320])
        self._inner_splitter.setStretchFactor(0, 1)  # Video stretches
        self._inner_splitter.setStretchFactor(1, 0)  # Controls stay fixed width

        top_section_layout.addWidget(self._inner_splitter)

        # ===================================================================
        # BOTTOM SECTION - rally list + navigation + generate
        # ===================================================================
        bottom_section = QWidget()
        bottom_layout = QVBoxLayout(bottom_section)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(SPACE_MD)

        # Rally list header with navigation buttons
        list_header_layout = QHBoxLayout()
        list_header_layout.setSpacing(SPACE_MD)

        list_title = QLabel("RALLY LIST (click to navigate)")
        list_title.setFont(Fonts.body(size=12, weight=600))
        list_title.setStyleSheet(f"color: {TEXT_SECONDARY};")
        list_header_layout.addWidget(list_title)

        list_header_layout.addStretch()

        # Navigation buttons
        prev_button = QPushButton("◀ Prev")
        prev_button.setFont(Fonts.button_other())
        prev_button.clicked.connect(self._on_previous_clicked)
        self._style_nav_button(prev_button)
        list_header_layout.addWidget(prev_button)

        next_button = QPushButton("Next ▶")
        next_button.setFont(Fonts.button_other())
        next_button.clicked.connect(self._on_next_clicked)
        self._style_nav_button(next_button)
        list_header_layout.addWidget(next_button)

        bottom_layout.addLayout(list_header_layout)

        # Rally list
        self._rally_list = RallyListWidget()
        self._rally_list.rally_selected.connect(self._on_rally_selected)
        bottom_layout.addWidget(self._rally_list)

        # Generate section
        generate_container = QWidget()
        generate_layout = QVBoxLayout(generate_container)
        generate_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        generate_layout.setSpacing(SPACE_SM)

        summary_label = QLabel("✓ Ready to generate output")
        summary_label.setFont(Fonts.body(size=14, weight=500))
        summary_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        generate_layout.addWidget(summary_label)

        # Mark Game Completed checkbox
        self._mark_complete_checkbox = QCheckBox("Mark Game Completed")
        self._mark_complete_checkbox.setFont(Fonts.button_other())
        self._mark_complete_checkbox.toggled.connect(self._on_mark_complete_toggled)
        generate_layout.addWidget(self._mark_complete_checkbox)

        # Final score display (hidden until checkbox checked)
        self._final_score_label = QLabel("")
        self._final_score_label.setFont(Fonts.display(size=16, weight=600))
        self._final_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._final_score_label.hide()
        generate_layout.addWidget(self._final_score_label)

        # Export path section
        export_path_layout = QHBoxLayout()
        export_path_layout.setSpacing(SPACE_SM)

        export_label = QLabel("Export to:")
        export_label.setFont(Fonts.label())
        export_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        export_path_layout.addWidget(export_label)

        self._export_path_edit = QLineEdit()
        self._export_path_edit.setPlaceholderText("Click Browse or use default location...")
        self._export_path_edit.setReadOnly(False)
        self._export_path_edit.textChanged.connect(self._on_export_path_changed)
        self._export_path_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px;
            }}
            QLineEdit:focus {{
                border-color: {PRIMARY_ACTION};
            }}
        """)
        export_path_layout.addWidget(self._export_path_edit, stretch=1)

        self._browse_button = QPushButton("Browse")
        self._browse_button.setFont(Fonts.button_other())
        self._browse_button.clicked.connect(self._on_browse_clicked)
        self._browse_button.setStyleSheet(f"""
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
        export_path_layout.addWidget(self._browse_button)

        generate_layout.addLayout(export_path_layout)

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
        bottom_layout.addWidget(generate_container)

        # ===================================================================
        # Add sections to outer splitter
        # ===================================================================
        self._outer_splitter.addWidget(top_section)
        self._outer_splitter.addWidget(bottom_section)
        self._outer_splitter.setSizes([400, 200])

        main_layout.addWidget(self._outer_splitter)

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
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {BG_BORDER};
                border-color: {PRIMARY_ACTION};
            }}
        """)

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

    def set_rallies(self, rallies: list[Rally], fps: float = 60.0, is_highlights: bool = False) -> None:
        """Populate the review mode with rallies.

        Args:
            rallies: List of Rally objects
            fps: Video frames per second for time calculations
            is_highlights: If True, hide score-related controls
        """
        self._rallies = rallies
        self._fps = fps
        self._is_highlights = is_highlights

        # Hide score widget in highlights mode
        if is_highlights:
            self._score_widget.hide()
        else:
            self._score_widget.show()

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

        # Update timing controls (convert frames to seconds using actual fps)
        start_seconds = rally.start_frame / self._fps
        end_seconds = rally.end_frame / self._fps
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

    def get_video_placeholder(self) -> QWidget:
        """Get the video placeholder widget for external embedding.

        MainWindow can use this to parent the video widget inside the review mode.

        Returns:
            Video placeholder widget
        """
        return self._video_placeholder

    def get_inner_splitter(self) -> QSplitter:
        """Get the inner horizontal splitter for external configuration.

        Returns:
            Inner QSplitter (horizontal)
        """
        return self._inner_splitter

    def get_outer_splitter(self) -> QSplitter:
        """Get the outer vertical splitter for external configuration.

        Returns:
            Outer QSplitter (vertical)
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
