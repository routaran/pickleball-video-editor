"""Force Side-Out Dialog for the Pickleball Video Editor.

This module provides a modal dialog for manually forcing a side-out when the
automatic serving state tracking makes an error. Common scenarios include:
- Missed side-out during fast play
- Video editing mistake requiring correction
- Server switch not detected by the editor

The dialog shows the current server, previews the server after side-out, and
allows optional score correction.
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
class ForceSideOutResult:
    """Result of the Force Side-Out dialog.

    Attributes:
        new_score: Optional corrected score string, None to keep current
        comment: Optional explanation for the intervention
    """
    new_score: str | None
    comment: str | None


class ForceSideOutDialog(QDialog):
    """Modal dialog for forcing a side-out.

    Allows users to manually trigger a side-out when automatic tracking fails.
    Shows current and next server states, with optional score correction.

    Example:
        ```python
        dialog = ForceSideOutDialog(
            current_server_info="Team 1 - Server 2",
            next_server_info="Team 2 - Server 1",
            current_score="7-5-2",
            is_doubles=True,
            parent=main_window
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                rally_manager.force_sideout(result.new_score, result.comment)
        ```
    """

    def __init__(
        self,
        current_server_info: str,
        next_server_info: str,
        current_score: str,
        is_doubles: bool,
        parent=None
    ):
        """Initialize the Force Side-Out dialog.

        Args:
            current_server_info: Current server display (e.g., "Team 1 - Server 2")
            next_server_info: Server after side-out (e.g., "Team 2 - Server 1")
            current_score: Current score string
            is_doubles: True for doubles format validation, False for singles
            parent: Parent widget for modal behavior
        """
        super().__init__(parent)
        self.setObjectName("forceSideoutDialog")

        self.current_server_info = current_server_info
        self.next_server_info = next_server_info
        self.current_score = current_score
        self.is_doubles = is_doubles
        self.result: ForceSideOutResult | None = None

        self._setup_ui()
        self._apply_styles()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Create and layout the dialog widgets."""
        self.setWindowTitle("Force Side-Out")
        self.setModal(True)
        self.setFixedWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_LG)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)

        # Title
        title_label = QLabel("Force Side-Out")
        title_label.setFont(Fonts.dialog_title())
        layout.addWidget(title_label)

        # Server transition section
        server_layout = QHBoxLayout()
        server_layout.setSpacing(SPACE_MD)

        # Current server
        current_container = QVBoxLayout()
        current_label = QLabel("Current Server")
        current_label.setFont(Fonts.secondary())
        current_container.addWidget(current_label)

        self.current_server_display = QLabel(self.current_server_info)
        self.current_server_display.setFont(Fonts.body())
        self.current_server_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_server_display.setFixedHeight(48)
        self.current_server_display.setObjectName("server_display")
        current_container.addWidget(self.current_server_display)

        # Arrow
        arrow_label = QLabel("→")
        arrow_label.setFont(Fonts.score_display())
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # After side-out server
        after_container = QVBoxLayout()
        after_label = QLabel("After Side-Out")
        after_label.setFont(Fonts.secondary())
        after_container.addWidget(after_label)

        self.after_server_display = QLabel(self.next_server_info)
        self.after_server_display.setFont(Fonts.body())
        self.after_server_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.after_server_display.setFixedHeight(48)
        self.after_server_display.setObjectName("server_display_highlight")
        after_container.addWidget(self.after_server_display)

        server_layout.addLayout(current_container, 1)
        server_layout.addWidget(arrow_label)
        server_layout.addLayout(after_container, 1)

        layout.addLayout(server_layout)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setObjectName("separator")
        layout.addWidget(separator1)

        # New score section (optional)
        score_label = QLabel("NEW SCORE (optional)")
        score_label.setFont(Fonts.secondary())
        layout.addWidget(score_label)

        self.new_score_input = QLineEdit()
        self.new_score_input.setFont(Fonts.input_text())
        self.new_score_input.setPlaceholderText(
            f"Leave blank to keep current: {self.current_score}"
        )
        self.new_score_input.setFixedHeight(48)
        self.new_score_input.setObjectName("new_score_input")
        layout.addWidget(self.new_score_input)

        score_hint = QLabel("Leave blank to keep current score")
        score_hint.setFont(Fonts.secondary())
        score_hint.setObjectName("score_hint")
        layout.addWidget(score_hint)

        # Error message (initially hidden)
        self.error_label = QLabel()
        self.error_label.setFont(Fonts.secondary())
        self.error_label.setObjectName("error_label")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setObjectName("separator")
        layout.addWidget(separator2)

        # Comment section
        comment_label = QLabel("COMMENT (optional)")
        comment_label.setFont(Fonts.secondary())
        layout.addWidget(comment_label)

        self.comment_input = QTextEdit()
        self.comment_input.setFont(Fonts.input_text())
        self.comment_input.setPlaceholderText("Explain why a side-out was forced...")
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

            QLabel#server_display {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_SECONDARY};
            }}

            QLabel#server_display_highlight {{
                background-color: {BG_TERTIARY};
                border: 2px solid {TEXT_ACCENT};
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
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

            QLabel#score_hint {{
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
        """Validate the score format if provided.

        If the score input is empty, validation passes (optional field).
        If score is provided, validates the format matches game type.
        """
        score_text = self.new_score_input.text().strip()

        # Empty is valid (optional field)
        if not score_text:
            self.error_label.setVisible(False)
            self.apply_button.setEnabled(True)
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
        # Get normalized score (None if empty)
        score_text = self.new_score_input.text().strip()
        new_score = score_text if score_text else None

        # Get comment (None if empty)
        comment_text = self.comment_input.toPlainText().strip()
        comment = comment_text if comment_text else None

        self.result = ForceSideOutResult(
            new_score=new_score,
            comment=comment
        )

        self.accept()

    def get_result(self) -> ForceSideOutResult | None:
        """Get the dialog result after execution.

        Returns:
            ForceSideOutResult if the dialog was accepted, None if cancelled
        """
        return self.result


__all__ = ["ForceSideOutDialog", "ForceSideOutResult"]
