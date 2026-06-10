"""Icon infrastructure for the Pickleball Video Editor.

Loads vendored Lucide SVGs from ``resources/icons/``, recolors them by
substituting ``currentColor`` with the requested hex color, renders 1x and
2x pixmaps via ``PyQt6.QtSvg.QSvgRenderer``, and returns a ``QIcon`` with
both resolutions.  All results are cached by ``(name, color, size)`` so
repeated calls within a session cost nothing after the first render.

Public API::

    from src.ui.styles.icons import icon, pixmap

    button.setIcon(icon("play", color="#3DDC84", size=20))
    label.setPixmap(pixmap("trash-2", color="#EF5350", size=16))

No new pip dependencies are required.  ``PyQt6.QtSvg`` ships as part of the
standard PyQt6 distribution and is already present in the project environment.

Icon set
--------
Lucide (https://lucide.dev), ISC license.  See ``resources/icons/LICENSE``.
Vendored icons: skip-back, rewind, play, pause, fast-forward, skip-forward,
trash-2, triangle-alert, arrow-right, chevron-left, chevron-right,
circle-check, info, circle-x, x, folder-open.
"""

from functools import cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from src.ui.styles.colors import TEXT_PRIMARY

__all__ = ["icon", "pixmap"]


# ---------------------------------------------------------------------------
# Path resolution — robust regardless of process working directory
# ---------------------------------------------------------------------------

# src/ui/styles/icons.py  →  parent  → src/ui/styles/
#                         →  parent  → src/ui/
#                         →  parent  → src/
#                         →  parent  → project root
#                         →  resources/icons/
_ICONS_DIR: Path = (
    Path(__file__).parent   # src/ui/styles/
    .parent                 # src/ui/
    .parent                 # src/
    .parent                 # project root
    / "resources"
    / "icons"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@cache
def _svg_bytes(name: str, color: str) -> bytes:
    """Return SVG bytes for *name* with ``currentColor`` replaced by *color*.

    Cached by ``(name, color)`` so each (icon, color) combination is read
    from disk only once per process lifetime.

    Args:
        name:  Lucide icon name without the ``.svg`` extension (e.g. ``"play"``).
        color: CSS hex color string to substitute (e.g. ``"#F5F5F5"``).

    Returns:
        Modified SVG content as bytes, ready for ``QSvgRenderer``.

    Raises:
        FileNotFoundError: When the named SVG is absent from ``resources/icons/``.
    """
    svg_path = _ICONS_DIR / f"{name}.svg"
    if not svg_path.exists():
        available = sorted(p.stem for p in _ICONS_DIR.glob("*.svg"))
        raise FileNotFoundError(
            f"Icon '{name}' not found in {_ICONS_DIR}. "
            f"Available: {available}"
        )
    raw = svg_path.read_bytes()
    # Lucide SVGs use stroke="currentColor"; replace with the requested color.
    # The substitution is byte-level and case-sensitive — Lucide always writes
    # "currentColor" in exactly that casing, so no case-folding is needed.
    return raw.replace(b"currentColor", color.encode("ascii"))


def _render_to_pixmap(svg_data: bytes, px: int) -> QPixmap:
    """Render *svg_data* into a square *px* x *px* ``QPixmap``.

    Args:
        svg_data: SVG content as bytes (``currentColor`` already substituted).
        px:       Side length in physical pixels.

    Returns:
        Transparent-background ``QPixmap`` at the requested pixel size.
    """
    renderer = QSvgRenderer(QByteArray(svg_data))
    pm = QPixmap(QSize(px, px))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@cache
def pixmap(name: str, color: str = TEXT_PRIMARY, size: int = 20) -> QPixmap:
    """Return a 1x ``QPixmap`` for the named Lucide icon.

    Results are cached by ``(name, color, size)``.  The first call reads the
    SVG from disk and renders it; subsequent calls return the cached object.

    For HiDPI displays prefer :func:`icon`, which bundles both 1x and 2x
    resolutions and lets Qt select the right one automatically.

    Args:
        name:  Lucide icon name without the ``.svg`` extension, e.g. ``"play"``.
        color: Hex color applied to all strokes (default: ``TEXT_PRIMARY``).
        size:  Rendered side length in logical pixels (default: 20).

    Returns:
        A ``QPixmap`` at 1x device pixel ratio.

    Raises:
        FileNotFoundError: When the named SVG is not vendored in
        ``resources/icons/``.
    """
    svg_data = _svg_bytes(name, color)
    pm = _render_to_pixmap(svg_data, size)
    pm.setDevicePixelRatio(1.0)
    return pm


@cache
def icon(name: str, color: str = TEXT_PRIMARY, size: int = 20) -> QIcon:
    """Return a multi-resolution ``QIcon`` for the named Lucide icon.

    Renders the SVG at 1x (*size* x *size* logical pixels) and 2x
    (``2 * size`` physical pixels, ``devicePixelRatio = 2.0``) and adds
    both pixmaps to the returned ``QIcon``.  Qt picks the appropriate
    resolution at paint time based on the screen device pixel ratio.

    Results are cached by ``(name, color, size)`` — the first call renders
    both pixmaps; subsequent calls return the cached ``QIcon`` instantly.

    Args:
        name:  Lucide icon name without the ``.svg`` extension, e.g. ``"play"``.
        color: Hex color applied to all strokes (default: ``TEXT_PRIMARY``).
        size:  Logical pixel size of the icon (default: 20).  The 2x pixmap
               is rendered at ``2 * size`` physical pixels.

    Returns:
        A ``QIcon`` containing 1x and 2x pixmaps for automatic HiDPI support.

    Raises:
        FileNotFoundError: When the named SVG is not vendored in
        ``resources/icons/``.

    Example::

        button.setIcon(icon("play", color=RALLY_START, size=20))
        button.setIconSize(QSize(20, 20))
    """
    svg_data = _svg_bytes(name, color)

    pm_1x = _render_to_pixmap(svg_data, size)
    pm_1x.setDevicePixelRatio(1.0)

    pm_2x = _render_to_pixmap(svg_data, size * 2)
    pm_2x.setDevicePixelRatio(2.0)

    qi = QIcon()
    qi.addPixmap(pm_1x)
    qi.addPixmap(pm_2x)
    return qi
