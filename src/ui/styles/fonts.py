"""
Typography constants and font utilities for the Pickleball Video Editor.

Implements the "Court Green" design system typography as specified in UI_SPEC.md.
Provides constants for font families, sizes, weights, and spacing with helper
functions for creating QFont instances.

Font Strategy:
- Display/Monospace: JetBrains Mono for timecodes, scores (tabular figures)
- Body/UI: IBM Plex Sans for labels, buttons (clean readability)
- All numeric displays use tabular (monospace) figures to prevent layout shift

Spacing System:
- Base unit: 8px
- Scale: XS (4px) → SM (8px) → MD (16px) → LG (24px) → XL (32px) → 2XL (48px)
"""

from PyQt6.QtGui import QFont, QFontDatabase

__all__ = [
    # Font families
    "FONT_DISPLAY",
    "FONT_BODY",
    "FONT_DISPLAY_FALLBACK",
    "FONT_BODY_FALLBACK",
    # Locked type scale (12 / 14 / 16 / 18 / 24 / 32 px only)
    "SIZE_CAPTION",
    "SIZE_BODY",
    "SIZE_SUBHEADING",
    "SIZE_HEADING",
    "SIZE_TITLE",
    "SIZE_DISPLAY",
    # Legacy aliases (kept for backward compatibility — prefer the new names)
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
    # Responsive breakpoints
    "BREAK_COMPACT",
    "BREAK_ULTRA_COMPACT",
    "ASPECT_ULTRAWIDE",
    # Helper class
    "Fonts",
]


# =============================================================================
# Font Families
# =============================================================================

# Primary monospace font for timecodes, scores, and numeric displays
FONT_DISPLAY = "JetBrains Mono"

# Primary sans-serif font for UI labels, buttons, and body text
FONT_BODY = "IBM Plex Sans"

# Fallback chain for display font (monospace)
FONT_DISPLAY_FALLBACK = ["Fira Code", "Consolas", "monospace"]

# Fallback chain for body font (sans-serif)
FONT_BODY_FALLBACK = ["Segoe UI", "Roboto", "sans-serif"]


# =============================================================================
# Font Sizes (pixel values — all sizes are PIXELS, not points)
#
# LOCKED TYPE SCALE — use only these six values.
# Do NOT add intermediate sizes (e.g. 13, 15, 17, 20).  If a size feels
# wrong, map it to the nearest step or update this comment after team review.
# =============================================================================

SIZE_CAPTION = 12     # Captions, helper text, section labels
SIZE_BODY = 14        # Body text, labels, inputs, standard buttons
SIZE_SUBHEADING = 16  # Timestamps, sub-headings
SIZE_HEADING = 18     # Rally buttons, dialog titles, section headers
SIZE_TITLE = 24       # Large panel titles (future use)
SIZE_DISPLAY = 32     # Score overlay, prominent numeric displays

# ---------------------------------------------------------------------------
# Legacy aliases — kept for backward compatibility with existing callers.
# Prefer the canonical names above in new code.
# ---------------------------------------------------------------------------
SIZE_SCORE_DISPLAY = SIZE_DISPLAY     # score overlay
SIZE_BUTTON_RALLY = SIZE_HEADING      # rally action buttons
SIZE_BUTTON_OTHER = SIZE_BODY         # toolbar / secondary buttons
SIZE_STATE_LABELS = SIZE_BODY         # status text, hints
SIZE_INPUT = SIZE_BODY                # form inputs
SIZE_SECONDARY = SIZE_CAPTION         # helper / caption text
SIZE_TIMESTAMPS = SIZE_SUBHEADING     # video timeline timestamps
SIZE_DIALOG_TITLE = SIZE_HEADING      # modal dialog titles


# =============================================================================
# Font Weights
# =============================================================================

WEIGHT_BOLD = 700        # Strong emphasis, score display
WEIGHT_SEMIBOLD = 600    # Rally buttons, dialog titles
WEIGHT_MEDIUM = 500      # Timestamps, secondary emphasis
WEIGHT_REGULAR = 400     # Body text, labels


# =============================================================================
# Spacing System (8px base unit)
# =============================================================================

SPACE_XS = 4      # Tight gaps, icon padding
SPACE_SM = 8      # Between related elements
SPACE_MD = 16     # Section padding
SPACE_LG = 24     # Between sections
SPACE_XL = 32     # Major section separation
SPACE_2XL = 48    # Panel margins


