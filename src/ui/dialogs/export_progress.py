"""Export Progress dialog for FFmpeg video encoding with background threading.

This module provides the ExportProgressDialog class, which shows progress during
FFmpeg video export operations. It runs encoding in a background thread to prevent
UI blocking and supports cancellation.

Visual Design:
- Progress header with spinning indicator during encoding
- Progress bar showing encoding completion percentage
- Status label showing current operation phase
- Cancel button to abort encoding
- Success/error state display on completion

Dialog Dimensions:
- Min width: 500px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.1)
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.output.ffmpeg_exporter import FFmpegExporter

from src.ui.styles.colors import (
    ACTION_DANGER,
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    PRIMARY_ACTION,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.styles.fonts import (
    RADIUS_XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    Fonts,
)


@dataclass
class ExportProgressResult:
    """Result from export progress dialog.

    Attributes:
        success: True if export completed successfully
        output_path: Path to exported file if successful, None otherwise
        error_message: Error description if failed, None otherwise
        cancelled: True if user cancelled the export
    """

    success: bool
    output_path: Path | None
    error_message: str | None
    cancelled: bool


class FFmpegWorker(QThread):
    """Background worker for FFmpeg export operations.

    Runs FFmpeg encoding in a separate thread and emits progress signals.
    Supports cancellation via the cancel() method.

    Signals:
        progress_updated: Emitted with progress percentage (0-100)
        status_changed: Emitted with current status message
        export_completed: Emitted with output path on success
        export_failed: Emitted with error message on failure
    """

    progress_updated = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    export_completed = pyqtSignal(Path)
    export_failed = pyqtSignal(str)

    def __init__(
        self,
        exporter: "FFmpegExporter",
        output_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the FFmpeg worker.

        Args:
            exporter: FFmpegExporter instance configured with segments
            output_path: Destination path for output MP4
            parent: Parent QObject for memory management
        """
        super().__init__(parent)
        self.exporter = exporter
        self.output_path = output_path
        self._cancelled = False
        self._process: subprocess.Popen[str] | None = None

    def run(self) -> None:
        """Execute FFmpeg export in background thread."""
        ass_path: Path | None = None
        try:
            self.status_changed.emit("Generating subtitles...")

            # Generate ASS subtitle file
            ass_path = self.exporter._write_ass_file(self.output_path)

            if self._cancelled:
                self._cleanup_files(ass_path)
                return

            self.status_changed.emit("Encoding video...")
            self.progress_updated.emit(5)

            # Run FFmpeg with progress reporting
            success = self._run_ffmpeg_with_progress(ass_path)

            if self._cancelled:
                self._cleanup_files(ass_path, self.output_path)
                return

            if success:
                # Clean up temp ASS file on success
                self._cleanup_files(ass_path)
                self.progress_updated.emit(100)
                self.export_completed.emit(self.output_path)
            else:
                # Clean up temp files on failure
                self._cleanup_files(ass_path, self.output_path)
                self.export_failed.emit("FFmpeg encoding failed")

        except Exception as e:
            # Clean up temp files on exception
            if ass_path is not None:
                self._cleanup_files(ass_path, self.output_path)
            if not self._cancelled:
                self.export_failed.emit(str(e))

    def _run_ffmpeg_with_progress(self, ass_path: Path) -> bool:
        """Run FFmpeg with progress parsing.

        Args:
            ass_path: Path to ASS subtitle file

        Returns:
            True if encoding succeeded, False otherwise

        Raises:
            Exception: If FFmpeg process fails unexpectedly
        """
        from src.output.hardware_detect import get_optimal_config

        # Get optimal encoder configuration
        config = get_optimal_config()

        # Build filter complex and get the correct audio output label
        filter_complex, audio_label = self.exporter._build_filter_complex(ass_path)

        # Build ffmpeg command with progress output
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-progress", "pipe:1",
            "-i", str(self.exporter.video_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", audio_label,
            "-fps_mode", "cfr",
            "-c:v", config.codec,
            "-preset", config.preset,
            *config.rate_control,
            *config.extra_opts,
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(self.output_path),
        ]

        # Calculate total expected duration for progress calculation
        total_duration = self._calculate_total_duration()

        try:
            # Use start_new_session on POSIX for proper process group control
            # This allows killing the entire process tree on cancel
            use_new_session = sys.platform != "win32"

            self._process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # Capture for logging
                text=True,
                start_new_session=use_new_session,
            )

            # Parse progress output
            if self._process.stdout:
                for line in self._process.stdout:
                    if self._cancelled:
                        self._terminate_process()
                        return False

                    # Parse out_time_us from progress output (FFmpeg outputs microseconds)
                    if line.startswith("out_time_us="):
                        try:
                            time_us = int(line.split("=")[1].strip())
                            if total_duration > 0:
                                # Convert microseconds to seconds and calculate progress
                                time_sec = time_us / 1_000_000
                                # Map 5-95% to encoding phase
                                progress = int(5 + (time_sec / total_duration) * 90)
                                progress = min(95, max(5, progress))
                                self.progress_updated.emit(progress)
                        except (ValueError, IndexError):
                            pass

                    # Check for completion
                    if line.startswith("progress=end"):
                        break

            # Wait for process to complete and capture stderr
            _, stderr = self._process.communicate(timeout=30)
            return_code = self._process.returncode
            self._process = None

            # Log stderr for debugging (not surfaced to UI)
            if stderr and stderr.strip():
                for line in stderr.strip().split("\n"):
                    logger.debug("ffmpeg: %s", line)
                if return_code != 0:
                    logger.error("FFmpeg failed with code %d. Stderr:\n%s", return_code, stderr)

            return return_code == 0

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg process timed out during communicate()")
            self._terminate_process()
            raise
        except Exception:
            self._terminate_process()
            raise

    def _calculate_total_duration(self) -> float:
        """Calculate total output duration from segments.

        Returns:
            Total duration in seconds
        """
        total = 0.0
        for segment in self.exporter.segments:
            in_frame = segment["in"]
            out_frame = segment["out"]
            duration = (out_frame - in_frame) / self.exporter.fps
            total += duration

        # Add game completion extension if applicable
        if (
            self.exporter.game_completion is not None
            and self.exporter.game_completion.is_completed
        ):
            total += self.exporter.game_completion.extension_seconds

        return total

    def _cleanup_files(self, *paths: Path) -> None:
        """Remove temporary/partial files after cancellation.

        Args:
            *paths: File paths to remove if they exist
        """
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    def _terminate_process(self) -> None:
        """Terminate the FFmpeg process and clean up.

        Uses SIGTERM first, then SIGKILL if process doesn't terminate.
        On POSIX with start_new_session, kills entire process group.
        """
        if self._process is None:
            return

        try:
            if sys.platform != "win32":
                # Kill entire process group on POSIX
                os.killpg(self._process.pid, signal.SIGTERM)
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Process didn't terminate, force kill
                    logger.warning("FFmpeg didn't terminate, force killing")
                    os.killpg(self._process.pid, signal.SIGKILL)
                    self._process.wait(timeout=2)
            else:
                # Windows: terminate parent process
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg didn't terminate, force killing")
                    self._process.kill()
                    self._process.wait(timeout=2)
        except (OSError, ProcessLookupError) as e:
            logger.debug("Error terminating ffmpeg process: %s", e)
        finally:
            self._process = None

    def cancel(self) -> None:
        """Request cancellation of the export.

        Signals the worker to stop and terminates the FFmpeg process if running.
        """
        self._cancelled = True
        self._terminate_process()


