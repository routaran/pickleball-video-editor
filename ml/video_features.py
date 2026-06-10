"""Video frame extraction and geometric normalization utilities.

Provides canonical court-view clips from raw video by:
1. Extracting frames from a time range (decord primary, torchvision fallback)
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
import warnings
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


__all__ = [
    "extract_clip",
    "compute_homography",
    "warp_clip_to_canonical",
    "hash_clip_key",
    # Legacy constants retained for consumers that import them directly.
    "CANONICAL_SIZE",
    "CLIP_FPS",
    "CLIP_DURATION_S",
    # Legacy high-level wrapper retained for backward compatibility.
    "get_canonical_clip",
]

logger = logging.getLogger(__name__)

# Emit the decord-unavailable warning only once per process.
_decord_warned: bool = False

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

    # Fall back to decord metadata if available.
    try:
        from decord import VideoReader, cpu  # type: ignore[import-untyped]

        vr = VideoReader(str(video_path), ctx=cpu(0))
        width = int(getattr(vr, "width", 0))
        height = int(getattr(vr, "height", 0))
        if width > 0 and height > 0:
            return width, height

        # As a final fallback under decord, read the first frame to infer dimensions.
        sample = vr.get_batch([0]).asnumpy()
        if sample.size > 0:
            h, w = sample.shape[1], sample.shape[2]
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass

    # torchvision fallback (uses the same backend family already used by extract_clip).
    try:
        import torchvision.io as tvio  # type: ignore[import-untyped]

        video, _, _info = tvio.read_video(
            str(video_path),
            start_pts=0.0,
            end_pts=1.0,
            pts_unit="sec",
        )
        if video.numel() > 0:
            _, h, w, _ = video.shape
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass

    logger.warning(
        "Native frame-size probe failed for '%s' via all available backends "
        "(cv2, decord, torchvision). Callers will fall back to canonical size "
        "%s, which likely produces incorrect (near-black) warped clips.",
        video_path_str,
        CANONICAL_SIZE,
    )
    return None


def get_video_frame_size(video_path: Path) -> tuple[int, int] | None:
    """Return native video frame size as (width, height), or None on failure."""
    return _get_video_frame_size_cached(str(video_path))

# ---------------------------------------------------------------------------
# Private extraction helpers
# ---------------------------------------------------------------------------

def _extract_with_decord(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps_out: int,
    size: tuple[int, int],
) -> np.ndarray:
    """Extract and resize frames using decord.VideoReader (preferred path)."""
    from decord import VideoReader, cpu  # type: ignore[import-untyped]

    vr = VideoReader(str(video_path), ctx=cpu(0))
    native_fps: float = vr.get_avg_fps()

    start_frame = max(0, int(start_s * native_fps))
    end_frame = min(len(vr) - 1, int(end_s * native_fps))

    n = max(1, round((end_s - start_s) * fps_out))
    indices = list(np.linspace(start_frame, end_frame, n, dtype=int))

    raw_frames: np.ndarray = vr.get_batch(indices).asnumpy()  # (T, H_orig, W_orig, 3)

    width, height = size
    resized = np.stack(
        [cv2.resize(frame, (width, height)) for frame in raw_frames],
        axis=0,
    )
    return resized  # (T, height, width, 3)


def _extract_with_torchvision(
    video_path: Path,
    start_s: float,
    end_s: float,
    fps_out: int,
    size: tuple[int, int],
) -> np.ndarray:
    """Extract and resize frames using torchvision.io.read_video (fallback)."""
    import torchvision.io as tvio  # type: ignore[import-untyped]

    video, _, _info = tvio.read_video(
        str(video_path),
        start_pts=start_s,
        end_pts=end_s,
        pts_unit="sec",
    )
    # video: (T, H, W, C) uint8 tensor
    if video.numel() == 0:
        raise RuntimeError(
            f"torchvision.io.read_video returned empty tensor for {video_path}"
        )

    n = max(1, round((end_s - start_s) * fps_out))
    idx = np.linspace(0, len(video) - 1, n, dtype=int)
    frames_np: np.ndarray = video[idx].numpy()  # (T, H_orig, W_orig, 3)

    width, height = size
    resized = np.stack(
        [cv2.resize(frame, (width, height)) for frame in frames_np],
        axis=0,
    )
    return resized  # (T, height, width, 3)


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

    decord is used when available for accurate frame seeking.  If decord is not
    installed, torchvision.io.read_video is used instead and a one-time warning
    is emitted.

    Args:
        video_path: Path to the source video file.
        start_s: Clip start time in seconds.
        end_s: Clip end time in seconds.
        fps_out: Target output frame rate (frames per second).
        size: Output frame dimensions as (width, height).

    Returns:
        Numpy array of shape (T, height, width, 3), dtype uint8.
    """
    global _decord_warned

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

    frames: np.ndarray

    try:
        import decord  # noqa: F401 — probe availability only

        frames = _extract_with_decord(video_path, start_s, end_s, fps_out, size)
    except ImportError:
        if not _decord_warned:
            warnings.warn(
                "decord is not available; falling back to torchvision.io.read_video. "
                "Install decord for faster and more accurate frame seeking.",
                stacklevel=2,
            )
            _decord_warned = True
        frames = _extract_with_torchvision(video_path, start_s, end_s, fps_out, size)

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

    source_size = get_video_frame_size(video_path)
    extract_size = source_size if source_size is not None else canonical_size

    frames = extract_clip(video_path, start_s, end_s, fps_out, extract_size)
    homography = compute_homography(corners, canonical_size)
    return warp_clip_to_canonical(frames, homography, canonical_size)
