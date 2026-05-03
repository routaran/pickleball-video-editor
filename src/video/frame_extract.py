"""Frame extraction utility for Pickleball Video Editor.

Provides a module-level helper that extracts a single video frame at a given
timestamp using ffmpeg.  This is the canonical frame-extraction primitive used
by both the SetupDialog calibration path and the FrameSelectorDialog slider.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QMessageBox, QWidget

__all__ = ["extract_frame_at"]

_log = logging.getLogger(__name__)


def extract_frame_at(
    video_path: Path,
    offset_s: float,
    parent_widget: QWidget | None = None,
) -> QPixmap | None:
    """Extract a single video frame at *offset_s* seconds and return it as a QPixmap.

    Uses ffmpeg to seek to *offset_s* and capture one JPEG frame into a
    temporary file, which is converted to a QPixmap and immediately deleted.

    LBYL guards:
    - If *video_path* does not exist the function logs a warning and returns
      ``None`` immediately (no modal shown).
    - If *offset_s* is negative it is clamped to 0.

    Error reporting behaviour depends on whether *parent_widget* is provided:
    - ``parent_widget`` is a ``QWidget``: error details are shown via
      ``QMessageBox.critical`` anchored to that widget.
    - ``parent_widget`` is ``None``: error details are written to the module
      logger at WARNING level and no modal is shown.  This is the intended mode
      for the slider-scrubbing path where a single bad seek must not spam
      modals.

    Args:
        video_path: Absolute path to the source video file.
        offset_s: Seek position in seconds.  Negative values are clamped to 0.
        parent_widget: Optional parent widget for ``QMessageBox`` dialogs.
            Pass ``None`` to suppress all modal error dialogs.

    Returns:
        A valid QPixmap on success, or ``None`` on any failure.
    """
    # LBYL: check file existence before attempting anything.
    if not video_path.exists():
        _log.warning(
            "extract_frame_at: video file does not exist: %s", video_path
        )
        return None

    # Clamp negative offset rather than propagating an invalid seek.
    if offset_s < 0:
        offset_s = 0.0

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    ffmpeg_cmd = [
        "ffmpeg",
        "-ss", str(offset_s),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(tmp_path),
        "-y",
    ]

    try:
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        _report_error(
            parent_widget,
            "ffmpeg Not Found",
            "ffmpeg is required for frame extraction.\n"
            "Install it with: sudo pacman -S ffmpeg",
        )
        return None
    except subprocess.TimeoutExpired:
        _report_error(
            parent_widget,
            "ffmpeg Timeout",
            "ffmpeg timed out while extracting the frame.",
        )
        return None

    if result.returncode != 0 or not tmp_path.exists():
        error_detail = result.stderr.strip() if result.stderr else "Unknown error"
        _report_error(
            parent_widget,
            "Frame Extraction Failed",
            f"ffmpeg could not extract a frame from the video:\n{error_detail}",
        )
        if tmp_path.exists():
            tmp_path.unlink()
        return None

    pixmap = QPixmap(str(tmp_path))
    tmp_path.unlink()  # Clean up temp file immediately after loading.

    if pixmap.isNull():
        _report_error(
            parent_widget,
            "Image Load Failed",
            "The extracted frame could not be loaded as an image.",
        )
        return None

    return pixmap


def _report_error(
    parent_widget: QWidget | None,
    title: str,
    message: str,
) -> None:
    """Show a modal critical dialog when *parent_widget* is set, else log a warning."""
    if parent_widget is not None:
        QMessageBox.critical(parent_widget, title, message)
    else:
        _log.warning("%s: %s", title, message)
