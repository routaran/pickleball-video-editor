#!/usr/bin/env python3
"""Demo script for testing Toast notification widget.

Run this script to see the toast notifications in action with all four types.
Each toast will appear with the correct styling, animation, and auto-dismiss.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from ui.widgets import ToastManager, ToastType
from ui.styles.colors import BG_PRIMARY


class ToastDemo(QMainWindow):
    """Demo window for testing toast notifications."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Toast Notification Demo")
        self.setGeometry(100, 100, 800, 600)

        # Set dark background matching the app theme
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")

        # Create central widget with buttons
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Create buttons for each toast type
        button_style = """
            QPushButton {
                background-color: #2D3340;
                color: #F5F5F5;
                border: 1px solid #3D4450;
                border-radius: 4px;
                padding: 12px 24px;
                font-size: 14px;
                min-width: 200px;
            }
            QPushButton:hover {
                background-color: #3D4450;
            }
            QPushButton:pressed {
                background-color: #252A33;
            }
        """

        success_btn = QPushButton("Show Success Toast")
        success_btn.setStyleSheet(button_style)
        success_btn.clicked.connect(self._show_success)
        layout.addWidget(success_btn)

        info_btn = QPushButton("Show Info Toast")
        info_btn.setStyleSheet(button_style)
        info_btn.clicked.connect(self._show_info)
        layout.addWidget(info_btn)

        warning_btn = QPushButton("Show Warning Toast")
        warning_btn.setStyleSheet(button_style)
        warning_btn.clicked.connect(self._show_warning)
        layout.addWidget(warning_btn)

        error_btn = QPushButton("Show Error Toast")
        error_btn.setStyleSheet(button_style)
        error_btn.clicked.connect(self._show_error)
        layout.addWidget(error_btn)

        auto_btn = QPushButton("Show All (Auto-sequence)")
        auto_btn.setStyleSheet(button_style)
        auto_btn.clicked.connect(self._show_all)
        layout.addWidget(auto_btn)

    def _show_success(self) -> None:
        """Show a success toast."""
        ToastManager.show_success(self, "Rally saved successfully")

    def _show_info(self) -> None:
        """Show an info toast."""
        ToastManager.show_info(self, "Video loaded: pickleball_match_2024.mp4")

    def _show_warning(self) -> None:
        """Show a warning toast."""
        ToastManager.show_warning(self, "Cannot end rally - no rally in progress")

    def _show_error(self) -> None:
        """Show an error toast."""
        ToastManager.show_error(self, "Failed to load video file")

    def _show_all(self) -> None:
        """Show all toast types in sequence."""
        # Success immediately
        ToastManager.show_success(self, "Operation completed successfully")

        # Info after 1 second
        QTimer.singleShot(1000, lambda: ToastManager.show_info(
            self, "Processing video file..."
        ))

        # Warning after 2 seconds
        QTimer.singleShot(2000, lambda: ToastManager.show_warning(
            self, "Low disk space warning"
        ))

        # Error after 3 seconds
        QTimer.singleShot(3000, lambda: ToastManager.show_error(
            self, "Network connection lost"
        ))


def main() -> None:
    """Run the toast demo application."""
    app = QApplication(sys.argv)

    window = ToastDemo()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
