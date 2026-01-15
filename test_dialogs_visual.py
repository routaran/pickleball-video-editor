#!/usr/bin/env python3
"""Visual test script to display and interact with intervention dialogs.

This script creates a simple launcher window with buttons to open each
intervention dialog. Useful for:
- Visual inspection of dialog layout and styling
- Manual testing of validation logic
- Verifying result objects are correctly constructed

Run this script to see the dialogs in action and test their functionality.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
)
from PyQt6.QtCore import Qt

from src.ui.dialogs import (
    EditScoreDialog,
    ForceSideOutDialog,
    AddCommentDialog,
)
from src.ui.styles.colors import BG_PRIMARY, TEXT_PRIMARY
from src.ui.styles.fonts import Fonts


class DialogTestWindow(QMainWindow):
    """Test window with buttons to launch each dialog."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Intervention Dialogs - Visual Test")
        self.setMinimumSize(600, 500)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel("Intervention Dialogs Test Suite")
        title.setFont(Fonts.dialog_title())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "Click each button to test the corresponding dialog.\n"
            "Results will be displayed below when you click Apply/Add."
        )
        instructions.setFont(Fonts.label())
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        layout.addSpacing(16)

        # Edit Score Dialog button
        edit_score_btn = QPushButton("Test Edit Score Dialog")
        edit_score_btn.setFont(Fonts.button_other())
        edit_score_btn.setMinimumHeight(48)
        edit_score_btn.clicked.connect(self.test_edit_score)
        layout.addWidget(edit_score_btn)

        # Force Side-Out Dialog button
        force_sideout_btn = QPushButton("Test Force Side-Out Dialog")
        force_sideout_btn.setFont(Fonts.button_other())
        force_sideout_btn.setMinimumHeight(48)
        force_sideout_btn.clicked.connect(self.test_force_sideout)
        layout.addWidget(force_sideout_btn)

        # Add Comment Dialog button
        add_comment_btn = QPushButton("Test Add Comment Dialog")
        add_comment_btn.setFont(Fonts.button_other())
        add_comment_btn.setMinimumHeight(48)
        add_comment_btn.clicked.connect(self.test_add_comment)
        layout.addWidget(add_comment_btn)

        layout.addSpacing(8)

        # Result display
        result_label = QLabel("Results:")
        result_label.setFont(Fonts.label())
        layout.addWidget(result_label)

        self.result_display = QTextEdit()
        self.result_display.setFont(Fonts.input_text())
        self.result_display.setReadOnly(True)
        self.result_display.setPlaceholderText(
            "Dialog results will appear here..."
        )
        layout.addWidget(self.result_display)

        # Apply styling
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG_PRIMARY};
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
            }}
            QPushButton {{
                background-color: #2D3340;
                border: 2px solid #3D4450;
                border-radius: 6px;
                padding: 12px;
                color: {TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: #3D4450;
                border-color: #3DDC84;
            }}
            QTextEdit {{
                background-color: #2D3340;
                border: 1px solid #3D4450;
                border-radius: 4px;
                padding: 8px;
                color: {TEXT_PRIMARY};
            }}
        """)

    def test_edit_score(self):
        """Test the Edit Score dialog."""
        dialog = EditScoreDialog(
            current_score="7-5-2",
            is_doubles=True,
            parent=self
        )

        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.result_display.append(
                    f"\n{'='*60}\n"
                    f"EDIT SCORE DIALOG - Accepted\n"
                    f"{'='*60}\n"
                    f"New Score: {result.new_score}\n"
                    f"Comment: {result.comment or '(none)'}\n"
                )
        else:
            self.result_display.append(
                f"\n{'='*60}\n"
                f"EDIT SCORE DIALOG - Cancelled\n"
                f"{'='*60}\n"
            )

    def test_force_sideout(self):
        """Test the Force Side-Out dialog."""
        dialog = ForceSideOutDialog(
            current_server_info="Team 1 - Server 2",
            next_server_info="Team 2 - Server 1",
            current_score="7-5-2",
            is_doubles=True,
            parent=self
        )

        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.result_display.append(
                    f"\n{'='*60}\n"
                    f"FORCE SIDE-OUT DIALOG - Accepted\n"
                    f"{'='*60}\n"
                    f"New Score: {result.new_score or '(keep current)'}\n"
                    f"Comment: {result.comment or '(none)'}\n"
                )
        else:
            self.result_display.append(
                f"\n{'='*60}\n"
                f"FORCE SIDE-OUT DIALOG - Cancelled\n"
                f"{'='*60}\n"
            )

    def test_add_comment(self):
        """Test the Add Comment dialog."""
        dialog = AddCommentDialog(
            timestamp=123.45,
            parent=self
        )

        if dialog.exec():
            result = dialog.get_result()
            if result:
                self.result_display.append(
                    f"\n{'='*60}\n"
                    f"ADD COMMENT DIALOG - Accepted\n"
                    f"{'='*60}\n"
                    f"Timestamp: {result.timestamp:.2f} seconds\n"
                    f"Comment: {result.comment}\n"
                    f"Duration: {result.duration} seconds\n"
                )
        else:
            self.result_display.append(
                f"\n{'='*60}\n"
                f"ADD COMMENT DIALOG - Cancelled\n"
                f"{'='*60}\n"
            )


def main():
    """Run the visual test application."""
    app = QApplication(sys.argv)

    window = DialogTestWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
