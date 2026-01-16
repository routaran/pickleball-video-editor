"""Configuration Dialog for the Pickleball Video Editor.

This module provides a modal dialog for configuring application settings through
a tabbed interface. Settings include keyboard shortcuts, video skip durations,
and window size constraints.

The dialog validates inputs in real-time and prevents invalid configurations from
being applied (e.g., duplicate shortcuts, invalid key characters).

Settings are persisted to ~/.config/pickleball-editor/config.json when applied.
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QWidget,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QFrame,
    QGroupBox,
)

from src.core.app_config import AppSettings, ShortcutConfig, SkipDurationConfig, WindowSizeConfig
from src.ui.styles.colors import (
    BG_SECONDARY,
    BG_TERTIARY,
    BG_BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_ACCENT,
    PRIMARY_ACTION,
)
from src.ui.styles.fonts import (
    Fonts,
    SPACE_MD,
    SPACE_LG,
    RADIUS_XL,
    RADIUS_MD,
)


@dataclass
class ConfigDialogResult:
    """Result of the configuration dialog.

    Attributes:
        settings: The configured application settings
    """
    settings: AppSettings


class ConfigDialog(QDialog):
    """Modal dialog for configuring application settings.

    Provides a tabbed interface for configuring:
    - Tab 1: Keyboard shortcuts for rally actions
    - Tab 2: Skip durations for playback buttons and arrow keys
    - Tab 3: Window size constraints

    All inputs are validated in real-time. The Apply button is disabled when
    validation errors exist.

    Example:
        ```python
        current_settings = AppSettings.load()
        dialog = ConfigDialog(current_settings, parent=main_window)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                result.settings.save()
                # Apply settings to application
        ```
    """

    def __init__(self, current_settings: AppSettings, parent=None):
        """Initialize the Configuration dialog.

        Args:
            current_settings: Current application settings to edit
            parent: Parent widget for modal behavior
        """
        super().__init__(parent)
        self.setObjectName("configDialog")

        self.current_settings = current_settings
        self.result: ConfigDialogResult | None = None

        # Validation state
        self.validation_errors: list[str] = []

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()
        self._load_current_settings()

    def _setup_ui(self) -> None:
        """Create and layout the dialog widgets."""
        self.setWindowTitle("Configuration")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Title
        title_label = QLabel("Configuration")
        title_label.setFont(Fonts.dialog_title())
        layout.addWidget(title_label)

        # Tabbed interface
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("config_tabs")

        # Tab 1: Shortcuts
        self.shortcuts_tab = self._create_shortcuts_tab()
        self.tab_widget.addTab(self.shortcuts_tab, "Shortcuts")

        # Tab 2: Skip Durations
        self.skip_durations_tab = self._create_skip_durations_tab()
        self.tab_widget.addTab(self.skip_durations_tab, "Skip Durations")

        # Tab 3: Window Size
        self.window_size_tab = self._create_window_size_tab()
        self.tab_widget.addTab(self.window_size_tab, "Window Size")

        layout.addWidget(self.tab_widget)

        # Error message (initially hidden)
        self.error_label = QLabel()
        self.error_label.setFont(Fonts.secondary())
        self.error_label.setObjectName("error_label")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFont(Fonts.button_other())
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.setMinimumWidth(100)
        self.cancel_button.setObjectName("cancel_button")
        button_layout.addWidget(self.cancel_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setFont(Fonts.button_other())
        self.apply_button.setFixedHeight(40)
        self.apply_button.setMinimumWidth(100)
        self.apply_button.setObjectName("apply_button")
        button_layout.addWidget(self.apply_button)

        layout.addLayout(button_layout)

    def _create_shortcuts_tab(self) -> QWidget:
        """Create the Shortcuts configuration tab.

        Returns:
            QWidget containing shortcut configuration controls
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Instructions
        instructions = QLabel(
            "Configure keyboard shortcuts for rally actions. "
            "Shortcuts must be single alphanumeric characters and cannot be duplicated."
        )
        instructions.setFont(Fonts.secondary())
        instructions.setWordWrap(True)
        instructions.setObjectName("instructions_label")
        layout.addWidget(instructions)

        # Shortcut grid
        grid = QGridLayout()
        grid.setSpacing(SPACE_MD)
        grid.setColumnStretch(1, 1)

        # Rally Start
        rally_start_label = QLabel("Rally Start:")
        rally_start_label.setFont(Fonts.label())
        grid.addWidget(rally_start_label, 0, 0)

        self.rally_start_input = QLineEdit()
        self.rally_start_input.setFont(Fonts.input_text())
        self.rally_start_input.setMaxLength(1)
        self.rally_start_input.setPlaceholderText("C")
        self.rally_start_input.setObjectName("shortcut_input")
        grid.addWidget(self.rally_start_input, 0, 1)

        rally_start_default = QLabel("Default: C")
        rally_start_default.setFont(Fonts.secondary())
        rally_start_default.setObjectName("default_label")
        grid.addWidget(rally_start_default, 0, 2)

        # Server Wins
        server_wins_label = QLabel("Server Wins:")
        server_wins_label.setFont(Fonts.label())
        grid.addWidget(server_wins_label, 1, 0)

        self.server_wins_input = QLineEdit()
        self.server_wins_input.setFont(Fonts.input_text())
        self.server_wins_input.setMaxLength(1)
        self.server_wins_input.setPlaceholderText("S")
        self.server_wins_input.setObjectName("shortcut_input")
        grid.addWidget(self.server_wins_input, 1, 1)

        server_wins_default = QLabel("Default: S")
        server_wins_default.setFont(Fonts.secondary())
        server_wins_default.setObjectName("default_label")
        grid.addWidget(server_wins_default, 1, 2)

        # Receiver Wins
        receiver_wins_label = QLabel("Receiver Wins:")
        receiver_wins_label.setFont(Fonts.label())
        grid.addWidget(receiver_wins_label, 2, 0)

        self.receiver_wins_input = QLineEdit()
        self.receiver_wins_input.setFont(Fonts.input_text())
        self.receiver_wins_input.setMaxLength(1)
        self.receiver_wins_input.setPlaceholderText("R")
        self.receiver_wins_input.setObjectName("shortcut_input")
        grid.addWidget(self.receiver_wins_input, 2, 1)

        receiver_wins_default = QLabel("Default: R")
        receiver_wins_default.setFont(Fonts.secondary())
        receiver_wins_default.setObjectName("default_label")
        grid.addWidget(receiver_wins_default, 2, 2)

        # Undo
        undo_label = QLabel("Undo:")
        undo_label.setFont(Fonts.label())
        grid.addWidget(undo_label, 3, 0)

        self.undo_input = QLineEdit()
        self.undo_input.setFont(Fonts.input_text())
        self.undo_input.setMaxLength(1)
        self.undo_input.setPlaceholderText("U")
        self.undo_input.setObjectName("shortcut_input")
        grid.addWidget(self.undo_input, 3, 1)

        undo_default = QLabel("Default: U")
        undo_default.setFont(Fonts.secondary())
        undo_default.setObjectName("default_label")
        grid.addWidget(undo_default, 3, 2)

        layout.addLayout(grid)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        # Reset to defaults button
        reset_button = QPushButton("Reset to Defaults")
        reset_button.setFont(Fonts.button_other())
        reset_button.setFixedHeight(36)
        reset_button.setObjectName("reset_button")
        reset_button.clicked.connect(self._reset_shortcuts_to_defaults)
        layout.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        return tab

    def _create_skip_durations_tab(self) -> QWidget:
        """Create the Skip Durations configuration tab.

        Returns:
            QWidget containing skip duration configuration controls
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Instructions
        instructions = QLabel(
            "Configure video skip durations in seconds for playback buttons and keyboard arrows."
        )
        instructions.setFont(Fonts.secondary())
        instructions.setWordWrap(True)
        instructions.setObjectName("instructions_label")
        layout.addWidget(instructions)

        # Playback Buttons Section
        playback_group = QGroupBox("Playback Buttons")
        playback_group.setFont(Fonts.label())
        playback_group.setObjectName("config_group")
        playback_layout = QGridLayout(playback_group)
        playback_layout.setSpacing(SPACE_MD)

        # Small Backward
        playback_layout.addWidget(QLabel("Small Backward:"), 0, 0)
        self.small_backward_spin = QDoubleSpinBox()
        self.small_backward_spin.setRange(0.5, 60.0)
        self.small_backward_spin.setSingleStep(0.5)
        self.small_backward_spin.setSuffix(" s")
        self.small_backward_spin.setObjectName("duration_spin")
        playback_layout.addWidget(self.small_backward_spin, 0, 1)

        # Large Backward
        playback_layout.addWidget(QLabel("Large Backward:"), 1, 0)
        self.large_backward_spin = QDoubleSpinBox()
        self.large_backward_spin.setRange(0.5, 60.0)
        self.large_backward_spin.setSingleStep(0.5)
        self.large_backward_spin.setSuffix(" s")
        self.large_backward_spin.setObjectName("duration_spin")
        playback_layout.addWidget(self.large_backward_spin, 1, 1)

        # Small Forward
        playback_layout.addWidget(QLabel("Small Forward:"), 2, 0)
        self.small_forward_spin = QDoubleSpinBox()
        self.small_forward_spin.setRange(0.5, 60.0)
        self.small_forward_spin.setSingleStep(0.5)
        self.small_forward_spin.setSuffix(" s")
        self.small_forward_spin.setObjectName("duration_spin")
        playback_layout.addWidget(self.small_forward_spin, 2, 1)

        # Large Forward
        playback_layout.addWidget(QLabel("Large Forward:"), 3, 0)
        self.large_forward_spin = QDoubleSpinBox()
        self.large_forward_spin.setRange(0.5, 60.0)
        self.large_forward_spin.setSingleStep(0.5)
        self.large_forward_spin.setSuffix(" s")
        self.large_forward_spin.setObjectName("duration_spin")
        playback_layout.addWidget(self.large_forward_spin, 3, 1)

        layout.addWidget(playback_group)

        # Keyboard Arrows Section
        arrows_group = QGroupBox("Keyboard Arrows")
        arrows_group.setFont(Fonts.label())
        arrows_group.setObjectName("config_group")
        arrows_layout = QGridLayout(arrows_group)
        arrows_layout.setSpacing(SPACE_MD)

        # Left Arrow
        arrows_layout.addWidget(QLabel("Left Arrow:"), 0, 0)
        self.arrow_left_spin = QDoubleSpinBox()
        self.arrow_left_spin.setRange(-60.0, 0.0)
        self.arrow_left_spin.setSingleStep(0.5)
        self.arrow_left_spin.setSuffix(" s")
        self.arrow_left_spin.setObjectName("duration_spin")
        arrows_layout.addWidget(self.arrow_left_spin, 0, 1)

        # Right Arrow
        arrows_layout.addWidget(QLabel("Right Arrow:"), 1, 0)
        self.arrow_right_spin = QDoubleSpinBox()
        self.arrow_right_spin.setRange(0.5, 60.0)
        self.arrow_right_spin.setSingleStep(0.5)
        self.arrow_right_spin.setSuffix(" s")
        self.arrow_right_spin.setObjectName("duration_spin")
        arrows_layout.addWidget(self.arrow_right_spin, 1, 1)

        # Down Arrow
        arrows_layout.addWidget(QLabel("Down Arrow:"), 2, 0)
        self.arrow_down_spin = QDoubleSpinBox()
        self.arrow_down_spin.setRange(-60.0, 0.0)
        self.arrow_down_spin.setSingleStep(0.5)
        self.arrow_down_spin.setSuffix(" s")
        self.arrow_down_spin.setObjectName("duration_spin")
        arrows_layout.addWidget(self.arrow_down_spin, 2, 1)

        # Up Arrow
        arrows_layout.addWidget(QLabel("Up Arrow:"), 3, 0)
        self.arrow_up_spin = QDoubleSpinBox()
        self.arrow_up_spin.setRange(0.5, 60.0)
        self.arrow_up_spin.setSingleStep(0.5)
        self.arrow_up_spin.setSuffix(" s")
        self.arrow_up_spin.setObjectName("duration_spin")
        arrows_layout.addWidget(self.arrow_up_spin, 3, 1)

        layout.addWidget(arrows_group)

        layout.addStretch()

        return tab

    def _create_window_size_tab(self) -> QWidget:
        """Create the Window Size configuration tab.

        Returns:
            QWidget containing window size configuration controls
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(SPACE_MD)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Instructions
        instructions = QLabel(
            "Configure minimum and maximum window size constraints. "
            "Set maximum to 0 for unlimited size."
        )
        instructions.setFont(Fonts.secondary())
        instructions.setWordWrap(True)
        instructions.setObjectName("instructions_label")
        layout.addWidget(instructions)

        # Size grid
        grid = QGridLayout()
        grid.setSpacing(SPACE_MD)

        # Minimum Width
        min_width_label = QLabel("Minimum Width:")
        min_width_label.setFont(Fonts.label())
        grid.addWidget(min_width_label, 0, 0)

        self.min_width_spin = QSpinBox()
        self.min_width_spin.setRange(800, 3840)
        self.min_width_spin.setSingleStep(100)
        self.min_width_spin.setSuffix(" px")
        self.min_width_spin.setObjectName("size_spin")
        grid.addWidget(self.min_width_spin, 0, 1)

        # Minimum Height
        min_height_label = QLabel("Minimum Height:")
        min_height_label.setFont(Fonts.label())
        grid.addWidget(min_height_label, 1, 0)

        self.min_height_spin = QSpinBox()
        self.min_height_spin.setRange(600, 2160)
        self.min_height_spin.setSingleStep(100)
        self.min_height_spin.setSuffix(" px")
        self.min_height_spin.setObjectName("size_spin")
        grid.addWidget(self.min_height_spin, 1, 1)

        # Maximum Width
        max_width_label = QLabel("Maximum Width:")
        max_width_label.setFont(Fonts.label())
        grid.addWidget(max_width_label, 2, 0)

        self.max_width_spin = QSpinBox()
        self.max_width_spin.setRange(0, 7680)
        self.max_width_spin.setSingleStep(100)
        self.max_width_spin.setSuffix(" px")
        self.max_width_spin.setSpecialValueText("Unlimited")
        self.max_width_spin.setObjectName("size_spin")
        grid.addWidget(self.max_width_spin, 2, 1)

        # Maximum Height
        max_height_label = QLabel("Maximum Height:")
        max_height_label.setFont(Fonts.label())
        grid.addWidget(max_height_label, 3, 0)

        self.max_height_spin = QSpinBox()
        self.max_height_spin.setRange(0, 4320)
        self.max_height_spin.setSingleStep(100)
        self.max_height_spin.setSuffix(" px")
        self.max_height_spin.setSpecialValueText("Unlimited")
        self.max_height_spin.setObjectName("size_spin")
        grid.addWidget(self.max_height_spin, 3, 1)

        layout.addLayout(grid)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        # Unlimited maximum checkbox
        self.unlimited_max_checkbox = QCheckBox("Unlimited maximum size")
        self.unlimited_max_checkbox.setFont(Fonts.label())
        self.unlimited_max_checkbox.setObjectName("unlimited_checkbox")
        self.unlimited_max_checkbox.stateChanged.connect(self._on_unlimited_max_changed)
        layout.addWidget(self.unlimited_max_checkbox)

        layout.addStretch()

        return tab

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

            QLabel#instructions_label {{
                color: {TEXT_SECONDARY};
                padding: {SPACE_MD}px;
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
            }}

            QLabel#default_label {{
                color: {TEXT_SECONDARY};
            }}

            QLabel#error_label {{
                color: #EF5350;
                padding: {SPACE_MD}px;
                background-color: rgba(239, 83, 80, 0.1);
                border: 1px solid #EF5350;
                border-radius: {RADIUS_MD}px;
            }}

            QTabWidget::pane {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                top: -1px;
            }}

            QTabWidget#config_tabs::tab-bar {{
                alignment: left;
            }}

            QTabBar::tab {{
                background-color: {BG_TERTIARY};
                color: {TEXT_SECONDARY};
                padding: 10px 20px;
                border: 1px solid {BG_BORDER};
                border-bottom: none;
                border-top-left-radius: {RADIUS_MD}px;
                border-top-right-radius: {RADIUS_MD}px;
                margin-right: 4px;
            }}

            QTabBar::tab:selected {{
                background-color: {BG_SECONDARY};
                color: {TEXT_ACCENT};
                border-bottom: 2px solid {TEXT_ACCENT};
            }}

            QTabBar::tab:hover:!selected {{
                background-color: {BG_BORDER};
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

            QLineEdit#shortcut_input {{
                max-width: 80px;
            }}

            QDoubleSpinBox, QSpinBox {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 6px;
                color: {TEXT_PRIMARY};
                min-width: 120px;
            }}

            QDoubleSpinBox:focus, QSpinBox:focus {{
                border-color: {TEXT_ACCENT};
            }}

            QDoubleSpinBox::up-button, QSpinBox::up-button,
            QDoubleSpinBox::down-button, QSpinBox::down-button {{
                background-color: {BG_BORDER};
                border: none;
                width: 20px;
            }}

            QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
                background-color: {TEXT_ACCENT};
            }}

            QGroupBox {{
                background-color: transparent;
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_MD}px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: 600;
                color: {TEXT_PRIMARY};
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                left: 12px;
                color: {TEXT_ACCENT};
            }}

            QCheckBox {{
                color: {TEXT_PRIMARY};
                spacing: 8px;
            }}

            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                background-color: {BG_TERTIARY};
            }}

            QCheckBox::indicator:checked {{
                background-color: {PRIMARY_ACTION};
                border-color: {PRIMARY_ACTION};
            }}

            QCheckBox::indicator:hover {{
                border-color: {TEXT_ACCENT};
            }}

            QFrame#separator {{
                background-color: {BG_BORDER};
                max-height: 1px;
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

            QPushButton:disabled {{
                opacity: 0.4;
                background-color: {BG_TERTIARY};
                border-color: {BG_BORDER};
                color: {TEXT_SECONDARY};
            }}

            QPushButton#reset_button {{
                background-color: transparent;
                border: 2px solid {BG_BORDER};
                color: {TEXT_ACCENT};
            }}

            QPushButton#reset_button:hover {{
                background-color: {BG_TERTIARY};
                border-color: {TEXT_ACCENT};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        # Shortcut inputs - validate on text change
        self.rally_start_input.textChanged.connect(self._validate_shortcuts)
        self.server_wins_input.textChanged.connect(self._validate_shortcuts)
        self.receiver_wins_input.textChanged.connect(self._validate_shortcuts)
        self.undo_input.textChanged.connect(self._validate_shortcuts)

        # Dialog buttons
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._on_apply)

    def _load_current_settings(self) -> None:
        """Load current settings into the dialog inputs."""
        # Shortcuts
        self.rally_start_input.setText(self.current_settings.shortcuts.rally_start)
        self.server_wins_input.setText(self.current_settings.shortcuts.server_wins)
        self.receiver_wins_input.setText(self.current_settings.shortcuts.receiver_wins)
        self.undo_input.setText(self.current_settings.shortcuts.undo)

        # Skip Durations - Playback buttons
        self.small_backward_spin.setValue(self.current_settings.skip_durations.small_backward)
        self.large_backward_spin.setValue(self.current_settings.skip_durations.large_backward)
        self.small_forward_spin.setValue(self.current_settings.skip_durations.small_forward)
        self.large_forward_spin.setValue(self.current_settings.skip_durations.large_forward)

        # Skip Durations - Arrow keys
        self.arrow_left_spin.setValue(self.current_settings.skip_durations.arrow_left)
        self.arrow_right_spin.setValue(self.current_settings.skip_durations.arrow_right)
        self.arrow_down_spin.setValue(self.current_settings.skip_durations.arrow_down)
        self.arrow_up_spin.setValue(self.current_settings.skip_durations.arrow_up)

        # Window Size
        self.min_width_spin.setValue(self.current_settings.window_size.min_width)
        self.min_height_spin.setValue(self.current_settings.window_size.min_height)
        self.max_width_spin.setValue(self.current_settings.window_size.max_width)
        self.max_height_spin.setValue(self.current_settings.window_size.max_height)

        # Update checkbox state
        is_unlimited = (
            self.current_settings.window_size.max_width == 0
            and self.current_settings.window_size.max_height == 0
        )
        self.unlimited_max_checkbox.setChecked(is_unlimited)

        # Initial validation
        self._validate_shortcuts()

    def _validate_shortcuts(self) -> None:
        """Validate shortcut inputs and update Apply button state.

        Checks for:
        - Empty shortcuts
        - Non-alphanumeric characters
        - Duplicate shortcuts (case-insensitive)

        Updates error label and Apply button accordingly.
        """
        # Get all shortcut values
        shortcuts = {
            "Rally Start": self.rally_start_input.text().strip(),
            "Server Wins": self.server_wins_input.text().strip(),
            "Receiver Wins": self.receiver_wins_input.text().strip(),
            "Undo": self.undo_input.text().strip(),
        }

        errors: list[str] = []

        # Check each shortcut is valid
        for name, key in shortcuts.items():
            if not key:
                errors.append(f"{name}: Empty shortcut not allowed")
                continue

            if len(key) != 1:
                errors.append(f"{name}: Must be single character")
                continue

            if not key.isalnum():
                errors.append(f"{name}: Must be alphanumeric (got '{key}')")

        # Check for duplicates (case-insensitive)
        seen: dict[str, str] = {}
        for name, key in shortcuts.items():
            if not key or len(key) != 1:
                continue

            key_upper = key.upper()
            if key_upper in seen:
                errors.append(
                    f"Duplicate shortcut '{key}' used for {seen[key_upper]} and {name}"
                )
            else:
                seen[key_upper] = name

        # Update UI based on validation
        self.validation_errors = errors

        if errors:
            error_text = "⚠ Validation Errors:\n" + "\n".join(f"  • {err}" for err in errors)
            self.error_label.setText(error_text)
            self.error_label.setVisible(True)
            self.apply_button.setEnabled(False)
        else:
            self.error_label.setVisible(False)
            self.apply_button.setEnabled(True)

    def _reset_shortcuts_to_defaults(self) -> None:
        """Reset all shortcut inputs to default values."""
        defaults = ShortcutConfig()
        self.rally_start_input.setText(defaults.rally_start)
        self.server_wins_input.setText(defaults.server_wins)
        self.receiver_wins_input.setText(defaults.receiver_wins)
        self.undo_input.setText(defaults.undo)

    def _on_unlimited_max_changed(self, state: int) -> None:
        """Handle unlimited maximum checkbox state change.

        Args:
            state: Qt.CheckState value (Checked or Unchecked)
        """
        is_checked = state == Qt.CheckState.Checked.value

        if is_checked:
            # Set both max values to 0 (unlimited)
            self.max_width_spin.setValue(0)
            self.max_height_spin.setValue(0)
            self.max_width_spin.setEnabled(False)
            self.max_height_spin.setEnabled(False)
        else:
            # Re-enable max spinboxes
            self.max_width_spin.setEnabled(True)
            self.max_height_spin.setEnabled(True)

    def _on_apply(self) -> None:
        """Handle Apply button click.

        Collects all settings from inputs, creates result, and accepts dialog.
        """
        # Collect shortcut settings
        shortcuts = ShortcutConfig(
            rally_start=self.rally_start_input.text().strip(),
            server_wins=self.server_wins_input.text().strip(),
            receiver_wins=self.receiver_wins_input.text().strip(),
            undo=self.undo_input.text().strip(),
        )

        # Collect skip duration settings
        skip_durations = SkipDurationConfig(
            small_backward=self.small_backward_spin.value(),
            large_backward=self.large_backward_spin.value(),
            small_forward=self.small_forward_spin.value(),
            large_forward=self.large_forward_spin.value(),
            arrow_left=self.arrow_left_spin.value(),
            arrow_right=self.arrow_right_spin.value(),
            arrow_down=self.arrow_down_spin.value(),
            arrow_up=self.arrow_up_spin.value(),
        )

        # Collect window size settings
        window_size = WindowSizeConfig(
            min_width=self.min_width_spin.value(),
            min_height=self.min_height_spin.value(),
            max_width=self.max_width_spin.value(),
            max_height=self.max_height_spin.value(),
        )

        # Create result
        settings = AppSettings(
            shortcuts=shortcuts,
            skip_durations=skip_durations,
            window_size=window_size,
        )

        self.result = ConfigDialogResult(settings=settings)
        self.accept()

    def get_result(self) -> ConfigDialogResult | None:
        """Get the dialog result after execution.

        Returns:
            ConfigDialogResult if the dialog was accepted, None if cancelled
        """
        return self.result


__all__ = ["ConfigDialog", "ConfigDialogResult"]
