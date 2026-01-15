#!/usr/bin/env python3
"""Test script for MainWindow review mode integration.

This script tests the integration of ReviewModeWidget with MainWindow:
- Mode switching (editing <-> review)
- Rally navigation
- Timing adjustment
- Score editing with cascade
- Play rally feature

Usage:
    python test_review_integration.py path/to/video.mp4
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.setup_dialog import GameConfig


def main() -> int:
    """Run the test application.

    Returns:
        Exit code (0 for success)
    """
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python test_review_integration.py <video_file>")
        print("Example: python test_review_integration.py examples/sample.mp4")
        return 1

    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        return 1

    # Create application
    app = QApplication(sys.argv)

    # Create test configuration
    config = GameConfig(
        video_path=video_path,
        game_type="doubles",
        victory_rule="11",
        team1_players=["Alice", "Bob"],
        team2_players=["Carol", "Dave"],
        session_state=None,
    )

    # Create main window
    window = MainWindow(config)
    window.show()

    # Print instructions
    print("\n" + "=" * 70)
    print("REVIEW MODE INTEGRATION TEST")
    print("=" * 70)
    print("\nTest Instructions:")
    print("1. Mark a few rallies using Rally Start / Server Wins / Receiver Wins")
    print("2. Click 'Final Review' button to enter review mode")
    print("3. Test the following features:")
    print("   - Click rally cards to navigate between rallies")
    print("   - Use Previous/Next buttons")
    print("   - Adjust timing with +/-0.1s buttons")
    print("   - Edit score and test cascade option")
    print("   - Click 'Play Rally' to watch a rally")
    print("   - Click 'Exit Review' to return to editing mode")
    print("4. Verify video seeks correctly when changing rallies")
    print("5. Verify timing adjustments update the display")
    print("6. Verify score cascade recalculates subsequent rallies")
    print("\nExpected Behavior:")
    print("- Rally controls and toolbar hide in review mode")
    print("- Video seeks to rally start when rally changes")
    print("- Timing adjustments show OSD feedback")
    print("- Play Rally plays from start to end and auto-pauses")
    print("- Exit Review returns to exact state before entering review")
    print("=" * 70 + "\n")

    # Run application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
