"""Tests for AutoEditProgressDialog cancel lifecycle.

Covers:
- Test group 1: Esc keypress while worker running → dialog NOT closed,
  cancel requested (event set, button disabled, label updated).
- Test group 2: reject() while running → not closed, cancel requested.
- Test group 3: closeEvent while running → event ignored, cancel requested.
- Test group 4: result_ready (success path) → dialog accepted, get_result()
  returns the result object.
- Test group 5: cancelled path → dialog rejected, get_result() returns None.
- Test group 6: AutoEditWorker signal naming — result_ready exists; 'finished'
  is not shadowed in the class __dict__.

All worker/pipeline slots are driven directly (calling _on_finished() etc.)
rather than running a real QThread, so tests are fully deterministic and do
not require ML dependencies at runtime.

The ``ml.auto_edit`` module is injected into sys.modules before importing the
dialog so the top-level ``from ml.auto_edit import AutoEditSetup`` succeeds
without pulling in torch or other heavy ML dependencies.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Inject a minimal fake ml.auto_edit before importing the dialog module so
# the top-level ``from ml.auto_edit import AutoEditSetup`` succeeds.  If the
# real module is already importable (and already in sys.modules) this block is
# skipped and tests use the genuine classes.
# ---------------------------------------------------------------------------
if "ml" not in sys.modules:
    _ml_pkg = types.ModuleType("ml")
    sys.modules["ml"] = _ml_pkg

if "ml.auto_edit" not in sys.modules:
    _fake_ml_auto_edit = types.ModuleType("ml.auto_edit")

    class _FakeAutoEditSetup:
        def __init__(self, game_type: str = "singles", victory_rule: str = "11", **_kw):
            self.game_type = game_type
            self.victory_rule = victory_rule

    class _FakeAutoEditCancelled(RuntimeError):
        """Stub for AutoEditCancelled used when the real module is absent."""

    _fake_ml_auto_edit.AutoEditSetup = _FakeAutoEditSetup
    _fake_ml_auto_edit.AutoEditCancelled = _FakeAutoEditCancelled
    _fake_ml_auto_edit.auto_edit = MagicMock(return_value=None)
    _fake_ml_auto_edit.__all__ = ["AutoEditSetup", "AutoEditCancelled", "auto_edit"]
    sys.modules["ml.auto_edit"] = _fake_ml_auto_edit


# ---------------------------------------------------------------------------
# Qt availability guard (mirrors the pattern in test_winner_flip.py)
# ---------------------------------------------------------------------------

def _qt_available() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401
        return True
    except Exception:
        return False


_QT_SKIP_REASON = "Qt not available in this test environment"


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication fixture; skips the module if Qt is absent."""
    if not _qt_available():
        pytest.skip(_QT_SKIP_REASON)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app


# ---------------------------------------------------------------------------
# FakeWorker — controllable QObject stub for AutoEditWorker
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _fake_worker_class(qapp):
    """Return the FakeWorker class (needs QApplication to subclass QObject)."""
    from PyQt6.QtCore import pyqtSignal, QObject

    class FakeWorker(QObject):
        """Deterministic stub that replaces AutoEditWorker in the dialog.

        Signals mirror AutoEditWorker exactly (including the corrected name
        ``result_ready``).  ``start()`` records that it was called and sets
        ``_running = True``; ``isRunning()`` returns the controllable flag.
        """

        phase_changed = pyqtSignal(str)
        result_ready = pyqtSignal(object)
        error = pyqtSignal(str)
        cancelled = pyqtSignal()

        def __init__(self, *args, **kwargs):
            parent = kwargs.get("parent")
            super().__init__(parent)
            self._running = False
            self.cancel_called = False
            self.start_called = False

        def start(self) -> None:
            self.start_called = True
            self._running = True

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self.cancel_called = True

        def wait(self, msecs: int | None = None) -> bool:  # noqa: ARG002
            return True

        def set_running(self, value: bool) -> None:
            """Test helper: override the running state."""
            self._running = value

    return FakeWorker


# ---------------------------------------------------------------------------
# Dialog factory
# ---------------------------------------------------------------------------

