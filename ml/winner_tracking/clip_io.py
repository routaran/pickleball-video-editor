"""Full-resolution clip extraction for ball tracking (system ffmpeg only).

Unlike ``ml.video_features.extract_clip`` (which resamples to a fixed N frames for
the temporal CNN), tracking needs *every* frame at a true frame rate so the ball's
motion is continuous.  This module returns all decoded frames at native resolution.

Frames are NOT cached to disk: a 3.5 s 1080p60 clip is ~1.5 GB raw.  Callers extract,
detect, then discard the pixels — only the tiny candidate lists are cached.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np

from ml.video_features import _clean_ffmpeg_env

__all__ = ["extract_raw_frames"]


def extract_raw_frames(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps: int,
    size: tuple[int, int],
) -> tuple[np.ndarray, float]:
    """Decode ``[start_s, end_s]`` at ``fps`` and ``size`` via the system ffmpeg.

    Args:
        video_path: Source video.
        start_s: Window start (clamped to >= 0).
        end_s: Window end.
        fps: Output frame rate (true sampling rate; no fixed-N resample).
        size: (width, height) to scale to (use native to preserve the ball).

    Returns:
        (frames, actual_fps) where frames is (T, H, W, 3) uint8 (RGB) and
        actual_fps is ``fps`` (the requested rate, used for velocity scaling).
    """
    width, height = size
    start_s = max(0.0, start_s)
    duration_s = max(0.0, end_s - start_s)

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel", "error",
        "-ss", f"{start_s:.6f}",
        "-i", str(video_path),
        "-t", f"{duration_s:.6f}",
        "-vf", f"fps={fps},scale={width}:{height}:flags=bilinear",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, env=_clean_ffmpeg_env())
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"ffmpeg extraction failed for {video_path} "
            f"[{start_s:.2f}-{end_s:.2f}s] (rc={result.returncode}): {stderr}"
        )

    frame_bytes = width * height * 3
    buf = result.stdout
    if frame_bytes <= 0 or len(buf) < frame_bytes:
        raise RuntimeError(
            f"ffmpeg returned insufficient data for {video_path} "
            f"[{start_s:.2f}-{end_s:.2f}s]: {len(buf)} bytes"
        )
    t_actual = len(buf) // frame_bytes
    frames = np.frombuffer(buf[: t_actual * frame_bytes], dtype=np.uint8).reshape(
        t_actual, height, width, 3
    )
    return frames, float(fps)
