"""Tests for src/video/frame_extract.py::extract_frame_at.

All tests mock subprocess.run so that no real ffmpeg process is spawned and the
suite runs cleanly on machines where ffmpeg is absent.

The QApplication singleton is created once for the session (offscreen QPA) so
QPixmap objects can be constructed in headless CI environments.  This follows
the same pattern established in tests/test_main_window.py.

Heavy ML dependencies that are transitively pulled through the project's import
chain are stubbed before any project import.

Coverage:
- Missing video file: returns None immediately and logs a warning; no
  subprocess.run call is made.
- ffmpeg binary not on PATH (FileNotFoundError from subprocess.run): returns
  None and reports via _report_error.
- ffmpeg exits with non-zero returncode: returns None and reports error.
- ffmpeg succeeds but QPixmap.isNull() is True (bad JPEG): returns None and
  reports error.
- ffmpeg succeeds and produces a valid 1x1 JPEG: returns a non-null QPixmap;
  temporary file is cleaned up.
- Negative offset is clamped to 0 before building the ffmpeg command.
"""

import os
import sys
import subprocess
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so absolute imports resolve.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pre-emptively stub heavy ML deps — same technique as test_main_window.py.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]

from src.video.frame_extract import extract_frame_at  # noqa: E402 (after stubs)


# ---------------------------------------------------------------------------
# Session-scoped QApplication fixture (headless)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the singleton QApplication, creating it if necessary."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helper: build a minimal valid JPEG byte string via QPixmap
# ---------------------------------------------------------------------------


def _make_jpeg_bytes(qapp: QApplication) -> bytes:
    """Return a valid minimal JPEG as bytes (1x1 white pixel).

    Requires a live QApplication to call QPixmap.save().

    Args:
        qapp: The active QApplication instance.

    Returns:
        Raw JPEG bytes for a 1x1 white pixel image.
    """
    px = QPixmap(1, 1)
    px.fill()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out_path = Path(f.name)
    px.save(str(out_path), "JPEG")
    data = out_path.read_bytes()
    out_path.unlink()
    return data


# ---------------------------------------------------------------------------
# Fake subprocess.CompletedProcess builder
# ---------------------------------------------------------------------------


