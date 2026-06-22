"""Run the heavy motion-feature extraction out-of-process.

The GUI process must never import ultralytics / full OpenCV in-process: they
interpose on python-mpv (libxcb / Qt) and segfault the player.  This module
shells out to the isolated ``.venv-motion`` interpreter to run
``ml.tools.extract_motion_features`` for a single video, so YOLO/ByteTrack run
in a child process and only the cheap ``.npz`` cache crosses back into the GUI.

IMPORTANT: imports here are stdlib-only on purpose — importing this module must
stay cv2/ultralytics/torch free so it is safe to import from the GUI ``.venv``
(including the mpv-bound main process).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

__all__ = ["MOTION_VENV_ENV_VAR", "motion_venv_python", "extract_features_subprocess"]

logger = logging.getLogger(__name__)

# Override env var: point this at the .venv-motion interpreter
# (…/.venv-motion/bin/python) or the venv root (…/.venv-motion).  Needed when
# running the PyInstaller-frozen *installed* binary, whose bundle-relative file
# path cannot see the source-tree venv.
MOTION_VENV_ENV_VAR = "PICKLEBALL_MOTION_VENV"

# ml/motion/extract_runner.py -> project root is three parents up.  Correct when
# running from the source tree (e.g. `make run`); meaningless inside a frozen
# bundle, which is exactly why MOTION_VENV_ENV_VAR exists.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _interpreter_in(venv_root: Path) -> Path | None:
    """Return the python interpreter inside ``venv_root`` (bin/python[3]), or None."""
    for name in ("python", "python3"):
        candidate = venv_root / "bin" / name
        if candidate.exists():
            return candidate
    return None


def motion_venv_python() -> Path | None:
    """Locate the ``.venv-motion`` Python interpreter, or ``None`` if absent.

    Lookup order:
      1. ``$PICKLEBALL_MOTION_VENV`` — either the interpreter itself
         (…/.venv-motion/bin/python) or the venv root (…/.venv-motion).  Use
         this to make motion fusion work from the *installed* binary.
      2. ``<project-root>/.venv-motion/bin/python`` — works when running from
         the source tree (``make run``).

    The detector only runs when this resolves; otherwise the caller degrades to
    audio-only segmentation.
    """
    override = os.environ.get(MOTION_VENV_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            found = _interpreter_in(candidate)
            if found is not None:
                return found
        logger.warning(
            "%s=%r does not point to a usable interpreter or venv directory; "
            "falling back to the source-tree location.",
            MOTION_VENV_ENV_VAR,
            override,
        )

    return _interpreter_in(_PROJECT_ROOT / ".venv-motion")


def _source_root_for(interpreter: Path) -> Path:
    """Repo root that owns ``interpreter`` (…/.venv-motion/bin/python -> repo).

    The detector subprocess must run with this as its working directory (and on
    PYTHONPATH) so the external interpreter can import the ``ml`` source package.
    Falls back to the build-time project root for non-standard layouts.

    Note: we normalize but deliberately do NOT follow symlinks — a venv's
    ``bin/python`` is a symlink to the base interpreter, and resolving it would
    point outside the venv (e.g. /usr/bin) and lose the repo location.
    """
    normalized = Path(os.path.abspath(interpreter))
    # python -> bin -> .venv-motion -> <repo>
    if len(normalized.parents) >= 3:
        return normalized.parents[2]
    return _PROJECT_ROOT


def _child_env(source_root: Path) -> dict[str, str]:
    """Environment for the detector child: ml importable, no bundle lib leakage.

    When we are ourselves frozen by PyInstaller, the loader rewrites
    LD_LIBRARY_PATH to point into the bundle and stashes the original in
    ``*_ORIG``.  The .venv-motion interpreter is a separate runtime with its own
    CUDA/torch libraries, so it must NOT inherit the bundle's lib path.
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
        os.pathsep.join([str(source_root), existing]) if existing else str(source_root)
    )
    return env


def _terminate(proc: subprocess.Popen) -> None:
    """Terminate a child process, escalating to kill if it ignores SIGTERM."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Motion extraction child did not die after kill().")


def extract_features_subprocess(
    video_path: Path,
    corners: list[tuple[int, int]],
    out_dir: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
    progress_cb: Callable[[str], None] | None = None,
    poll_seconds: float = 0.5,
) -> bool:
    """Extract motion features for one video via the ``.venv-motion`` subprocess.

    Args:
        video_path: Source video to run the detector over.
        corners: Four (x, y) court corners in source-video pixel space.
        out_dir: Cache directory the ``.npz`` is written to.
        cancel_check: Optional zero-arg callable; when it returns True the child
            process is terminated and ``False`` is returned (no exception).
        progress_cb: Optional callable invoked once with a human-readable phase
            string when extraction starts (the progress bar is indeterminate, so
            sub-progress is not streamed).
        poll_seconds: Cancellation poll interval.

    Returns:
        ``True`` only when the child exits 0; ``False`` on any failure, a missing
        ``.venv-motion``, or cancellation.  Callers should still re-check that
        the cache file exists before relying on it.
    """
    py = motion_venv_python()
    if py is None:
        logger.warning("Motion venv (.venv-motion) not found; skipping extraction.")
        return False

    source_root = _source_root_for(py)
    cmd = [
        str(py),
        "-m",
        "ml.tools.extract_motion_features",
        "--video",
        str(video_path),
        "--corners-json",
        json.dumps([[int(x), int(y)] for x, y in corners]),
        "--out-dir",
        str(out_dir),
    ]
    logger.info("Launching motion extraction (cwd=%s): %s", source_root, " ".join(cmd))

    if progress_cb is not None:
        progress_cb("Extracting motion features (GPU — first run for this video)…")

    # Child output is file-backed (not PIPE) so a chatty detector can never
    # deadlock us on a full pipe buffer while we poll for cancellation.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as logf:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(source_root),
                env=_child_env(source_root),
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            logger.warning("Failed to launch motion extraction: %s", exc)
            return False

        while proc.poll() is None:
            if cancel_check is not None and cancel_check():
                logger.info("Cancellation requested; terminating motion extraction.")
                _terminate(proc)
                return False
            time.sleep(poll_seconds)

        returncode = proc.returncode
        if returncode != 0:
            logf.seek(0)
            tail = logf.read()[-2000:]
            logger.warning(
                "Motion extraction exited with code %s:\n%s", returncode, tail
            )
            return False

    logger.info("Motion extraction completed for %s", video_path.name)
    return True
