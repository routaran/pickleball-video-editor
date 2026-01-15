#!/usr/bin/env python3
"""Demo script to test the StatusOverlay widget.

This script creates a simple window with the StatusOverlay widget and
demonstrates different states:
- WAITING state (amber dot)
- IN RALLY state (green dot)
- Different score formats (singles vs doubles)
- Different server information

Press 't' to toggle between WAITING and IN RALLY states.
Press 's' to cycle through different score examples.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.widgets.status_overlay import StatusOverlay
from src.ui.styles.colors import BG_PRIMARY


class StatusOverlayDemo(QMainWindow):
    """Demo window for testing StatusOverlay widget."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("StatusOverlay Widget Demo")
        self.resize(800, 600)

        # Track state for toggling
        self._in_rally = False
        self._score_index = 0

        # Example scores
        self._score_examples = [
            ("0-0-2", "Team 1 #1"),
            ("3-2-1", "Team 2 (Alice) #1"),
            ("7-5-2", "Team 1 (Bob) #2"),
            ("10-9-1", "Team 2 (Charlie) #1"),
            ("11-9", "Server (Alice)"),  # Singles example
        ]

        # Setup UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the demo UI."""
        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Apply dark background
        central.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_PRIMARY};
            }}
        """)

        # Create layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(40, 40, 40, 40)

        # Add instructions
        instructions = QLabel(
            "StatusOverlay Widget Demo\n\n"
            "Press 't' to toggle rally state (WAITING ↔ IN RALLY)\n"
            "Press 's' to cycle through score examples\n"
            "Press 'q' to quit"
        )
        instructions.setStyleSheet("""
            QLabel {
                color: #F5F5F5;
                font-size: 14px;
                padding: 20px;
                background-color: rgba(45, 51, 64, 0.5);
                border-radius: 8px;
            }
        """)
        layout.addWidget(instructions)

        # Add spacer
        layout.addSpacing(40)

        # Add the status overlay
        self.overlay = StatusOverlay()
        layout.addWidget(self.overlay)

        # Push overlay to top
        layout.addStretch()

        # Set initial state
        self._update_overlay()

    def _update_overlay(self) -> None:
        """Update the overlay with current state."""
        score, server_info = self._score_examples[self._score_index]
        self.overlay.update_display(
            in_rally=self._in_rally,
            score=score,
            server_info=server_info,
        )

    def keyPressEvent(self, event):
        """Handle keyboard input for demo controls."""
        key = event.key()

        if key == Qt.Key.Key_T:
            # Toggle rally state
            self._in_rally = not self._in_rally
            self._update_overlay()
            print(f"Toggled rally state: {'IN RALLY' if self._in_rally else 'WAITING'}")

        elif key == Qt.Key.Key_S:
            # Cycle through scores
            self._score_index = (self._score_index + 1) % len(self._score_examples)
            self._update_overlay()
            score, server = self._score_examples[self._score_index]
            print(f"Changed score: {score}, Server: {server}")

        elif key == Qt.Key.Key_Q:
            # Quit
            self.close()

        else:
            super().keyPressEvent(event)


def main():
    """Run the demo application."""
    app = QApplication(sys.argv)
    app.setApplicationName("StatusOverlay Demo")

    # Create and show demo window
    demo = StatusOverlayDemo()
    demo.show()

    # Print startup message
    print("\n" + "="*60)
    print("StatusOverlay Widget Demo")
    print("="*60)
    print("Controls:")
    print("  't' - Toggle rally state (WAITING ↔ IN RALLY)")
    print("  's' - Cycle through score examples")
    print("  'q' - Quit")
    print("="*60 + "\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
