"""QSS string factories for reusable component styling.

Provides QSS string factories for consistent widget styling across the
application.  Each factory returns a complete stylesheet string (base,
hover, pressed, disabled, and focus states) built from the tokens in
colors.py and fonts.py.

Usage — direct stylesheet application:
    widget.setStyleSheet(ButtonStyles.secondary())

Usage — property-class system (theme.qss handles the rules):
    set_class(widget, "secondary")   # sets buttonClass property
    # theme.qss: QPushButton[buttonClass="secondary"] { ... }

Usage — label text-role system (theme.qss handles the rules):
    set_label_role(label, "body")    # sets textRole property
    # theme.qss: QLabel[textRole="body"] { color: #9E9E9E; font-size: 14px; }

Available textRole names (see theme.qss §2 text-role system):
    "caption"      — 12px / regular  / #98A2B3  (TEXT_TERTIARY, de-emphasis)
    "body"         — 14px / regular  / #9E9E9E  (TEXT_SECONDARY)
    "bodyPrimary"  — 14px / regular  / #F5F5F5  (TEXT_PRIMARY)
    "heading"      — 16px / semibold / #F5F5F5  (TEXT_PRIMARY)
    "subheading"   — 18px / semibold / #F5F5F5  (TEXT_PRIMARY)
    "score"        — 24px / bold     / #F5F5F5  (TEXT_PRIMARY)
    "display"      — 32px / bold     / #F5F5F5  (TEXT_PRIMARY)
    "danger"       — 14px / regular  / #F87171  (DANGER_TEXT, 4.6:1 contrast)
    "warning"      — 14px / regular  / #FFE082  (TEXT_WARNING)
    "accent"       — 14px / regular  / #3DDC84  (TEXT_ACCENT, green)
    "sectionLabel" — 12px / semibold / #9E9E9E  (TEXT_SECONDARY, uppercase)
                     NOTE: also set Fonts.section_label() QFont and call
                     label.setText(text.upper()) — Qt QSS cannot apply
                     text-transform or letter-spacing.

Button tier constants:
    Rally   (primary actions)  44 h / 110 w
    Standard (secondary)       36 h /  88 w  padding 8px 16px
    Compact  (utility)         32 h /  64 w
"""

from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from src.ui.styles.colors import (
    BG_BORDER,
    BG_HOVER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    FOCUS_RING,
    PRIMARY_ACTION,
    PRIMARY_HOVER,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    UNDO,
)
from src.ui.styles.fonts import RADIUS_LG, RADIUS_MD, RADIUS_SM

__all__ = [
    "ButtonStyles",
    "CardStyles",
    "InputStyles",
    "set_class",
    "set_label_role",
    "BTN_RALLY_H",
    "BTN_RALLY_W",
    "BTN_STANDARD_H",
    "BTN_STANDARD_W",
    "BTN_COMPACT_H",
    "BTN_COMPACT_W",
]

# ---------------------------------------------------------------------------
# Button tier dimension constants
# ---------------------------------------------------------------------------
BTN_RALLY_H: int = 44       # Rally (primary action) minimum height in px
BTN_RALLY_W: int = 110      # Rally minimum width in px
BTN_STANDARD_H: int = 36    # Standard button minimum height in px
BTN_STANDARD_W: int = 88    # Standard button minimum width in px
BTN_COMPACT_H: int = 32     # Compact button minimum height in px
BTN_COMPACT_W: int = 64     # Compact button minimum width in px


