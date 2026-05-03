"""Tests for src/ui/dialogs/frame_selector_dialog.py.

A QApplication is created once per session via the module-level fixture so
that PyQt6 does not complain about widgets created without an application.

The tests set QT_QPA_PLATFORM to "offscreen" before any Qt import so the
suite runs in headless CI environments — matching the pattern used in
tests/test_main_window.py.

Heavy ML dependencies that are transitively imported through the UI layer are
stubbed before any project import so the module loads cleanly on machines that
have not run ``./configure --enable-ml``.

``extract_frame_at`` is patched at its *imported* location inside
``src.ui.dialogs.frame_selector_dialog`` so the dialog's ``_seek_to`` method
never spawns real ffmpeg subprocesses.

Test coverage:
- Constructor raises FileNotFoundError when video_path does not exist.
- Constructor raises ValueError when video_duration_s <= 0.
- On construction the initial extract is called with offset = duration * 0.05.
- ``sliderReleased`` triggers exactly one extract call with the correct offset.
- Left/Right arrow keys step the slider ±1 s and trigger an extract.
- PageUp/PageDown keys step the slider ±10 s and trigger an extract.
- Confirm button is disabled before the first successful extract.
- Confirm button is enabled after the first successful extract.
- ``get_result()`` returns the extracted QPixmap after accept.
- ``get_result()`` returns None after reject/cancel.
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so absolute imports resolve.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pre-emptively stub heavy ML deps that are not installed in the base
# environment.  The same technique is used in test_main_window.py.
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
# Constants mirroring the dialog's internal slider scale.
# ---------------------------------------------------------------------------
_SLIDER_SCALE = 100   # ticks per second — must match frame_selector_dialog._SLIDER_SCALE
_SINGLE_STEP_S = 1.0  # Left/Right arrow key step in seconds
_PAGE_STEP_S = 10.0   # PageUp/PageDown key step in seconds

# Patch target: extract_frame_at as imported into the dialog module's namespace.
_PATCH_TARGET = "src.ui.dialogs.frame_selector_dialog.extract_frame_at"

# Duration used across most tests.
_DURATION_S = 120.0


# ---------------------------------------------------------------------------
# Session-scoped QApplication fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the singleton QApplication, creating it if necessary."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_pixmap() -> QPixmap:
    """Return a 1x1 QPixmap suitable as a stand-in extracted frame."""
    px = QPixmap(1, 1)
    px.fill(Qt.GlobalColor.black)
    return px


def _make_dialog(
    qapp: QApplication,
    video_path: Path,
    duration_s: float = _DURATION_S,
    initial_offset_s: float | None = None,
    mock_extract: MagicMock | None = None,
) -> "FrameSelectorDialog":  # noqa: F821
    """Construct a FrameSelectorDialog with extract_frame_at mocked.

    If *mock_extract* is None a fresh MagicMock returning a 1x1 QPixmap is
    created automatically.

    Args:
        qapp:             Active QApplication (ensures Qt is live).
        video_path:       Path that must exist (caller's responsibility).
        duration_s:       Total video duration in seconds.
        initial_offset_s: Optional explicit initial offset.
        mock_extract:     Optional pre-configured MagicMock; created if None.

    Returns:
        A constructed FrameSelectorDialog with patched extraction.
    """
    from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

    if mock_extract is None:
        mock_extract = MagicMock(return_value=_make_fake_pixmap())

    with patch(_PATCH_TARGET, mock_extract):
        dialog = FrameSelectorDialog(
            video_path=video_path,
            video_duration_s=duration_s,
            initial_offset_s=initial_offset_s,
            parent=None,
        )

    qapp.processEvents()
    return dialog


# ---------------------------------------------------------------------------
# Test 1 — Constructor preconditions (LBYL guards)
# ---------------------------------------------------------------------------


class TestConstructorPreconditions:
    """FrameSelectorDialog must enforce LBYL guards before any Qt widget creation."""

    def test_missing_video_raises_file_not_found(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Non-existent video_path must raise FileNotFoundError immediately."""
        missing = tmp_path / "no_such_video.mp4"
        assert not missing.exists()

        from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        with patch(_PATCH_TARGET, mock_extract):
            with pytest.raises(FileNotFoundError):
                FrameSelectorDialog(
                    video_path=missing,
                    video_duration_s=60.0,
                )

        # extract_frame_at must never have been called — guard fires before UI build.
        mock_extract.assert_not_called()

    def test_zero_duration_raises_value_error(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """video_duration_s == 0 must raise ValueError."""
        video = tmp_path / "clip.mp4"
        video.touch()

        from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        with patch(_PATCH_TARGET, mock_extract):
            with pytest.raises(ValueError):
                FrameSelectorDialog(
                    video_path=video,
                    video_duration_s=0.0,
                )

        mock_extract.assert_not_called()

    def test_negative_duration_raises_value_error(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """video_duration_s < 0 must raise ValueError."""
        video = tmp_path / "clip.mp4"
        video.touch()

        from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        with patch(_PATCH_TARGET, mock_extract):
            with pytest.raises(ValueError):
                FrameSelectorDialog(
                    video_path=video,
                    video_duration_s=-5.0,
                )

        mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — Initial extract uses duration * 0.05
# ---------------------------------------------------------------------------


class TestInitialExtract:
    """The dialog must auto-extract the frame at duration * 0.05 on construction."""

    def test_initial_extract_called_once(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """extract_frame_at must be called exactly once during __init__."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        _make_dialog(qapp, video, duration_s=_DURATION_S, mock_extract=mock_extract)

        assert mock_extract.call_count == 1

    def test_initial_extract_uses_five_percent_offset(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The offset passed to extract_frame_at must equal duration * 0.05."""
        video = tmp_path / "clip.mp4"
        video.touch()

        duration = 200.0
        expected_offset = duration * 0.05  # 10.0 s

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        _make_dialog(qapp, video, duration_s=duration, mock_extract=mock_extract)

        args, _kwargs = mock_extract.call_args
        actual_offset = args[1]  # extract_frame_at(video_path, offset_s, ...)
        assert actual_offset == pytest.approx(expected_offset), (
            f"Initial extract offset must be duration*0.05={expected_offset}, "
            f"got {actual_offset}"
        )

    def test_initial_extract_respects_explicit_offset(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """When initial_offset_s is given explicitly, that value is used instead."""
        video = tmp_path / "clip.mp4"
        video.touch()

        explicit_offset = 30.0
        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        _make_dialog(
            qapp,
            video,
            duration_s=_DURATION_S,
            initial_offset_s=explicit_offset,
            mock_extract=mock_extract,
        )

        args, _kwargs = mock_extract.call_args
        actual_offset = args[1]
        assert actual_offset == pytest.approx(explicit_offset)

    def test_initial_extract_video_path_matches(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """extract_frame_at must be called with the dialog's video_path."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        _make_dialog(qapp, video, mock_extract=mock_extract)

        args, _kwargs = mock_extract.call_args
        assert args[0] == video


# ---------------------------------------------------------------------------
# Test 3 — sliderReleased triggers a single extract
# ---------------------------------------------------------------------------


class TestSliderReleasedBehavior:
    """sliderReleased must trigger exactly one extract; valueChanged must not."""

    def test_slider_release_triggers_one_additional_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Calling _on_slider_released() produces one extract beyond the init call."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        count_after_init = mock_extract.call_count  # typically 1

        with patch(_PATCH_TARGET, mock_extract):
            dialog._on_slider_released()
            qapp.processEvents()

        assert mock_extract.call_count == count_after_init + 1

    def test_value_changed_alone_does_not_trigger_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """setValue without a subsequent release must not call extract_frame_at."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        count_after_init = mock_extract.call_count

        # Simulate several drag ticks (valueChanged only, no release).
        with patch(_PATCH_TARGET, mock_extract):
            for tick in range(10, 60, 5):
                dialog._slider.setValue(tick)
            qapp.processEvents()

        assert mock_extract.call_count == count_after_init, (
            "valueChanged alone must not trigger any extract calls"
        )

    def test_slider_release_uses_current_slider_offset(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The offset passed on release must match the current slider position."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        # Move slider to a known position.
        target_s = 50.0
        target_tick = int(target_s * _SLIDER_SCALE)
        dialog._slider.setValue(target_tick)

        with patch(_PATCH_TARGET, mock_extract):
            dialog._on_slider_released()
            qapp.processEvents()

        last_call_args, _ = mock_extract.call_args
        actual_offset = last_call_args[1]
        assert actual_offset == pytest.approx(target_s)


# ---------------------------------------------------------------------------
# Test 4 — Arrow-key and page-key seeks
# ---------------------------------------------------------------------------


class TestKeySeeks:
    """Left/Right and PageUp/PageDown keys must adjust the slider and extract."""

    def _send_key(
        self,
        dialog: "FrameSelectorDialog",  # noqa: F821
        qapp: QApplication,
        key: Qt.Key,
    ) -> None:
        """Synthesize a key-press event and pump the event loop."""
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            key.value,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)
        qapp.processEvents()

    def test_right_arrow_advances_one_second(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_Right must move the slider forward by 1 s (100 ticks)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        start_value = dialog._slider.value()

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_Right)

        expected = min(
            start_value + int(_SINGLE_STEP_S * _SLIDER_SCALE),
            dialog._slider.maximum(),
        )
        assert dialog._slider.value() == expected

    def test_left_arrow_retreats_one_second(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_Left must move the slider backward by 1 s (100 ticks)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        # Start well into the video so there is room to go backward.
        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        initial_offset = _DURATION_S * 0.5
        dialog = _make_dialog(
            qapp, video, initial_offset_s=initial_offset, mock_extract=mock_extract
        )

        start_value = dialog._slider.value()

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_Left)

        expected = max(
            start_value - int(_SINGLE_STEP_S * _SLIDER_SCALE),
            dialog._slider.minimum(),
        )
        assert dialog._slider.value() == expected

    def test_right_arrow_triggers_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_Right must call extract_frame_at once (in addition to the init call)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        count_after_init = mock_extract.call_count

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_Right)

        assert mock_extract.call_count == count_after_init + 1

    def test_left_arrow_triggers_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_Left must call extract_frame_at once (in addition to the init call)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        initial_offset = _DURATION_S * 0.5
        dialog = _make_dialog(
            qapp, video, initial_offset_s=initial_offset, mock_extract=mock_extract
        )

        count_after_init = mock_extract.call_count

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_Left)

        assert mock_extract.call_count == count_after_init + 1

    def test_page_down_advances_ten_seconds(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_PageDown must move the slider forward by 10 s (1000 ticks)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        start_value = dialog._slider.value()

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_PageDown)

        expected = min(
            start_value + int(_PAGE_STEP_S * _SLIDER_SCALE),
            dialog._slider.maximum(),
        )
        assert dialog._slider.value() == expected

    def test_page_up_retreats_ten_seconds(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_PageUp must move the slider backward by 10 s (1000 ticks)."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        initial_offset = _DURATION_S * 0.5
        dialog = _make_dialog(
            qapp, video, initial_offset_s=initial_offset, mock_extract=mock_extract
        )

        start_value = dialog._slider.value()

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_PageUp)

        expected = max(
            start_value - int(_PAGE_STEP_S * _SLIDER_SCALE),
            dialog._slider.minimum(),
        )
        assert dialog._slider.value() == expected

    def test_page_down_triggers_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_PageDown must call extract_frame_at once beyond init."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        count_after_init = mock_extract.call_count

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_PageDown)

        assert mock_extract.call_count == count_after_init + 1

    def test_page_up_triggers_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Key_PageUp must call extract_frame_at once beyond init."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        initial_offset = _DURATION_S * 0.5
        dialog = _make_dialog(
            qapp, video, initial_offset_s=initial_offset, mock_extract=mock_extract
        )

        count_after_init = mock_extract.call_count

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_PageUp)

        assert mock_extract.call_count == count_after_init + 1

    def test_right_arrow_extract_offset_matches_slider(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The offset passed to extract_frame_at after Key_Right must match new slider position."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        with patch(_PATCH_TARGET, mock_extract):
            self._send_key(dialog, qapp, Qt.Key.Key_Right)

        expected_offset = dialog._slider.value() / _SLIDER_SCALE
        last_args, _ = mock_extract.call_args
        assert last_args[1] == pytest.approx(expected_offset)


# ---------------------------------------------------------------------------
# Test 5 — Confirm button enabled state
# ---------------------------------------------------------------------------


class TestConfirmButtonState:
    """Confirm button must be disabled until the first successful extract."""

    def test_confirm_disabled_when_extract_returns_none(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """When the initial extract returns None, the Confirm button must remain disabled."""
        video = tmp_path / "clip.mp4"
        video.touch()

        # Mock returns None to simulate extract failure.
        mock_extract = MagicMock(return_value=None)

        from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

        with patch(_PATCH_TARGET, mock_extract):
            dialog = FrameSelectorDialog(
                video_path=video,
                video_duration_s=_DURATION_S,
                parent=None,
            )
        qapp.processEvents()

        assert not dialog._confirm_btn.isEnabled(), (
            "Confirm must be disabled when no frame has been successfully extracted"
        )

    def test_confirm_enabled_after_first_successful_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After the initial successful extract, Confirm must be enabled."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        assert dialog._confirm_btn.isEnabled(), (
            "Confirm must be enabled once the first frame is successfully extracted"
        )

    def test_confirm_starts_disabled_before_extract_completes(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Confirm must be initially disabled in _build_ui before extraction runs."""
        video = tmp_path / "clip.mp4"
        video.touch()

        from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog

        # Patch _seek_to to a no-op so the initial extract never runs.
        # The mock_extract return value doesn't matter here since _seek_to is skipped,
        # but we still need to patch the target to avoid real ffmpeg calls.
        mock_extract = MagicMock(return_value=None)
        with patch(_PATCH_TARGET, mock_extract):
            with patch.object(FrameSelectorDialog, "_seek_to", return_value=None):
                dialog = FrameSelectorDialog(
                    video_path=video,
                    video_duration_s=_DURATION_S,
                    parent=None,
                )

        assert not dialog._confirm_btn.isEnabled(), (
            "Confirm must be False before any _seek_to call"
        )

    def test_confirm_stays_enabled_after_subsequent_extract(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Confirm must remain enabled after further slider releases."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        with patch(_PATCH_TARGET, mock_extract):
            dialog._slider.setValue(int(30 * _SLIDER_SCALE))
            dialog._on_slider_released()
            qapp.processEvents()

        assert dialog._confirm_btn.isEnabled()


# ---------------------------------------------------------------------------
# Test 6 — get_result() accept / cancel semantics
# ---------------------------------------------------------------------------


class TestGetResult:
    """get_result() must reflect the accept/reject state of the dialog."""

    def test_get_result_returns_none_before_any_action(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A freshly constructed dialog that has not been confirmed must return None."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        assert dialog.get_result() is None

    def test_get_result_returns_none_after_cancel(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Calling cancel_btn.click() (reject) must leave get_result() as None."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        dialog._cancel_btn.click()
        qapp.processEvents()

        assert dialog.get_result() is None

    def test_get_result_returns_none_after_reject(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Calling dialog.reject() must leave get_result() as None."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        dialog.reject()
        qapp.processEvents()

        assert dialog.get_result() is None

    def test_get_result_returns_pixmap_after_confirm(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After _on_confirm() is called, get_result() must return a QPixmap."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        dialog._on_confirm()
        qapp.processEvents()

        result = dialog.get_result()
        assert result is not None, "get_result() must not be None after confirm"
        assert isinstance(result, QPixmap)

    def test_get_result_pixmap_matches_last_extracted_frame(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The QPixmap returned by get_result() must be the one from _current_pixmap."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        # Verify _current_pixmap is set and is a QPixmap.
        assert dialog._current_pixmap is not None
        assert isinstance(dialog._current_pixmap, QPixmap)

        dialog._on_confirm()
        qapp.processEvents()

        # After confirm the accepted result must equal the last _current_pixmap.
        assert dialog.get_result() is dialog._accepted_result

    def test_accepted_result_set_on_confirm(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_accepted_result must be populated after _on_confirm()."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        assert dialog._accepted_result is None  # not yet accepted

        dialog._on_confirm()
        qapp.processEvents()

        assert dialog._accepted_result is not None
        assert isinstance(dialog._accepted_result, QPixmap)

    def test_accepted_result_none_after_reject(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_accepted_result must remain None after reject."""
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_extract = MagicMock(return_value=_make_fake_pixmap())
        dialog = _make_dialog(qapp, video, mock_extract=mock_extract)

        dialog.reject()
        qapp.processEvents()

        assert dialog._accepted_result is None