class ExportProgressDialog(QDialog):
    """Non-modal dialog showing FFmpeg export progress.

    Displays a progress bar and status messages during video encoding.
    Runs FFmpeg in a background thread to prevent UI blocking.
    Supports cancellation via a Cancel button. Non-modal to allow
    continued interaction with the main application during export.

    Signals:
        export_finished: Emitted when export completes (success, output_path, error_message)
        export_cancelled_signal: Emitted when user cancels the export

    Example:
        >>> dialog = ExportProgressDialog(
        ...     exporter=ffmpeg_exporter,
        ...     output_path=Path("/home/user/Videos/match.mp4"),
        ...     parent=main_window
        ... )
        >>> dialog.export_finished.connect(on_export_done)
        >>> dialog.export_cancelled_signal.connect(on_export_cancelled)
        >>> dialog.show()  # Non-blocking
    """

    # Signals for non-modal operation
    export_finished = pyqtSignal(bool, Path, str)  # (success, output_path, error_message)
    export_cancelled_signal = pyqtSignal()

    def __init__(
        self,
        exporter: "FFmpegExporter",
        output_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Export Progress dialog.

        Args:
            exporter: FFmpegExporter instance with configured segments
            output_path: Destination path for output MP4
            parent: Parent widget for dialog positioning
        """
        super().__init__(parent)
        self.setObjectName("exportProgressDialog")

        self._exporter = exporter
        self._output_path = output_path
        self._result: ExportProgressResult | None = None
        self._worker: FFmpegWorker | None = None

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        self.setWindowTitle("Exporting Video")
        self.setModal(False)  # Non-modal to allow continued work
        self.setMinimumWidth(500)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACE_MD)

        # Title
        self._title_label = QLabel("Exporting Video")
        self._title_label.setFont(Fonts.dialog_title())
        self._title_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        # Minimize button
        self._minimize_btn = QPushButton("_")
        self._minimize_btn.setObjectName("minimize_button")
        self._minimize_btn.setFixedSize(28, 28)
        self._minimize_btn.setToolTip("Minimize to continue working")
        self._minimize_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self._minimize_btn)

        layout.addLayout(header_layout)

        # Status label
        self._status_label = QLabel("Preparing export...")
        self._status_label.setFont(Fonts.label())
        self._status_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(self._status_label)

        layout.addSpacing(SPACE_SM)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        layout.addWidget(self._progress_bar)

        layout.addSpacing(SPACE_XL)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFont(Fonts.button_other())
        self._cancel_btn.setMinimumHeight(40)
        self._cancel_btn.setObjectName("cancel_button")
        self._cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self._cancel_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QProgressBar {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                text-align: center;
                color: {TEXT_PRIMARY};
                min-height: 24px;
            }}

            QProgressBar::chunk {{
                background-color: {TEXT_ACCENT};
                border-radius: 3px;
            }}

            QPushButton#cancel_button {{
                background-color: {BG_TERTIARY};
                border: 2px solid {BG_BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: 8px 24px;
                min-width: 100px;
            }}

            QPushButton#cancel_button:hover {{
                border-color: {ACTION_DANGER};
                color: {ACTION_DANGER};
            }}

            QPushButton#minimize_button {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                font-weight: bold;
            }}

            QPushButton#minimize_button:hover {{
                background-color: {PRIMARY_ACTION};
            }}
        """)

    def showEvent(self, event) -> None:
        """Handle dialog show event - start export worker.

        Guards against duplicate worker creation if showEvent is triggered
        multiple times (e.g., minimize/restore).
        """
        super().showEvent(event)

        # Only start worker once
        if self._worker is not None:
            return

        # Start worker thread
        self._worker = FFmpegWorker(
            exporter=self._exporter,
            output_path=self._output_path,
            parent=self,
        )

        # Connect signals
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.export_completed.connect(self._on_export_completed)
        self._worker.export_failed.connect(self._on_export_failed)

        # Start encoding
        self._worker.start()

    def _on_progress_updated(self, progress: int) -> None:
        """Handle progress update from worker.

        Args:
            progress: Progress percentage (0-100)
        """
        self._progress_bar.setValue(progress)

    def _on_status_changed(self, status: str) -> None:
        """Handle status message from worker.

        Args:
            status: Status message to display
        """
        self._status_label.setText(status)

    def _on_export_completed(self, output_path: Path) -> None:
        """Handle successful export completion.

        Args:
            output_path: Path to the exported file
        """
        self._result = ExportProgressResult(
            success=True,
            output_path=output_path,
            error_message=None,
            cancelled=False,
        )
        self.export_finished.emit(True, output_path, "")
        self.close()

    def _on_export_failed(self, error_message: str) -> None:
        """Handle export failure.

        Args:
            error_message: Description of the error
        """
        self._result = ExportProgressResult(
            success=False,
            output_path=None,
            error_message=error_message,
            cancelled=False,
        )
        self.export_finished.emit(False, Path(), error_message)
        self.close()

    def _on_cancel(self) -> None:
        """Handle Cancel button click."""
        if self._worker is not None:
            self._status_label.setText("Cancelling...")
            self._cancel_btn.setEnabled(False)
            self._worker.cancel()

            # Wait for worker to finish with timeout
            self._worker.wait(5000)  # 5 second timeout

            # Force terminate if still running
            if self._worker.isRunning():
                logger.warning("Worker still running after cancel timeout, force terminating")
                self._worker.terminate()
                self._worker.wait(2000)  # Brief wait for termination

        self._result = ExportProgressResult(
            success=False,
            output_path=None,
            error_message=None,
            cancelled=True,
        )
        self.export_cancelled_signal.emit()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.

        If export is still running, trigger cancellation instead of closing.

        Args:
            event: Close event from Qt
        """
        if self._worker is not None and self._worker.isRunning():
            self._on_cancel()
            event.ignore()
        else:
            super().closeEvent(event)

    def exec_and_get_result(self) -> ExportProgressResult:
        """Show the dialog and return the export result.

        This is a convenience method that combines exec() and result extraction.

        Returns:
            ExportProgressResult with success status, path, and error info

        Example:
            >>> dialog = ExportProgressDialog(exporter, output_path, parent=self)
            >>> result = dialog.exec_and_get_result()
            >>> if result.success:
            ...     print(f"Exported to {result.output_path}")
        """
        self.exec()

        if self._result is None:
            # Dialog was closed without a result (shouldn't happen)
            return ExportProgressResult(
                success=False,
                output_path=None,
                error_message="Dialog closed unexpectedly",
                cancelled=True,
            )

        return self._result


__all__ = [
    "ExportProgressDialog",
    "ExportProgressResult",
    "FFmpegWorker",
]
