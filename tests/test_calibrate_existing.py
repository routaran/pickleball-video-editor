"""Tests for ml/tools/calibrate_existing.py.

A QApplication is created once per session via the module-level fixture so
that PyQt6 does not complain about widgets created without an application.

QT_QPA_PLATFORM is set to "offscreen" before any Qt import so the suite
runs in headless CI environments — matching the pattern used in
tests/test_court_calibrator.py.

Heavy ML and torch dependencies are stubbed before any project import so the
module loads cleanly on machines that have not run ``./configure --enable-ml``.

Test coverage:
- ``--auto-frame`` flag: ``_process_file`` calls ``_extract_frame_pixmap`` at
  5% of the video duration (the original behavior preserved for back-compat).
- Interactive path (no ``--auto-frame``): ``FramePickerDialog`` is constructed
  with the correct video path; when it returns Accepted, the returned pixmap
  flows into ``_run_calibration_dialog``.
- ``_process_file`` returns ``_Result.SKIPPED`` when the user cancels
  ``FramePickerDialog`` (interactive path, dialog not accepted).
- Files that already have ``court_corners`` are skipped without showing any dialog.
- ``_process_file`` returns ``_Result.UPDATED`` and writes corners back to JSON
  when the full accept flow completes.
"""

import json
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

from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so absolute imports resolve.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pre-emptively stub heavy deps (torch, ml.predict, ml.auto_edit, decord).
# calibrate_existing.py imports FramePickerDialog which lazily imports decord,
# but the module-level import chain from src.ui still needs torch stubs.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]

if "decord" not in sys.modules:
    _decord_stub = types.ModuleType("decord")
    _decord_stub.VideoReader = MagicMock  # type: ignore[attr-defined]
    _decord_stub.bridge = types.SimpleNamespace(set_bridge=MagicMock())  # type: ignore[attr-defined]
    sys.modules["decord"] = _decord_stub  # type: ignore[assignment]

from ml.tools.calibrate_existing import _process_file, _Result, _probe_duration


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


def _make_1x1_pixmap() -> QPixmap:
    """Return a valid 1×1 white QPixmap.

    Returns:
        A non-null 1×1 QPixmap suitable as a stub frame.
    """
    px = QPixmap(1, 1)
    px.fill()
    return px


def _write_training_json(path: Path, court_corners: list | None = None) -> None:
    """Write a minimal .training.json fixture to *path*.

    Args:
        path:          Where to write the JSON file.
        court_corners: If given, set ``video.court_corners`` in the fixture so
                       the file appears already calibrated.
    """
    data: dict = {
        "schema_version": "1.0",
        "video": {
            "path": str(path.parent / "clip.mp4"),
        },
        "rallies": [],
    }
    if court_corners is not None:
        data["video"]["court_corners"] = court_corners
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1 — already-calibrated files are skipped (no dialog opened)
# ---------------------------------------------------------------------------


