"""
QApplication configuration and setup.

This module provides centralized application-level configuration including:
- Application metadata
- Global stylesheet application
- Font configuration
- Resource initialization
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .ui.styles.fonts import Fonts

__all__ = ["AppConfig", "create_application"]


class AppConfig:
    """
    Application configuration and initialization.

    Handles application-wide setup including font configuration and theme
    stylesheet loading. This class should be instantiated once during
    application startup.
    """

    def __init__(self, app: QApplication) -> None:
        """
        Initialize application configuration.

        Args:
            app: The QApplication instance to configure

        This will automatically:
        - Set up default fonts
        - Apply the default theme stylesheet
        """
        self.app = app
        self._configure_fonts()
        self.apply_theme()

    def _configure_fonts(self) -> None:
        """
        Configure application-wide font defaults.

        Sets the application font to IBM Plex Sans (with fallback chain)
        using the design system's body font configuration.
        """
        default_font = Fonts.body()
        self.app.setFont(default_font)

    def apply_theme(self, theme_name: str = "court_green") -> None:
        """
        Apply a color theme to the application.

        Args:
            theme_name: Name of the theme to apply (default: "court_green")

        Currently only the "court_green" theme is supported. This method
        loads the theme.qss stylesheet from src/ui/styles/ and applies it
        to the application.

        If the stylesheet file cannot be found, a warning is printed to
        stderr but the application continues (using Qt default styling).
        """
        stylesheet_path = self._get_stylesheet_path()

        if not stylesheet_path.exists():
            print(
                f"Warning: Stylesheet not found at {stylesheet_path}",
                file=sys.stderr,
            )
            return

        stylesheet = stylesheet_path.read_text(encoding="utf-8")
        self.app.setStyleSheet(stylesheet)

    def _get_stylesheet_path(self) -> Path:
        """
        Get the absolute path to the theme stylesheet.

        Returns:
            Path object pointing to theme.qss

        Handles both development mode and PyInstaller bundle mode.
        """
        # Check if running as PyInstaller bundle
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            # Running as bundle - look in _MEIPASS/src/ui/styles/
            base_path = Path(sys._MEIPASS)
            return base_path / "src" / "ui" / "styles" / "theme.qss"
        else:
            # Development mode - relative to this file
            src_dir = Path(__file__).parent
            return src_dir / "ui" / "styles" / "theme.qss"


def create_application() -> tuple[QApplication, AppConfig]:
    """
    Factory function to create and configure the QApplication.

    Returns:
        Tuple of (QApplication instance, AppConfig instance)

    This is the recommended way to create the application instance.
    It handles all necessary setup in the correct order.

    Example:
        ```python
        from app import create_application

        app, config = create_application()
        # ... create main window ...
        sys.exit(app.exec())
        ```
    """
    app = QApplication(sys.argv)

    # CRITICAL: Qt resets locale during QApplication init.
    # MPV requires LC_NUMERIC="C" or it crashes with segfault.
    # Use ctypes to call C library setlocale directly - Python's locale
    # module doesn't reliably affect the C library on all systems.
    import ctypes
    import locale
    import os
    os.environ["LC_NUMERIC"] = "C"
    locale.setlocale(locale.LC_NUMERIC, "C")
    libc = ctypes.CDLL("libc.so.6")
    libc.setlocale.restype = ctypes.c_char_p
    result = libc.setlocale(1, b"C")  # LC_NUMERIC = 1 on Linux
    print(f"DEBUG app.py after QApplication: C setlocale returned: {result}")

    app.setApplicationName("Pickleball Video Editor")
    app.setOrganizationName("Pickleball Video Editor")
    app.setOrganizationDomain("pickleballeditor.local")

    config = AppConfig(app)

    return app, config
