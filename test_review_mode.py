#!/usr/bin/env python3
"""Test and demonstrate the Final Review Mode UI.

This test creates a standalone window showing the ReviewModeWidget populated
with sample rally data. Useful for visual testing and development.

Usage:
    python3 test_review_mode.py
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.models import Rally
from ui.review_mode import ReviewModeWidget


def create_sample_rallies() -> list[Rally]:
    """Create sample rally data for testing.

    Returns:
        List of Rally objects with realistic data
    """
    rallies = [
        Rally(start_frame=300, end_frame=600, score_at_start="0-0-2", winner="server"),
        Rally(start_frame=750, end_frame=1200, score_at_start="1-0-1", winner="receiver"),
        Rally(start_frame=1350, end_frame=1800, score_at_start="1-0-2", winner="receiver"),
        Rally(start_frame=1950, end_frame=2400, score_at_start="1-1-1", winner="server"),
        Rally(start_frame=2550, end_frame=3000, score_at_start="2-1-1", winner="server"),
        Rally(start_frame=3150, end_frame=3600, score_at_start="3-1-1", winner="receiver"),
        Rally(start_frame=3750, end_frame=4200, score_at_start="3-1-2", winner="server"),
        Rally(start_frame=4350, end_frame=4800, score_at_start="4-1-2", winner="receiver"),
        Rally(start_frame=4950, end_frame=5400, score_at_start="4-2-1", winner="server"),
        Rally(start_frame=5550, end_frame=6000, score_at_start="5-2-1", winner="server"),
        Rally(start_frame=6150, end_frame=6600, score_at_start="6-2-1", winner="receiver"),
        Rally(start_frame=6750, end_frame=7200, score_at_start="6-2-2", winner="receiver"),
        Rally(start_frame=7350, end_frame=7800, score_at_start="6-3-1", winner="server"),
        Rally(start_frame=7950, end_frame=8400, score_at_start="7-3-1", winner="receiver"),
        Rally(start_frame=8550, end_frame=9000, score_at_start="7-3-2", winner="server"),
        Rally(start_frame=9150, end_frame=9600, score_at_start="8-3-2", winner="receiver"),
        Rally(start_frame=9750, end_frame=10200, score_at_start="8-4-1", winner="server"),
        Rally(start_frame=10350, end_frame=10800, score_at_start="9-4-1", winner="receiver"),
        Rally(start_frame=10950, end_frame=11400, score_at_start="9-4-2", winner="server"),
        Rally(start_frame=11550, end_frame=12000, score_at_start="10-4-2", winner="receiver"),
    ]
    return rallies


def main() -> None:
    """Run the test application."""
    app = QApplication(sys.argv)

    # Create main window
    window = QMainWindow()
    window.setWindowTitle("Review Mode Test - Pickleball Video Editor")
    window.setMinimumSize(1024, 768)

    # Create and populate review widget
    review_widget = ReviewModeWidget()
    rallies = create_sample_rallies()
    review_widget.set_rallies(rallies)

    # Connect signals for demonstration
    review_widget.rally_changed.connect(
        lambda idx: print(f"Rally changed to: {idx + 1}")
    )
    review_widget.timing_adjusted.connect(
        lambda idx, field, delta: print(
            f"Rally {idx + 1} {field} adjusted by {delta:+.1f}s"
        )
    )
    review_widget.score_changed.connect(
        lambda idx, score, cascade: print(
            f"Rally {idx + 1} score changed to: {score} (cascade: {cascade})"
        )
    )
    review_widget.exit_requested.connect(lambda: print("Exit review requested"))
    review_widget.generate_requested.connect(
        lambda: print("Generate Kdenlive requested")
    )
    review_widget.play_rally_requested.connect(
        lambda idx: print(f"Play rally {idx + 1} requested")
    )
    review_widget.navigate_previous.connect(lambda: print("Navigate previous"))
    review_widget.navigate_next.connect(lambda: print("Navigate next"))

    # Set as central widget
    window.setCentralWidget(review_widget)

    # Show window
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
