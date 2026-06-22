"""Retrain rally detector dialog — human-in-the-loop retraining feature.

This module provides:
- ``decide_default_apply`` / ``format_result_text`` — pure module-level helpers
  (testable without Qt or a subprocess).
- ``RetrainWorker`` — QThread that runs ``ml.tools.retrain_rally_combiner``
  out-of-process, streams STDERR progress, and parses the final STDOUT JSON.
- ``RetrainProgressDialog`` — indeterminate progress dialog wrapping the worker
  (mirrors the AutoEditProgressDialog pattern exactly).
- ``RetrainResultDialog`` — shows the F1 summary; lets the user Apply or Keep
  the current model.  On Apply it spawns a second ``RetrainProgressDialog``
  with ``apply=True`` and reports success/failure.

Subprocess architecture
-----------------------
The heavy ML (sklearn, numpy, feature loading) runs in a child process::

    command = [sys.executable, "-m", "ml.tools.retrain_rally_combiner"]

The GUI process **never** imports torch / sklearn / cv2 / ultralytics.
The worker reads subprocess STDERR line-by-line and emits Qt ``progress``
signals; it reads STDOUT once (after the process exits) to parse the single
JSON result line.

CLI contract
------------
Generate (no --apply): prints progress to STDERR; prints ONE final JSON to STDOUT::

    {"status":"ok","eligible":N,"skipped":[{"path":"..","reason":".."}],
     "before_loso_f1":<float|null>,"after_loso_f1":<float>,
     "delta":<float|null>,"candidate":"<abs>","manifest":"<abs>"}

Apply (--apply): ``{"status":"applied","backup":"<abs>","combiner":"<abs>","manifest":"<abs>"}``.
Errors: nonzero exit + ``{"status":"error","message":".."}``

Frozen-mode handling
--------------------
When ``getattr(sys, "frozen", False)`` is True (PyInstaller bundle), the
menu action is disabled with the tooltip "Available when running from source
(make run)".  The worker/dialog classes are importable but should never be
instantiated in a frozen context.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    ACTION_DANGER,
    BG_BORDER,
    BG_SECONDARY,
    BG_TERTIARY,
    SERVER_WINS,
    TEXT_ACCENT,
    TEXT_PRIMARY,
)
from src.ui.styles.components import ButtonStyles, set_label_role
from src.ui.styles.fonts import (
    RADIUS_XL,
    SIZE_BODY,
    SIZE_DIALOG_TITLE,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    WEIGHT_SEMIBOLD,
    Fonts,
)

__all__ = [
    "REPO_ROOT",
    "decide_default_apply",
    "format_result_text",
    "RetrainWorker",
    "RetrainProgressDialog",
    "RetrainResultDialog",
]

logger = logging.getLogger(__name__)

# Public module constant: repo root derived from this file's location.
# src/ui/dialogs/retrain_dialog.py → parents[3] = project root.
# Valid for source-tree runs; irrelevant when frozen (action is disabled).
REPO_ROOT: Path = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Pure helper functions — no Qt, no subprocess; trivially unit-testable.
# ---------------------------------------------------------------------------


def decide_default_apply(summary: dict) -> bool:
    """Return True if "Apply candidate" should be the default button.

    Pre-selects Apply when ``after_loso_f1 >= before_loso_f1`` (improvement
    or equal), or when ``before_loso_f1`` is None (no prior baseline exists).
    Returns False (default: "Keep current") when the candidate would regress
    the held-out F1.

    **Never auto-applies** — this only controls which button receives default
    focus when the result dialog opens.

    Args:
        summary: Parsed JSON summary dict from ``ml.tools.retrain_rally_combiner``.

    Returns:
        True  → default focus on "Apply candidate".
        False → default focus on "Keep current".
    """
    after_f1 = summary.get("after_loso_f1")
    before_f1 = summary.get("before_loso_f1")

    if after_f1 is None:
        # Cannot assess quality → safe default is Keep.
        return False
    if before_f1 is None:
        # No prior baseline → any trained candidate is an improvement.
        return True
    try:
        return float(after_f1) >= float(before_f1)
    except (TypeError, ValueError):
        return False


def format_result_text(summary: dict) -> str:
    """Format the retrain result summary for display in the result dialog.

    Produces a multi-line string covering:

    * Eligible and skipped session counts.
    * Held-out interval F1 before → after (Δ), or "no prior baseline".
    * Skipped session details (filename + reason).

    Args:
        summary: Parsed JSON summary dict from ``ml.tools.retrain_rally_combiner``.

    Returns:
        Human-readable multi-line summary string.
    """
    eligible: int = summary.get("eligible", 0)
    skipped: list[dict] = summary.get("skipped", [])
    after_f1 = summary.get("after_loso_f1")
    before_f1 = summary.get("before_loso_f1")
    delta = summary.get("delta")

    lines: list[str] = []
    lines.append(f"Eligible sessions: {eligible}")
    lines.append(f"Skipped sessions:  {len(skipped)}")

    if after_f1 is not None:
        try:
            after_str = f"{float(after_f1):.4f}"
        except (TypeError, ValueError):
            after_str = str(after_f1)

        if before_f1 is not None:
            try:
                before_str = f"{float(before_f1):.4f}"
                delta_str = f"{float(delta):+.4f}" if delta is not None else "N/A"
            except (TypeError, ValueError):
                before_str = str(before_f1)
                delta_str = str(delta) if delta is not None else "N/A"
            lines.append(
                f"Held-out interval F1:  before {before_str} → after {after_str}"
                f"  (Δ {delta_str})"
            )
        else:
            lines.append(
                f"Held-out interval F1:  {after_str}  (no prior baseline)"
            )

    if skipped:
        lines.append("")
        lines.append("Skipped sessions:")
        for item in skipped:
            path_str = item.get("path", "?")
            reason = item.get("reason", "?")
            # Show only the filename to keep the display compact.
            filename = Path(path_str).name if path_str != "?" else "?"
            lines.append(f"  • {filename}: {reason}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Child-process environment helper
# ---------------------------------------------------------------------------


def _retrain_child_env(repo_root: Path) -> dict[str, str]:
    """Build a clean environment dict for the retrain subprocess.

    When running inside a PyInstaller bundle, ``LD_LIBRARY_PATH`` is
    rewritten to point at bundle libraries.  Restoring the ``*_ORIG``
    variable (set by PyInstaller) ensures the child Python resolves
    its own shared libraries, not the bundle's.

    PYTHONPATH is prepended with *repo_root* so ``import ml`` works in
    the child even if the child Python has no installed ``ml`` package.

    Args:
        repo_root: Absolute path to the repository root.

    Returns:
        A modified copy of ``os.environ`` suitable for the child process.
    """
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        original = env.pop(f"{var}_ORIG", None)
        if original is not None:
            env[var] = original
        elif getattr(sys, "frozen", False):
            env.pop(var, None)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        os.pathsep.join([str(repo_root), existing]) if existing else str(repo_root)
    )
    return env


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class RetrainWorker(QThread):
    """QThread that runs ``ml.tools.retrain_rally_combiner`` out-of-process.

    The worker spawns a child Python interpreter and:

    * Streams STDERR lines to the ``progress`` signal (phase text).
    * Accumulates STDOUT in a background thread to avoid pipe-buffer deadlocks.
    * Parses the last JSON-looking line from STDOUT when the process exits.
    * Emits ``finished(dict)`` on success, ``failed(str)`` on error, or
      ``cancelled`` when cooperative cancellation is honoured.

    The GUI process **never** imports torch / sklearn / cv2 / ultralytics;
    all heavy ML runs in the child.

    Signals:
        progress:  Each non-empty STDERR line from the child (phase text).
        finished:  Parsed JSON result ``dict`` on successful completion.
        failed:    Human-readable error ``str`` on failure.
        cancelled: Emitted when cancellation was requested and honoured.
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        interpreter: str,
        repo_root: Path,
        apply: bool = False,
        parent: "QWidget | None" = None,
    ) -> None:
        """Initialise the worker.

        Args:
            interpreter: Absolute path to the Python interpreter (``sys.executable``
                when running from source).
            repo_root: Repository root directory (``ml`` package importable from here).
            apply: Pass ``--apply`` to the engine when True (apply phase).
            parent: Parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._interpreter = interpreter
        self._repo_root = repo_root
        self._apply = apply
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation.

        Sets a threading.Event polled by the process-exit loop.  The child
        receives SIGTERM first; if it does not exit within 5 s it is killed.
        """
        self._cancel_event.set()

    def run(self) -> None:
        """Execute the retrain subprocess in the background thread.

        Streams STDERR progress, polls for cancellation, and on normal exit
        parses the last JSON line from STDOUT as the result dict.
        """
        cmd = [self._interpreter, "-m", "ml.tools.retrain_rally_combiner"]
        if self._apply:
            cmd.append("--apply")

        env = _retrain_child_env(self._repo_root)

        logger.info(
            "Launching retrain subprocess (apply=%s, cwd=%s): %s",
            self._apply,
            self._repo_root,
            " ".join(cmd),
        )

        stdout_lines: list[str] = []

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self._repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            logger.exception("Failed to launch retrain subprocess")
            self.failed.emit(f"Failed to launch retrain process: {exc}")
            return

        # Two background threads drain the pipes so we never deadlock on a
        # full pipe buffer while polling for cancellation.
        def _drain_stdout() -> None:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                stripped = line.rstrip()
                if stripped:
                    stdout_lines.append(stripped)

        def _drain_stderr() -> None:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stripped = line.rstrip()
                if stripped:
                    self.progress.emit(stripped)

        stdout_thread = threading.Thread(target=_drain_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        # Poll for process exit, checking cancellation each iteration.
        while proc.poll() is None:
            if self._cancel_event.is_set():
                logger.info("Cancellation requested; terminating retrain subprocess.")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Retrain subprocess did not exit after kill(); giving up."
                        )
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                self.cancelled.emit()
                return
            time.sleep(0.2)

        # Process has exited; wait for drain threads to finish reading.
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)

        # A cancellation request that arrived while the process was finishing
        # is treated as user-initiated cancellation rather than an error.
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return

        returncode = proc.returncode

        # Find the last JSON-looking line in stdout (skip any preceding debug output).
        json_line = ""
        for line in reversed(stdout_lines):
            stripped = line.strip()
            if stripped.startswith("{"):
                json_line = stripped
                break

        if not json_line:
            msg = (
                f"Retrain subprocess exited with code {returncode} "
                "and produced no JSON output.\n"
                "Verify that ml.tools.retrain_rally_combiner is implemented."
            )
            logger.warning(msg)
            self.failed.emit(msg)
            return

        try:
            summary = json.loads(json_line)
        except json.JSONDecodeError as exc:
            self.failed.emit(
                f"Could not parse retrain output as JSON: {exc}\n"
                f"Raw output: {json_line!r}"
            )
            return

        status = summary.get("status", "")
        if returncode != 0 or status == "error":
            error_msg = summary.get(
                "message", f"Subprocess exited with code {returncode}"
            )
            self.failed.emit(f"Retrain failed: {error_msg}")
            return

        self.finished.emit(summary)


# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------


class RetrainProgressDialog(QDialog):
    """Modal progress dialog for the retrain subprocess.

    Manages a ``RetrainWorker`` internally; callers construct the dialog and
    call ``exec()``.  After ``exec()`` returns, call ``get_summary()`` to
    obtain the result dict or ``None`` if cancelled / failed.

    The same class handles both phases (``apply=False`` for the generate
    phase; ``apply=True`` for the apply phase).

    Cancel lifecycle mirrors ``AutoEditProgressDialog`` exactly:
    Esc, the Cancel button, ``reject()``, and ``closeEvent()`` all converge
    on ``_request_cancel()``.  The dialog does **not** close until the worker
    emits ``cancelled`` or ``failed``; this prevents the
    "QThread: Destroyed while thread is still running" abort.
    """

    def __init__(
        self,
        interpreter: str,
        repo_root: Path,
        apply: bool = False,
        parent: "QWidget | None" = None,
    ) -> None:
        """Initialise the dialog and start the background worker immediately.

        Args:
            interpreter: Python interpreter path (``sys.executable`` from source).
            repo_root: Repository root directory.
            apply: Run the engine with ``--apply`` when True.
            parent: Parent widget for dialog positioning.
        """
        super().__init__(parent)
        self.setObjectName("retrainProgressDialog")
        self._summary: dict | None = None

        self._setup_ui(apply=apply)
        self._apply_styles()

        self._worker = RetrainWorker(
            interpreter=interpreter,
            repo_root=repo_root,
            apply=apply,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)

        # Start immediately so work begins before exec() is called.
        self._worker.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self, apply: bool) -> None:
        """Construct the progress dialog layout."""
        if apply:
            title = "Applying candidate model…"
            init_phase = "Running ml.tools.retrain_rally_combiner --apply…"
        else:
            title = "Retraining rally detector…"
            init_phase = "Starting retrain engine…"

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        title_label = QLabel(title)
        title_label.setFont(Fonts.body(size=SIZE_DIALOG_TITLE, weight=WEIGHT_SEMIBOLD))
        set_label_role(title_label, "subheading")
        layout.addWidget(title_label)

        layout.addSpacing(SPACE_SM)

        self._phase_label = QLabel(init_phase)
        self._phase_label.setFont(Fonts.label())
        set_label_role(self._phase_label, "body")
        self._phase_label.setWordWrap(True)
        layout.addWidget(self._phase_label)

        layout.addSpacing(SPACE_SM)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate animated bar
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addSpacing(SPACE_XL)

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
        """Apply QSS stylesheet matching the Court Green theme."""
        self.setStyleSheet(f"""
            QDialog#retrainProgressDialog {{
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
    # Cancel helpers
    # ------------------------------------------------------------------

    def _request_cancel(self) -> None:
        """Request cooperative cancellation and update UI.

        Idempotent — safe to call multiple times (Esc and Cancel button in
        quick succession).  Only takes effect while the worker is running.
        """
        self._cancel_btn.setEnabled(False)
        self._phase_label.setText("Cancelling…")
        self._worker.cancel()

    def _wait_for_worker(self) -> None:
        """Block until the worker thread has fully stopped.

        Called immediately before any ``accept()`` / ``super().reject()`` that
        closes the dialog so the QThread is never destroyed while running.
        """
        if not self._worker.isRunning():
            return
        if not self._worker.wait(5000):
            logger.warning(
                "RetrainWorker did not finish within 5 s; waiting 30 s more."
            )
            self._worker.wait(30000)

    # ------------------------------------------------------------------
    # QDialog lifecycle overrides
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Route Esc through the cancel path while the worker is running."""
        if event.key() == Qt.Key.Key_Escape and self._worker.isRunning():
            self._request_cancel()
            return
        super().keyPressEvent(event)

    def reject(self) -> None:
        """Guard against closing while the worker is running."""
        if self._worker.isRunning():
            self._request_cancel()
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Prevent window-X close while the worker is running."""
        if self._worker.isRunning():
            self._request_cancel()
            event.ignore()
            return
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _on_progress(self, phase: str) -> None:
        """Update the phase label when the worker emits a STDERR line."""
        self._phase_label.setText(phase)

    @pyqtSlot(dict)
    def _on_finished(self, summary: dict) -> None:
        """Store the result and accept the dialog on successful completion."""
        self._summary = summary
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        self._wait_for_worker()
        self.accept()

    @pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        """Show an error message box and reject the dialog on failure."""
        logger.error("RetrainWorker reported failure: %s", message)
        error_box = QMessageBox(self)
        error_box.setWindowTitle("Retrain Failed")
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText("The retrain engine encountered an error.")
        error_box.setInformativeText(message)
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_box.exec()
        self._wait_for_worker()
        super().reject()

    @pyqtSlot()
    def _on_cancelled(self) -> None:
        """Reject the dialog when the worker honours a cancellation request."""
        self._wait_for_worker()
        super().reject()

    # ------------------------------------------------------------------
    # UI interaction
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_cancel_clicked(self) -> None:
        """Handle Cancel button press."""
        self._request_cancel()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_summary(self) -> dict | None:
        """Return the parsed JSON result dict, or None if cancelled / failed."""
        return self._summary


# ---------------------------------------------------------------------------
# Result dialog
# ---------------------------------------------------------------------------


class RetrainResultDialog(QDialog):
    """Shows the retrain result summary with Apply / Keep current options.

    The user can inspect the F1 improvement (or regression) and the list of
    skipped sessions, then choose to apply the candidate model or keep the
    current one.

    Default-button pre-selection:
    - "Apply candidate" is the default when ``after_loso_f1 >= before_loso_f1``
      or when there is no prior baseline (``before_loso_f1`` is null).
    - "Keep current" is the default when the candidate would regress F1.

    On "Apply candidate":
    1. A second ``RetrainProgressDialog`` runs ``--apply`` in the background.
    2. Success shows a confirmation message box, then closes this dialog.
    3. Failure re-enables both buttons so the user can retry or keep.

    Note shown in the dialog::

        "Validation refits the combiner per held-out session; the applied
        candidate is fit once on all eligible data."
    """

    def __init__(
        self,
        summary: dict,
        interpreter: str,
        repo_root: Path,
        parent: "QWidget | None" = None,
    ) -> None:
        """Initialise the result dialog.

        Args:
            summary: Parsed JSON result dict from the generate phase.
            interpreter: Python interpreter path.
            repo_root: Repository root directory.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setObjectName("retrainResultDialog")
        self._summary = summary
        self._interpreter = interpreter
        self._repo_root = repo_root
        self._applied = False

        self._setup_ui()
        self._apply_styles()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Construct the result dialog layout."""
        self.setWindowTitle("Retrain Result — Rally Detector")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(320)

        layout = QVBoxLayout()
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        # Title
        title_label = QLabel("Rally Detector Retrain Complete")
        title_label.setFont(Fonts.body(size=SIZE_DIALOG_TITLE, weight=WEIGHT_SEMIBOLD))
        set_label_role(title_label, "subheading")
        layout.addWidget(title_label)

        # Summary text (monospace, scrollable)
        summary_text = format_result_text(self._summary)
        self._summary_edit = QTextEdit()
        self._summary_edit.setReadOnly(True)
        self._summary_edit.setPlainText(summary_text)
        self._summary_edit.setFont(Fonts.display(size=SIZE_BODY, weight=400))
        self._summary_edit.setMinimumHeight(140)
        self._summary_edit.setMaximumHeight(260)
        layout.addWidget(self._summary_edit)

        # Validation note
        note_label = QLabel(
            "Note: Validation refits the combiner per held-out session; "
            "the applied candidate is fit once on all eligible data."
        )
        note_label.setFont(Fonts.label())
        set_label_role(note_label, "body")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)

        layout.addSpacing(SPACE_SM)

        # Button row — Keep (left of Apply)
        button_row = QHBoxLayout()
        button_row.setSpacing(SPACE_MD)
        button_row.addStretch()

        self._keep_btn = QPushButton("Keep current")
        self._keep_btn.setFont(Fonts.button_other())
        self._keep_btn.setMinimumHeight(40)
        self._keep_btn.setMinimumWidth(120)
        self._keep_btn.clicked.connect(self._on_keep_clicked)
        button_row.addWidget(self._keep_btn)

        self._apply_btn = QPushButton("Apply candidate")
        self._apply_btn.setFont(Fonts.button_other())
        self._apply_btn.setMinimumHeight(40)
        self._apply_btn.setMinimumWidth(140)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        button_row.addWidget(self._apply_btn)

        layout.addLayout(button_row)
        self.setLayout(layout)

        # Pre-select the appropriate default button
        if decide_default_apply(self._summary):
            self._apply_btn.setDefault(True)
            self._apply_btn.setFocus()
        else:
            self._keep_btn.setDefault(True)
            self._keep_btn.setFocus()

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet matching the Court Green theme."""
        self.setStyleSheet(f"""
            QDialog#retrainResultDialog {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_XL}px;
            }}

            QTextEdit {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        # "Apply candidate" uses server-wins blue to contrast with the
        # standard green and signal that this is a significant action.
        self._apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {SERVER_WINS};
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #81D4FA;
            }}
            QPushButton:pressed {{
                background-color: #29B6F6;
            }}
            QPushButton:disabled {{
                background-color: {BG_TERTIARY};
                color: #5A6270;
                border: 1px solid {BG_BORDER};
            }}
        """)
        self._keep_btn.setStyleSheet(ButtonStyles.secondary())

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_keep_clicked(self) -> None:
        """Close the dialog without applying the candidate model."""
        self.reject()

    @pyqtSlot()
    def _on_apply_clicked(self) -> None:
        """Run the engine with ``--apply``, show progress, confirm success."""
        self._apply_btn.setEnabled(False)
        self._keep_btn.setEnabled(False)

        progress_dialog = RetrainProgressDialog(
            interpreter=self._interpreter,
            repo_root=self._repo_root,
            apply=True,
            parent=self,
        )
        progress_dialog.exec()
        apply_result = progress_dialog.get_summary()

        if apply_result is None:
            # Cancelled or failed — re-enable buttons and let the user decide.
            self._apply_btn.setEnabled(True)
            self._keep_btn.setEnabled(True)
            return

        # Build a confirmation message from the apply result.
        combiner_path = apply_result.get("combiner", "")
        backup_path = apply_result.get("backup", "")

        detail_parts: list[str] = []
        if combiner_path:
            detail_parts.append(f"Combiner: {combiner_path}")
        if backup_path:
            detail_parts.append(f"Backup:   {backup_path}")
        detail = "\n".join(detail_parts)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Model Applied")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText("Candidate model applied successfully.")
        if detail:
            msg_box.setInformativeText(detail)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

        self._applied = True
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def was_applied(self) -> bool:
        """Return True if the candidate model was successfully applied."""
        return self._applied
