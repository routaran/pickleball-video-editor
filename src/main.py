"""
Application entry point for Pickleball Video Editor.

This module initializes the Qt application and launches the main window.
The application flow is:
1. Show SetupDialog for video and game configuration
2. If setup is accepted, show MainWindow for rally editing
3. MainWindow handles session management and review mode
"""

import sys

from src import __version__
from src.app import create_application
from src.ui.setup_dialog import SetupDialog
from src.ui.main_window import MainWindow


def main() -> int:
    """
    Main entry point for the application.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Create and configure the application
    app, config = create_application()

    print(f"Pickleball Video Editor v{__version__}")
    print("Starting application...")

    # Show setup dialog first
    setup_dialog = SetupDialog()

    if setup_dialog.exec():
        # User accepted the setup dialog
        game_config = setup_dialog.get_config()

        if game_config is not None:
            print(f"Loading video: {game_config.video_path}")
            print(f"Game type: {game_config.game_type}")

            # Create and show main window
            main_window = MainWindow(game_config)
            main_window.show()

            # Run the event loop
            return app.exec()
        else:
            print("Error: Invalid configuration from setup dialog")
            return 1
    else:
        # User cancelled the setup dialog
        print("Setup cancelled by user")
        return 0


if __name__ == "__main__":
    sys.exit(main())
