"""Export Complete dialog for confirming successful Kdenlive project generation.

This module provides the ExportCompleteDialog class, which is shown after successfully
generating a Kdenlive project file. It displays the output path, offers options to
delete the saved session, and provides buttons to open the output folder or dismiss.

Visual Design:
- Success header with accent green checkmark
- File path display in copyable read-only field
- Optional checkbox to delete saved session (only shown if show_delete_option=True)
- Help text explaining the delete option
- Two action buttons: Open Folder (secondary) and Done (primary)

Dialog Dimensions:
- Max width: 600px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.1)
"""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    PRIMARY_ACTION,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import (
    RADIUS_XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    Fonts,
)


@dataclass
class ExportCompleteResult:
    """Result from the Export Complete dialog.

    Attributes:
        delete_session: True if user wants to delete the saved session
        open_folder: True if user clicked "Open Folder" (False if clicked "Done")
    """
    delete_session: bool
    open_folder: bool


class ExportCompleteDialog(QDialog):
    """Modal dialog announcing successful Kdenlive project generation.

    This dialog is shown after the export completes successfully. It displays:
    - Success message with file path
    - Copyable file path field
    - Optional checkbox to delete the saved session
    - Options to open the output folder or dismiss

    The delete session checkbox is only shown when show_delete_option=True,
    which should be False if there is no saved session for this video.

    Example:
        >>> dialog = ExportCompleteDialog(
        ...     kdenlive_path=Path("/home/user/Videos/match.kdenlive"),
        ...     show_delete_option=True,
        ...     parent=main_window
        ... )
        >>> result = dialog.exec_and_get_result()
        >>> if result.delete_session:
        ...     session_manager.delete_session(video_hash)
        >>> if result.open_folder:
        ...     open_in_file_manager(kdenlive_path.parent)
    """

    def __init__(
        self,
        kdenlive_path: Path,
        show_delete_option: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Export Complete dialog.

        Args:
            kdenlive_path: Path to the generated Kdenlive project file
            show_delete_option: Whether to show the delete session checkbox
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)
        self.setObjectName("exportCompleteDialog")

        self._kdenlive_path = kdenlive_path
        self._show_delete_option = show_delete_option
        self._delete_checkbox: QCheckBox | None = None
        self._open_folder = False

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        # Configure dialog window
        self.setWindowTitle("Export Complete")
        self.setModal(True)
        self.setMinimumWidth(600)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Success header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACE_MD)

        # Checkmark icon (using Unicode)
        checkmark_label = QLabel("✓")
        checkmark_label.setFont(Fonts.body(size=28, weight=700))
        checkmark_label.setStyleSheet(f"color: {TEXT_ACCENT};")
        header_layout.addWidget(checkmark_label)

        # "Export Complete" title
        title_label = QLabel("Export Complete")
        title_label.setFont(Fonts.dialog_title())
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        layout.addSpacing(SPACE_MD)

        # "Kdenlive project saved to:" label
        path_label = QLabel("Kdenlive project saved to:")
        path_label.setFont(Fonts.label())
        path_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(path_label)

        layout.addSpacing(SPACE_SM)

        # File path display (read-only, selectable QLineEdit)
        path_display = self._create_path_display()
        layout.addWidget(path_display)

        # Delete session option (conditionally shown)
        if self._show_delete_option:
            layout.addSpacing(SPACE_LG)

            # Checkbox
            self._delete_checkbox = QCheckBox("Delete saved session for this video")
            self._delete_checkbox.setFont(Fonts.label())
            self._delete_checkbox.setStyleSheet(f"color: {TEXT_PRIMARY};")
            layout.addWidget(self._delete_checkbox)

            # Help text
            help_text = QLabel("(You can always re-edit from the Kdenlive project)")
            help_text.setFont(Fonts.secondary())
            help_text.setStyleSheet(f"color: {TEXT_SECONDARY}; padding-left: 24px;")
            layout.addWidget(help_text)

        layout.addSpacing(SPACE_XL)

        # Action buttons
        button_layout = self._create_button_row()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _create_path_display(self) -> QLineEdit:
        """Create the file path display field.

        Returns:
            QLineEdit configured as read-only and selectable for copying
        """
        path_field = QLineEdit()
        path_field.setText(str(self._kdenlive_path))
        path_field.setReadOnly(True)
        path_field.setFont(Fonts.input_text())
        path_field.setObjectName("path_display")
        path_field.setCursorPosition(0)  # Scroll to start of path

        return path_field

    def _create_button_row(self) -> QHBoxLayout:
        """Create the button row with Open Folder and Done buttons.

        Returns:
            Horizontal layout containing both action buttons
        """
        button_layout = QHBoxLayout()
        button_layout.setSpacing(SPACE_MD)

        # Spacer to push buttons to right
        button_layout.addStretch()

        # Open Folder (secondary) - left button
        open_btn = QPushButton("Open Folder")
        open_btn.setFont(Fonts.button_other())
        open_btn.setMinimumHeight(40)
        open_btn.setObjectName("secondary_button")
        open_btn.clicked.connect(self._on_open_folder)

        # Done (primary) - right button
        done_btn = QPushButton("Done")
        done_btn.setFont(Fonts.button_other())
        done_btn.setMinimumHeight(40)
        done_btn.setObjectName("primary_button")
        done_btn.clicked.connect(self._on_done)
        done_btn.setDefault(True)  # Enter key triggers this

        button_layout.addWidget(open_btn)
        button_layout.addWidget(done_btn)

        return button_layout

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QLineEdit#path_display {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                padding: 10px 12px;
                selection-background-color: {TEXT_ACCENT};
                selection-color: {BG_SECONDARY};
            }}

            QCheckBox {{
                spacing: 8px;
            }}

            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {BG_BORDER};
                border-radius: 4px;
                background-color: {BG_TERTIARY};
            }}

            QCheckBox::indicator:hover {{
                border-color: {TEXT_ACCENT};
            }}

            QCheckBox::indicator:checked {{
                background-color: {TEXT_ACCENT};
                border-color: {TEXT_ACCENT};
                image: url(none);  /* Remove default checkmark, we'll use border hack */
            }}

            QCheckBox::indicator:checked {{
                /* Use a custom checkmark */
                background-color: {TEXT_ACCENT};
                border-color: {TEXT_ACCENT};
            }}

            QPushButton#secondary_button {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: 8px 16px;
                min-width: 140px;
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
                min-width: 140px;
            }}

            QPushButton#primary_button:hover {{
                background-color: #4FE695;
            }}
        """)

    def _on_open_folder(self) -> None:
        """Handle Open Folder button click."""
        self._open_folder = True
        self.accept()

    def _on_done(self) -> None:
        """Handle Done button click."""
        self._open_folder = False
        self.accept()

    def exec_and_get_result(self) -> ExportCompleteResult:
        """Show the dialog and return the user's choices.

        This is a convenience method that combines exec() and result extraction.

        Returns:
            ExportCompleteResult with delete_session and open_folder flags

        Example:
            >>> dialog = ExportCompleteDialog(kdenlive_path, parent=self)
            >>> result = dialog.exec_and_get_result()
            >>> if result.delete_session:
            ...     session_manager.delete_session(video_hash)
            >>> if result.open_folder:
            ...     subprocess.run(["xdg-open", str(kdenlive_path.parent)])
        """
        self.exec()

        # Check delete checkbox state (False if checkbox not shown)
        delete_session = False
        if self._delete_checkbox is not None:
            delete_session = self._delete_checkbox.isChecked()

        return ExportCompleteResult(
            delete_session=delete_session,
            open_folder=self._open_folder,
        )


__all__ = [
    "ExportCompleteDialog",
    "ExportCompleteResult",
]
