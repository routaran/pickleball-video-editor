"""UI styling system for the Pickleball Video Editor.

This package provides:
- Color constants following the "Court Green" theme
- Typography constants (fonts, sizes)
- QSS stylesheets for widgets
- Utility functions for theming
"""

from src.ui.styles.colors import (
    # Background colors
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    BG_BORDER,
    BG_HOVER,
    BG_BORDER_HOVER,
    # Action colors
    RALLY_START,
    SERVER_WINS,
    RECEIVER_WINS,
    RECEIVER_WINS_HOVER,
    UNDO,
    PRIMARY_ACTION,
    PRIMARY_HOVER,
    # Focus ring
    FOCUS_RING,
    # Text colors
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_ACCENT,
    TEXT_WARNING,
    TEXT_DISABLED,
    DANGER_TEXT,
    # Glow effects
    GLOW_GREEN,
    GLOW_BLUE,
    GLOW_ORANGE,
    GLOW_RED,
    PRIMARY_ACTION_TINT,
    # Utility class
    Colors,
    # Semantic aliases
    WINDOW_BG,
    PANEL_BG,
    BUTTON_BG,
    BORDER_COLOR,
    VIDEO_BG,
    ACTION_PRIMARY,
    ACTION_SUCCESS,
    ACTION_INFO,
    ACTION_WARNING,
    ACTION_DANGER,
)
from src.ui.styles.icons import icon, pixmap
from src.ui.styles.fonts import (
    # Font families
    FONT_DISPLAY,
    FONT_BODY,
    FONT_DISPLAY_FALLBACK,
    FONT_BODY_FALLBACK,
    # Font sizes
    SIZE_SCORE_DISPLAY,
    SIZE_BUTTON_RALLY,
    SIZE_BUTTON_OTHER,
    SIZE_STATE_LABELS,
    SIZE_INPUT,
    SIZE_SECONDARY,
    SIZE_TIMESTAMPS,
    SIZE_DIALOG_TITLE,
    # Font weights
    WEIGHT_BOLD,
    WEIGHT_SEMIBOLD,
    WEIGHT_MEDIUM,
    WEIGHT_REGULAR,
    # Spacing system
    SPACE_XS,
    SPACE_SM,
    SPACE_MD,
    SPACE_LG,
    SPACE_XL,
    SPACE_2XL,
    # Border radius
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    RADIUS_XL,
    # Helper class
    Fonts,
)

__all__ = [
    # Icon API
    "icon",
    "pixmap",
    # Background colors
    "BG_PRIMARY",
    "BG_SECONDARY",
    "BG_TERTIARY",
    "BG_BORDER",
    "BG_HOVER",
    "BG_BORDER_HOVER",
    # Action colors
    "RALLY_START",
    "SERVER_WINS",
    "RECEIVER_WINS",
    "RECEIVER_WINS_HOVER",
    "UNDO",
    "PRIMARY_ACTION",
    "PRIMARY_HOVER",
    # Focus ring
    "FOCUS_RING",
    # Text colors
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_TERTIARY",
    "TEXT_ACCENT",
    "TEXT_WARNING",
    "TEXT_DISABLED",
    "DANGER_TEXT",
    # Glow effects
    "GLOW_GREEN",
    "GLOW_BLUE",
    "GLOW_ORANGE",
    "GLOW_RED",
    "PRIMARY_ACTION_TINT",
    # Utility class
    "Colors",
    # Semantic aliases
    "WINDOW_BG",
    "PANEL_BG",
    "BUTTON_BG",
    "BORDER_COLOR",
    "VIDEO_BG",
    "ACTION_PRIMARY",
    "ACTION_SUCCESS",
    "ACTION_INFO",
    "ACTION_WARNING",
    "ACTION_DANGER",
    # Font families
    "FONT_DISPLAY",
    "FONT_BODY",
    "FONT_DISPLAY_FALLBACK",
    "FONT_BODY_FALLBACK",
    # Font sizes
    "SIZE_SCORE_DISPLAY",
    "SIZE_BUTTON_RALLY",
    "SIZE_BUTTON_OTHER",
    "SIZE_STATE_LABELS",
    "SIZE_INPUT",
    "SIZE_SECONDARY",
    "SIZE_TIMESTAMPS",
    "SIZE_DIALOG_TITLE",
    # Font weights
    "WEIGHT_BOLD",
    "WEIGHT_SEMIBOLD",
    "WEIGHT_MEDIUM",
    "WEIGHT_REGULAR",
    # Spacing system
    "SPACE_XS",
    "SPACE_SM",
    "SPACE_MD",
    "SPACE_LG",
    "SPACE_XL",
    "SPACE_2XL",
    # Border radius
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
    "RADIUS_XL",
    # Font helper class
    "Fonts",
]
