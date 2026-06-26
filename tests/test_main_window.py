"""Tests for src/ui/main_window.py — Mark Court Corners flow.

A QApplication is created once per session via the module-level fixture so
that PyQt6 does not complain about widgets created without an application.

The tests set QT_QPA_PLATFORM to "offscreen" before any Qt import so the
suite runs in headless CI environments — matching the pattern used in
tests/test_court_calibrator.py.

Heavy ML dependencies that are transitively imported through the UI layer are
stubbed before any project import so the module loads cleanly on machines that
have not run ``./configure --enable-ml``.

Test coverage:
- ``btn_mark_corners`` button exists and is connected to ``_on_mark_court_corners``.
- When ``get_current_frame_pixmap`` returns a 1×1 QPixmap, accepting the calibrator
  dialog writes four corners to ``config.court_corners`` and sets ``_dirty = True``.
- When ``get_current_frame_pixmap`` returns ``None``, a warning toast is shown and
  no dialog is opened (``CourtCalibratorWidget`` is never constructed).
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDialog,
    QWidget,
)

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so absolute imports resolve.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pre-emptively stub heavy ML deps that are not installed in the base
# environment.  The same technique is used in test_frame_picker_dialog.py.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]

from src.core.app_config import AppSettings, ShortcutConfig
from src.ui.responsive import LayoutMode
from src.ui.setup_dialog import GameConfig
from src.ui.main_window import MainWindow


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
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> GameConfig:
    """Return a minimal GameConfig pointing at a touch-created video stub.

    Args:
        tmp_path: pytest temporary directory for this test.

    Returns:
        GameConfig with singles/11 rules and two single-player teams.
    """
    video = tmp_path / "match.mp4"
    video.touch()
    return GameConfig(
        video_path=video,
        game_type="singles",
        victory_rule="11",
        team1_players=["Alice"],
        team2_players=["Bob"],
    )


def _make_window(
    qapp: QApplication,
    config: GameConfig,
    app_settings: AppSettings | None = None,
) -> MainWindow:
    """Construct a MainWindow without spawning a real MPV player.

    ``VideoWidget._create_player`` is patched to a no-op so that the window
    builds fully (all buttons, all signal connections) while ``_player``
    stays ``None``.  Tests then inject a mock ``_player`` or a mock return
    value for ``get_current_frame_pixmap`` as needed.

    Args:
        qapp: Active QApplication (ensures Qt is live).
        config: Game configuration.

    Returns:
        Fully constructed MainWindow with MPV creation suppressed.
    """
    with patch("src.video.player.VideoWidget._create_player"):
        window = MainWindow(config, app_settings=app_settings)
    qapp.processEvents()
    return window


def _make_1x1_pixmap() -> QPixmap:
    """Return a valid 1×1 QPixmap (white fill).

    Returns:
        A non-null 1×1 QPixmap.
    """
    px = QPixmap(1, 1)
    px.fill()
    return px


# ---------------------------------------------------------------------------
# Test 1 — button wiring
# ---------------------------------------------------------------------------


class TestMarkCornerButtonWiring:
    """The Mark Court Corners button must exist and connect to the slot."""

    def test_button_exists(self, qapp: QApplication, tmp_path: Path) -> None:
        """MainWindow must have a ``btn_mark_corners`` QPushButton attribute."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert hasattr(window, "btn_mark_corners"), (
            "MainWindow must expose btn_mark_corners as an instance attribute"
        )

    def test_button_object_name(self, qapp: QApplication, tmp_path: Path) -> None:
        """The button's objectName must be 'markCornersButton' for stylesheet targeting."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.btn_mark_corners.objectName() == "markCornersButton"

    def test_button_click_invokes_slot(self, qapp: QApplication, tmp_path: Path) -> None:
        """Clicking btn_mark_corners must invoke _on_mark_court_corners."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)

        called: list[bool] = []

        original_slot = window._on_mark_court_corners

        def _tracking_slot() -> None:
            called.append(True)
            original_slot()

        window.btn_mark_corners.clicked.disconnect()
        window.btn_mark_corners.clicked.connect(_tracking_slot)

        # Suppress any dialog that opens by making get_current_frame_pixmap return None.
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=None)

        window.btn_mark_corners.click()
        qapp.processEvents()

        assert called, "Clicking btn_mark_corners must call _on_mark_court_corners"


# ---------------------------------------------------------------------------
# Test 2 — touch counter shortcut wiring
# ---------------------------------------------------------------------------