def _completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    """Return a subprocess.CompletedProcess with the given attributes.

    Args:
        returncode: The simulated process exit code.
        stderr: The simulated stderr text.

    Returns:
        A CompletedProcess instance.
    """
    return subprocess.CompletedProcess(
        args=["ffmpeg"],
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Test group 1: missing video — early return without touching subprocess
# ---------------------------------------------------------------------------


class TestMissingVideoEarlyReturn:
    """extract_frame_at returns None immediately when the video file is absent."""

    def test_returns_none_for_missing_video(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A non-existent path must cause an immediate None return."""
        missing = tmp_path / "no_such_file.mp4"
        assert not missing.exists()

        with patch("src.video.frame_extract.subprocess.run") as mock_run:
            result = extract_frame_at(missing, 5.0)

        assert result is None
        mock_run.assert_not_called()

    def test_logs_warning_for_missing_video(
        self, qapp: QApplication, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning must be emitted to the module logger when the file is absent."""
        import logging

        missing = tmp_path / "ghost.mp4"
        with patch("src.video.frame_extract.subprocess.run"):
            with caplog.at_level(logging.WARNING, logger="src.video.frame_extract"):
                extract_frame_at(missing, 5.0)

        assert any("does not exist" in rec.message for rec in caplog.records), (
            "Expected a 'does not exist' warning in the log"
        )


# ---------------------------------------------------------------------------
# Test group 2: ffmpeg binary missing (FileNotFoundError)
# ---------------------------------------------------------------------------


class TestFfmpegMissing:
    """When ffmpeg is not on PATH, extract_frame_at returns None without crashing."""

    def test_returns_none_when_ffmpeg_missing(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """FileNotFoundError from subprocess.run must be caught; None returned."""
        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            side_effect=FileNotFoundError("ffmpeg: not found"),
        ):
            result = extract_frame_at(video, 5.0)

        assert result is None

    def test_no_parent_widget_suppresses_modal_on_ffmpeg_missing(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """With parent_widget=None, QMessageBox.critical must NOT be called."""
        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with patch("src.video.frame_extract.QMessageBox") as mock_msgbox:
                extract_frame_at(video, 5.0, parent_widget=None)

        mock_msgbox.critical.assert_not_called()

    def test_with_parent_widget_shows_modal_on_ffmpeg_missing(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """With a parent widget, QMessageBox.critical must be called once."""
        video = tmp_path / "match.mp4"
        video.touch()
        fake_parent = MagicMock()

        with patch(
            "src.video.frame_extract.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with patch("src.video.frame_extract.QMessageBox") as mock_msgbox:
                extract_frame_at(video, 5.0, parent_widget=fake_parent)

        mock_msgbox.critical.assert_called_once()

    def test_logs_warning_when_ffmpeg_missing_no_parent(
        self, qapp: QApplication, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When parent_widget is None, a warning must be logged for a missing ffmpeg."""
        import logging

        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with caplog.at_level(logging.WARNING, logger="src.video.frame_extract"):
                extract_frame_at(video, 5.0, parent_widget=None)

        assert caplog.records, "Expected at least one warning log record"


# ---------------------------------------------------------------------------
# Test group 3: ffmpeg non-zero exit code
# ---------------------------------------------------------------------------


class TestFfmpegNonZeroExit:
    """When ffmpeg returns a non-zero exit code, extract_frame_at returns None."""

    def test_returns_none_on_nonzero_returncode(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """Non-zero returncode from ffmpeg must produce None."""
        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            return_value=_completed(returncode=1, stderr="codec error"),
        ):
            result = extract_frame_at(video, 5.0)

        assert result is None

    def test_no_modal_without_parent_on_nonzero_exit(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """With parent_widget=None, QMessageBox.critical must not be called."""
        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            return_value=_completed(returncode=2, stderr="fatal error"),
        ):
            with patch("src.video.frame_extract.QMessageBox") as mock_msgbox:
                extract_frame_at(video, 5.0, parent_widget=None)

        mock_msgbox.critical.assert_not_called()

    def test_modal_shown_with_parent_on_nonzero_exit(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """With a parent widget, QMessageBox.critical must be called once."""
        video = tmp_path / "match.mp4"
        video.touch()
        fake_parent = MagicMock()

        with patch(
            "src.video.frame_extract.subprocess.run",
            return_value=_completed(returncode=1, stderr="codec error"),
        ):
            with patch("src.video.frame_extract.QMessageBox") as mock_msgbox:
                extract_frame_at(video, 5.0, parent_widget=fake_parent)

        mock_msgbox.critical.assert_called_once()

    def test_logs_warning_without_parent_on_nonzero_exit(
        self, qapp: QApplication, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning must be logged when ffmpeg fails and parent_widget is None."""
        import logging

        video = tmp_path / "match.mp4"
        video.touch()

        with patch(
            "src.video.frame_extract.subprocess.run",
            return_value=_completed(returncode=1, stderr="codec error"),
        ):
            with caplog.at_level(logging.WARNING, logger="src.video.frame_extract"):
                extract_frame_at(video, 5.0, parent_widget=None)

        assert caplog.records, "Expected a warning log record for non-zero ffmpeg exit"


# ---------------------------------------------------------------------------
# Test group 4: null QPixmap (bad JPEG written by ffmpeg)
# ---------------------------------------------------------------------------


class TestNullPixmap:
    """When QPixmap.isNull() is True after loading the temp file, return None."""

    def test_returns_none_when_pixmap_is_null(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A null QPixmap (unreadable image data) must result in None."""
        video = tmp_path / "match.mp4"
        video.touch()

        def _fake_run(cmd, **kwargs):
            # Locate the tmp output path (last positional arg before '-y')
            # and write zero bytes so QPixmap cannot load it.
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(b"not a jpeg")
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            result = extract_frame_at(video, 5.0, parent_widget=None)

        assert result is None

    def test_no_modal_without_parent_when_pixmap_null(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """With parent_widget=None, no QMessageBox.critical call for a null pixmap."""
        video = tmp_path / "match.mp4"
        video.touch()

        def _fake_run(cmd, **kwargs):
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(b"\x00\x01")
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            with patch("src.video.frame_extract.QMessageBox") as mock_msgbox:
                extract_frame_at(video, 5.0, parent_widget=None)

        mock_msgbox.critical.assert_not_called()


# ---------------------------------------------------------------------------
# Test group 5: success path
# ---------------------------------------------------------------------------


class TestSuccessPath:
    """When ffmpeg succeeds and the JPEG is valid, a non-null QPixmap is returned."""

    def test_returns_non_null_pixmap_on_success(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """A valid JPEG written by ffmpeg must produce a non-null QPixmap."""
        video = tmp_path / "match.mp4"
        video.touch()
        jpeg_bytes = _make_jpeg_bytes(qapp)

        def _fake_run(cmd, **kwargs):
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(jpeg_bytes)
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            result = extract_frame_at(video, 5.0)

        assert result is not None
        assert not result.isNull()

    def test_temp_file_cleaned_up_on_success(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The temporary JPEG file must be deleted after successful QPixmap load."""
        video = tmp_path / "match.mp4"
        video.touch()
        jpeg_bytes = _make_jpeg_bytes(qapp)

        captured_tmp: list[Path] = []

        def _fake_run(cmd, **kwargs):
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            captured_tmp.append(out_path)
            out_path.write_bytes(jpeg_bytes)
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            extract_frame_at(video, 5.0)

        assert captured_tmp, "Expected the fake_run side-effect to record a tmp path"
        assert not captured_tmp[0].exists(), (
            f"Temp file {captured_tmp[0]} must be deleted after successful extraction"
        )

    def test_ffmpeg_called_with_correct_offset(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The -ss argument passed to ffmpeg must equal offset_s."""
        video = tmp_path / "match.mp4"
        video.touch()
        jpeg_bytes = _make_jpeg_bytes(qapp)

        run_calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            run_calls.append(list(cmd))
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(jpeg_bytes)
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            extract_frame_at(video, 12.5)

        assert run_calls, "subprocess.run must have been called"
        cmd = run_calls[0]
        ss_idx = cmd.index("-ss")
        assert cmd[ss_idx + 1] == "12.5", (
            f"Expected -ss 12.5 in ffmpeg command, got {cmd!r}"
        )


# ---------------------------------------------------------------------------
# Test group 6: negative offset clamp
# ---------------------------------------------------------------------------


class TestNegativeOffsetClamp:
    """Negative offset_s values must be clamped to 0 before the ffmpeg call."""

    def test_negative_offset_clamped_to_zero(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """The -ss flag must be '0.0' when offset_s < 0."""
        video = tmp_path / "match.mp4"
        video.touch()
        jpeg_bytes = _make_jpeg_bytes(qapp)

        run_calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            run_calls.append(list(cmd))
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(jpeg_bytes)
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            result = extract_frame_at(video, -30.0)

        assert result is not None, "Should still succeed after clamp"
        assert run_calls, "subprocess.run must have been called"
        cmd = run_calls[0]
        ss_idx = cmd.index("-ss")
        ss_value = float(cmd[ss_idx + 1])
        assert ss_value == 0.0, (
            f"Negative offset must be clamped to 0.0, got {ss_value}"
        )

    def test_zero_offset_unchanged(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        """An offset of exactly 0 must pass through unchanged (no alteration)."""
        video = tmp_path / "match.mp4"
        video.touch()
        jpeg_bytes = _make_jpeg_bytes(qapp)

        run_calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            run_calls.append(list(cmd))
            out_idx = cmd.index("-y") - 1
            out_path = Path(cmd[out_idx])
            out_path.write_bytes(jpeg_bytes)
            return _completed(returncode=0)

        with patch("src.video.frame_extract.subprocess.run", side_effect=_fake_run):
            extract_frame_at(video, 0.0)

        cmd = run_calls[0]
        ss_value = float(cmd[cmd.index("-ss") + 1])
        assert ss_value == 0.0
