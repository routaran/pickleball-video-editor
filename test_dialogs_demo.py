#!/usr/bin/env python3
"""Demo script to test and preview system dialogs.

This script creates a simple PyQt6 application to demonstrate all three
system dialogs:
1. Game Over Dialog
2. Resume Session Dialog
3. Unsaved Changes Warning Dialog

Run this script to visually verify the dialogs match the UI specification.

Usage:
    python test_dialogs_demo.py
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.dialogs import (
    GameOverDialog,
    GameOverResult,
    ResumeSessionDialog,
    ResumeSessionResult,
    SessionDetails,
    UnsavedWarningDialog,
    UnsavedWarningResult,
)


class DialogDemoWindow(QMainWindow):
    """Main window with buttons to launch each dialog."""

    def __init__(self) -> None:
        """Initialize the demo window."""
        super().__init__()
        self.setWindowTitle("System Dialogs Demo")
        self.setMinimumSize(400, 300)

        # Central widget
        central = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        # Buttons to launch each dialog
        self._create_buttons(layout)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _create_buttons(self, layout: QVBoxLayout) -> None:
        """Create buttons for launching dialogs.

        Args:
            layout: Layout to add buttons to
        """
        # Game Over - Standard Game
        btn_game_over = QPushButton("1. Game Over (Standard)")
        btn_game_over.clicked.connect(self._show_game_over_standard)
        layout.addWidget(btn_game_over)

        # Game Over - Timed Game
        btn_game_over_timed = QPushButton("2. Game Over (Timed)")
        btn_game_over_timed.clicked.connect(self._show_game_over_timed)
        layout.addWidget(btn_game_over_timed)

        # Resume Session
        btn_resume = QPushButton("3. Resume Session")
        btn_resume.clicked.connect(self._show_resume_session)
        layout.addWidget(btn_resume)

        # Unsaved Warning
        btn_unsaved = QPushButton("4. Unsaved Changes Warning")
        btn_unsaved.clicked.connect(self._show_unsaved_warning)
        layout.addWidget(btn_unsaved)

    def _show_game_over_standard(self) -> None:
        """Show Game Over dialog for standard game."""
        dialog = GameOverDialog(
            winner_team=1,
            final_score="11-9-2",
            rally_count=23,
            is_timed=False,
            parent=self,
        )
        dialog.exec()
        result = dialog.get_result()
        print(f"Game Over (Standard) result: {result}")

    def _show_game_over_timed(self) -> None:
        """Show Game Over dialog for timed game."""
        dialog = GameOverDialog(
            winner_team=2,
            final_score="8-7",
            rally_count=18,
            is_timed=True,
            parent=self,
        )
        dialog.exec()
        result = dialog.get_result()
        print(f"Game Over (Timed) result: {result}")

    def _show_resume_session(self) -> None:
        """Show Resume Session dialog."""
        details = SessionDetails(
            video_name="match_2026-01-14.mp4",
            rally_count=15,
            current_score="8-6-1",
            last_position=323.45,
            game_type="Doubles",
            victory_rule="Game to 11",
        )
        dialog = ResumeSessionDialog(details, parent=self)
        dialog.exec()
        result = dialog.get_result()
        print(f"Resume Session result: {result}")

    def _show_unsaved_warning(self) -> None:
        """Show Unsaved Changes Warning dialog."""
        dialog = UnsavedWarningDialog(parent=self)
        dialog.exec()
        result = dialog.get_result()
        print(f"Unsaved Warning result: {result}")


def main() -> None:
    """Run the dialog demo application."""
    app = QApplication(sys.argv)

    # Set application-wide dark theme
    app.setStyle("Fusion")

    window = DialogDemoWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
