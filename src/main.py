"""
Application entry point for Pickleball Video Editor.

This module initializes the Qt application and launches the main window.
The application flow is:
1. Load AppSettings from disk
2. Show SetupDialog for video and game configuration
3. If setup is accepted, show MainWindow for rally editing
4. MainWindow handles session management and review mode
5. User can return to main menu from review mode, which loops back to step 2

The main() function implements a loop that allows returning to the setup dialog
after closing the main window via "Return to Main Menu" action.
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
from src.core.app_config import AppSettings
from src.ui.setup_dialog import SetupDialog
from src.ui.main_window import MainWindow


def main() -> int:
    """
    Main entry point for the application.

    This function implements the main application loop that allows users to:
    1. Start with the setup dialog (new session or resume existing)
    2. Edit video in the main window
    3. Return to the setup dialog from review mode if needed

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Create and configure the application
    app, config = create_application()

    print(">>> CODE VERSION: 2026-01-15-MENU-LOOP <<<")
    print(f"Pickleball Video Editor v{__version__}")
    print("Starting application...")

    # Load application settings
    app_settings = AppSettings.load()

    # Main application loop - allows returning to menu
    while True:
        # Show setup dialog with app settings
        setup_dialog = SetupDialog(app_settings=app_settings)

        if not setup_dialog.exec():
            # User cancelled the setup dialog - exit application
            print("Setup cancelled by user")
            return 0

        # User accepted the setup dialog
        game_config = setup_dialog.get_config()

        if game_config is None:
            print("Error: Invalid configuration from setup dialog")
            continue

        # Try to get updated app settings from dialog (if supported)
        # If not supported, continue with existing settings
        if hasattr(setup_dialog, "get_app_settings"):
            app_settings = setup_dialog.get_app_settings()
            print("Updated app settings from setup dialog")

        print(f"Loading video: {game_config.video_path}")
        print(f"Game type: {game_config.game_type}")

        # Create main window with game config and app settings
        main_window = MainWindow(game_config, app_settings)

        # Track if we should return to menu
        return_to_menu = False

        def on_return_to_menu() -> None:
            """Handle return to menu request from main window."""
            nonlocal return_to_menu
            return_to_menu = True
            print("Return to menu requested")
            main_window.close()

        # Connect the return to menu signal
        main_window.return_to_menu_requested.connect(on_return_to_menu)

        # Show the main window
        main_window.show()

        # Run the event loop until window closes
        app.exec()

        # Check if we should return to menu or exit
        if not return_to_menu:
            # Window was closed normally (not via return to menu)
            print("Application exiting")
            break

        # If return_to_menu is True, loop continues to show setup dialog again
        print("Returning to setup dialog...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
