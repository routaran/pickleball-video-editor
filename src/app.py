"""
QApplication configuration and setup.

This module provides centralized application-level configuration including:
- Application metadata
- Global stylesheet application
- Signal handling
- Resource initialization
"""

from typing import Optional

from PyQt6.QtWidgets import QApplication


class AppConfig:
    """
    Application configuration and initialization.

    TODO: Implement in Phase 2
    - Load and apply global QSS stylesheet
    - Configure application-wide settings
    - Setup signal handlers for clean shutdown
    - Initialize resource paths
    """

    def __init__(self, app: QApplication) -> None:
        """
        Initialize application configuration.

        Args:
            app: The QApplication instance to configure
        """
        self.app = app
        # TODO: Load stylesheet from src/ui/styles/
        # TODO: Setup application icon
        # TODO: Configure font defaults

    def apply_theme(self, theme_name: str = "court_green") -> None:
        """
        Apply a color theme to the application.

        Args:
            theme_name: Name of the theme to apply (default: "court_green")

        TODO: Implement theme loading and application
        """
        pass
