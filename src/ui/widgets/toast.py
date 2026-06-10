"""Toast notification widget for non-blocking feedback messages.

Provides a modern toast notification system with:
- Auto-dismiss after configurable duration (default 4 seconds)
- Smooth fade in/out animations with slide down/up effects
- Color-coded left accent border based on message type
- Support for stacking multiple toasts
- Manual dismiss button

Toast types:
- SUCCESS: Green accent for successful operations
- INFO: Blue accent for informational messages
- WARNING: Amber accent for warnings
- ERROR: Red accent for errors

Example usage:
    # Show a success toast
    ToastManager.show_success(parent_widget, "Rally saved successfully")

    # Show a warning with custom duration
    ToastManager.show_warning(parent_widget, "Video file is large", duration_ms=6000)

    # Manual control
    toast = Toast("Custom message", ToastType.ERROR, parent=window)
    toast.show_toast()
"""

from enum import Enum

from PyQt6.QtCore import QPropertyAnimation, QRect, QSize, Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from src.ui.styles.colors import (
    ACTION_DANGER,
    ACTION_INFO,
    ACTION_SUCCESS,
    ACTION_WARNING,
    BG_SECONDARY,
    BORDER_COLOR,
    DANGER_TEXT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import SIZE_BODY, Fonts
from src.ui.styles.icons import icon as make_icon, pixmap as make_pixmap


class ToastType(Enum):
    """Toast notification type with corresponding color and icon."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Toast(QFrame):
    """A self-contained toast notification widget.

    Displays a temporary message with an icon, text, and dismiss button.
    Automatically fades in/out with slide animations and auto-dismisses
    after the specified duration.

    Signals:
        closed: Emitted when the toast is dismissed (either auto or manual)
    """

    closed = pyqtSignal()

    # Toast configuration
    TOAST_WIDTH = 320
    TOAST_MIN_HEIGHT = 48
    ACCENT_BORDER_WIDTH = 4
    ANIMATION_DURATION_IN = 200  # milliseconds
    ANIMATION_DURATION_OUT = 150  # milliseconds

    # Lucide icon names for each toast type
    _ICON_NAMES = {
        ToastType.SUCCESS: "circle-check",
        ToastType.INFO: "info",
        ToastType.WARNING: "triangle-alert",
        ToastType.ERROR: "circle-x",
    }

    # Icon stroke colors — ERROR uses DANGER_TEXT (softer, informational)
    # rather than the full ACTION_DANGER used for the destructive-action border.
    _ICON_COLORS = {
        ToastType.SUCCESS: ACTION_SUCCESS,
        ToastType.INFO: ACTION_INFO,
        ToastType.WARNING: ACTION_WARNING,
        ToastType.ERROR: DANGER_TEXT,
    }

    # Accent colors for left border
    _ACCENT_COLORS = {
        ToastType.SUCCESS: ACTION_SUCCESS,
        ToastType.INFO: ACTION_INFO,
        ToastType.WARNING: ACTION_WARNING,
        ToastType.ERROR: ACTION_DANGER,
    }

    def __init__(
        self,
        message: str,
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 4000,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the toast notification.

        Args:
            message: The message text to display
            toast_type: Type of toast (SUCCESS, INFO, WARNING, ERROR)
            duration_ms: Auto-dismiss duration in milliseconds (0 = no auto-dismiss)
            parent: Parent widget (required for positioning)
        """
        super().__init__(parent)

        self.message = message
        self.toast_type = toast_type
        self.duration_ms = duration_ms

        # Animation state
        self._fade_animation: QPropertyAnimation | None = None
        self._slide_animation: QPropertyAnimation | None = None
        self._auto_dismiss_timer: QTimer | None = None

        self._setup_ui()
        self._apply_styles()

        # Never steal keyboard focus from the main window when toasts appear.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Start hidden (will animate in when show_toast() is called)
        self.setWindowOpacity(0.0)
        self.hide()

    def _setup_ui(self) -> None:
        """Set up the toast widget layout and child widgets."""
        # Configure frame properties
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # Width is set dynamically in show_toast() based on parent width.
        # Apply the fallback minimum now so adjustSize() has a sensible floor.
        self.setFixedWidth(self.TOAST_WIDTH)
        self.setMinimumHeight(self.TOAST_MIN_HEIGHT)

        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)

        # Icon label — Lucide SVG pixmap, aligned to top for multi-line messages
        self.icon_label = QLabel()
        self.icon_label.setObjectName("toastIcon")
        self.icon_label.setPixmap(
            make_pixmap(
                self._ICON_NAMES[self.toast_type],
                self._ICON_COLORS[self.toast_type],
                20,
            )
        )
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        # Message label
        self.message_label = QLabel(self.message)
        self.message_label.setObjectName("toastMessage")
        self.message_label.setWordWrap(True)
        message_font = Fonts.body(SIZE_BODY)
        self.message_label.setFont(message_font)
        layout.addWidget(self.message_label, 1, Qt.AlignmentFlag.AlignVCenter)

        # Dismiss button — Lucide "x" icon, aligned to top for multi-line messages
        self.dismiss_button = QPushButton()
        self.dismiss_button.setObjectName("toastDismiss")
        self.dismiss_button.setIcon(make_icon("x", TEXT_SECONDARY, 14))
        self.dismiss_button.setIconSize(QSize(14, 14))
        self.dismiss_button.setFixedSize(24, 24)
        self.dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_button.clicked.connect(self.dismiss)
        layout.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignTop)

        # Set object name for styling
        self.setObjectName(f"toast_{self.toast_type.value}")

    def _apply_styles(self) -> None:
        """Apply QSS styles to the toast widget."""
        accent_color = self._ACCENT_COLORS[self.toast_type]

        stylesheet = f"""
            QFrame#toast_{self.toast_type.value} {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-left: {self.ACCENT_BORDER_WIDTH}px solid {accent_color};
                border-radius: 4px;
            }}

            QLabel#toastIcon {{
                color: {accent_color};
                background: transparent;
                border: none;
            }}

            QLabel#toastMessage {{
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}

            QPushButton#toastDismiss {{
                background: transparent;
                border: none;
                color: {TEXT_SECONDARY};
                padding: 0px;
            }}

            QPushButton#toastDismiss:hover {{
                color: {TEXT_PRIMARY};
            }}
        """

        self.setStyleSheet(stylesheet)

    def show_toast(self) -> None:
        """Show the toast with fade-in and slide-down animation."""
        if not self.parent():
            # Cannot position without parent
            self.show()
            return

        # Position at top-center of parent
        parent_widget = self.parent()
        if not isinstance(parent_widget, QWidget):
            self.show()
            return

        # Dynamic width: one-third of parent, clamped to [320, 480] px.
        # Reapply setFixedWidth here so word-wrap reflows before adjustSize().
        toast_width = min(max(320, parent_widget.width() // 3), 480)
        self.setFixedWidth(toast_width)

        # Calculate actual height based on content (allow for multi-line text)
        self.adjustSize()
        toast_height = self.sizeHint().height()

        parent_width = parent_widget.width()
        x = (parent_width - toast_width) // 2
        y_start = -toast_height  # Start above visible area
        y_end = 16  # Final position (16px from top)

        # Set starting position
        self.setGeometry(x, y_start, toast_width, toast_height)
        self.show()

        # Fade in animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(self.ANIMATION_DURATION_IN)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)

        # Slide down animation
        self._slide_animation = QPropertyAnimation(self, b"geometry")
        self._slide_animation.setDuration(self.ANIMATION_DURATION_IN)
        self._slide_animation.setStartValue(
            QRect(x, y_start, toast_width, toast_height)
        )
        self._slide_animation.setEndValue(
            QRect(x, y_end, toast_width, toast_height)
        )

        # Start animations
        self._fade_animation.start()
        self._slide_animation.start()

        # Set up auto-dismiss timer
        if self.duration_ms > 0:
            self._auto_dismiss_timer = QTimer(self)
            self._auto_dismiss_timer.setSingleShot(True)
            self._auto_dismiss_timer.timeout.connect(self.dismiss)
            self._auto_dismiss_timer.start(self.duration_ms)

    @pyqtSlot()
    def dismiss(self) -> None:
        """Dismiss the toast with fade-out and slide-up animation."""
        # Stop auto-dismiss timer if running
        if self._auto_dismiss_timer and self._auto_dismiss_timer.isActive():
            self._auto_dismiss_timer.stop()

        if not self.parent():
            self.closed.emit()
            self.deleteLater()
            return

        parent_widget = self.parent()
        if not isinstance(parent_widget, QWidget):
            self.closed.emit()
            self.deleteLater()
            return

        # Get current position and size
        current_rect = self.geometry()
        x = current_rect.x()
        y_start = current_rect.y()
        toast_width = current_rect.width()
        toast_height = current_rect.height()
        y_end = -toast_height  # Slide up out of view

        # Fade out animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(self.ANIMATION_DURATION_OUT)
        self._fade_animation.setStartValue(self.windowOpacity())
        self._fade_animation.setEndValue(0.0)

        # Slide up animation
        self._slide_animation = QPropertyAnimation(self, b"geometry")
        self._slide_animation.setDuration(self.ANIMATION_DURATION_OUT)
        self._slide_animation.setStartValue(current_rect)
        self._slide_animation.setEndValue(
            QRect(x, y_end, toast_width, toast_height)
        )

        # Clean up and emit signal when animation finishes
        self._slide_animation.finished.connect(self._on_dismiss_finished)

        # Start animations
        self._fade_animation.start()
        self._slide_animation.start()

    @pyqtSlot()
    def _on_dismiss_finished(self) -> None:
        """Handle cleanup after dismiss animation completes."""
        self.closed.emit()
        self.deleteLater()


class ToastManager:
    """Manages toast notifications and handles stacking.

    Provides static methods for showing toast notifications with automatic
    positioning and stacking. Multiple toasts will be stacked vertically
    with appropriate spacing.

    Note: Currently shows one toast at a time. Stacking can be implemented
    by tracking active toasts and adjusting y-positions accordingly.
    """

    # Track active toasts for stacking (future enhancement)
    _active_toasts: list[Toast] = []

    @staticmethod
    def show_toast(
        parent: QWidget,
        message: str,
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 4000,
    ) -> Toast:
        """Show a toast notification.

        Args:
            parent: Parent widget for positioning
            message: Message text to display
            toast_type: Type of toast (SUCCESS, INFO, WARNING, ERROR)
            duration_ms: Auto-dismiss duration in milliseconds

        Returns:
            The created Toast widget
        """
        toast = Toast(message, toast_type, duration_ms, parent)

        # Register toast for tracking
        ToastManager._active_toasts.append(toast)
        toast.closed.connect(lambda: ToastManager._remove_toast(toast))

        # Show the toast
        toast.show_toast()

        return toast

    @staticmethod
    def show_success(parent: QWidget, message: str, duration_ms: int = 4000) -> Toast:
        """Show a success toast notification.

        Args:
            parent: Parent widget for positioning
            message: Success message to display
            duration_ms: Auto-dismiss duration in milliseconds

        Returns:
            The created Toast widget
        """
        return ToastManager.show_toast(parent, message, ToastType.SUCCESS, duration_ms)

    @staticmethod
    def show_info(parent: QWidget, message: str, duration_ms: int = 4000) -> Toast:
        """Show an info toast notification.

        Args:
            parent: Parent widget for positioning
            message: Info message to display
            duration_ms: Auto-dismiss duration in milliseconds

        Returns:
            The created Toast widget
        """
        return ToastManager.show_toast(parent, message, ToastType.INFO, duration_ms)

    @staticmethod
    def show_warning(parent: QWidget, message: str, duration_ms: int = 4000) -> Toast:
        """Show a warning toast notification.

        Args:
            parent: Parent widget for positioning
            message: Warning message to display
            duration_ms: Auto-dismiss duration in milliseconds

        Returns:
            The created Toast widget
        """
        return ToastManager.show_toast(parent, message, ToastType.WARNING, duration_ms)

    @staticmethod
    def show_error(parent: QWidget, message: str, duration_ms: int = 4000) -> Toast:
        """Show an error toast notification.

        Args:
            parent: Parent widget for positioning
            message: Error message to display
            duration_ms: Auto-dismiss duration in milliseconds

        Returns:
            The created Toast widget
        """
        return ToastManager.show_toast(parent, message, ToastType.ERROR, duration_ms)

    @staticmethod
    def _remove_toast(toast: Toast) -> None:
        """Remove a toast from the active list.

        Args:
            toast: Toast widget to remove
        """
        if toast in ToastManager._active_toasts:
            ToastManager._active_toasts.remove(toast)


__all__ = ["Toast", "ToastType", "ToastManager"]
