"""
Application entry point for Pickleball Video Editor.

This module initializes the Qt application and launches the main window.
"""

import sys

from PyQt6.QtWidgets import QApplication

from src import __version__


def main() -> int:
    """
    Main entry point for the application.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    app = QApplication(sys.argv)
    app.setApplicationName("Pickleball Video Editor")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Pickleball Video Editor Team")

    print(f"Pickleball Video Editor v{__version__}")
    print("Initializing application...")

    # TODO: Initialize main window once implemented
    # from src.ui.main_window import MainWindow
    # main_window = MainWindow()
    # main_window.show()

    # For now, just exit cleanly
    print("Setup complete. Exiting (main window not yet implemented).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
