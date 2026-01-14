"""Add Comment Dialog for the Pickleball Video Editor.

This module provides a modal dialog for adding commentary markers at specific
timestamps during video editing. Useful for:
- Noting exceptional plays or highlights
- Marking referee calls or controversial points
- Adding context for future review or export

Comments are stored with timestamps and duration for overlay generation.
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QPushButton,
    QFrame,
)

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
)


@dataclass
class AddCommentResult:
    """Result of the Add Comment dialog.

    Attributes:
        timestamp: Video timestamp in seconds where comment should appear
        comment: Comment text to display
        duration: How long the comment should be visible (in seconds)
    """
    timestamp: float
    comment: str
    duration: float


class AddCommentDialog(QDialog):
    """Modal dialog for adding a comment marker at a timestamp.

    Allows users to add annotations at specific video positions with configurable
    duration. Comments can be exported as subtitle overlays or documentation.

    Example:
        ```python
        # Get current video position
        current_time = player.get_position()

        dialog = AddCommentDialog(
            timestamp=current_time,
            parent=main_window
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                comment_manager.add_comment(
                    result.timestamp,
                    result.comment,
                    result.duration
                )
        ```
    """

    def __init__(
        self,
        timestamp: float,
        parent=None
    ):
        """Initialize the Add Comment dialog.

        Args:
            timestamp: Video timestamp in seconds for the comment
            parent: Parent widget for modal behavior
        """
        super().__init__(parent)

        self.timestamp = timestamp
        self.result: AddCommentResult | None = None

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Create and layout the dialog widgets."""
        self.setWindowTitle("Add Comment")
        self.setModal(True)
        self.setFixedWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Title
        title_label = QLabel("Add Comment")
        title_label.setFont(Fonts.dialog_title())
        layout.addWidget(title_label)

        # Timestamp section (read-only)
        timestamp_label = QLabel("TIMESTAMP")
        timestamp_label.setFont(Fonts.secondary())
        layout.addWidget(timestamp_label)

        self.timestamp_display = QLineEdit()
        self.timestamp_display.setFont(Fonts.display())
        self.timestamp_display.setText(self._format_timestamp(self.timestamp))
        self.timestamp_display.setReadOnly(True)
        self.timestamp_display.setFixedHeight(48)
        self.timestamp_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timestamp_display.setObjectName("timestamp_display")
        layout.addWidget(self.timestamp_display)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setObjectName("separator")
        layout.addWidget(separator1)

        # Comment section (required)
        comment_label = QLabel("COMMENT *")
        comment_label.setFont(Fonts.secondary())
        layout.addWidget(comment_label)

        self.comment_input = QTextEdit()
        self.comment_input.setFont(Fonts.input_text())
        self.comment_input.setPlaceholderText("Enter your comment here...")
        self.comment_input.setFixedHeight(120)
        self.comment_input.setObjectName("comment_input")
        layout.addWidget(self.comment_input)

        # Duration section
        duration_label = QLabel("DURATION")
        duration_label.setFont(Fonts.secondary())
        layout.addWidget(duration_label)

        duration_layout = QHBoxLayout()
        duration_layout.setSpacing(SPACE_MD)

        self.duration_spinner = QSpinBox()
        self.duration_spinner.setFont(Fonts.input_text())
        self.duration_spinner.setMinimum(1)
        self.duration_spinner.setMaximum(60)
        self.duration_spinner.setValue(5)  # Default: 5 seconds
        self.duration_spinner.setSuffix(" seconds")
        self.duration_spinner.setFixedHeight(48)
        self.duration_spinner.setObjectName("duration_spinner")
        duration_layout.addWidget(self.duration_spinner)

        duration_hint = QLabel("How long should the comment be visible?")
        duration_hint.setFont(Fonts.secondary())
        duration_hint.setObjectName("duration_hint")
        duration_layout.addWidget(duration_hint)
        duration_layout.addStretch()

        layout.addLayout(duration_layout)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFont(Fonts.button_other())
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.setMinimumWidth(100)
        self.cancel_button.setObjectName("cancel_button")
        button_layout.addWidget(self.cancel_button)

        self.add_button = QPushButton("Add")
        self.add_button.setFont(Fonts.button_other())
        self.add_button.setFixedHeight(40)
        self.add_button.setMinimumWidth(100)
        self.add_button.setObjectName("add_button")
        self.add_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.add_button)

        layout.addLayout(button_layout)

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

            QLabel#duration_hint {{
                color: {TEXT_SECONDARY};
            }}

            QLineEdit {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
            }}

            QLineEdit#timestamp_display {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                color: {TEXT_SECONDARY};
                font-variant-numeric: tabular-nums;
            }}

            QTextEdit {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
            }}

            QTextEdit:focus {{
                border-color: {TEXT_ACCENT};
            }}

            QSpinBox {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
                font-variant-numeric: tabular-nums;
            }}

            QSpinBox:focus {{
                border-color: {TEXT_ACCENT};
            }}

            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {BG_BORDER};
                border: none;
                width: 20px;
            }}

            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {TEXT_ACCENT};
            }}

            QSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 6px solid {TEXT_PRIMARY};
                width: 0;
                height: 0;
            }}

            QSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {TEXT_PRIMARY};
                width: 0;
                height: 0;
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

            QPushButton#add_button {{
                background-color: {PRIMARY_ACTION};
                border-color: {PRIMARY_ACTION};
                color: {BG_SECONDARY};
                font-weight: 600;
            }}

            QPushButton#add_button:hover:!disabled {{
                background-color: {TEXT_ACCENT};
                border-color: {TEXT_ACCENT};
            }}

            QPushButton:disabled {{
                opacity: 0.4;
                background-color: {BG_TERTIARY};
                border-color: {BG_BORDER};
                color: {TEXT_SECONDARY};
            }}
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.comment_input.textChanged.connect(self._validate_comment)
        self.cancel_button.clicked.connect(self.reject)
        self.add_button.clicked.connect(self._on_add)

    def _validate_comment(self) -> None:
        """Validate the comment text and enable/disable the Add button.

        The Add button is only enabled when the comment text is non-empty.
        """
        comment_text = self.comment_input.toPlainText().strip()
        self.add_button.setEnabled(bool(comment_text))

    def _format_timestamp(self, seconds: float) -> str:
        """Format a timestamp in MM:SS.ss format.

        Args:
            seconds: Timestamp in seconds

        Returns:
            Formatted string (e.g., "03:45.23")
        """
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes:02d}:{remaining_seconds:05.2f}"

    def _on_add(self) -> None:
        """Handle Add button click.

        Creates the result object and accepts the dialog.
        """
        comment_text = self.comment_input.toPlainText().strip()
        duration = float(self.duration_spinner.value())

        self.result = AddCommentResult(
            timestamp=self.timestamp,
            comment=comment_text,
            duration=duration
        )

        self.accept()

    def get_result(self) -> AddCommentResult | None:
        """Get the dialog result after execution.

        Returns:
            AddCommentResult if the dialog was accepted, None if cancelled
        """
        return self.result


__all__ = ["AddCommentDialog", "AddCommentResult"]