class TestAlreadyCalibratedSkipped:
    """Files with existing court_corners must be skipped without any dialog."""

    def test_returns_skipped_for_calibrated_file(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_process_file must return SKIPPED and not open any dialog when
        court_corners is already present in the JSON."""
        json_path = tmp_path / "game.training.json"
        _write_training_json(json_path, court_corners=[[1, 2], [3, 4], [5, 6], [7, 8]])

        with patch(
            "ml.tools.calibrate_existing._run_calibration_dialog"
        ) as mock_dialog:
            result = _process_file(qapp, json_path, auto_frame=True)

        assert result is _Result.SKIPPED
        mock_dialog.assert_not_called()

    def test_skipped_for_calibrated_file_interactive_path(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """SKIPPED even on the interactive path when corners already exist."""
        json_path = tmp_path / "game.training.json"
        _write_training_json(json_path, court_corners=[[1, 2], [3, 4], [5, 6], [7, 8]])

        with patch("ml.tools.calibrate_existing.FramePickerDialog") as MockPicker:
            result = _process_file(qapp, json_path, auto_frame=False)

        assert result is _Result.SKIPPED
        MockPicker.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — missing video returns SKIPPED (both paths)
# ---------------------------------------------------------------------------


class TestMissingVideoSkipped:
    """Files whose referenced video does not exist must be skipped gracefully."""

    def test_auto_frame_skips_missing_video(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_process_file(auto_frame=True) must return SKIPPED for a missing video."""
        json_path = tmp_path / "game.training.json"
        _write_training_json(json_path)
        # The clip.mp4 that _write_training_json references does NOT exist.

        result = _process_file(qapp, json_path, auto_frame=True)

        assert result is _Result.SKIPPED

    def test_interactive_skips_missing_video(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_process_file(auto_frame=False) must return SKIPPED for a missing video."""
        json_path = tmp_path / "game.training.json"
        _write_training_json(json_path)

        with patch("ml.tools.calibrate_existing.FramePickerDialog") as MockPicker:
            result = _process_file(qapp, json_path, auto_frame=False)

        assert result is _Result.SKIPPED
        MockPicker.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — --auto-frame path preserves 5%-extraction behavior
# ---------------------------------------------------------------------------


class TestAutoFramePath:
    """``auto_frame=True`` must call _extract_frame_pixmap at 5% of the duration."""

    def test_extract_frame_pixmap_called_at_five_percent(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_extract_frame_pixmap must be called with offset = duration * 0.05."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_duration = 100.0
        expected_offset = fake_duration * 0.05
        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[10, 20], [30, 40], [50, 60], [70, 80]]

        with patch(
            "ml.tools.calibrate_existing._probe_duration",
            return_value=fake_duration,
        ) as mock_probe:
            with patch(
                "ml.tools.calibrate_existing._extract_frame_pixmap",
                return_value=fake_pixmap,
            ) as mock_extract:
                with patch(
                    "ml.tools.calibrate_existing._run_calibration_dialog",
                    return_value=fake_corners,
                ):
                    result = _process_file(qapp, json_path, auto_frame=True)

        mock_probe.assert_called_once_with(video)
        mock_extract.assert_called_once_with(video, pytest.approx(expected_offset))
        assert result is _Result.UPDATED

    def test_frame_picker_dialog_not_called_in_auto_frame_mode(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """FramePickerDialog must never be instantiated when auto_frame=True."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[1, 2], [3, 4], [5, 6], [7, 8]]

        with patch("ml.tools.calibrate_existing._probe_duration", return_value=60.0):
            with patch(
                "ml.tools.calibrate_existing._extract_frame_pixmap",
                return_value=fake_pixmap,
            ):
                with patch(
                    "ml.tools.calibrate_existing._run_calibration_dialog",
                    return_value=fake_corners,
                ):
                    with patch(
                        "ml.tools.calibrate_existing.FramePickerDialog"
                    ) as MockPicker:
                        _process_file(qapp, json_path, auto_frame=True)

        MockPicker.assert_not_called()

    def test_auto_frame_skips_when_extract_returns_none(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """When _extract_frame_pixmap returns None, _process_file returns SKIPPED."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        with patch("ml.tools.calibrate_existing._probe_duration", return_value=60.0):
            with patch(
                "ml.tools.calibrate_existing._extract_frame_pixmap",
                return_value=None,
            ):
                result = _process_file(qapp, json_path, auto_frame=True)

        assert result is _Result.SKIPPED


# ---------------------------------------------------------------------------
# Test 4 — interactive path (no --auto-frame) uses FramePickerDialog
# ---------------------------------------------------------------------------


class TestInteractivePath:
    """``auto_frame=False`` must open FramePickerDialog and use its returned pixmap."""

    def test_frame_picker_constructed_with_video_path(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """FramePickerDialog must be instantiated with the correct video_path."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[10, 20], [30, 40], [50, 60], [70, 80]]

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_picker_instance.get_result.return_value = fake_pixmap

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ) as MockPicker:
            with patch(
                "ml.tools.calibrate_existing._run_calibration_dialog",
                return_value=fake_corners,
            ):
                _process_file(qapp, json_path, auto_frame=False)

        MockPicker.assert_called_once_with(video)

    def test_extract_frame_pixmap_not_called_in_interactive_mode(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_extract_frame_pixmap must not be called when auto_frame=False."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[1, 2], [3, 4], [5, 6], [7, 8]]

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_picker_instance.get_result.return_value = fake_pixmap

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ):
            with patch(
                "ml.tools.calibrate_existing._run_calibration_dialog",
                return_value=fake_corners,
            ):
                with patch(
                    "ml.tools.calibrate_existing._extract_frame_pixmap"
                ) as mock_extract:
                    _process_file(qapp, json_path, auto_frame=False)

        mock_extract.assert_not_called()

    def test_picker_pixmap_passed_to_calibration_dialog(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The pixmap from FramePickerDialog.get_result() must be forwarded to
        _run_calibration_dialog as its second positional argument."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[10, 20], [30, 40], [50, 60], [70, 80]]

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_picker_instance.get_result.return_value = fake_pixmap

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ):
            with patch(
                "ml.tools.calibrate_existing._run_calibration_dialog",
                return_value=fake_corners,
            ) as mock_run:
                _process_file(qapp, json_path, auto_frame=False)

        # The second positional arg to _run_calibration_dialog is the pixmap.
        assert mock_run.call_count == 1
        _, call_pixmap, _ = mock_run.call_args.args
        assert call_pixmap is fake_pixmap, (
            "The pixmap from FramePickerDialog must be forwarded verbatim to "
            "_run_calibration_dialog"
        )

    def test_returns_skipped_when_picker_cancelled(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """If the user cancels FramePickerDialog, _process_file returns SKIPPED."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Rejected

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ):
            result = _process_file(qapp, json_path, auto_frame=False)

        assert result is _Result.SKIPPED

    def test_calibration_dialog_not_called_when_picker_cancelled(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """_run_calibration_dialog must not be called if FramePickerDialog is rejected."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Rejected

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ):
            with patch(
                "ml.tools.calibrate_existing._run_calibration_dialog"
            ) as mock_run:
                _process_file(qapp, json_path, auto_frame=False)

        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — full accept flow writes corners to JSON and bumps schema_version
# ---------------------------------------------------------------------------


class TestFullAcceptFlowWritesJson:
    """_process_file must persist corners to JSON and bump schema to 1.1 on success."""

    def test_auto_frame_writes_corners_to_json(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After a successful auto-frame calibration, corners appear in the JSON file."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data: dict = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[10, 20], [30, 40], [50, 60], [70, 80]]

        with patch("ml.tools.calibrate_existing._probe_duration", return_value=100.0):
            with patch(
                "ml.tools.calibrate_existing._extract_frame_pixmap",
                return_value=fake_pixmap,
            ):
                with patch(
                    "ml.tools.calibrate_existing._run_calibration_dialog",
                    return_value=fake_corners,
                ):
                    result = _process_file(qapp, json_path, auto_frame=True)

        assert result is _Result.UPDATED

        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["video"]["court_corners"] == fake_corners
        assert saved["schema_version"] == "1.1"

    def test_interactive_writes_corners_to_json(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """After a successful interactive calibration, corners appear in the JSON file."""
        json_path = tmp_path / "game.training.json"
        video = tmp_path / "clip.mp4"
        video.touch()

        data: dict = {
            "schema_version": "1.0",
            "video": {"path": str(video)},
            "rallies": [],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        fake_pixmap = _make_1x1_pixmap()
        fake_corners = [[11, 22], [33, 44], [55, 66], [77, 88]]

        mock_picker_instance = MagicMock()
        mock_picker_instance.exec.return_value = QDialog.DialogCode.Accepted
        mock_picker_instance.get_result.return_value = fake_pixmap

        with patch(
            "ml.tools.calibrate_existing.FramePickerDialog",
            return_value=mock_picker_instance,
        ):
            with patch(
                "ml.tools.calibrate_existing._run_calibration_dialog",
                return_value=fake_corners,
            ):
                result = _process_file(qapp, json_path, auto_frame=False)

        assert result is _Result.UPDATED

        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["video"]["court_corners"] == fake_corners
        assert saved["schema_version"] == "1.1"
