#!/usr/bin/env python3
"""Test script to demonstrate RallyButton widget with pulse animations.

This script creates a simple window with all four rally button types,
allowing you to toggle their active states and see the pulse animation.

Usage:
    python test_rally_button.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from src.ui.styles.colors import BG_PRIMARY
from src.ui.widgets import (
    BUTTON_TYPE_RALLY_START,
    BUTTON_TYPE_RECEIVER_WINS,
    BUTTON_TYPE_SERVER_WINS,
    BUTTON_TYPE_UNDO,
    RallyButton,
)


class TestWindow(QWidget):
    """Test window demonstrating RallyButton widget."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RallyButton Test - Pickleball Video Editor")
        self.setMinimumSize(800, 400)

        # Set dark background
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")

        # Create rally buttons
        self.rally_start_btn = RallyButton("RALLY START", BUTTON_TYPE_RALLY_START)
        self.server_wins_btn = RallyButton("SERVER WINS", BUTTON_TYPE_SERVER_WINS)
        self.receiver_wins_btn = RallyButton(
            "RECEIVER WINS", BUTTON_TYPE_RECEIVER_WINS
        )
        self.undo_btn = RallyButton("UNDO", BUTTON_TYPE_UNDO)

        # Create toggle buttons for testing active states
        self.toggle_start = QPushButton("Toggle Rally Start Active")
        self.toggle_server = QPushButton("Toggle Server Wins Active")
        self.toggle_receiver = QPushButton("Toggle Receiver Wins Active")
        self.toggle_disabled = QPushButton("Toggle Disabled States")

        # Connect toggle buttons
        self.toggle_start.clicked.connect(self._toggle_rally_start)
        self.toggle_server.clicked.connect(self._toggle_server_wins)
        self.toggle_receiver.clicked.connect(self._toggle_receiver_wins)
        self.toggle_disabled.clicked.connect(self._toggle_disabled)

        # Layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(32, 32, 32, 32)

        # Rally buttons row
        rally_layout = QHBoxLayout()
        rally_layout.setSpacing(16)
        rally_layout.addWidget(self.rally_start_btn)
        rally_layout.addWidget(self.server_wins_btn)
        rally_layout.addWidget(self.receiver_wins_btn)
        rally_layout.addStretch()

        # Undo button row
        undo_layout = QHBoxLayout()
        undo_layout.addStretch()
        undo_layout.addWidget(self.undo_btn)

        # Toggle controls row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self.toggle_start)
        controls_layout.addWidget(self.toggle_server)
        controls_layout.addWidget(self.toggle_receiver)
        controls_layout.addWidget(self.toggle_disabled)

        # Add all layouts
        main_layout.addLayout(rally_layout)
        main_layout.addLayout(undo_layout)
        main_layout.addStretch()
        main_layout.addLayout(controls_layout)

        # Initial state: Rally Start is active (waiting for rally)
        self.rally_start_btn.set_active(True)

        # Connect rally button clicks
        self.rally_start_btn.clicked.connect(self._on_rally_start)
        self.server_wins_btn.clicked.connect(self._on_server_wins)
        self.receiver_wins_btn.clicked.connect(self._on_receiver_wins)
        self.undo_btn.clicked.connect(self._on_undo)

    def _toggle_rally_start(self) -> None:
        """Toggle Rally Start button active state."""
        current = self.rally_start_btn.is_active()
        self.rally_start_btn.set_active(not current)

    def _toggle_server_wins(self) -> None:
        """Toggle Server Wins button active state."""
        current = self.server_wins_btn.is_active()
        self.server_wins_btn.set_active(not current)

    def _toggle_receiver_wins(self) -> None:
        """Toggle Receiver Wins button active state."""
        current = self.receiver_wins_btn.is_active()
        self.receiver_wins_btn.set_active(not current)

    def _toggle_disabled(self) -> None:
        """Toggle disabled state for all rally buttons."""
        current = self.rally_start_btn.isEnabled()
        for btn in [
            self.rally_start_btn,
            self.server_wins_btn,
            self.receiver_wins_btn,
            self.undo_btn,
        ]:
            btn.setEnabled(not current)

    def _on_rally_start(self) -> None:
        """Simulate starting a rally (transitions to in-rally state)."""
        print("Rally started!")
        self.rally_start_btn.set_active(False)
        self.server_wins_btn.set_active(True)
        self.receiver_wins_btn.set_active(True)

    def _on_server_wins(self) -> None:
        """Simulate server winning (return to waiting state)."""
        print("Server wins!")
        self.server_wins_btn.set_active(False)
        self.receiver_wins_btn.set_active(False)
        self.rally_start_btn.set_active(True)

    def _on_receiver_wins(self) -> None:
        """Simulate receiver winning (return to waiting state)."""
        print("Receiver wins!")
        self.server_wins_btn.set_active(False)
        self.receiver_wins_btn.set_active(False)
        self.rally_start_btn.set_active(True)

    def _on_undo(self) -> None:
        """Simulate undo action."""
        print("Undo clicked!")


def main() -> None:
    """Run the test application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Use Fusion style for consistent appearance

    window = TestWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
