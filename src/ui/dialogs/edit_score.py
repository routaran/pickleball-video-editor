"""Edit Score Dialog for the Pickleball Video Editor.

This module provides a modal dialog for manually correcting rally scores during
video editing. Used when the automatic score tracking makes an error.

The dialog displays the current score as read-only, with an input field for the
corrected score and an optional comment field for documentation.

Format validation:
- Singles: X-Y (two numbers separated by a dash)
- Doubles: X-Y-Z (three numbers separated by dashes)
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
class EditScoreResult:
    """Result of the Edit Score dialog.

    Attributes:
        new_score: The corrected score string (e.g., "7-5-2")
        comment: Optional explanation for the correction
    """
    new_score: str
    comment: str | None


class EditScoreDialog(QDialog):
    """Modal dialog for editing a rally's score.

    Allows users to manually correct the score when automatic tracking fails.
    Validates score format based on game type (singles vs doubles) and prevents
    submission of invalid scores.

    Example:
        ```python
        dialog = EditScoreDialog(
            current_score="7-5-2",
            is_doubles=True,
            parent=main_window
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                rally_manager.update_score(result.new_score, result.comment)
        ```
    """

    def __init__(
        self,
        current_score: str,
        is_doubles: bool,
        parent=None
    ):
        """Initialize the Edit Score dialog.

        Args:
            current_score: Current score string to be edited
            is_doubles: True for doubles format (X-Y-Z), False for singles (X-Y)
            parent: Parent widget for modal behavior
        """
        super().__init__(parent)

        self.current_score = current_score
        self.is_doubles = is_doubles
        self.result: EditScoreResult | None = None

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Create and layout the dialog widgets."""
        self.setWindowTitle("Edit Score")
        self.setModal(True)
        self.setFixedWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Title
        title_label = QLabel("Edit Score")
        title_label.setFont(Fonts.dialog_title())
        layout.addWidget(title_label)

        # Score section
        score_layout = QHBoxLayout()
        score_layout.setSpacing(SPACE_MD)

        # Current score (read-only display)
        current_container = QVBoxLayout()
        current_label = QLabel("CURRENT")
        current_label.setFont(Fonts.secondary())
        current_container.addWidget(current_label)

        self.current_score_display = QLabel(self.current_score)
        self.current_score_display.setFont(Fonts.display())
        self.current_score_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_score_display.setFixedHeight(48)
        self.current_score_display.setObjectName("current_score_display")
        current_container.addWidget(self.current_score_display)

        # Arrow
        arrow_label = QLabel("→")
        arrow_label.setFont(Fonts.score_display())
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # New score input
        new_container = QVBoxLayout()
        new_label = QLabel("NEW SCORE *")
        new_label.setFont(Fonts.secondary())
        new_container.addWidget(new_label)

        self.new_score_input = QLineEdit()
        self.new_score_input.setFont(Fonts.input_text())
        self.new_score_input.setPlaceholderText(
            "X-Y-Z" if self.is_doubles else "X-Y"
        )
        self.new_score_input.setFixedHeight(48)
        self.new_score_input.setObjectName("new_score_input")
        new_container.addWidget(self.new_score_input)

        # Format hint
        format_hint = QLabel(
            f"Format: {'X-Y-Z (doubles)' if self.is_doubles else 'X-Y (singles)'}"
        )
        format_hint.setFont(Fonts.secondary())
        format_hint.setObjectName("format_hint")
        new_container.addWidget(format_hint)

        score_layout.addLayout(current_container, 1)
        score_layout.addWidget(arrow_label)
        score_layout.addLayout(new_container, 2)

        layout.addLayout(score_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        # Error message (initially hidden)
        self.error_label = QLabel()
        self.error_label.setFont(Fonts.secondary())
        self.error_label.setObjectName("error_label")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Comment section
        comment_label = QLabel("COMMENT (optional)")
        comment_label.setFont(Fonts.secondary())
        layout.addWidget(comment_label)

        self.comment_input = QTextEdit()
        self.comment_input.setFont(Fonts.input_text())
        self.comment_input.setPlaceholderText("Explain why the score needed correction...")
        self.comment_input.setFixedHeight(80)
        self.comment_input.setObjectName("comment_input")
        layout.addWidget(self.comment_input)

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
        self.apply_button.setEnabled(False)
        button_layout.addWidget(self.apply_button)

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

            QLabel#current_score_display {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_SECONDARY};
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

            QLineEdit#new_score_input {{
                font-variant-numeric: tabular-nums;
            }}

            QLabel#format_hint {{
                color: {TEXT_SECONDARY};
                margin-top: 4px;
            }}

            QLabel#error_label {{
                color: #EF5350;
                margin-top: -8px;
                margin-bottom: 8px;
            }}

            QFrame#separator {{
                background-color: {BG_BORDER};
                max-height: 1px;
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
        """)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self.new_score_input.textChanged.connect(self._validate_score)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._on_apply)

    def _validate_score(self) -> None:
        """Validate the score format and enable/disable the Apply button.

        Checks that the score matches the expected format:
        - Singles: X-Y (two numbers)
        - Doubles: X-Y-Z (three numbers)

        Updates the error label and Apply button state accordingly.
        """
        score_text = self.new_score_input.text().strip()

        # Empty input - disable button, no error
        if not score_text:
            self.apply_button.setEnabled(False)
            self.error_label.setVisible(False)
            return

        # Split by dash
        parts = score_text.split("-")

        # Check expected number of parts
        expected_parts = 3 if self.is_doubles else 2
        if len(parts) != expected_parts:
            self._show_error(
                f"Expected {expected_parts} numbers separated by dashes"
            )
            self.apply_button.setEnabled(False)
            return

        # Check that all parts are numeric
        if not all(part.strip().isdigit() for part in parts):
            self._show_error("Score must contain only numbers and dashes")
            self.apply_button.setEnabled(False)
            return

        # Valid score
        self.error_label.setVisible(False)
        self.apply_button.setEnabled(True)

    def _show_error(self, message: str) -> None:
        """Display an inline error message.

        Args:
            message: Error message to display
        """
        self.error_label.setText(f"⚠ {message}")
        self.error_label.setVisible(True)

    def _on_apply(self) -> None:
        """Handle Apply button click.

        Creates the result object and accepts the dialog.
        """
        # Get normalized score (strip extra whitespace)
        new_score = self.new_score_input.text().strip()

        # Get comment (None if empty)
        comment_text = self.comment_input.toPlainText().strip()
        comment = comment_text if comment_text else None

        self.result = EditScoreResult(
            new_score=new_score,
            comment=comment
        )

        self.accept()

    def get_result(self) -> EditScoreResult | None:
        """Get the dialog result after execution.

        Returns:
            EditScoreResult if the dialog was accepted, None if cancelled
        """
        return self.result


__all__ = ["EditScoreDialog", "EditScoreResult"]