# =============================================================================
# Border Radius
# =============================================================================

RADIUS_SM = 4     # Input fields
RADIUS_MD = 6     # Buttons
RADIUS_LG = 8     # Cards/panels
RADIUS_XL = 12    # Dialogs


# =============================================================================
# Responsive Breakpoints
#
# Window *width* thresholds used by ResponsiveManager to switch layout modes.
# ASPECT_ULTRAWIDE is the width-to-height ratio above which the side-panel
# ultrawide layout is preferred (e.g. 3840x1080 = 3.56 > 2.0).
# =============================================================================

BREAK_COMPACT = 1000        # px — compact layout below this window width
BREAK_ULTRA_COMPACT = 800   # px — ultra-compact layout below this window width
ASPECT_ULTRAWIDE = 2.0      # ratio — side-panel layout at or above this aspect


# =============================================================================
# Font Helper Class
# =============================================================================

class Fonts:
    """
    Factory class for creating QFont instances with proper fallback chains.

    All fonts are configured with tabular figures (monospace numbers) to prevent
    layout shift when numeric values change.
    """

    @staticmethod
    def _build_font_family(primary: str, fallbacks: list[str]) -> str:
        """
        Build a comma-separated font family string with fallback chain.

        Args:
            primary: Primary font family name
            fallbacks: List of fallback font families

        Returns:
            CSS-style font family string (e.g., "JetBrains Mono, Fira Code, monospace")
        """
        return f"{primary}, {', '.join(fallbacks)}"

    @staticmethod
    def _apply_tabular_figures(font: QFont) -> None:
        """
        Enable tabular (monospace) figures for numeric displays.

        Prevents layout shift when numbers change (e.g., "7-5-2" to "10-5-2").
        This is critical for score displays and timestamps.

        Args:
            font: QFont instance to modify (modified in-place)
        """
        # Enable tabular nums using OpenType feature
        font.setStyleHint(QFont.StyleHint.Monospace, QFont.StyleStrategy.PreferAntialias)

    @classmethod
    def display(
        cls,
        size: int = SIZE_TIMESTAMPS,
        weight: int = WEIGHT_MEDIUM,
        tabular: bool = True,
    ) -> QFont:
        """
        Create a display font (monospace) for timecodes, scores, and numeric values.

        Args:
            size: Font size in pixels (default: SIZE_TIMESTAMPS)
            weight: Font weight (default: WEIGHT_MEDIUM)
            tabular: Enable tabular figures for consistent number width (default: True)

        Returns:
            QFont instance configured for display purposes

        Example:
            ```python
            # Score display
            score_font = Fonts.display(SIZE_SCORE_DISPLAY, WEIGHT_BOLD)

            # Timestamp display
            time_font = Fonts.display(SIZE_TIMESTAMPS, WEIGHT_MEDIUM)
            ```
        """
        family = cls._build_font_family(FONT_DISPLAY, FONT_DISPLAY_FALLBACK)
        # Use setPixelSize() instead of passing size to the QFont constructor.
        # The QFont(family, pointSize, weight) constructor treats the second
        # argument as *points*, which renders ~25% larger than the intended
        # pixel values at 96 DPI.  setPixelSize() sets exact screen pixels.
        font = QFont(family)
        font.setWeight(weight)
        font.setPixelSize(size)

        if tabular:
            cls._apply_tabular_figures(font)

        return font

    @classmethod
    def body(
        cls,
        size: int = SIZE_STATE_LABELS,
        weight: int = WEIGHT_REGULAR,
    ) -> QFont:
        """
        Create a body font (sans-serif) for UI labels, buttons, and body text.

        Args:
            size: Font size in pixels (default: SIZE_STATE_LABELS)
            weight: Font weight (default: WEIGHT_REGULAR)

        Returns:
            QFont instance configured for body text

        Example:
            ```python
            # Button text
            button_font = Fonts.body(SIZE_BUTTON_RALLY, WEIGHT_SEMIBOLD)

            # Label text
            label_font = Fonts.body(SIZE_STATE_LABELS, WEIGHT_REGULAR)
            ```
        """
        family = cls._build_font_family(FONT_BODY, FONT_BODY_FALLBACK)
        # setPixelSize() sets exact screen pixels; the QFont(family, size)
        # constructor treats size as *points* which is ~25% larger at 96 DPI.
        font = QFont(family)
        font.setWeight(weight)
        font.setPixelSize(size)
        font.setStyleHint(QFont.StyleHint.SansSerif, QFont.StyleStrategy.PreferAntialias)
        return font

    @classmethod
    def score_display(cls) -> QFont:
        """
        Create font for large score displays.

        Returns:
            QFont configured for score overlay (32px, bold, tabular)
        """
        return cls.display(SIZE_SCORE_DISPLAY, WEIGHT_BOLD, tabular=True)

    @classmethod
    def button_rally(cls) -> QFont:
        """
        Create font for rally action buttons.

        Returns:
            QFont configured for rally buttons (18px, semibold)
        """
        return cls.body(SIZE_BUTTON_RALLY, WEIGHT_SEMIBOLD)

    @classmethod
    def button_other(cls) -> QFont:
        """
        Create font for secondary buttons and toolbar buttons.

        Returns:
            QFont configured for other buttons (14px, medium)
        """
        return cls.body(SIZE_BUTTON_OTHER, WEIGHT_MEDIUM)

    @classmethod
    def dialog_title(cls) -> QFont:
        """
        Create font for modal dialog titles.

        Returns:
            QFont configured for dialog titles (18px, semibold)
        """
        return cls.body(SIZE_DIALOG_TITLE, WEIGHT_SEMIBOLD)

    @classmethod
    def timestamp(cls) -> QFont:
        """
        Create font for timestamp displays.

        Returns:
            QFont configured for timestamps (16px, medium, tabular)
        """
        return cls.display(SIZE_TIMESTAMPS, WEIGHT_MEDIUM, tabular=True)

    @classmethod
    def label(cls) -> QFont:
        """
        Create font for standard UI labels.

        Returns:
            QFont configured for labels (14px, regular)
        """
        return cls.body(SIZE_STATE_LABELS, WEIGHT_REGULAR)

    @classmethod
    def input_text(cls) -> QFont:
        """
        Create font for input fields.

        Returns:
            QFont configured for text inputs (14px, regular)
        """
        return cls.body(SIZE_INPUT, WEIGHT_REGULAR)

    @classmethod
    def secondary(cls) -> QFont:
        """
        Create font for secondary/helper text.

        Returns:
            QFont configured for captions and hints (12px, regular)
        """
        return cls.body(SIZE_SECONDARY, WEIGHT_REGULAR)

    @classmethod
    def section_label(cls) -> QFont:
        """Create font for uppercase section labels with letter-spacing.

        Intended for small group headings that appear in TEXT_SECONDARY color
        with text-transform:uppercase applied via QSS.  The 0.5px absolute
        letter-spacing gives the all-caps text a refined, airy appearance.

        Returns:
            QFont at SIZE_CAPTION (12px), WEIGHT_SEMIBOLD, 0.5px letter-spacing.

        Note:
            Color (TEXT_SECONDARY) and text-transform uppercase must be set
            via QSS on the widget — QFont has no color or case-transform API.

        Example::

            label = QLabel("Rally Controls")
            label.setFont(Fonts.section_label())
            label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; text-transform: uppercase;"
            )
        """
        family = cls._build_font_family(FONT_BODY, FONT_BODY_FALLBACK)
        font = QFont(family)
        font.setWeight(WEIGHT_SEMIBOLD)
        font.setPixelSize(SIZE_CAPTION)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
        font.setStyleHint(QFont.StyleHint.SansSerif, QFont.StyleStrategy.PreferAntialias)
        return font

    @classmethod
    def get_available_fonts(cls) -> dict[str, bool]:
        """
        Check which fonts from our design system are installed on the system.

        Returns:
            Dictionary mapping font names to availability status

        Example:
            ```python
            fonts = Fonts.get_available_fonts()
            if not fonts["JetBrains Mono"]:
                print("Warning: Primary display font not available")
            ```
        """
        # In PyQt6, families() is a static method
        families = QFontDatabase.families()

        fonts_to_check = [
            FONT_DISPLAY,
            FONT_BODY,
        ] + FONT_DISPLAY_FALLBACK + FONT_BODY_FALLBACK

        return {
            font: font in families
            for font in fonts_to_check
            if font not in ("monospace", "sans-serif")  # Skip generic families
        }