class TestTouchCounterShortcutWiring:
    """Manual touch-counter shortcuts must stay reachable."""

    def test_r_alias_created_when_receiver_wins_does_not_use_r(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """R increments the Me/Ravi counter when R is otherwise free."""
        config = _make_config(tmp_path)
        settings = AppSettings(
            shortcuts=ShortcutConfig(
                rally_start="A",
                server_wins="S",
                receiver_wins="D",
                undo="U",
                ravi_touch="J",
                partner_touch="E",
            )
        )

        window = _make_window(qapp, config, app_settings=settings)

        assert window._shortcut_ravi_touch_r_alias is not None
        assert window._shortcut_undo_ravi_touch_r_alias is not None


# ---------------------------------------------------------------------------
# Test 3 — ultrawide bottom drawer layout
# ---------------------------------------------------------------------------


class TestUltrawideBottomDrawerLayout:
    """Ultrawide editing mode keeps video dominant with a bottom drawer."""

    def test_ultrawide_collapses_secondary_controls_by_default(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A 3440×1440 window keeps panels at the bottom and hides the drawer."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)

        mode = window._responsive_manager.evaluate(QSize(3440, 1440))
        qapp.processEvents()

        assert mode is LayoutMode.ULTRAWIDE
        assert window.rally_controls_panel.parent() is window._stacked_panels
        assert window.toolbar_panel.parent() is window._stacked_panels
        assert window._ultrawide_right.isHidden()
        assert not window.btn_more_controls.isHidden()
        assert window.toolbar_panel.isHidden()
        assert (
            window.toolbar_panel.layout().direction()
            == QBoxLayout.Direction.LeftToRight
        )

    def test_more_button_toggles_secondary_drawer(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The More button reveals and hides secondary toolbar actions."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)

        window._responsive_manager.evaluate(QSize(3440, 1440))
        qapp.processEvents()

        window.btn_more_controls.click()
        qapp.processEvents()

        assert window._secondary_drawer_open
        assert not window.toolbar_panel.isHidden()
        assert window.btn_more_controls.text() == "Hide"

        window.btn_more_controls.click()
        qapp.processEvents()

        assert not window._secondary_drawer_open
        assert window.toolbar_panel.isHidden()
        assert window.btn_more_controls.text() == "More"

    def test_leaving_ultrawide_restores_secondary_controls(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Non-ultrawide modes show the regular toolbar and hide More."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)

        window._responsive_manager.evaluate(QSize(3440, 1440))
        window.btn_more_controls.click()
        window._responsive_manager.evaluate(QSize(1600, 1100))
        qapp.processEvents()

        assert window.toolbar_panel.parent() is window._stacked_panels
        assert not window.toolbar_panel.isHidden()
        assert window.btn_more_controls.isHidden()
        assert window.btn_more_controls.text() == "More"


# ---------------------------------------------------------------------------
# Test 3 — pixmap is None branch (warning toast, no dialog)
# ---------------------------------------------------------------------------


class TestMarkCornersNullPixmap:
    """When get_current_frame_pixmap returns None, show warning and do not open dialog."""

    def test_warning_shown_when_no_pixmap(self, qapp: QApplication, tmp_path: Path) -> None:
        """ToastManager.show_warning must be called when pixmap is None."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=None)

        with patch(
            "src.ui.main_window.ToastManager.show_warning"
        ) as mock_warning:
            window._on_mark_court_corners()
            qapp.processEvents()

        mock_warning.assert_called_once()
        call_args = mock_warning.call_args
        # First positional arg is the parent widget; second is the message string.
        message = call_args.args[1] if len(call_args.args) >= 2 else call_args.kwargs.get("message", "")
        assert "video" in message.lower() or "frame" in message.lower(), (
            f"Warning message should mention video or frame, got: {message!r}"
        )

    def test_no_dialog_opened_when_no_pixmap(self, qapp: QApplication, tmp_path: Path) -> None:
        """CourtCalibratorWidget must never be instantiated when pixmap is None."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=None)

        with patch(
            "src.ui.main_window.CourtCalibratorWidget"
        ) as mock_calibrator_cls:
            with patch("src.ui.main_window.ToastManager.show_warning"):
                window._on_mark_court_corners()
                qapp.processEvents()

        mock_calibrator_cls.assert_not_called()

    def test_dirty_flag_unchanged_when_no_pixmap(self, qapp: QApplication, tmp_path: Path) -> None:
        """_dirty must remain False when get_current_frame_pixmap returns None."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert not window._dirty

        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=None)

        with patch("src.ui.main_window.ToastManager.show_warning"):
            window._on_mark_court_corners()
            qapp.processEvents()

        assert not window._dirty, "_dirty must not be set when no frame is available"

    def test_court_corners_unchanged_when_no_pixmap(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """config.court_corners must remain None when get_current_frame_pixmap returns None."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.config.court_corners is None

        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=None)

        with patch("src.ui.main_window.ToastManager.show_warning"):
            window._on_mark_court_corners()
            qapp.processEvents()

        assert window.config.court_corners is None


# ---------------------------------------------------------------------------
# Test 3 — accepted calibrator path writes corners and sets _dirty
# ---------------------------------------------------------------------------


class _StubCalibratorWidget(QWidget):
    """Minimal QWidget stand-in for CourtCalibratorWidget used in accept-path tests.

    Records calls to ``cornersCaptured.connect`` and allows the test to trigger
    the slot immediately (synchronous emission) without needing a real pixmap or
    a real CourtCalibratorWidget.

    Attributes:
        _connect_slot: The slot registered by the caller via ``cornersCaptured.connect``.
    """

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._connect_slot: object = None
        # Expose a minimal cornersCaptured namespace that mirrors the real signal's
        # ``.connect()`` method.  This is the only attribute _on_mark_court_corners
        # uses on the calibrator object.
        self.cornersCaptured = _FakeSignal(self)

    def emit_corners(self, corners: list[list[int]]) -> None:
        """Call the registered slot with *corners*, simulating a real signal emit.

        Args:
            corners: The list of four [x, y] pairs to pass to the slot.
        """
        self.cornersCaptured._emit(corners)


class _FakeSignal:
    """Minimal stand-in for a PyQt signal that records connect() calls."""

    def __init__(self, owner: "_StubCalibratorWidget") -> None:
        self._owner = owner
        self._slot: object = None

    def connect(self, slot: object) -> None:
        """Record the connected slot.

        Args:
            slot: The callable connected by the caller.
        """
        self._slot = slot

    def _emit(self, corners: list[list[int]]) -> None:
        """Fire the stored slot with *corners*.

        Args:
            corners: Corners payload to forward.
        """
        if callable(self._slot):
            self._slot(corners)


def _run_accept_flow(
    qapp: QApplication,
    window: MainWindow,
    fake_corners: list[list[int]],
    *,
    accepted: bool,
) -> None:
    """Drive ``_on_mark_court_corners`` through a complete dialog cycle.

    Uses a real ``QDialog`` and a ``_StubCalibratorWidget`` so that
    ``QVBoxLayout(dialog)`` and ``layout.addWidget(calibrator)`` both succeed,
    while still allowing the test to control whether ``cornersCaptured`` fires
    and whether ``exec`` returns Accepted or Rejected.

    Args:
        qapp:         Active QApplication.
        window:       The MainWindow whose slot will be called.
        fake_corners: The corners payload to emit via the stub calibrator.
        accepted:     True to simulate Confirm; False to simulate Cancel.
    """
    accepted_code = QDialog.DialogCode.Accepted
    rejected_code = QDialog.DialogCode.Rejected

    stub_calibrator: _StubCalibratorWidget | None = None

    def _make_stub(pixmap: QPixmap, parent: QWidget | None = None) -> _StubCalibratorWidget:
        nonlocal stub_calibrator
        stub_calibrator = _StubCalibratorWidget(pixmap, parent=parent)
        return stub_calibrator

    def _fake_exec(self_dialog: QDialog) -> QDialog.DialogCode:
        """Emit corners and return the desired result code."""
        if accepted and stub_calibrator is not None:
            stub_calibrator.emit_corners(fake_corners)
        return accepted_code if accepted else rejected_code

    with patch("src.ui.main_window.CourtCalibratorWidget", side_effect=_make_stub):
        with patch.object(QDialog, "exec", _fake_exec):
            with patch("src.ui.main_window.ToastManager.show_success"):
                window._on_mark_court_corners()
                qapp.processEvents()


class TestReviewStateAnchorPostGame:
    """Regression coverage for converting PG cuts through Apply to Rally."""

    def test_apply_to_pg_rally_clears_post_game_and_updates_score(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A valid state anchor turns the selected PG cut back into a scored rally."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.score_state is not None

        snapshot = window.score_state.save_snapshot()
        window.rally_manager.start_rally(10.0, snapshot)
        rally = window.rally_manager.end_rally(15.0, "", "", snapshot)
        rally.is_post_game = True

        with patch("src.ui.main_window.ToastManager.show_success") as mock_success:
            with patch("src.ui.main_window.ToastManager.show_error") as mock_error:
                window._on_review_state_anchor_set(0, 0, "3-2")
                qapp.processEvents()

        assert rally.is_post_game is False
        assert rally.score_at_start == "3-2"
        assert rally.score_snapshot_at_start is not None
        assert rally.score_snapshot_at_start.score == (3, 2)
        assert rally.score_snapshot_at_start.serving_team == 0
        assert window._dirty is True
        mock_success.assert_called_once()
        mock_error.assert_not_called()

    def test_invalid_state_anchor_does_not_clear_post_game_flag(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Invalid Apply to Rally input must not convert a PG cut."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.score_state is not None

        snapshot = window.score_state.save_snapshot()
        window.rally_manager.start_rally(10.0, snapshot)
        rally = window.rally_manager.end_rally(15.0, "", "", snapshot)
        rally.is_post_game = True

        with patch("src.ui.main_window.ToastManager.show_success") as mock_success:
            with patch("src.ui.main_window.ToastManager.show_error") as mock_error:
                window._on_review_state_anchor_set(0, 0, "not-a-score")
                qapp.processEvents()

        assert rally.is_post_game is True
        assert rally.score_at_start == ""
        assert window._dirty is False
        mock_success.assert_not_called()
        mock_error.assert_called_once()


class TestMarkCornersAcceptPath:
    """When the user accepts the calibrator dialog, corners and dirty flag are set."""

    def test_court_corners_written_on_accept(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """config.court_corners must hold four [x,y] pairs after a successful calibration."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.config.court_corners is None

        pixmap = _make_1x1_pixmap()
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=pixmap)

        fake_corners: list[list[int]] = [[10, 20], [30, 40], [50, 60], [70, 80]]
        _run_accept_flow(qapp, window, fake_corners, accepted=True)

        assert window.config.court_corners is not None, (
            "config.court_corners must be set after successful calibration"
        )
        assert len(window.config.court_corners) == 4, (
            f"Expected 4 corners, got {len(window.config.court_corners)}"
        )

    def test_dirty_set_on_accept(self, qapp: QApplication, tmp_path: Path) -> None:
        """_dirty must be True after a successful calibration."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert not window._dirty

        pixmap = _make_1x1_pixmap()
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=pixmap)

        fake_corners: list[list[int]] = [[1, 2], [3, 4], [5, 6], [7, 8]]
        _run_accept_flow(qapp, window, fake_corners, accepted=True)

        assert window._dirty, "_dirty must be True after accepting the calibration dialog"

    def test_success_toast_shown_on_accept(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A success toast must be shown after the user confirms the calibration."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)

        pixmap = _make_1x1_pixmap()
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=pixmap)

        fake_corners: list[list[int]] = [[1, 2], [3, 4], [5, 6], [7, 8]]
        stub_holder: list[_StubCalibratorWidget] = []

        def _make_stub(px: QPixmap, parent: QWidget | None = None) -> _StubCalibratorWidget:
            stub = _StubCalibratorWidget(px, parent=parent)
            stub_holder.append(stub)
            return stub

        def _fake_exec(self_dialog: QDialog) -> QDialog.DialogCode:
            if stub_holder:
                stub_holder[0].emit_corners(fake_corners)
            return QDialog.DialogCode.Accepted

        with patch("src.ui.main_window.CourtCalibratorWidget", side_effect=_make_stub):
            with patch.object(QDialog, "exec", _fake_exec):
                with patch(
                    "src.ui.main_window.ToastManager.show_success"
                ) as mock_success:
                    window._on_mark_court_corners()
                    qapp.processEvents()

        mock_success.assert_called_once()

    def test_corners_not_set_on_cancel(self, qapp: QApplication, tmp_path: Path) -> None:
        """If the user cancels the dialog, config.court_corners must remain None."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert window.config.court_corners is None

        pixmap = _make_1x1_pixmap()
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=pixmap)

        _run_accept_flow(qapp, window, [], accepted=False)

        assert window.config.court_corners is None, (
            "config.court_corners must remain None when dialog is cancelled"
        )

    def test_dirty_not_set_on_cancel(self, qapp: QApplication, tmp_path: Path) -> None:
        """_dirty must remain False when the calibration dialog is cancelled."""
        config = _make_config(tmp_path)
        window = _make_window(qapp, config)
        assert not window._dirty

        pixmap = _make_1x1_pixmap()
        window.video_widget.get_current_frame_pixmap = MagicMock(return_value=pixmap)

        _run_accept_flow(qapp, window, [], accepted=False)

        assert not window._dirty, "_dirty must remain False when calibration is cancelled"
