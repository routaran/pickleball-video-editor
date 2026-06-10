"""Screen geometry helpers for responsive dialog and window sizing.

Provides fit_to_screen() which computes a clamped widget size as a fraction
of the available screen area and centers the widget on that screen.  It works
both before (pre-show, uses QGuiApplication.primaryScreen()) and after (post-
show, uses widget.screen()) the widget has been realized as a native window.
"""

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget


__all__ = ["fit_to_screen"]


def fit_to_screen(
    widget: QWidget,
    w_frac: float,
    h_frac: float,
    min_w: int,
    min_h: int,
    max_w: int,
    max_h: int,
) -> None:
    """Resize and center a widget relative to the available screen geometry.

    Computes target dimensions as a fraction of the screen's available
    geometry (excludes task-bars and docks), clamps them to [min, max] bounds,
    resizes the widget to the clamped size, then centers it on the screen.

    Uses ``widget.screen()`` when the widget already has a native handle (i.e.
    has been shown); falls back to ``QGuiApplication.primaryScreen()`` before
    the first show so dialogs are sized correctly on construction.

    Args:
        widget: The widget to resize and center.
        w_frac: Fraction of available screen width to target (0.0–1.0).
        h_frac: Fraction of available screen height to target (0.0–1.0).
        min_w: Minimum width in logical pixels.
        min_h: Minimum height in logical pixels.
        max_w: Maximum width in logical pixels.
        max_h: Maximum height in logical pixels.
    """
    screen = widget.screen()
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        # No screen available (e.g. headless tests) — use minimum sizes.
        widget.resize(min_w, min_h)
        return

    avail = screen.availableGeometry()

    clamped_w = max(min_w, min(max_w, int(avail.width() * w_frac)))
    clamped_h = max(min_h, min(max_h, int(avail.height() * h_frac)))

    widget.resize(clamped_w, clamped_h)

    # Center within the screen's available area (not the full monitor area so
    # the window does not appear under task-bars on single-screen setups).
    x = avail.x() + (avail.width() - clamped_w) // 2
    y = avail.y() + (avail.height() - clamped_h) // 2
    widget.move(x, y)
