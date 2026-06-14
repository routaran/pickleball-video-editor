"""Video frame extraction and geometric normalization utilities.

Provides canonical court-view clips from raw video by:
1. Extracting frames from a time range via the system ffmpeg CLI (subprocess).
   In-process decoders (decord, torchvision/PyAV) are deliberately NOT used:
   decord loads its bundled ffmpeg + libxcb with RTLD_GLOBAL, whose symbols
   interpose on the system X/ffmpeg libraries that the GUI's mpv video output
   needs, segfaulting review mode.  Shelling out to the system ffmpeg keeps all
   video decoding in a separate process, matching how the rest of the app
   (export, frame_extract) already works.
2. Computing perspective homography from 4 annotated court corners
3. Warping each frame to a canonical rectangle

Canonical court dimensions: 256x128 pixels (aspect ratio ≈ 2.2).
Corner order: top-left, top-right, bottom-right, bottom-left.

Public API
----------
extract_clip(video_path, start_s, end_s, fps_out, size) -> np.ndarray  (T, H, W, 3) uint8
compute_homography(corners_pixel, canonical_size) -> np.ndarray  3x3 float64
warp_clip_to_canonical(frames, homography, canonical_size) -> np.ndarray  (T, H, W, 3) uint8
hash_clip_key(video_path, start_s, end_s, fps_out, size) -> str

No PyQt6 or other UI imports are used in this module.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


__all__ = [
    "extract_clip",
    "compute_homography",
    "warp_clip_to_canonical",
    "hash_clip_key",
    "resolve_extract_geometry",
    # Legacy constants retained for consumers that import them directly.
    "CANONICAL_SIZE",
    "CLIP_FPS",
    "CLIP_DURATION_S",
    # Legacy high-level wrapper retained for backward compatibility.
    "get_canonical_clip",
]

logger = logging.getLogger(__name__)


def _clean_ffmpeg_env() -> dict[str, str]:
    """Return an env for ffmpeg/ffprobe children that uses the *system* libs.

    Both the dev venv (opencv-python-headless prepends ``site-packages/<pkg>.libs``
    to ``LD_LIBRARY_PATH``) and the PyInstaller bundle (the bootloader prepends
    ``sys._MEIPASS``) inject directories full of older, ABI-incompatible
    ``libav*`` copies.  A system ffmpeg child that inherits those paths can load
    the wrong shared objects (``undefined symbol`` / ABI errors).  Strip both
    kinds of entry so the child resolves against the system FFmpeg install.
    """
    env = os.environ.copy()
    ld = env.get("LD_LIBRARY_PATH", "")
    if not ld:
        return env
    meipass = getattr(sys, "_MEIPASS", None)
    cleaned: list[str] = []
    for p in ld.split(":"):
        if not p or "site-packages" in p:
            continue
        if meipass and (p == meipass or p.startswith(meipass.rstrip("/") + "/")):
            continue
        cleaned.append(p)
    if cleaned:
        env["LD_LIBRARY_PATH"] = ":".join(cleaned)
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

CANONICAL_SIZE: tuple[int, int] = (256, 128)   # (width, height)
CANONICAL_WIDTH: int = 256
CANONICAL_HEIGHT: int = 128
CLIP_FPS: int = 8
CLIP_DURATION_S: float = 2.5  # seconds before rally end to include


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def hash_clip_key(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps_out: int,
    size: tuple[int, int],
) -> str:
    """Return a stable hex cache key for the given clip parameters.

    Uses MD5 of the canonical string representation of all arguments so the
    key is deterministic across Python processes and interpreter restarts.

    Args:
        video_path: Absolute (or relative) path to the source video.
        start_s: Clip start time in seconds.
        end_s: Clip end time in seconds.
        fps_out: Target output frame rate.
        size: Output frame dimensions as (width, height).

    Returns:
        32-character lowercase hex string.
    """
    key_str = f"{video_path!s}|{start_s}|{end_s}|{fps_out}|{size[0]}x{size[1]}"
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_cache_dir() -> Path:
    """Return the clip cache directory, creating it on first call."""
    cache_dir = Path(__file__).parent / "cache" / "clips"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@lru_cache(maxsize=256)
def _get_video_frame_size_cached(video_path_str: str) -> tuple[int, int] | None:
    """Resolve and cache native frame size for a video as (width, height).

    Returns None when size cannot be resolved via available probes.
    """
    video_path = Path(video_path_str)
    if not video_path.exists():
        return None

    # Try OpenCV's lightweight reader first (very fast when metadata is present).
    if hasattr(cv2, "VideoCapture"):
        capture = cv2.VideoCapture(str(video_path))
        try:
            if capture.isOpened():
                width_prop = getattr(cv2, "CAP_PROP_FRAME_WIDTH", 3)
                height_prop = getattr(cv2, "CAP_PROP_FRAME_HEIGHT", 4)
                width = int(capture.get(width_prop))
                height = int(capture.get(height_prop))
                if width > 0 and height > 0:
                    return width, height
        except Exception:
            pass
        finally:
            capture.release()

    # Fall back to the system ffprobe (same FFmpeg install used for extraction).
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=_clean_ffmpeg_env(),
            timeout=30,
        )
        if result.returncode == 0:
            text = result.stdout.decode("utf-8", "replace").strip().splitlines()
            if text:
                parts = text[0].split("x")
                if len(parts) == 2:
                    w, h = int(parts[0]), int(parts[1])
                    if w > 0 and h > 0:
                        return w, h
    except Exception:
        pass

    logger.warning(
        "Native frame-size probe failed for '%s' via all available backends "
        "(cv2, ffprobe). Callers will fall back to canonical size %s, which "
        "likely produces incorrect (near-black) warped clips.",
        video_path_str,
        CANONICAL_SIZE,
    )
    return None


def get_video_frame_size(video_path: Path) -> tuple[int, int] | None:
    """Return native video frame size as (width, height), or None on failure."""
    return _get_video_frame_size_cached(str(video_path))


def resolve_extract_geometry(
    native_size: tuple[int, int] | None,
    corners: list[tuple[int, int]],
    canonical_size: tuple[int, int] = CANONICAL_SIZE,
    max_extract_dim: int = 640,
) -> tuple[tuple[int, int], list[tuple[float, float]]]:
    """Resolve a cache-efficient extraction size and matching scaled corners.

    The court homography is computed in the coordinate space of the *extracted*
    frames, so the corner coordinates must be expressed in that same space.
    Extracting at full native resolution (the geometrically-correct but very
    large option) caches ~140 MB per clip at 1080p.  This helper downscales the
    extraction so the longest side is at most ``max_extract_dim`` (never
    upscaling) and scales the corners by the identical factor, shrinking the
    cache by ~(native/extract)**2 while leaving the canonical warp output
    unchanged apart from minor interpolation differences.

    Args:
        native_size: Native video frame size as (width, height), or None when
            the probe failed.
        corners: Four (x, y) court corners in *native* pixel coordinates.
        canonical_size: Canonical output size (width, height); used only for the
            None-fallback return value.
        max_extract_dim: Maximum allowed longest side of the extracted frame.

    Returns:
        Tuple of (extract_size, scaled_corners): ``extract_size`` is
        (width, height); ``scaled_corners`` are floats in the extracted-frame
        coordinate space.  When ``native_size`` is None, returns
        ``(canonical_size, corners-as-floats)`` to preserve the prior
        probe-failure fallback behaviour.
    """
    if native_size is None:
        return canonical_size, [(float(x), float(y)) for x, y in corners]

    native_w, native_h = native_size
    longest = max(native_w, native_h)
    scale = min(1.0, max_extract_dim / float(longest)) if longest > 0 else 1.0

    extract_w = max(1, round(native_w * scale))
    extract_h = max(1, round(native_h * scale))

    scale_x = extract_w / float(native_w)
    scale_y = extract_h / float(native_h)
    scaled_corners = [(x * scale_x, y * scale_y) for (x, y) in corners]

    return (extract_w, extract_h), scaled_corners

# ---------------------------------------------------------------------------
# Private extraction helpers
# ---------------------------------------------------------------------------

def _extract_with_ffmpeg(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps_out: int,
    size: tuple[int, int],
) -> np.ndarray:
    """Extract and resize frames using the system ffmpeg CLI (subprocess).

    One ffmpeg invocation seeks to ``start_s``, reads ``end_s - start_s``
    seconds, resamples to ``fps_out`` and scales to ``size``, streaming raw
    RGB24 frames to stdout.  The decoded frames are then resampled to exactly
    ``n = max(1, round(duration * fps_out))`` evenly-spaced frames, mirroring
    the fixed-length sequence the previous decord path produced (the temporal
    head expects a stable frame count).

    Decoding happens in a separate process, so no in-process video libraries
    are loaded into the GUI — see the module docstring for why that matters.
    """
    width, height = size
    duration_s = max(0.0, end_s - start_s)
    n = max(1, round(duration_s * fps_out))

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel", "error",
        "-ss", f"{start_s:.6f}",
        "-i", str(video_path),
        "-t", f"{duration_s:.6f}",
        "-vf", f"fps={fps_out},scale={width}:{height}:flags=bilinear",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "-",
    ]

    result = subprocess.run(cmd, capture_output=True, env=_clean_ffmpeg_env())
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"ffmpeg frame extraction failed for {video_path} "
            f"[{start_s:.2f}-{end_s:.2f}s] (rc={result.returncode}): {stderr}"
        )

    frame_bytes = width * height * 3
    buf = result.stdout
    if frame_bytes <= 0 or len(buf) < frame_bytes:
        raise RuntimeError(
            f"ffmpeg returned insufficient frame data for {video_path} "
            f"[{start_s:.2f}-{end_s:.2f}s]: got {len(buf)} bytes, "
            f"need >= {frame_bytes} for one {width}x{height} frame"
        )

    t_actual = len(buf) // frame_bytes
    frames = np.frombuffer(buf[: t_actual * frame_bytes], dtype=np.uint8).reshape(
        t_actual, height, width, 3
    )  # (T_actual, height, width, 3)

    # Resample to exactly n evenly-spaced frames (decord-equivalent semantics).
    idx = np.linspace(0, t_actual - 1, n).astype(int)
    return np.ascontiguousarray(frames[idx])  # (n, height, width, 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_clip(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps_out: int,
    size: tuple[int, int],  # (width, height)
) -> np.ndarray:
    """Extract a clip as a (T, H, W, 3) uint8 array. Cached under ml/cache/clips/.

    Frames are decoded and resampled to fps_out, then resized to size.  Results
    are persisted as .npy files keyed by hash_clip_key(); a cache hit skips
    all decoding entirely.  Cache entries are never auto-evicted.

    Decoding is performed by the system ffmpeg CLI in a separate process so no
    in-process video libraries are loaded into the GUI (see module docstring).

    Args:
        video_path: Path to the source video file.
        start_s: Clip start time in seconds.
        end_s: Clip end time in seconds.
        fps_out: Target output frame rate (frames per second).
        size: Output frame dimensions as (width, height).

    Returns:
        Numpy array of shape (T, height, width, 3), dtype uint8.
    """
    cache_dir = _get_cache_dir()
    cache_key = hash_clip_key(video_path, start_s, end_s, fps_out, size)
    cache_path = cache_dir / f"{cache_key}.npy"

    if cache_path.exists():
        logger.debug("Cache hit for clip %s", cache_key)
        return np.load(str(cache_path))

    logger.debug(
        "Cache miss — extracting %.2f–%.2f s from %s",
        start_s,
        end_s,
        video_path,
    )

    frames = _extract_with_ffmpeg(video_path, start_s, end_s, fps_out, size)

    np.save(str(cache_path), frames)
    logger.debug("Cached clip to %s", cache_path)
    return frames


def compute_homography(
    corners_pixel: list[tuple[int, int]],
    canonical_size: tuple[int, int] = CANONICAL_SIZE,  # (width, height)
) -> np.ndarray:
    """Return a 3x3 perspective transform matrix.

    Maps the four source corners to the corners of the canonical rectangle.
    Corner order must be: top-left, top-right, bottom-right, bottom-left.

    Args:
        corners_pixel: Four (x, y) pixel coordinates in the source image.
        canonical_size: Target canvas dimensions as (width, height).

    Returns:
        3x3 float64 homography matrix suitable for cv2.warpPerspective.
    """
    if len(corners_pixel) != 4:
        raise ValueError(
            f"corners_pixel must contain exactly 4 points, got {len(corners_pixel)}"
        )

    src = np.float32(corners_pixel)

    w, h = canonical_size
    dst = np.float32(
        [
            [0, 0],           # top-left
            [w - 1, 0],       # top-right
            [w - 1, h - 1],   # bottom-right
            [0, h - 1],       # bottom-left
        ]
    )

    return cv2.getPerspectiveTransform(src, dst)  # (3, 3) float64


def warp_clip_to_canonical(
    frames: np.ndarray,       # (T, H, W, 3) uint8
    homography: np.ndarray,   # 3x3 float64
    canonical_size: tuple[int, int] = CANONICAL_SIZE,  # (width, height)
) -> np.ndarray:
    """Apply a perspective homography to every frame in a clip.

    Args:
        frames: Source frames with shape (T, H, W, 3), dtype uint8.
        homography: 3x3 perspective transform matrix from compute_homography.
        canonical_size: Output canvas dimensions as (width, height).

    Returns:
        Warped frames with shape (T, canonical_size[1], canonical_size[0], 3),
        dtype uint8.
    """
    w, h = canonical_size
    return np.stack(
        [cv2.warpPerspective(frame, homography, (w, h)) for frame in frames],
        axis=0,
    )  # (T, h, w, 3)


# ---------------------------------------------------------------------------
# Legacy high-level wrapper (retained for backward compatibility)
# ---------------------------------------------------------------------------

def get_canonical_clip(
    video_path: Path,
    end_s: float,
    corners: list[tuple[int, int]],
    fps_out: int = CLIP_FPS,
    duration_s: float = CLIP_DURATION_S,
    canonical_size: tuple[int, int] = CANONICAL_SIZE,
    max_extract_dim: int = 640,
) -> np.ndarray:
    """Return a warped clip ending at end_s from the canonical court view.

    This is a convenience wrapper around extract_clip + compute_homography +
    warp_clip_to_canonical.  Prefer calling those functions directly in new code.

    Args:
        video_path: Path to the source video file.
        end_s: Rally end timestamp in seconds (clip ends here).
        corners: 4 (x, y) tuples in original video pixel coordinates.
        fps_out: Target output frame rate.
        duration_s: Clip duration; clip starts at end_s - duration_s.
        canonical_size: (width, height) of the canonical output rectangle.

    Returns:
        Array of shape (T, H, W, 3) uint8.
    """
    start_s = max(0.0, end_s - duration_s)

    extract_size, scaled_corners = resolve_extract_geometry(
        get_video_frame_size(video_path), corners, canonical_size, max_extract_dim
    )

    frames = extract_clip(video_path, start_s, end_s, fps_out, extract_size)
    homography = compute_homography(scaled_corners, canonical_size)
    return warp_clip_to_canonical(frames, homography, canonical_size)
