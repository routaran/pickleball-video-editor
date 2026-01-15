"""
Application entry point for Pickleball Video Editor.

This module initializes the Qt application and launches the main window.
The application flow is:
1. Show SetupDialog for video and game configuration
2. If setup is accepted, show MainWindow for rally editing
3. MainWindow handles session management and review mode
"""

# CRITICAL: Force X11/XCB backend BEFORE any Qt imports.
# MPV embedding is most reliable with X11. On Wayland, the window IDs
# are not directly usable by MPV's video output drivers.
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"

# CRITICAL: Set LC_NUMERIC BEFORE any imports.
# MPV requires LC_NUMERIC to be "C" or it will crash with segfault.
# Use ctypes to call C library setlocale directly.
import ctypes
import locale
from pathlib import Path

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")
_libc = ctypes.CDLL("libc.so.6")
_libc.setlocale.restype = ctypes.c_char_p
_result = _libc.setlocale(1, b"C")  # LC_NUMERIC = 1 on Linux

# Write to file in the project directory to prove this code runs
_debug_file = Path(__file__).parent.parent / "DEBUG_LOCALE.txt"
_debug_file.write_text(f"main.py executed at {Path(__file__)}\nsetlocale returned: {_result}\n")

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

    print(">>> CODE VERSION: 2026-01-14-FIX <<<")
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
