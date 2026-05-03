"""
Application entry point for Pickleball Video Editor.

This module initializes the Qt application and launches the main window.
The application flow is:
1. Load AppSettings from disk
2. Show SetupDialog for video and game configuration
3a. Manual mode: If setup is accepted, show MainWindow for rally editing
3b. Auto mode: Run AutoEditProgressDialog, then jump directly to review mode
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

import logging
import sys

from src import __version__
from src.app import create_application
from src.core.app_config import AppSettings
from src.core.export_manager import ExportManager
from src.ui.setup_dialog import SetupDialog
from src.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Main entry point for the application.

    This function implements the main application loop that allows users to:
    1. Start with the setup dialog (new session or resume existing)
    2. Edit video in the main window
    3. Return to the setup dialog from review mode if needed

    FFmpeg exports are managed by ExportManager and survive MainWindow
    destruction (e.g., returning to menu). The app stays alive until all
    exports complete.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Create and configure the application
    app, config = create_application()

    logger.info("Pickleball Video Editor v%s", __version__)

    # Load application settings
    app_settings = AppSettings.load()

    # Create application-level export manager (survives MainWindow lifecycle)
    export_manager = ExportManager()

    # Main application loop - allows returning to menu
    while True:
        # Show setup dialog with app settings
        setup_dialog = SetupDialog(app_settings=app_settings)

        if not setup_dialog.exec():
            # User cancelled the setup dialog
            if export_manager.has_active_exports():
                # Keep app alive until exports finish
                logger.info("Setup cancelled, waiting for active exports to finish...")
                export_manager.all_exports_finished.connect(app.quit)
                app.exec()
                export_manager.all_exports_finished.disconnect(app.quit)
            logger.info("Setup cancelled by user")
            return 0

        # User accepted the setup dialog
        game_config = setup_dialog.get_config()

        if game_config is None:
            logger.error("Invalid configuration from setup dialog")
            continue

        # Try to get updated app settings from dialog (if supported)
        # If not supported, continue with existing settings
        if hasattr(setup_dialog, "get_app_settings"):
            app_settings = setup_dialog.get_app_settings()
            logger.info("Updated app settings from setup dialog")

        logger.info("Loading video: %s", game_config.video_path)
        logger.info("Game type: %s", game_config.game_type)

        # ------------------------------------------------------------------
        # Auto-edit path: run the ML pipeline, then jump to review mode.
        # ------------------------------------------------------------------
        if game_config.auto_mode:
            from ml.auto_edit import AutoEditSetup
            from src.ui.dialogs.auto_edit_progress import AutoEditProgressDialog

            project_root = Path(__file__).parent.parent
            checkpoint_path = project_root / "ml" / "checkpoints" / "best_winner.pt"
            output_dir = game_config.video_path.parent

            # Corners from setup dialog are list[list[int]]; the worker
            # expects list[tuple[int, int]].
            raw_corners = game_config.court_corners or []
            corners_tuples: list[tuple[int, int]] = [
                (int(pt[0]), int(pt[1])) for pt in raw_corners
            ]

            # Translate GameConfig to AutoEditSetup at the UI/ML boundary.
            # GameConfig stays in the UI layer; AutoEditSetup has no PyQt dep.
            auto_setup = AutoEditSetup(
                game_type=game_config.game_type,
                victory_rule=game_config.victory_rule,
                team1_players=list(game_config.team1_players),
                team2_players=list(game_config.team2_players),
                court_corners=list(game_config.court_corners) if game_config.court_corners else None,
            )

            progress_dialog = AutoEditProgressDialog(
                video_path=game_config.video_path,
                setup=auto_setup,
                corners=corners_tuples,
                output_dir=output_dir,
                checkpoint_path=checkpoint_path,
                parent=None,
            )
            accepted = progress_dialog.exec()

            if not accepted:
                # Cancelled or failed — loop back to setup dialog.
                logger.info("Auto-edit cancelled or failed; returning to setup dialog.")
                continue

            auto_result = progress_dialog.get_result()
            if auto_result is None:
                logger.info("Auto-edit returned no result; returning to setup dialog.")
                continue

            logger.info(
                "Auto-edit complete: %d rallies, low-confidence indices: %s",
                auto_result.predicted_rally_count,
                auto_result.low_confidence_rally_indices,
            )

            # Use the SessionState built in-memory by auto_edit() — it has the
            # correct final current_score, serving_team, server_number, and
            # first_server_player_index that review mode needs to show the right score.
            game_config.session_state = auto_result.session_state

            # Create main window (it will restore rally_manager from the session).
            main_window = MainWindow(game_config, app_settings, export_manager=export_manager)

            # Track if we should return to menu.
            return_to_menu = False

            def on_return_to_menu_auto() -> None:
                """Handle return to menu request from main window (auto path)."""
                nonlocal return_to_menu
                return_to_menu = True
                logger.info("Return to menu requested (auto path)")
                main_window.close()
                app.quit()

            main_window.return_to_menu_requested.connect(on_return_to_menu_auto)
            main_window.show()

            # Enter review mode immediately after the window is visible and
            # MPV has had a chance to initialise its native window.  We use
            # a zero-delay single-shot timer so Qt can finish its show() pass
            # before we reparent the video container.
            from PyQt6.QtCore import QTimer

            low_conf_set: set[int] = set(auto_result.low_confidence_rally_indices)

            def _enter_auto_review() -> None:
                main_window.enter_review_mode()
                if main_window._review_widget is not None:
                    main_window._review_widget.set_low_confidence_indices(low_conf_set)

            QTimer.singleShot(0, _enter_auto_review)

            app.exec()

            if not return_to_menu:
                logger.info("Application exiting (auto path)")
                break

            logger.info("Returning to setup dialog (auto path)...")
            continue

        # ------------------------------------------------------------------
        # Normal (manual) path.
        # ------------------------------------------------------------------

        # Create main window with game config, app settings, and export manager
        main_window = MainWindow(game_config, app_settings, export_manager=export_manager)

        # Track if we should return to menu
        return_to_menu = False

        def on_return_to_menu() -> None:
            """Handle return to menu request from main window."""
            nonlocal return_to_menu
            return_to_menu = True
            logger.info("Return to menu requested")
            main_window.close()
            # Force app.exec() to return so the loop continues
            app.quit()

        # Connect the return to menu signal
        main_window.return_to_menu_requested.connect(on_return_to_menu)

        # Show the main window
        main_window.show()

        # Run the event loop until window closes
        app.exec()

        # Check if we should return to menu or exit
        if not return_to_menu:
            # Window was closed normally (not via return to menu)
            logger.info("Application exiting")
            break

        # If return_to_menu is True, loop continues to show setup dialog again
        logger.info("Returning to setup dialog...")

    # If exports are still running, keep the app alive until they finish
    if export_manager.has_active_exports():
        logger.info("Waiting for active exports to finish...")
        export_manager.all_exports_finished.connect(app.quit)
        app.exec()

    return 0


if __name__ == "__main__":
    sys.exit(main())