class ButtonStyles:
    """QSS string factories for QPushButton styling.

    Each method returns a complete stylesheet string including base, hover,
    pressed, disabled, and focus states.  Apply with setStyleSheet().
    """

    @staticmethod
    def primary() -> str:
        """Filled green primary action button (rally tier, 44 h / 110 w).

        Use sparingly — only ONE primary action should be visible per view.
        """
        return f"""
QPushButton {{
    background-color: {PRIMARY_ACTION};
    color: {BG_PRIMARY};
    border: 2px solid {PRIMARY_ACTION};
    border-radius: {RADIUS_MD}px;
    padding: 8px 16px;
    font-weight: 600;
    min-height: {BTN_RALLY_H}px;
    min-width: {BTN_RALLY_W}px;
}}
QPushButton:hover {{
    background-color: {PRIMARY_HOVER};
    border-color: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background-color: #2DCC74;
    border-color: #2DCC74;
}}
QPushButton:disabled {{
    background-color: {BG_TERTIARY};
    border-color: {BG_BORDER};
    color: {TEXT_DISABLED};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 7px 15px;
}}
"""

    @staticmethod
    def secondary() -> str:
        """Bordered secondary button with subdued styling (standard tier, 36 h / 88 w)."""
        return f"""
QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 8px 16px;
    min-height: {BTN_STANDARD_H}px;
    min-width: {BTN_STANDARD_W}px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: #4D5460;
}}
QPushButton:pressed {{
    background-color: {BG_SECONDARY};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BG_BORDER};
    background-color: {BG_TERTIARY};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 7px 15px;
}}
"""

    @staticmethod
    def outline(accent_hex: str, *, rally_tier: bool = False) -> str:
        """Outline button: transparent base, accent border/text, fills on hover.

        Args:
            accent_hex:  Hex color string for border, text, and hover fill.
            rally_tier:  When True, use rally dimensions (44 h / 110 w).
                         When False (default), use standard (36 h / 88 w).
        """
        h = BTN_RALLY_H if rally_tier else BTN_STANDARD_H
        w = BTN_RALLY_W if rally_tier else BTN_STANDARD_W
        return f"""
QPushButton {{
    background-color: transparent;
    color: {accent_hex};
    border: 2px solid {accent_hex};
    border-radius: {RADIUS_MD}px;
    padding: 8px 16px;
    min-height: {h}px;
    min-width: {w}px;
}}
QPushButton:hover {{
    background-color: {accent_hex};
    color: {BG_PRIMARY};
}}
QPushButton:pressed {{
    background-color: {accent_hex};
    color: {BG_PRIMARY};
    border-color: {accent_hex};
}}
QPushButton:disabled {{
    background-color: transparent;
    border-color: {BG_BORDER};
    color: {TEXT_DISABLED};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 7px 15px;
}}
"""

    @staticmethod
    def danger() -> str:
        """Filled red destructive action button (compact tier, 32 h / 64 w)."""
        return f"""
QPushButton {{
    background-color: {UNDO};
    color: {TEXT_PRIMARY};
    border: 1px solid {UNDO};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
    min-height: {BTN_COMPACT_H}px;
    min-width: {BTN_COMPACT_W}px;
}}
QPushButton:hover {{
    background-color: #D84845;
    border-color: #D84845;
}}
QPushButton:pressed {{
    background-color: #C13F3C;
    border-color: #C13F3C;
}}
QPushButton:disabled {{
    background-color: {BG_TERTIARY};
    border-color: {BG_BORDER};
    color: {TEXT_DISABLED};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 3px;
}}
"""

    @staticmethod
    def compact() -> str:
        """Compact secondary utility button (compact tier, 32 h / 64 w)."""
        return f"""
QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 12px;
    min-height: {BTN_COMPACT_H}px;
    min-width: {BTN_COMPACT_W}px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: #4D5460;
}}
QPushButton:pressed {{
    background-color: {BG_SECONDARY};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BG_BORDER};
    background-color: {BG_TERTIARY};
}}
QPushButton:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 5px 11px;
}}
"""


class CardStyles:
    """QSS string factories for panel/card container styling.

    These strings target QFrame widgets via setStyleSheet().
    For plain QWidget containers use set_class(widget, "panel") instead,
    which relies on the theme.qss QWidget[cardClass="panel"] selector.
    """

    @staticmethod
    def panel() -> str:
        """Elevated panel: BG_SECONDARY background with border (for QFrame)."""
        return f"""
QFrame {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BG_BORDER};
    border-radius: {RADIUS_LG}px;
}}
"""

    @staticmethod
    def card() -> str:
        """Card surface: BG_TERTIARY background with border (for QFrame)."""
        return f"""
QFrame {{
    background-color: {BG_TERTIARY};
    border: 1px solid {BG_BORDER};
    border-radius: {RADIUS_LG}px;
}}
"""


