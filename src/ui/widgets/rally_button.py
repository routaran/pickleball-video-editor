"""Rally button widget with pulsing glow animation for active state.

This module provides the RallyButton class, a custom QPushButton specialized for
marking rally events in the Pickleball Video Editor. Each button type (Rally Start,
Server Wins, Receiver Wins, Undo) has distinct colors and visual states.

Features:
- Four button types with unique color schemes
- Active state with animated pulse/glow effect
- Disabled state with reduced opacity
- Custom painting for precise visual control
- Consistent sizing per UI specification

Visual States:
- Normal: Dark background, colored border, colored text
- Active: Filled background, dark text, animated glow (pulse)
- Disabled: 40% opacity, gray colors, no interactions

The pulse animation runs continuously when the button is in the active state,
creating a breathing glow effect to draw attention to available actions.
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from src.ui.styles.colors import (
    BG_PRIMARY,
    BG_TERTIARY,
    RALLY_START,
    RECEIVER_WINS,
    SERVER_WINS,
    TEXT_DISABLED,
    UNDO,
    Colors,
)

# Button type constants
BUTTON_TYPE_RALLY_START = "rally_start"
BUTTON_TYPE_SERVER_WINS = "server_wins"
BUTTON_TYPE_RECEIVER_WINS = "receiver_wins"
BUTTON_TYPE_UNDO = "undo"


class RallyButton(QPushButton):
    """Custom button for rally event marking with animated glow effect.

    This button provides visual feedback for rally marking actions with three
    distinct states: normal (clickable), active (with pulsing glow), and disabled.
    The active state features a continuous pulse animation that draws attention
    to currently available actions.

    Button Types and Colors:
        - RALLY_START: Green (#3DDC84) - Start a new rally
        - SERVER_WINS: Blue (#4FC3F7) - Mark server victory
        - RECEIVER_WINS: Orange (#FFB300) - Mark receiver victory
        - UNDO: Red (#EF5350) - Undo last action

    Sizing (from UI_SPEC.md):
        - Rally Start/Server/Receiver: 160-180px width × 56px height
        - Undo: 100px width × 40px height

    Example:
        >>> start_btn = RallyButton("RALLY START", BUTTON_TYPE_RALLY_START)
        >>> start_btn.set_active(True)  # Enable pulse animation
        >>> start_btn.clicked.connect(on_rally_start)
    """

    def __init__(
        self,
        text: str,
        button_type: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize a rally button with specified type and text.

        Args:
            text: Button label text (e.g., "RALLY START", "SERVER WINS")
            button_type: One of the BUTTON_TYPE_* constants
            parent: Optional parent widget

        Raises:
            ValueError: If button_type is not one of the valid constants
        """
        super().__init__(text, parent)

        # Validate button type
        valid_types = {
            BUTTON_TYPE_RALLY_START,
            BUTTON_TYPE_SERVER_WINS,
            BUTTON_TYPE_RECEIVER_WINS,
            BUTTON_TYPE_UNDO,
        }
        if button_type not in valid_types:
            msg = f"Invalid button_type: {button_type}. Must be one of {valid_types}"
            raise ValueError(msg)

        self._button_type = button_type
        self._is_active = False
        self._glow_radius = 8  # Animated property for pulse effect

        # Set up animation for pulse effect
        self._pulse_animation = QPropertyAnimation(self, b"glow_radius")
        self._pulse_animation.setDuration(2000)  # 2 seconds per cycle
        self._pulse_animation.setStartValue(8)
        self._pulse_animation.setEndValue(16)
        self._pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse_animation.setLoopCount(-1)  # Infinite loop

        # Configure appearance
        self._setup_appearance()
        self._apply_size_constraints()

    def _setup_appearance(self) -> None:
        """Configure button font and styling."""
        # Set font based on button type
        font = QFont("IBM Plex Sans", 14 if self._button_type == BUTTON_TYPE_UNDO else 18)
        font.setWeight(
            QFont.Weight.Medium if self._button_type == BUTTON_TYPE_UNDO else QFont.Weight.DemiBold
        )
        self.setFont(font)

        # Set cursor
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _apply_size_constraints(self) -> None:
        """Apply minimum size based on button type per UI specification."""
        if self._button_type == BUTTON_TYPE_UNDO:
            # Undo button: 70px × 36px (reduced for 800px responsive support)
            self.setMinimumSize(70, 36)
        elif self._button_type == BUTTON_TYPE_RECEIVER_WINS:
            # Receiver Wins: 120px × 44px (reduced for 800px responsive support)
            self.setMinimumSize(120, 44)
        else:
            # Rally Start, Server Wins: 110px × 44px (reduced for 800px responsive support)
            self.setMinimumSize(110, 44)

    @property
    def button_type(self) -> str:
        """Get the button type constant.

        Returns:
            One of the BUTTON_TYPE_* constants
        """
        return self._button_type

    def is_active(self) -> bool:
        """Check if button is in active (pulsing) state.

        Returns:
            True if button is active and pulsing, False otherwise
        """
        return self._is_active

    def set_active(self, active: bool) -> None:
        """Enable or disable the active (pulsing glow) state.

        When active is True, the button:
        - Fills with its accent color
        - Displays dark text for contrast
        - Starts the pulse animation (breathing glow effect)

        When active is False, the button returns to normal appearance
        with just a colored border.

        Args:
            active: True to activate pulse, False to deactivate
        """
        if self._is_active == active:
            return  # No change needed

        self._is_active = active

        if active:
            self._pulse_animation.start()
        else:
            self._pulse_animation.stop()
            self._glow_radius = 8  # Reset to default

        self.update()  # Trigger repaint

    # Qt property for animation system
    @pyqtProperty(int)
    def glow_radius(self) -> int:
        """Get the current glow radius for animation.

        This property is animated by QPropertyAnimation to create the
        pulsing glow effect. It ranges from 8px to 16px.

        Returns:
            Current glow radius in pixels
        """
        return self._glow_radius

    @glow_radius.setter
    def glow_radius(self, radius: int) -> None:
        """Set the glow radius and trigger repaint.

        Args:
            radius: New glow radius in pixels (typically 8-16)
        """
        self._glow_radius = radius
        self.update()  # Trigger repaint with new radius

    def _get_color_for_type(self) -> str:
        """Get the accent color hex for this button type.

        Returns:
            Hex color string (e.g., "#3DDC84")
        """
        color_map = {
            BUTTON_TYPE_RALLY_START: RALLY_START,
            BUTTON_TYPE_SERVER_WINS: SERVER_WINS,
            BUTTON_TYPE_RECEIVER_WINS: RECEIVER_WINS,
            BUTTON_TYPE_UNDO: UNDO,
        }
        return color_map[self._button_type]

    def paintEvent(self, event) -> None:
        """Custom paint implementation for precise visual control.

        Draws the button with:
        1. Outer glow (when active) using current animated glow_radius
        2. Background fill (solid color when active, dark when normal/disabled)
        3. Border (colored when enabled, gray when disabled)
        4. Centered text (dark on active background, colored on normal)

        The glow effect is achieved by drawing progressively lighter circles
        with decreasing alpha values, creating a soft blur effect.

        Args:
            event: QPaintEvent (unused, required by Qt signature)
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        accent_color = self._get_color_for_type()

        # Handle disabled state
        if not self.isEnabled():
            painter.setOpacity(0.4)
            self._draw_disabled_button(painter, rect)
            return

        # Draw glow effect for active state
        if self._is_active:
            self._draw_glow(painter, rect, accent_color)

        # Draw button body
        if self._is_active:
            self._draw_active_button(painter, rect, accent_color)
        else:
            self._draw_normal_button(painter, rect, accent_color)

    def _draw_glow(self, painter: QPainter, rect: QRect, accent_color: str) -> None:
        """Draw the animated outer glow effect.

        Creates a soft glow by drawing multiple concentric rectangles with
        decreasing opacity, using the current animated glow_radius.

        Args:
            painter: QPainter instance
            rect: Button rectangle
            accent_color: Hex color for the glow
        """
        glow_color = Colors.to_qcolor(accent_color)

        # Draw multiple glow layers for smooth blur effect
        num_layers = 5
        for i in range(num_layers):
            # Calculate opacity: stronger near button, fading outward
            alpha = int(40 * (1 - i / num_layers))  # 40 to 0
            glow_color.setAlpha(alpha)

            # Calculate expansion: grows outward
            expansion = int(self._glow_radius * i / num_layers)
            glow_rect = rect.adjusted(-expansion, -expansion, expansion, expansion)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow_color)
            painter.drawRoundedRect(glow_rect, 6, 6)

    def _draw_active_button(
        self, painter: QPainter, rect: QRect, accent_color: str
    ) -> None:
        """Draw button in active state (filled background, dark text).

        Args:
            painter: QPainter instance
            rect: Button rectangle
            accent_color: Hex color for background
        """
        # Fill background with accent color
        bg_color = Colors.to_qcolor(accent_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 6, 6)

        # Draw border
        border_pen = QPen(bg_color, 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # Draw text in dark color for contrast
        painter.setPen(Colors.to_qcolor(BG_PRIMARY))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

    def _draw_normal_button(
        self, painter: QPainter, rect: QRect, accent_color: str
    ) -> None:
        """Draw button in normal state (dark background, colored border/text).

        Args:
            painter: QPainter instance
            rect: Button rectangle
            accent_color: Hex color for border and text
        """
        # Draw dark background
        bg_color = Colors.to_qcolor(BG_TERTIARY)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 6, 6)

        # Draw colored border
        border_pen = QPen(Colors.to_qcolor(accent_color), 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # Draw colored text
        painter.setPen(Colors.to_qcolor(accent_color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

    def _draw_disabled_button(self, painter: QPainter, rect: QRect) -> None:
        """Draw button in disabled state (gray, low opacity).

        Args:
            painter: QPainter instance
            rect: Button rectangle
        """
        # Draw dark background
        bg_color = Colors.to_qcolor(BG_TERTIARY)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 6, 6)

        # Draw gray border
        border_color = QColor("#3D4450")  # BG_BORDER
        border_pen = QPen(border_color, 2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # Draw gray text
        painter.setPen(Colors.to_qcolor(TEXT_DISABLED))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


__all__ = [
    "RallyButton",
    "BUTTON_TYPE_RALLY_START",
    "BUTTON_TYPE_SERVER_WINS",
    "BUTTON_TYPE_RECEIVER_WINS",
    "BUTTON_TYPE_UNDO",
]
