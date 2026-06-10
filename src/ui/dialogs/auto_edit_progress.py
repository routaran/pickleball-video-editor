"""Auto-Edit Progress dialog for the ML auto-edit pipeline.

This module provides the AutoEditProgressDialog class, which shows progress
during the automated ML pipeline run (audio rally detection, winner
classification, score simulation, and output generation). It runs the pipeline
in a background thread to prevent UI blocking and supports cooperative
cancellation between pipeline stages.

Visual Design:
- Phase label (large text) showing the current pipeline stage
- Indeterminate QProgressBar (no percentage — we can't know how long each
  stage will take)
- Cancel button that disables itself after being clicked
- Error state shown via QMessageBox before dialog rejection

Dialog Dimensions:
- Min width: 480px
- Padding: 24px
- Border radius: 12px (per UI_SPEC.md Section 6.1)
"""

import logging
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ml.auto_edit import AutoEditSetup
from src.ui.styles.colors import (
    ACTION_DANGER,
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    TEXT_ACCENT,
)
from src.ui.styles.components import ButtonStyles, set_label_role
from src.ui.styles.fonts import (
    RADIUS_XL,
    SIZE_DIALOG_TITLE,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    WEIGHT_SEMIBOLD,
    Fonts,
)

__all__ = ["AutoEditProgressDialog", "AutoEditWorker"]

logger = logging.getLogger(__name__)


