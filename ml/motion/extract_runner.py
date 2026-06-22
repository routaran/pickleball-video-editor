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
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

__all__ = ["motion_venv_python", "extract_features_subprocess"]

logger = logging.getLogger(__name__)

# ml/motion/extract_runner.py -> project root is three parents up.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def motion_venv_python() -> Path | None:
    """Locate the ``.venv-motion`` Python interpreter, or ``None`` if absent.

    The detector only runs when this exists; otherwise the caller degrades to
    audio-only segmentation.  Checked relative to the project root.
    """
    for name in ("python", "python3"):
        candidate = _PROJECT_ROOT / ".venv-motion" / "bin" / name
        if candidate.exists():
            return candidate
    return None


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
    logger.info("Launching motion extraction: %s", " ".join(cmd))

    if progress_cb is not None:
        progress_cb("Extracting motion features (GPU — first run for this video)…")

    # Child output is file-backed (not PIPE) so a chatty detector can never
    # deadlock us on a full pipe buffer while we poll for cancellation.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as logf:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_PROJECT_ROOT),
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
