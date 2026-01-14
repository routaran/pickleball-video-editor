"""Unsaved Changes Warning dialog for preventing data loss.

This module provides the UnsavedWarningDialog class, which is shown when the user
attempts to quit the application with unsaved changes. The dialog offers three
options: save and quit, discard changes, or cancel the quit action.

Visual Design:
- Simple warning message
- Three action buttons in a row: Don't Save, Cancel, Save & Quit
- Save & Quit is the primary action (rightmost, accent-styled)
- Cancel allows user to return to editing

Dialog Dimensions:
- Max width: 500px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.7)
"""

from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    PRIMARY_ACTION,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import (
    RADIUS_XL,
    SPACE_LG,
    SPACE_XL,
    Fonts,
)


class UnsavedWarningResult(Enum):
    """Result options from the Unsaved Changes Warning dialog.

    Attributes:
        DONT_SAVE: User chose to quit without saving
        CANCEL: User chose to cancel quit and return to editing
        SAVE_AND_QUIT: User chose to save changes and quit
    """
    DONT_SAVE = "dont_save"
    CANCEL = "cancel"
    SAVE_AND_QUIT = "save_quit"


class UnsavedWarningDialog(QDialog):
    """Modal dialog warning about unsaved changes when quitting.

    This dialog is shown when the user attempts to close the application or
    load a new video while there are unsaved changes to the current editing
    session. It prevents accidental data loss by giving the user three options:

    1. Don't Save: Discard changes and quit
    2. Cancel: Return to editing without quitting
    3. Save & Quit: Save changes before quitting (primary action)

    The dialog uses clear language and button positioning to guide the user
    toward the safe default action (Save & Quit).

    Example:
        >>> dialog = UnsavedWarningDialog(parent=main_window)
        >>> dialog.exec()
        >>> result = dialog.get_result()
        >>> if result == UnsavedWarningResult.SAVE_AND_QUIT:
        ...     save_session()
        ...     quit_application()
        >>> elif result == UnsavedWarningResult.DONT_SAVE:
        ...     quit_application()
        >>> # CANCEL: do nothing, continue editing
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the Unsaved Changes Warning dialog.

        Args:
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)

        self._result = UnsavedWarningResult.CANCEL

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        # Configure dialog window
        self.setWindowTitle("Unsaved Changes")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Title
        title_label = QLabel("Unsaved Changes")
        title_label.setFont(Fonts.dialog_title())
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(title_label)

        layout.addSpacing(SPACE_XL)

        # Warning message
        message_label = QLabel("You have unsaved changes that will be lost.")
        message_label.setFont(Fonts.label())
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        layout.addSpacing(SPACE_XL)

        # Action buttons
        button_layout = self._create_button_row()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _create_button_row(self) -> QHBoxLayout:
        """Create the button row with three action buttons.

        Layout: [Don't Save] [Cancel] [Save & Quit]
        - Don't Save: Secondary, left
        - Cancel: Secondary, center
        - Save & Quit: Primary, right (default)

        Returns:
            Horizontal layout containing all three action buttons
        """
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_LG := 24)

        # Don't Save (secondary, destructive) - left
        dont_save_btn = QPushButton("Don't Save")
        dont_save_btn.setFont(Fonts.button_other())
        dont_save_btn.setMinimumHeight(40)
        dont_save_btn.setObjectName("secondary_button")
        dont_save_btn.clicked.connect(self._on_dont_save)

        # Cancel (secondary) - center
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(Fonts.button_other())
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setObjectName("secondary_button")
        cancel_btn.clicked.connect(self._on_cancel)

        # Save & Quit (primary) - right
        save_quit_btn = QPushButton("Save & Quit")
        save_quit_btn.setFont(Fonts.button_other())
        save_quit_btn.setMinimumHeight(40)
        save_quit_btn.setObjectName("primary_button")
        save_quit_btn.clicked.connect(self._on_save_and_quit)
        save_quit_btn.setDefault(True)  # Enter key triggers this

        button_layout.addWidget(dont_save_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_quit_btn)

        return button_layout

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QPushButton#secondary_button {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: 8px 16px;
                min-width: 110px;
            }}

            QPushButton#secondary_button:hover {{
                border-color: {TEXT_PRIMARY};
            }}

            QPushButton#primary_button {{
                background-color: {PRIMARY_ACTION};
                border: 2px solid {PRIMARY_ACTION};
                border-radius: 6px;
                color: {BG_SECONDARY};
                padding: 8px 16px;
                font-weight: 600;
                min-width: 130px;
            }}

            QPushButton#primary_button:hover {{
                background-color: #4FE695;
            }}

            QPushButton:pressed {{
                transform: translateY(1px);
            }}
        """)

    def _on_dont_save(self) -> None:
        """Handle Don't Save button click."""
        self._result = UnsavedWarningResult.DONT_SAVE
        self.accept()

    def _on_cancel(self) -> None:
        """Handle Cancel button click."""
        self._result = UnsavedWarningResult.CANCEL
        self.reject()  # Use reject() to allow detecting Escape key press

    def _on_save_and_quit(self) -> None:
        """Handle Save & Quit button click."""
        self._result = UnsavedWarningResult.SAVE_AND_QUIT
        self.accept()

    def get_result(self) -> UnsavedWarningResult:
        """Get the user's choice after dialog is closed.

        This method should be called after exec() or show() has completed.

        Returns:
            UnsavedWarningResult indicating user's choice:
            - DONT_SAVE: Quit without saving
            - CANCEL: Don't quit, return to editing
            - SAVE_AND_QUIT: Save changes and quit

        Example:
            >>> dialog = UnsavedWarningDialog(parent=self)
            >>> dialog.exec()
            >>> result = dialog.get_result()
            >>> if result == UnsavedWarningResult.SAVE_AND_QUIT:
            ...     self.save_session()
            ...     self.close()
            >>> elif result == UnsavedWarningResult.DONT_SAVE:
            ...     self.close()
            >>> # CANCEL: continue editing
        """
        return self._result

    def keyPressEvent(self, event) -> None:
        """Handle keyboard events, specifically Escape key.

        Escape key is mapped to Cancel action per UI_SPEC.md Section 9.3.

        Args:
            event: QKeyEvent from Qt
        """
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)


__all__ = [
    "UnsavedWarningDialog",
    "UnsavedWarningResult",
]