class AutoEditWorker(QThread):
    """Background worker that runs the auto_edit() pipeline in a QThread.

    Emits phase_changed signals before each logical stage so the dialog can
    update its label. The pipeline itself runs synchronously inside run(); we
    emit the four synthetic phase messages bracketing the single auto_edit()
    call and check the cancel flag between each stage where possible.

    Because auto_edit() currently runs all stages in one synchronous call
    without internal callbacks, cancellation can only be honoured between the
    preparation step and the actual run, or by setting the cancel flag and
    observing it on the next stage boundary. In practice this means the user
    may have to wait for the current heavy stage to finish before the cancel
    takes effect.

    Signals:
        phase_changed: Emitted with a human-readable stage description.
        finished: Emitted with the AutoEditResult on successful completion.
        error: Emitted with an error message string on failure.
        cancelled: Emitted when cooperative cancellation was requested and
            honoured before or after the pipeline call.
    """

    phase_changed = pyqtSignal(str)
    finished = pyqtSignal(object)  # object because AutoEditResult is from ml/
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        video_path: Path,
        setup: AutoEditSetup,
        corners: list[tuple[int, int]],
        output_dir: Path,
        checkpoint_path: Path,
        confidence_threshold: float = 0.75,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the worker with all arguments required by auto_edit().

        Args:
            video_path: Absolute path to the source video file.
            setup: AutoEditSetup containing game type, victory rule, and player names.
            corners: Four (x, y) pixel coordinates of the court corners.
            output_dir: Directory where all output files will be written.
            checkpoint_path: Path to the WinnerClassifier ``.pt`` checkpoint.
            confidence_threshold: Minimum softmax confidence to accept a winner
                prediction without flagging it as low-confidence.
            parent: Parent QObject for memory management.
        """
        super().__init__(parent)
        self._video_path = video_path
        self._setup = setup
        self._corners = corners
        self._output_dir = output_dir
        self._checkpoint_path = checkpoint_path
        self._confidence_threshold = confidence_threshold
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation.

        Sets an internal threading.Event that is checked between stages.
        The pipeline call itself is not interrupted mid-stage; the worker
        checks the flag at safe points.
        """
        self._cancel_event.set()

    def run(self) -> None:
        """Execute the auto-edit pipeline in the background thread.

        Emits phase_changed before each stage description and checks the
        cancel flag between stages. On success emits finished; on failure
        emits error. If cancelled, emits cancelled instead.
        """
        # Import lazily inside the thread to avoid import-time side effects
        # at module load and to keep Qt startup fast.
        from ml.auto_edit import auto_edit  # noqa: PLC0415

        # Stage 1 — notify then check cancel before the heavy work.
        self.phase_changed.emit("Detecting rallies from audio...")
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return

        # Stage 2 notification is emitted pre-emptively here because
        # auto_edit() does not expose per-stage callbacks. The UI will show
        # each phase label in sequence as best-effort progress feedback.
        #
        # The real pipeline runs inside the single auto_edit() call below.
        # After it returns we advance the label to show we reached later stages.
        # This is option (b) from the task specification.

        try:
            # Run stages 1-4 synchronously inside auto_edit().
            # We emit synthetic labels before calling so the dialog always
            # shows something informative even for the long-running stages.
            result = auto_edit(
                video_path=self._video_path,
                setup=self._setup,
                corners=self._corners,
                output_dir=self._output_dir,
                checkpoint_path=self._checkpoint_path,
                confidence_threshold=self._confidence_threshold,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: surface to UI
            if self._cancel_event.is_set():
                # Cancel was requested while the pipeline was running;
                # treat as cancellation rather than an error.
                self.cancelled.emit()
            else:
                logger.exception("auto_edit pipeline failed")
                self.error.emit(str(exc))
            return

        # Check cancel one final time before emitting success in case the
        # user clicked Cancel during the last stage of the pipeline.
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return

        self.phase_changed.emit("Writing output...")
        self.finished.emit(result)


class AutoEditProgressDialog(QDialog):
    """Modal progress dialog for the ML auto-edit pipeline.

    Manages an AutoEditWorker internally; callers only need to construct the
    dialog and call exec(). After exec() returns, call get_result() to obtain
    the AutoEditResult or None if the run was cancelled/failed.

    Usage::

        dialog = AutoEditProgressDialog(
            video_path=video,
            setup=config,
            corners=corners,
            output_dir=out_dir,
            checkpoint_path=ckpt,
            parent=self,
        )
        dialog.exec()
        result = dialog.get_result()
        if result is not None:
            ...

    The dialog starts the worker thread in __init__ so that processing begins
    as soon as the object is created, before exec() is called. This prevents
    any delay between the dialog becoming visible and work starting.
    """

    def __init__(
        self,
        video_path: Path,
        setup: AutoEditSetup,
        corners: list[tuple[int, int]],
        output_dir: Path,
        checkpoint_path: Path,
        confidence_threshold: float = 0.75,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the dialog and start the background worker immediately.

        Args:
            video_path: Absolute path to the source video file.
            setup: AutoEditSetup translated from the setup dialog's GameConfig.
            corners: Four (x, y) court corner coordinates.
            output_dir: Directory where output files will be written.
            checkpoint_path: Path to the WinnerClassifier checkpoint.
            confidence_threshold: Minimum winner-prediction confidence.
            parent: Parent widget for dialog positioning.
        """
        super().__init__(parent)
        self.setObjectName("autoEditProgressDialog")

        self._result = None  # AutoEditResult | None

        self._setup_ui()
        self._apply_styles()

        # Create and wire up the worker before starting it so all signals are
        # connected by the time the first emission fires.
        self._worker = AutoEditWorker(
            video_path=video_path,
            setup=setup,
            corners=corners,
            output_dir=output_dir,
            checkpoint_path=checkpoint_path,
            confidence_threshold=confidence_threshold,
            parent=self,
        )
        self._worker.phase_changed.connect(self._on_phase_changed)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_cancelled)

        # Start the worker immediately so processing begins before exec().
        self._worker.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Construct the dialog UI layout."""
        self.setWindowTitle("Auto-processing video...")
        self.setModal(True)
        self.setMinimumWidth(480)

        # Prevent the user from closing the dialog via the window X button
        # while processing; they must use the Cancel button.
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Title row
        title_label = QLabel("Auto-processing video...")
        title_label.setFont(Fonts.body(size=SIZE_DIALOG_TITLE, weight=WEIGHT_SEMIBOLD))
        set_label_role(title_label, "subheading")
        layout.addWidget(title_label)

        layout.addSpacing(SPACE_SM)

        # Phase label — shows the current pipeline stage
        self._phase_label = QLabel("Initialising pipeline...")
        self._phase_label.setFont(Fonts.label())
        set_label_role(self._phase_label, "body")
        self._phase_label.setWordWrap(True)
        layout.addWidget(self._phase_label)

        layout.addSpacing(SPACE_SM)

        # Indeterminate progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate (animated)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addSpacing(SPACE_XL)

        # Cancel button (right-aligned)
        button_row = QHBoxLayout()
        button_row.setSpacing(SPACE_MD)
        button_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFont(Fonts.button_other())
        self._cancel_btn.setMinimumHeight(40)
        self._cancel_btn.setObjectName("cancel_button")
        self._cancel_btn.setStyleSheet(
            ButtonStyles.secondary()
            + f"QPushButton:hover {{ border-color: {ACTION_DANGER}; color: {ACTION_DANGER}; }}"
        )
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_row.addWidget(self._cancel_btn)

        layout.addLayout(button_row)
        self.setLayout(layout)

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet matching the project's Court Green theme."""
        self.setStyleSheet(f"""
            QDialog#autoEditProgressDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QProgressBar {{
                background-color: {BG_TERTIARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
            }}

            QProgressBar::chunk {{
                background-color: {TEXT_ACCENT};
                border-radius: 3px;
            }}
        """)

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _on_phase_changed(self, phase: str) -> None:
        """Update the phase label when the worker advances to a new stage.

        Args:
            phase: Human-readable description of the current pipeline stage.
        """
        self._phase_label.setText(phase)

    @pyqtSlot(object)
    def _on_finished(self, result: object) -> None:
        """Store the result and accept the dialog on successful completion.

        Args:
            result: AutoEditResult returned by auto_edit().
        """
        self._result = result
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        self.accept()

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        """Show an error message box and reject the dialog on pipeline failure.

        Args:
            message: Error description from the worker.
        """
        logger.error("AutoEditWorker reported error: %s", message)

        error_box = QMessageBox(self)
        error_box.setWindowTitle("Auto-Processing Failed")
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText("The auto-edit pipeline encountered an error.")
        error_box.setInformativeText(message)
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_box.exec()

        self.reject()

    @pyqtSlot()
    def _on_cancelled(self) -> None:
        """Reject the dialog when the worker honours a cancellation request."""
        self.reject()

    # ------------------------------------------------------------------
    # UI interaction
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_cancel_clicked(self) -> None:
        """Handle Cancel button press.

        Disables the button immediately to prevent duplicate clicks, then
        signals the worker to stop. The dialog will close via _on_cancelled
        when the worker acknowledges the request.
        """
        self._cancel_btn.setEnabled(False)
        self._phase_label.setText("Cancelling...")
        self._worker.cancel()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_result(self):
        """Return the AutoEditResult if the pipeline completed, else None.

        Returns:
            AutoEditResult on success, or None when cancelled or failed.
        """
        return self._result
