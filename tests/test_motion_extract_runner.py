"""Unit tests for the out-of-process motion-feature extraction runner.

These exercise the GUI-safe orchestration logic (venv discovery, subprocess
lifecycle, cancellation, exit-code handling) without launching a real detector
or importing cv2/ultralytics.  A fake ``Popen`` stands in for the child.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.motion import extract_runner


# ---------------------------------------------------------------------------
# motion_venv_python
# ---------------------------------------------------------------------------


def test_motion_venv_python_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / ".venv-motion" / "bin"
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / "python"
    interpreter.touch()
    monkeypatch.setattr(extract_runner, "_PROJECT_ROOT", tmp_path)
    assert extract_runner.motion_venv_python() == interpreter


def test_motion_venv_python_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_runner, "_PROJECT_ROOT", tmp_path)  # no .venv-motion
    assert extract_runner.motion_venv_python() is None


# ---------------------------------------------------------------------------
# extract_features_subprocess
# ---------------------------------------------------------------------------

_CORNERS = [(100, 200), (800, 200), (800, 600), (100, 600)]


class _FakePopen:
    """Minimal stand-in for subprocess.Popen driven by a scripted poll sequence."""

    instances: list["_FakePopen"] = []

    def __init__(self, *args, poll_sequence, final_returncode, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._seq = list(poll_sequence)
        self._final = final_returncode
        self.returncode = None
        self.terminated = False
        self.killed = False
        _FakePopen.instances.append(self)

    def poll(self):
        if self._seq:
            val = self._seq.pop(0)
        else:
            val = self._final
        self.returncode = val
        return val

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def _install_fake(monkeypatch, *, poll_sequence, final_returncode):
    _FakePopen.instances.clear()
    monkeypatch.setattr(extract_runner, "motion_venv_python", lambda: Path("/fake/py"))

    def factory(*args, **kwargs):
        return _FakePopen(
            *args, poll_sequence=poll_sequence, final_returncode=final_returncode, **kwargs
        )

    monkeypatch.setattr(extract_runner.subprocess, "Popen", factory)


def test_returns_false_when_venv_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_runner, "motion_venv_python", lambda: None)

    def boom(*a, **k):  # Popen must never be called
        raise AssertionError("Popen should not be launched without a motion venv")

    monkeypatch.setattr(extract_runner.subprocess, "Popen", boom)
    ok = extract_runner.extract_features_subprocess(
        Path("/v.mp4"), _CORNERS, Path("/out"), poll_seconds=0.0
    )
    assert ok is False


def test_success_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake(monkeypatch, poll_sequence=[None, 0], final_returncode=0)
    phases: list[str] = []
    ok = extract_runner.extract_features_subprocess(
        Path("/v.mp4"), _CORNERS, Path("/out"),
        progress_cb=phases.append, poll_seconds=0.0,
    )
    assert ok is True
    assert phases and "motion features" in phases[0].lower()
    # Verify the child command carried the single-video contract.
    cmd = _FakePopen.instances[0].args[0]
    assert "--video" in cmd and "--corners-json" in cmd and "--out-dir" in cmd


def test_nonzero_exit_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake(monkeypatch, poll_sequence=[None, 1], final_returncode=1)
    ok = extract_runner.extract_features_subprocess(
        Path("/v.mp4"), _CORNERS, Path("/out"), poll_seconds=0.0
    )
    assert ok is False


def test_cancellation_terminates_child(monkeypatch: pytest.MonkeyPatch) -> None:
    # Child never finishes on its own; cancel fires on the first poll.
    _install_fake(monkeypatch, poll_sequence=[None, None, None], final_returncode=0)
    ok = extract_runner.extract_features_subprocess(
        Path("/v.mp4"), _CORNERS, Path("/out"),
        cancel_check=lambda: True, poll_seconds=0.0,
    )
    assert ok is False
    assert _FakePopen.instances[0].terminated is True


def test_launch_oserror_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_runner, "motion_venv_python", lambda: Path("/fake/py"))

    def raise_oserror(*a, **k):
        raise OSError("cannot exec")

    monkeypatch.setattr(extract_runner.subprocess, "Popen", raise_oserror)
    ok = extract_runner.extract_features_subprocess(
        Path("/v.mp4"), _CORNERS, Path("/out"), poll_seconds=0.0
    )
    assert ok is False
