#!/usr/bin/env python3
"""
Demo script to test the application theme and font configuration.

This script creates a simple window with various UI elements to verify
that the "Court Green" theme is properly applied.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QRadioButton,
    QGroupBox,
)
from PyQt6.QtCore import Qt

from app import create_application


class ThemeDemo(QWidget):
    """Demo window showing various themed UI elements."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pickleball Editor - Theme Demo")
        self.setMinimumSize(800, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the demo UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("Court Green Theme Demo")
        header.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(header)

        # Typography Section
        typo_group = QGroupBox("Typography")
        typo_layout = QVBoxLayout()

        primary_label = QLabel("Primary Text - IBM Plex Sans")
        typo_layout.addWidget(primary_label)

        secondary_label = QLabel("Secondary text with muted styling")
        secondary_label.setProperty("class", "secondary")
        typo_layout.addWidget(secondary_label)

        timecode_label = QLabel("12:34.567")
        timecode_label.setProperty("timecode", "true")
        typo_layout.addWidget(timecode_label)

        score_label = QLabel("10-7-2")
        score_label.setProperty("class", "score-display")
        typo_layout.addWidget(score_label)

        typo_group.setLayout(typo_layout)
        layout.addWidget(typo_group)

        # Buttons Section
        btn_group = QGroupBox("Buttons")
        btn_layout = QVBoxLayout()

        # Rally buttons
        rally_row = QHBoxLayout()

        rally_start_btn = QPushButton("Start Rally")
        rally_start_btn.setObjectName("rallyStart")
        rally_row.addWidget(rally_start_btn)

        server_wins_btn = QPushButton("Server Wins")
        server_wins_btn.setObjectName("serverWins")
        rally_row.addWidget(server_wins_btn)

        receiver_wins_btn = QPushButton("Receiver Wins")
        receiver_wins_btn.setObjectName("receiverWins")
        rally_row.addWidget(receiver_wins_btn)

        btn_layout.addLayout(rally_row)

        # Other buttons
        other_row = QHBoxLayout()

        undo_btn = QPushButton("Undo")
        undo_btn.setObjectName("undo")
        other_row.addWidget(undo_btn)

        primary_btn = QPushButton("Primary Action")
        primary_btn.setProperty("class", "primary")
        other_row.addWidget(primary_btn)

        secondary_btn = QPushButton("Secondary")
        secondary_btn.setProperty("class", "secondary")
        other_row.addWidget(secondary_btn)

        other_row.addStretch()

        btn_layout.addLayout(other_row)
        btn_group.setLayout(btn_layout)
        layout.addWidget(btn_group)

        # Form Controls Section
        form_group = QGroupBox("Form Controls")
        form_layout = QVBoxLayout()

        line_edit = QLineEdit()
        line_edit.setPlaceholderText("Enter text here...")
        form_layout.addWidget(line_edit)

        combo = QComboBox()
        combo.addItems(["Singles", "Doubles", "Mixed Doubles"])
        form_layout.addWidget(combo)

        checkbox = QCheckBox("Enable automatic scoring")
        form_layout.addWidget(checkbox)

        radio_layout = QHBoxLayout()
        radio1 = QRadioButton("Option 1")
        radio2 = QRadioButton("Option 2")
        radio_layout.addWidget(radio1)
        radio_layout.addWidget(radio2)
        radio_layout.addStretch()
        form_layout.addLayout(radio_layout)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        layout.addStretch()

        # Footer
        footer = QLabel("Press ESC to close")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setProperty("class", "secondary")
        layout.addWidget(footer)

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()


def main() -> None:
    """Run the theme demo."""
    app, config = create_application()

    demo = ThemeDemo()
    demo.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