def _make_dialog(monkeypatch, fake_worker_class):
    """Create an AutoEditProgressDialog backed by FakeWorker.

    Returns ``(dialog, worker)`` where ``worker`` is the FakeWorker instance
    created inside the dialog's __init__.
    """
    from src.ui.dialogs.auto_edit_progress import AutoEditProgressDialog

    captured: list = []

    class CapturingFakeWorker(fake_worker_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured.append(self)

    monkeypatch.setattr(
        "src.ui.dialogs.auto_edit_progress.AutoEditWorker",
        CapturingFakeWorker,
    )

    dialog = AutoEditProgressDialog(
        video_path=Path("/tmp/test_video.mp4"),
        setup=MagicMock(),
        corners=[(0, 0), (1920, 0), (1920, 1080), (0, 1080)],
        output_dir=Path("/tmp/test_out"),
        checkpoint_path=Path("/tmp/ckpt.pt"),
    )

    assert len(captured) == 1, "Expected exactly one FakeWorker to be constructed"
    return dialog, captured[0]


# ---------------------------------------------------------------------------
# Test group 1: Esc while running
# ---------------------------------------------------------------------------

class TestEscWhileRunning:
    """Esc keypress while worker is active must not close the dialog."""

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_esc_does_not_close_dialog(self, monkeypatch, qapp, _fake_worker_class):
        """dialog.finished must NOT fire when Esc is pressed while running."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        assert worker.isRunning()

        finished_codes: list[int] = []
        dialog.finished.connect(lambda code: finished_codes.append(code))

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)

        assert finished_codes == [], (
            "Dialog emitted finished signal on Esc while worker was running"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_esc_sets_cancel_event_on_worker(self, monkeypatch, qapp, _fake_worker_class):
        """Esc while running must call worker.cancel()."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)

        assert worker.cancel_called, "worker.cancel() was not called after Esc"

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_esc_disables_cancel_button(self, monkeypatch, qapp, _fake_worker_class):
        """Cancel button must be disabled immediately when Esc is pressed."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)

        assert not dialog._cancel_btn.isEnabled(), (
            "Cancel button must be disabled after Esc while running"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_esc_updates_phase_label(self, monkeypatch, qapp, _fake_worker_class):
        """Phase label must read 'Cancelling...' after Esc while running."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)

        assert dialog._phase_label.text() == "Cancelling..."


# ---------------------------------------------------------------------------
# Test group 2: reject() while running
# ---------------------------------------------------------------------------

class TestRejectWhileRunning:
    """Calling reject() while the worker is active must not close the dialog."""

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_reject_does_not_close_dialog(self, monkeypatch, qapp, _fake_worker_class):
        """dialog.finished must NOT fire when reject() is called while running."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        assert worker.isRunning()

        finished_codes: list[int] = []
        dialog.finished.connect(lambda code: finished_codes.append(code))

        dialog.reject()

        assert finished_codes == [], (
            "Dialog emitted finished signal on reject() while worker was running"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_reject_requests_cancel(self, monkeypatch, qapp, _fake_worker_class):
        """reject() while running must call worker.cancel()."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        dialog.reject()

        assert worker.cancel_called, "worker.cancel() was not called on reject() while running"

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_reject_disables_cancel_button(self, monkeypatch, qapp, _fake_worker_class):
        """Cancel button must be disabled after reject() while running."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        dialog.reject()

        assert not dialog._cancel_btn.isEnabled()


# ---------------------------------------------------------------------------
# Test group 3: closeEvent while running
# ---------------------------------------------------------------------------

class TestCloseEventWhileRunning:
    """closeEvent while the worker is active must be ignored."""

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_close_event_is_ignored(self, monkeypatch, qapp, _fake_worker_class):
        """The close event must be ignored (event.ignore() called) while running."""
        from PyQt6.QtGui import QCloseEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        assert worker.isRunning()

        event = QCloseEvent()
        dialog.closeEvent(event)

        assert not event.isAccepted(), (
            "closeEvent must be ignored while worker is running"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_close_event_requests_cancel(self, monkeypatch, qapp, _fake_worker_class):
        """closeEvent while running must call worker.cancel()."""
        from PyQt6.QtGui import QCloseEvent

        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)

        event = QCloseEvent()
        dialog.closeEvent(event)

        assert worker.cancel_called


# ---------------------------------------------------------------------------
# Test group 4: success path — result_ready → dialog accepted
# ---------------------------------------------------------------------------

class TestSuccessPath:
    """Driving _on_finished() directly simulates the result_ready signal path."""

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_on_finished_accepts_dialog(self, monkeypatch, qapp, _fake_worker_class):
        """_on_finished() must emit dialog.accepted (dialog closes as Accepted)."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        worker.set_running(False)  # simulate run() completed before signal delivery

        accepted_fired = [False]
        dialog.accepted.connect(lambda: accepted_fired.__setitem__(0, True))

        dialog._on_finished(object())

        assert accepted_fired[0], "_on_finished() did not cause dialog.accepted to fire"

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_on_finished_stores_result(self, monkeypatch, qapp, _fake_worker_class):
        """get_result() must return the object passed to _on_finished()."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        worker.set_running(False)

        sentinel = object()
        dialog._on_finished(sentinel)

        assert dialog.get_result() is sentinel

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_get_result_none_before_completion(self, monkeypatch, qapp, _fake_worker_class):
        """get_result() must return None before _on_finished() is called."""
        dialog, _ = _make_dialog(monkeypatch, _fake_worker_class)

        assert dialog.get_result() is None


# ---------------------------------------------------------------------------
# Test group 5: cancelled path — _on_cancelled → dialog rejected
# ---------------------------------------------------------------------------

class TestCancelledPath:
    """Driving _on_cancelled() directly simulates the cancelled signal path."""

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_on_cancelled_rejects_dialog(self, monkeypatch, qapp, _fake_worker_class):
        """_on_cancelled() must emit dialog.rejected (dialog closes as Rejected)."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        worker.set_running(False)

        rejected_fired = [False]
        dialog.rejected.connect(lambda: rejected_fired.__setitem__(0, True))

        dialog._on_cancelled()

        assert rejected_fired[0], "_on_cancelled() did not cause dialog.rejected to fire"

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_get_result_none_after_cancel(self, monkeypatch, qapp, _fake_worker_class):
        """get_result() must remain None after cancellation."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        worker.set_running(False)

        dialog._on_cancelled()

        assert dialog.get_result() is None

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_cancel_button_triggers_worker_cancel(self, monkeypatch, qapp, _fake_worker_class):
        """Clicking the Cancel button must call worker.cancel() and disable the button."""
        dialog, worker = _make_dialog(monkeypatch, _fake_worker_class)
        assert worker.isRunning()

        dialog._cancel_btn.click()

        assert worker.cancel_called
        assert not dialog._cancel_btn.isEnabled()


# ---------------------------------------------------------------------------
# Test group 6: signal naming — result_ready exists; finished not shadowed
# ---------------------------------------------------------------------------

class TestWorkerSignalNaming:
    """AutoEditWorker must expose result_ready and must not shadow QThread.finished."""

    def test_result_ready_signal_exists(self, qapp):
        """AutoEditWorker must define a result_ready class attribute (pyqtSignal)."""
        from src.ui.dialogs.auto_edit_progress import AutoEditWorker
        assert hasattr(AutoEditWorker, "result_ready"), (
            "AutoEditWorker is missing the 'result_ready' signal"
        )

    def test_finished_not_defined_on_worker_class(self, qapp):
        """AutoEditWorker.__dict__ must NOT contain 'finished'.

        Defining ``finished = pyqtSignal(...)`` on a QThread subclass shadows
        the built-in QThread.finished signal, breaking ``thread.finished.connect``
        calls in other parts of the application and triggering
        'QThread: Destroyed while thread is still running' aborts.
        """
        from src.ui.dialogs.auto_edit_progress import AutoEditWorker
        assert "finished" not in AutoEditWorker.__dict__, (
            "AutoEditWorker.__dict__ contains 'finished', shadowing QThread.finished. "
            "Rename it to 'result_ready'."
        )
