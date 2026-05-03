"""Tests for ml/tools/frame_picker_dialog.py.

A QApplication is created once per session via the module-level fixture so
that PyQt6 does not complain about widgets created without an application.

The tests set QT_QPA_PLATFORM to "offscreen" before any Qt import so the
suite runs in headless CI environments — matching the pattern used in
tests/test_court_calibrator.py.

decord is mocked at the module level via monkeypatch so these tests run on
machines that have not run ``./configure --enable-ml``.  The mock injects a
fake VideoReader into the ``decord`` module that is lazily imported inside
FramePickerDialog.__init__ (the implementation does ``import decord`` inside
the constructor body to keep the import optional).

Test coverage:
- Constructor raises FileNotFoundError when video_path does not exist.
- Dialog slider is positioned at the 5% frame on first display.
- A single frame read occurs during construction (the 5% default frame).
- Slider-release triggers exactly one additional frame read (not drag ticks).
- Confirm button is disabled on creation and enabled after the first frame loads.
- get_result() returns None when the dialog is cancelled.
- get_result() returns a QPixmap when the dialog is accepted.
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# tests/test_auto_edit.py installs a MagicMock under sys.modules["numpy"] at
# module load. If that happened first, our `import numpy as np` below would
# bind to the mock and fake-frame construction (np.zeros) would yield a
# MagicMock that the dialog cannot unpack as (H, W, C). Drop the stub so the
# real numpy is imported here.
if isinstance(sys.modules.get("numpy"), MagicMock):
    del sys.modules["numpy"]

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QDialog

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so absolute imports resolve.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pre-emptively stub heavy ML dependencies that are not installed in the base
# environment.  ml/tools/frame_picker_dialog.py triggers a transitive import
# chain:
#   src.ui  →  src.ui.dialogs  →  ml.auto_edit  →  ml.predict  →  torch
# Stubbing these before any project import lets the module load cleanly.
# The stubs need enough attributes to satisfy all ``from <module> import X``
# statements in the import chain.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Session-scoped QApplication fixture (same pattern as test_court_calibrator.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the singleton QApplication, creating it if necessary."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers for building the decord mock
# ---------------------------------------------------------------------------

_FRAME_COUNT = 200  # arbitrary; enough that 5% = frame 10


def _make_rgb_frame(width: int = 4, height: int = 4) -> np.ndarray:
    """Return a minimal (H, W, 3) uint8 ndarray suitable as a decoded frame."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _make_fake_decord_module(
    frame_count: int = _FRAME_COUNT,
    frame_width: int = 4,
    frame_height: int = 4,
) -> tuple[types.ModuleType, MagicMock]:
    """Build a minimal fake *decord* module and return (module, reader_instance).

    The returned reader_instance is what ``decord.VideoReader(path)`` will
    return when the fake module is installed.  Tests can inspect
    ``reader_instance.__getitem__.call_count`` to count frame-read calls.

    Returns:
        A (fake_module, reader_instance) tuple.
    """
    frame = _make_rgb_frame(frame_width, frame_height)

    # Mimic decord's NDArray wrapper: ``reader[n]`` returns an object with
    # ``.asnumpy()`` method.
    frame_wrapper = MagicMock()
    frame_wrapper.asnumpy.return_value = frame

    reader_instance = MagicMock()
    reader_instance.__len__ = MagicMock(return_value=frame_count)
    reader_instance.__getitem__ = MagicMock(return_value=frame_wrapper)

    reader_cls = MagicMock(return_value=reader_instance)

    fake_module = types.ModuleType("decord")
    fake_module.VideoReader = reader_cls  # type: ignore[attr-defined]
    fake_module.bridge = types.SimpleNamespace(set_bridge=MagicMock())  # type: ignore[attr-defined]

    return fake_module, reader_instance


# ---------------------------------------------------------------------------
# Per-test dialog factory
# ---------------------------------------------------------------------------


def _make_dialog(
    qapp: QApplication,
    video_path: Path,
    fake_decord: types.ModuleType,
) -> "FramePickerDialog":  # noqa: F821
    """Construct a FramePickerDialog with the fake decord module injected.

    The dialog lazily imports ``decord`` inside ``__init__``, so we install
    the fake module into ``sys.modules`` before calling the constructor and
    remove it afterwards (leaving the import cache set to our fake so that
    later attribute look-ups on ``self._reader`` still work through the MagicMock).

    Args:
        qapp:        Active QApplication (ensures Qt is live).
        video_path:  Path that must exist (caller's responsibility).
        fake_decord: The fake module returned by ``_make_fake_decord_module``.

    Returns:
        A constructed FramePickerDialog.
    """
    from ml.tools.frame_picker_dialog import FramePickerDialog

    with patch.dict(sys.modules, {"decord": fake_decord}):
        dialog = FramePickerDialog(video_path, parent=None)

    qapp.processEvents()
    return dialog


# ---------------------------------------------------------------------------
# Test 1 — Constructor raises FileNotFoundError on missing file
# ---------------------------------------------------------------------------


