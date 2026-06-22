"""Unit tests for the out-of-process motion-feature extraction runner.

These exercise the GUI-safe orchestration logic (venv discovery, subprocess
lifecycle, cancellation, exit-code handling) without launching a real detector
or importing cv2/ultralytics.  A fake ``Popen`` stands in for the child.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ml.motion import extract_runner


@pytest.fixture(autouse=True)
def _clear_motion_venv_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from a real $PICKLEBALL_MOTION_VENV in the environment."""
    monkeypatch.delenv(extract_runner.MOTION_VENV_ENV_VAR, raising=False)


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


def test_env_override_points_to_interpreter_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    interp = tmp_path / "custom-python"
    interp.touch()
    monkeypatch.setenv(extract_runner.MOTION_VENV_ENV_VAR, str(interp))
    # Even with no source-tree venv, the override wins.
    monkeypatch.setattr(extract_runner, "_PROJECT_ROOT", tmp_path)
    assert extract_runner.motion_venv_python() == interp


def test_env_override_points_to_venv_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "mv" / "bin"
    bin_dir.mkdir(parents=True)
    interp = bin_dir / "python"
    interp.touch()
    monkeypatch.setenv(extract_runner.MOTION_VENV_ENV_VAR, str(tmp_path / "mv"))
    assert extract_runner.motion_venv_python() == interp


def test_env_override_invalid_falls_back_to_source_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Override points nowhere usable; source-tree venv also absent -> None.
    monkeypatch.setenv(extract_runner.MOTION_VENV_ENV_VAR, str(tmp_path / "nope"))
    monkeypatch.setattr(extract_runner, "_PROJECT_ROOT", tmp_path)
    assert extract_runner.motion_venv_python() is None


def test_source_root_derivation() -> None:
    interp = Path("/home/u/repo/.venv-motion/bin/python")
    assert extract_runner._source_root_for(interp) == Path("/home/u/repo")


def test_source_root_ignores_bin_python_symlink(tmp_path: Path) -> None:
    # A venv's bin/python is a symlink to the base interpreter; deriving the
    # source root must NOT follow it (that would point at /usr/bin and lose the
    # repo). Regression test for the resolve()-follows-symlink bug.
    repo = tmp_path / "myrepo"
    bin_dir = repo / ".venv-motion" / "bin"
    bin_dir.mkdir(parents=True)
    base_bin = tmp_path / "usr" / "bin"
    base_bin.mkdir(parents=True)
    real_python = base_bin / "python3.14"
    real_python.touch()
    link = bin_dir / "python"
    link.symlink_to(real_python)
    assert extract_runner._source_root_for(link) == repo


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
    inst = _FakePopen.instances[0]
    cmd = inst.args[0]
    assert "--video" in cmd and "--corners-json" in cmd and "--out-dir" in cmd
    # The child runs from the derived source root with ml on PYTHONPATH so the
    # external interpreter can import ml.tools.extract_motion_features.
    assert inst.kwargs["cwd"] == str(extract_runner._PROJECT_ROOT)
    assert str(extract_runner._PROJECT_ROOT) in inst.kwargs["env"]["PYTHONPATH"]


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
