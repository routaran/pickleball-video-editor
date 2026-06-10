"""
Responsive layout management for the Pickleball Video Editor.

Provides a LayoutMode enum and ResponsiveManager class that evaluates window
dimensions against the design-system breakpoint tokens defined in
``src/ui/styles/fonts.py`` and emits a signal when the active layout mode
changes.

Breakpoint tokens are defined once in fonts.py and imported here — values are
NOT duplicated in this module.
"""

from enum import Enum, auto

from PyQt6.QtCore import QObject, QSize, pyqtSignal

from src.ui.styles.fonts import ASPECT_ULTRAWIDE, BREAK_COMPACT, BREAK_ULTRA_COMPACT

__all__ = ["LayoutMode", "ResponsiveManager"]


class LayoutMode(Enum):
    """Layout mode resolved from the current window dimensions.

    Precedence order (highest wins):

    1. ULTRAWIDE     — ``width / height >= ASPECT_ULTRAWIDE`` (2.0).
                       A 3840x1080 window is ULTRAWIDE regardless of width.
    2. ULTRA_COMPACT — ``width < BREAK_ULTRA_COMPACT`` (800 px).
    3. COMPACT       — ``width < BREAK_COMPACT`` (1000 px).
    4. NORMAL        — all other windows.
    """

    ULTRA_COMPACT = auto()  # width < 800 px
    COMPACT = auto()        # 800 <= width < 1000 px, aspect < 2.0
    NORMAL = auto()         # width >= 1000 px, aspect < 2.0
    ULTRAWIDE = auto()      # width / height >= 2.0


class ResponsiveManager(QObject):
    """Evaluates window dimensions and emits ``mode_changed`` when the mode changes.

    Thresholds are read from ``src/ui/styles/fonts.py`` breakpoint tokens:
    ``BREAK_COMPACT``, ``BREAK_ULTRA_COMPACT``, and ``ASPECT_ULTRAWIDE``.

    Typical usage inside a QWidget::

        class MainWindow(QMainWindow):
            def __init__(self) -> None:
                super().__init__()
                self._responsive = ResponsiveManager(parent=self)
                self._responsive.mode_changed.connect(self._on_layout_changed)

            def resizeEvent(self, event) -> None:
                self._responsive.evaluate(event.size())
                super().resizeEvent(event)

            def _on_layout_changed(self, mode: LayoutMode) -> None:
                ...

    ``evaluate()`` is idempotent for the same size and only emits when the
    resolved mode actually changes, so it is safe to call on every resize
    event without debouncing.
    """

    #: Emitted with the new mode whenever ``evaluate()`` produces a mode
    #: different from the previous call.  Not emitted on the first call until
    #: the mode is established (it is emitted on that first call too).
    mode_changed = pyqtSignal(LayoutMode)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_mode: LayoutMode | None = None

    @property
    def current_mode(self) -> LayoutMode | None:
        """The most-recently evaluated LayoutMode, or None before the first call."""
        return self._current_mode

    def evaluate(self, size: QSize) -> LayoutMode:
        """Compute the LayoutMode for *size* and emit ``mode_changed`` if changed.

        Precedence (highest to lowest priority):

        - ``width / height >= ASPECT_ULTRAWIDE`` → :attr:`LayoutMode.ULTRAWIDE`
        - ``width < BREAK_ULTRA_COMPACT``        → :attr:`LayoutMode.ULTRA_COMPACT`
        - ``width < BREAK_COMPACT``              → :attr:`LayoutMode.COMPACT`
        - otherwise                              → :attr:`LayoutMode.NORMAL`

        A zero-height window skips the aspect check (avoids division by zero)
        and falls through to the width checks.

        Args:
            size: Current widget size to evaluate.

        Returns:
            The resolved :class:`LayoutMode` for the given size.
        """
        width = size.width()
        height = size.height()

        if height > 0 and (width / height) >= ASPECT_ULTRAWIDE:
            mode = LayoutMode.ULTRAWIDE
        elif width < BREAK_ULTRA_COMPACT:
            mode = LayoutMode.ULTRA_COMPACT
        elif width < BREAK_COMPACT:
            mode = LayoutMode.COMPACT
        else:
            mode = LayoutMode.NORMAL

        if mode is not self._current_mode:
            self._current_mode = mode
            self.mode_changed.emit(mode)

        return mode
