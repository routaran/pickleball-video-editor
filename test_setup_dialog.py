#!/usr/bin/env python3
"""Test script for SetupDialog.

This script demonstrates the SetupDialog in action and allows you to
verify the UI behavior and validation.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from src.ui.setup_dialog import SetupDialog


def main() -> None:
    """Run the setup dialog test."""
    app = QApplication(sys.argv)

    # Create and show the dialog
    dialog = SetupDialog()
    result = dialog.exec()

    # Check result
    if result == dialog.DialogCode.Accepted:
        config = dialog.get_config()
        if config:
            print("\n" + "=" * 60)
            print("CONFIGURATION ACCEPTED")
            print("=" * 60)
            print(f"Video Path:     {config.video_path}")
            print(f"Game Type:      {config.game_type}")
            print(f"Victory Rule:   {config.victory_rule}")
            print(f"Team 1 Players: {', '.join(config.team1_players)}")
            print(f"Team 2 Players: {', '.join(config.team2_players)}")
            print("=" * 60)
    else:
        print("\nDialog was cancelled.")

    sys.exit(0)


if __name__ == "__main__":
    main()