class InputStyles:
    """QSS string factories for form input widget styling."""

    @staticmethod
    def line_edit() -> str:
        """Standard text input with focus highlight and error state."""
        return f"""
QLineEdit {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 8px;
    selection-background-color: {PRIMARY_ACTION};
    selection-color: {BG_PRIMARY};
}}
QLineEdit:hover {{
    border-color: #4D5460;
}}
QLineEdit:focus {{
    border: 2px solid {FOCUS_RING};
    padding: 7px;
}}
QLineEdit:disabled {{
    background-color: {BG_SECONDARY};
    border-color: {BG_BORDER};
    color: {TEXT_DISABLED};
}}
QLineEdit[error="true"] {{
    border: 2px solid {UNDO};
    padding: 7px;
}}
"""

    @staticmethod
    def checkbox() -> str:
        """Standard checkbox with custom indicator and focus ring."""
        return f"""
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {BG_BORDER};
    border-radius: 3px;
    background-color: {BG_TERTIARY};
}}
QCheckBox::indicator:hover {{
    border-color: #4D5460;
}}
QCheckBox::indicator:checked {{
    background-color: {PRIMARY_ACTION};
    border-color: {PRIMARY_ACTION};
}}
QCheckBox::indicator:disabled {{
    background-color: {BG_SECONDARY};
    border-color: {BG_BORDER};
}}
QCheckBox:disabled {{
    color: {TEXT_DISABLED};
}}
QCheckBox:focus::indicator {{
    border: 2px solid {FOCUS_RING};
}}
"""


def set_class(widget: QWidget, name: str) -> None:
    """Apply a property-based style class to a widget and refresh its style.

    Sets ``buttonClass`` for QPushButton instances, ``cardClass`` for all
    others.  The corresponding theme.qss property-class selectors
    (e.g. ``QPushButton[buttonClass="secondary"]``) take effect after the
    property change is applied.

    Args:
        widget: Widget to style.
        name:   Class token — e.g. ``"primary"``, ``"secondary"``, ``"nav"``,
                ``"panel"``, ``"card"``.
    """
    prop = "buttonClass" if isinstance(widget, QPushButton) else "cardClass"
    widget.setProperty(prop, name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_label_role(label: QLabel, role: str) -> None:
    """Apply a text-role to a QLabel and refresh its style.

    Sets the ``textRole`` dynamic property so the matching theme.qss rule
    (e.g. ``QLabel[textRole="body"]``) takes effect after polishing.

    Available roles and their resolved palette values:
        ``"caption"``      — 12px / regular  / #98A2B3  (TEXT_TERTIARY)
        ``"body"``         — 14px / regular  / #9E9E9E  (TEXT_SECONDARY)
        ``"bodyPrimary"``  — 14px / regular  / #F5F5F5  (TEXT_PRIMARY)
        ``"heading"``      — 16px / semibold / #F5F5F5  (TEXT_PRIMARY)
        ``"subheading"``   — 18px / semibold / #F5F5F5  (TEXT_PRIMARY)
        ``"score"``        — 24px / bold     / #F5F5F5  (TEXT_PRIMARY)
        ``"display"``      — 32px / bold     / #F5F5F5  (TEXT_PRIMARY)
        ``"danger"``       — 14px / regular  / #F87171  (DANGER_TEXT)
        ``"warning"``      — 14px / regular  / #FFE082  (TEXT_WARNING)
        ``"accent"``       — 14px / regular  / #3DDC84  (TEXT_ACCENT)
        ``"sectionLabel"`` — 12px / semibold / #9E9E9E  (TEXT_SECONDARY)
                             Pair with ``Fonts.section_label()`` QFont and
                             ``label.setText(text.upper())`` — Qt QSS cannot
                             apply ``text-transform`` or ``letter-spacing``.

    Args:
        label: QLabel widget to style.
        role:  Text-role token name from the list above.
    """
    label.setProperty("textRole", role)
    label.style().unpolish(label)
    label.style().polish(label)
    label.update()
