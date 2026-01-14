"""Color palette for the Pickleball Video Editor - "Court Green" theme.

This module provides the complete color system used throughout the application,
including background colors, action colors, text colors, and utility functions
for working with Qt color objects.

All colors follow the design system specified in docs/UI_SPEC.md Section 2.2.
"""

from PyQt6.QtGui import QColor


# ============================================================================
# Background Colors
# ============================================================================

BG_PRIMARY = "#1A1D23"      # Deep Slate - Main window background
BG_SECONDARY = "#252A33"    # Elevated Surface - Panels, containers
BG_TERTIARY = "#2D3340"     # Card Surface - Buttons, input fields
BG_BORDER = "#3D4450"       # Subtle Edge - Dividers, borders


# ============================================================================
# Action Colors
# ============================================================================

RALLY_START = "#3DDC84"     # Pickle Green - Rally start button
SERVER_WINS = "#4FC3F7"     # Court Blue - Server wins button
RECEIVER_WINS = "#FFB300"   # Ball Orange - Receiver wins button
UNDO = "#EF5350"            # Coral Red - Undo button
PRIMARY_ACTION = "#3DDC84"  # Accent Green - Primary action buttons


# ============================================================================
# Text Colors
# ============================================================================

TEXT_PRIMARY = "#F5F5F5"    # Off White - Primary text
TEXT_SECONDARY = "#9E9E9E"  # Muted Gray - Secondary text, labels
TEXT_ACCENT = "#3DDC84"     # Pickle Green - Highlighted text
TEXT_WARNING = "#FFE082"    # Amber - Warning messages
TEXT_DISABLED = "#5A6270"   # Disabled text and controls


# ============================================================================
# Glow Effects (for active button states)
# ============================================================================

GLOW_GREEN = "rgba(61, 220, 132, 0.4)"      # Green button glow
GLOW_BLUE = "rgba(79, 195, 247, 0.4)"       # Blue button glow
GLOW_ORANGE = "rgba(255, 179, 0, 0.4)"      # Orange button glow
GLOW_RED = "rgba(239, 83, 80, 0.4)"         # Red button glow


class Colors:
    """Utility class for working with application colors.

    Provides helper methods to convert hex strings to QColor objects
    and generate rgba color strings with custom alpha values.
    """

    @staticmethod
    def to_qcolor(hex_color: str) -> QColor:
        """Convert a hex color string to a QColor object.

        Args:
            hex_color: Hex color string (e.g., "#1A1D23" or "#3DDC84")

        Returns:
            QColor object for use in PyQt6 widgets

        Example:
            >>> color = Colors.to_qcolor(BG_PRIMARY)
            >>> widget.setBackgroundColor(color)
        """
        return QColor(hex_color)

    @staticmethod
    def to_rgba(hex_color: str, alpha: float) -> str:
        """Convert hex color to rgba string with specified alpha.

        Args:
            hex_color: Hex color string (e.g., "#3DDC84")
            alpha: Alpha value between 0.0 (transparent) and 1.0 (opaque)

        Returns:
            RGBA color string (e.g., "rgba(61, 220, 132, 0.4)")

        Example:
            >>> glow = Colors.to_rgba(RALLY_START, 0.4)
            >>> # Use in QSS: box-shadow: 0 0 8px rgba(61, 220, 132, 0.4);
        """
        # Remove '#' prefix if present
        hex_color = hex_color.lstrip('#')

        # Convert hex to RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Clamp alpha to valid range
        alpha = max(0.0, min(1.0, alpha))

        return f"rgba({r}, {g}, {b}, {alpha})"

    @staticmethod
    def get_glow_for_action(action_color: str) -> str:
        """Get the appropriate glow color for an action button.

        Args:
            action_color: Hex color of the action button

        Returns:
            RGBA glow color string

        Example:
            >>> glow = Colors.get_glow_for_action(RALLY_START)
            >>> # Returns: "rgba(61, 220, 132, 0.4)"
        """
        glow_map = {
            RALLY_START: GLOW_GREEN,
            PRIMARY_ACTION: GLOW_GREEN,
            SERVER_WINS: GLOW_BLUE,
            RECEIVER_WINS: GLOW_ORANGE,
            UNDO: GLOW_RED,
        }

        if action_color in glow_map:
            return glow_map[action_color]

        # Default: generate glow with 0.4 alpha
        return Colors.to_rgba(action_color, 0.4)


# ============================================================================
# Semantic Color Aliases
# ============================================================================
# These provide semantic naming for specific UI elements

WINDOW_BG = BG_PRIMARY
PANEL_BG = BG_SECONDARY
BUTTON_BG = BG_TERTIARY
BORDER_COLOR = BG_BORDER

ACTION_PRIMARY = PRIMARY_ACTION
ACTION_SUCCESS = RALLY_START
ACTION_INFO = SERVER_WINS
ACTION_WARNING = RECEIVER_WINS
ACTION_DANGER = UNDO


__all__ = [
    # Background colors
    "BG_PRIMARY",
    "BG_SECONDARY",
    "BG_TERTIARY",
    "BG_BORDER",

    # Action colors
    "RALLY_START",
    "SERVER_WINS",
    "RECEIVER_WINS",
    "UNDO",
    "PRIMARY_ACTION",

    # Text colors
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_ACCENT",
    "TEXT_WARNING",
    "TEXT_DISABLED",

    # Glow effects
    "GLOW_GREEN",
    "GLOW_BLUE",
    "GLOW_ORANGE",
    "GLOW_RED",

    # Utility class
    "Colors",

    # Semantic aliases
    "WINDOW_BG",
    "PANEL_BG",
    "BUTTON_BG",
    "BORDER_COLOR",
    "ACTION_PRIMARY",
    "ACTION_SUCCESS",
    "ACTION_INFO",
    "ACTION_WARNING",
    "ACTION_DANGER",
]