class TestConstructorGuard:
    """FramePickerDialog must raise FileNotFoundError for a non-existent path."""

    def test_missing_video_raises_file_not_found(self, tmp_path: Path) -> None:
        """Passing a path that does not exist must raise FileNotFoundError before
        any Qt widgets are created (LBYL guard at top of __init__).

        The import uses the same fake-decord injection as all other tests so
        that the module-level import of ml.tools.frame_picker_dialog does not
        fail on machines without torch/decord installed.
        """
        missing = tmp_path / "no_such_video.mp4"
        assert not missing.exists()

        fake_decord, _ = _make_fake_decord_module()

        from ml.tools.frame_picker_dialog import FramePickerDialog

        with patch.dict(sys.modules, {"decord": fake_decord}):
            with pytest.raises(FileNotFoundError):
                FramePickerDialog(missing)


# ---------------------------------------------------------------------------
# Test 2 — Default 5% frame position
# ---------------------------------------------------------------------------


class TestDefaultFramePosition:
    """The slider must be set to the 5% frame index on first display."""

    def test_slider_value_is_five_percent_frame(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Slider value after construction must equal int(frame_count * 0.05)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        dialog = _make_dialog(qapp, video, fake_decord)

        expected = max(0, int(_FRAME_COUNT * 0.05))
        assert dialog._slider.value() == expected

    def test_slider_minimum_is_zero(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Slider minimum must always be 0."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        assert dialog._slider.minimum() == 0

    def test_slider_maximum_is_last_frame(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Slider maximum must equal frame_count - 1."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        dialog = _make_dialog(qapp, video, fake_decord)

        assert dialog._slider.maximum() == _FRAME_COUNT - 1


# ---------------------------------------------------------------------------
# Test 3 — Single frame read on construction
# ---------------------------------------------------------------------------


class TestInitialFrameRead:
    """Exactly one frame decode must happen during construction (the 5% frame)."""

    def test_one_frame_read_on_construction(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """``VideoReader.__getitem__`` must be called exactly once during __init__."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, reader = _make_fake_decord_module()
        _make_dialog(qapp, video, fake_decord)

        assert reader.__getitem__.call_count == 1

    def test_initial_frame_index_is_five_percent(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The frame read during construction must be at index int(count * 0.05)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, reader = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        _make_dialog(qapp, video, fake_decord)

        expected_index = max(0, int(_FRAME_COUNT * 0.05))
        reader.__getitem__.assert_called_once_with(expected_index)


# ---------------------------------------------------------------------------
# Test 4 — Slider release triggers frame read; drag does not
# ---------------------------------------------------------------------------


class TestSliderReleaseBehavior:
    """sliderReleased must trigger one decode; valueChanged must not."""

    def test_slider_release_reads_one_frame(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Calling _on_slider_released() must result in exactly one additional
        frame read beyond the initial construction decode."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, reader = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        dialog = _make_dialog(qapp, video, fake_decord)

        reads_after_init = reader.__getitem__.call_count  # should be 1

        # Move slider to a new position (simulating drag without releasing).
        new_index = 50
        dialog._slider.setValue(new_index)
        qapp.processEvents()

        # valueChanged alone must NOT trigger a decode.
        assert reader.__getitem__.call_count == reads_after_init, (
            "valueChanged must not trigger frame decode — only sliderReleased should"
        )

        # Now simulate slider release.
        dialog._on_slider_released()
        qapp.processEvents()

        assert reader.__getitem__.call_count == reads_after_init + 1

    def test_slider_release_reads_frame_at_current_value(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The frame index passed to decord on release must match the slider value."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, reader = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        dialog = _make_dialog(qapp, video, fake_decord)

        target_frame = 80
        dialog._slider.setValue(target_frame)
        dialog._on_slider_released()
        qapp.processEvents()

        reader.__getitem__.assert_called_with(target_frame)

    def test_multiple_value_changes_then_one_release_reads_once(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Simulating several drag ticks followed by one release must produce only
        one decode (not one per setValue call)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, reader = _make_fake_decord_module(frame_count=_FRAME_COUNT)
        dialog = _make_dialog(qapp, video, fake_decord)

        reads_after_init = reader.__getitem__.call_count

        # Simulate many drag ticks.
        for i in range(10, 60, 5):
            dialog._slider.setValue(i)
        qapp.processEvents()

        assert reader.__getitem__.call_count == reads_after_init, (
            "Drag ticks (valueChanged only) must not trigger any decodes"
        )

        # One release.
        dialog._on_slider_released()
        qapp.processEvents()

        assert reader.__getitem__.call_count == reads_after_init + 1


# ---------------------------------------------------------------------------
# Test 5 — Confirm button state
# ---------------------------------------------------------------------------


class TestConfirmButtonState:
    """Confirm must be disabled until the first frame is loaded."""

    def test_confirm_disabled_before_build(self, tmp_path: Path) -> None:
        """Before construction completes (i.e. before _extract_and_show is called),
        Confirm must be disabled.  We verify the flag is set False in _build_ui
        by checking the implementation directly via a partially-built dialog."""
        # We can verify this by inspecting _build_ui in isolation: the button is
        # created with setEnabled(False).  Here we confirm the post-construction
        # state reflects what _build_ui set, before the initial frame load.
        # Because the constructor calls _extract_and_show immediately, the easiest
        # check is to mock _extract_and_show to a no-op and confirm the button
        # remains disabled.
        video = tmp_path / "noop.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()

        from ml.tools.frame_picker_dialog import FramePickerDialog

        with patch.dict(sys.modules, {"decord": fake_decord}):
            with patch.object(
                FramePickerDialog, "_extract_and_show", return_value=None
            ):
                dialog = FramePickerDialog(video, parent=None)

        assert not dialog._confirm_btn.isEnabled(), (
            "Confirm must be disabled when no frame has been loaded yet"
        )

    def test_confirm_enabled_after_first_frame_loads(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After the initial 5% frame is decoded, Confirm must be enabled."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        assert dialog._confirm_btn.isEnabled(), (
            "Confirm must be enabled once the first frame has been decoded"
        )

    def test_confirm_stays_enabled_after_slider_release(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Moving the slider and releasing must not disable Confirm."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        dialog._slider.setValue(30)
        dialog._on_slider_released()
        qapp.processEvents()

        assert dialog._confirm_btn.isEnabled()


# ---------------------------------------------------------------------------
# Test 6 — get_result() on cancel
# ---------------------------------------------------------------------------


class TestGetResultCancel:
    """get_result() must return None when the dialog is cancelled."""

    def test_get_result_returns_none_before_any_action(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A freshly constructed dialog that has not been accepted must return None."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        # _accepted is False; get_result() must return None.
        assert dialog.get_result() is None

    def test_get_result_returns_none_after_cancel(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Clicking Cancel must leave get_result() returning None."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        # Simulate cancel without exec() (avoid blocking the event loop).
        dialog.reject()
        qapp.processEvents()

        assert dialog.get_result() is None

    def test_accepted_flag_false_after_reject(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_accepted must remain False after reject()."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)
        dialog.reject()

        assert not dialog._accepted


# ---------------------------------------------------------------------------
# Test 7 — get_result() on accept
# ---------------------------------------------------------------------------


class TestGetResultAccept:
    """get_result() must return a QPixmap when the dialog is accepted."""

    def test_get_result_returns_qpixmap_after_accept(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After _on_confirm() is called, get_result() must return a QPixmap."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        # Trigger accept path directly (avoid blocking exec() call).
        dialog._on_confirm()
        qapp.processEvents()

        result = dialog.get_result()
        assert result is not None, "get_result() must not be None after confirm"
        assert isinstance(result, QPixmap), (
            f"get_result() must return QPixmap, got {type(result)}"
        )

    def test_get_result_pixmap_has_nonzero_dimensions(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The returned QPixmap must have positive width and height."""
        video = tmp_path / "clip.mp4"
        video.touch()

        # Use a larger frame so the pixmap is non-degenerate.
        fake_decord, _ = _make_fake_decord_module(frame_width=16, frame_height=9)
        dialog = _make_dialog(qapp, video, fake_decord)
        dialog._on_confirm()
        qapp.processEvents()

        pixmap = dialog.get_result()
        assert pixmap is not None
        assert pixmap.width() > 0
        assert pixmap.height() > 0

    def test_accepted_flag_true_after_confirm(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_accepted must be True after _on_confirm() is called."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)
        dialog._on_confirm()

        assert dialog._accepted

    def test_confirm_then_cancel_sequence_returns_pixmap(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """If confirm is triggered (not cancel), get_result() returns a pixmap
        regardless of the QDialog result code inspection order."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)
        dialog._on_confirm()
        qapp.processEvents()

        # Confirm button path: _accepted=True, _current_pixmap is set.
        result = dialog.get_result()
        assert isinstance(result, QPixmap)


# ---------------------------------------------------------------------------
# Test 8 — Internal pixmap state tracks last decoded frame
# ---------------------------------------------------------------------------


class TestCurrentPixmapState:
    """_current_pixmap must reflect the most recently decoded frame."""

    def test_current_pixmap_set_after_construction(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After construction, _current_pixmap must be a QPixmap (not None)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        assert dialog._current_pixmap is not None
        assert isinstance(dialog._current_pixmap, QPixmap)

    def test_current_pixmap_updated_after_slider_release(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_current_pixmap must be updated (non-None) after a slider release."""
        video = tmp_path / "clip.mp4"
        video.touch()

        fake_decord, _ = _make_fake_decord_module()
        dialog = _make_dialog(qapp, video, fake_decord)

        dialog._slider.setValue(100)
        dialog._on_slider_released()
        qapp.processEvents()

        assert dialog._current_pixmap is not None
        assert isinstance(dialog._current_pixmap, QPixmap)
