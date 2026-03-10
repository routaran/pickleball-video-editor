"""Application-level export manager for independent FFmpeg exports.

Manages ExportProgressDialog instances independently of MainWindow lifecycle.
Exports survive MainWindow destruction (e.g., returning to menu) and can
run concurrently across sessions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

if TYPE_CHECKING:
    from src.output.ffmpeg_exporter import FFmpegExporter
    from src.ui.dialogs.export_progress import ExportProgressDialog

logger = logging.getLogger(__name__)

__all__ = ["ExportManager"]


class ExportManager(QObject):
    """Manages FFmpeg export dialogs independently of MainWindow.

    Created once in main() and passed to each MainWindow instance.
    Export dialogs are top-level windows (parent=None) that persist
    across MainWindow lifecycles.

    Signals:
        export_completed: Emitted with output path on successful export
        export_failed: Emitted with error message on failed export
        export_cancelled: Emitted when user cancels an export
    """

    export_completed = pyqtSignal(Path)
    export_failed = pyqtSignal(str)
    export_cancelled = pyqtSignal()
    all_exports_finished = pyqtSignal()  # Emitted when last active export ends

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active_exports: list[ExportProgressDialog] = []

    def start_export(
        self,
        exporter: FFmpegExporter,
        output_path: Path,
    ) -> ExportProgressDialog:
        """Start a new export with a top-level progress dialog.

        Args:
            exporter: Configured FFmpegExporter instance
            output_path: Destination path for output MP4

        Returns:
            The ExportProgressDialog instance
        """
        from src.ui.dialogs.export_progress import ExportProgressDialog

        dialog = ExportProgressDialog(
            exporter=exporter,
            output_path=output_path,
            parent=None,
        )
        dialog.setWindowTitle(f"Exporting: {output_path.name}")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._active_exports.append(dialog)
        dialog.export_finished.connect(
            lambda s, p, e: self._on_finished(dialog, s, p, e)
        )
        dialog.export_cancelled_signal.connect(
            lambda: self._on_cancelled(dialog)
        )
        dialog.show()
        return dialog

    def has_active_exports(self) -> bool:
        """Check if any exports are currently running."""
        return len(self._active_exports) > 0

    def cancel_all_exports(self) -> None:
        """Cancel all active exports.

        Blocks signals during batch cancellation to prevent premature
        all_exports_finished emission between individual dialog closes.
        """
        self.blockSignals(True)
        for dialog in list(self._active_exports):
            dialog.close()
        self._active_exports.clear()
        self.blockSignals(False)
        self.all_exports_finished.emit()

    def _on_finished(
        self,
        dialog: "ExportProgressDialog",
        success: bool,
        output_path: Path,
        error_message: str,
    ) -> None:
        """Handle export completion."""
        if dialog in self._active_exports:
            self._active_exports.remove(dialog)

        if success:
            logger.info("Export completed: %s", output_path)
            self.export_completed.emit(output_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path.parent)))
        else:
            logger.error("Export failed: %s", error_message)
            self.export_failed.emit(error_message)

        dialog.deleteLater()

        if not self._active_exports:
            self.all_exports_finished.emit()

    def _on_cancelled(self, dialog: "ExportProgressDialog") -> None:
        """Handle export cancellation."""
        if dialog in self._active_exports:
            self._active_exports.remove(dialog)

        logger.info("Export cancelled")
        self.export_cancelled.emit()
        dialog.deleteLater()

        if not self._active_exports:
            self.all_exports_finished.emit()
