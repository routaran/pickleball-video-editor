"""Tests for ml/video_features.py.

No real video file is required.  cv2 is patched out at the module boundary and
the ffmpeg/ffprobe subprocess calls are mocked, so the tests run in environments
where those binaries are not installed.

Test coverage:
- compute_homography: identity-like transform, shape guarantee, validation
- extract_clip: shape contract, disk cache hit (no second decode), cache miss path
- hash_clip_key: determinism and sensitivity to arguments
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Guard against cross-test sys.modules contamination.
#
# test_auto_edit.py stubs both "numpy" and "ml.video_features" as MagicMock
# objects in sys.modules (at module level) so it can import ml.auto_edit
# without torch.  When pytest collects this file after test_auto_edit.py,
# those stubs are still live, which causes:
#   - "import numpy as np" below to bind np to a MagicMock
#   - "from ml.video_features import CANONICAL_SIZE" to return a MagicMock
#     attribute that unpacks as an empty sequence → ValueError at line 86
#
# Fix: evict the stubs before any of our own imports so the real packages
# are always loaded.  This is safe because:
#   - We only remove entries that ARE MagicMock instances (real packages are
#     left untouched).
#   - We also evict any submodule entries that share the same prefix, since
#     Python's import system caches them independently.
# ---------------------------------------------------------------------------

_NEED_REAL = ("numpy", "ml.video_features")

for _evict_prefix in _NEED_REAL:
    for _key in list(sys.modules):
        if _key == _evict_prefix or _key.startswith(_evict_prefix + "."):
            if isinstance(sys.modules[_key], MagicMock):
                del sys.modules[_key]

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so both ml/ and src/ are importable.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _manual_get_perspective_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Return a 3x3 homography from four source/destination point pairs."""
    src64 = np.asarray(src, dtype=np.float64)
    dst64 = np.asarray(dst, dtype=np.float64)

    A: list[list[float]] = []
    b: list[float] = []
    for (x, y), (u, v) in zip(src64, dst64, strict=True):
        A.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        b.append(float(u))
        A.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        b.append(float(v))

    h = np.linalg.solve(np.asarray(A, dtype=np.float64), np.asarray(b, dtype=np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def _manual_warp_perspective(frame: np.ndarray, M: np.ndarray, dsize: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour perspective warp used when real cv2 is unavailable."""
    w, h = dsize
    out = np.zeros((h, w, frame.shape[2]), dtype=frame.dtype)
    inv = np.linalg.inv(np.asarray(M, dtype=np.float64))

    ys, xs = np.indices((h, w), dtype=np.float64)
    dst = np.stack([xs.ravel(), ys.ravel(), np.ones(h * w, dtype=np.float64)], axis=0)
    src = inv @ dst
    src_x = np.rint(src[0] / src[2]).astype(np.int64)
    src_y = np.rint(src[1] / src[2]).astype(np.int64)

    valid = (
        (src_x >= 0)
        & (src_x < frame.shape[1])
        & (src_y >= 0)
        & (src_y < frame.shape[0])
    )
    out.reshape(-1, frame.shape[2])[valid] = frame[src_y[valid], src_x[valid]]
    return out


def _convex_polygon_mask(height: int, width: int, corners: list[tuple[int, int]]) -> np.ndarray:
    """Return a boolean mask for points inside a convex polygon."""
    pts = np.asarray(corners, dtype=np.float64)
    centroid_x, centroid_y = np.mean(pts, axis=0)

    yy, xx = np.indices((height, width), dtype=np.float64)
    inside = np.ones((height, width), dtype=bool)
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        edge_cross_centroid = (centroid_x - x1) * (y2 - y1) - (centroid_y - y1) * (x2 - x1)
        cross = (xx - x1) * (y2 - y1) - (yy - y1) * (x2 - x1)
        inside &= cross * edge_cross_centroid >= 0.0
    return inside


# ---------------------------------------------------------------------------
# cv2 stub
#
# video_features.py imports cv2 at module level.  We inject a minimal stub
# before the module is imported so the tests work without opencv installed.
# ---------------------------------------------------------------------------

try:
    import cv2 as _cv2_real  # type: ignore[import-untyped]
    _CV2_AVAILABLE = True
except ImportError:
    _cv2_real = None
    _CV2_AVAILABLE = False

if "cv2" not in sys.modules:
    _cv2_stub = types.ModuleType("cv2")
    _cv2_stub.getPerspectiveTransform = (
        _cv2_real.getPerspectiveTransform
        if _cv2_real is not None and hasattr(_cv2_real, "getPerspectiveTransform")
        else _manual_get_perspective_transform
    )
    if _cv2_real is not None and hasattr(_cv2_real, "perspectiveTransform"):
        _cv2_stub.perspectiveTransform = _cv2_real.perspectiveTransform
    _cv2_stub.warpPerspective = (
        _cv2_real.warpPerspective
        if _cv2_real is not None and hasattr(_cv2_real, "warpPerspective")
        else _manual_warp_perspective
    )
    _cv2_stub.resize = lambda frame, dsize: np.zeros((dsize[1], dsize[0], 3), dtype=np.uint8)
    sys.modules["cv2"] = _cv2_stub


# ---------------------------------------------------------------------------
# Import the module under test (after making cv2 available).
#
# extract_clip decodes via the system ffmpeg CLI (ml.video_features.
# _extract_with_ffmpeg); tests patch that helper directly, so no in-process
# decoder library stubs are needed.
# ---------------------------------------------------------------------------

from ml import video_features as _video_features_module  # noqa: E402
from ml.video_features import (  # noqa: E402 — must come after stubs
    CANONICAL_SIZE,
    compute_homography,
    extract_clip,
    get_canonical_clip,
    hash_clip_key,
    warp_clip_to_canonical,
)

if "getPerspectiveTransform" not in getattr(_video_features_module.cv2, "__dict__", {}):
    _video_features_module.cv2.getPerspectiveTransform = _manual_get_perspective_transform
if "warpPerspective" not in getattr(_video_features_module.cv2, "__dict__", {}):
    _video_features_module.cv2.warpPerspective = _manual_warp_perspective


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

W, H = CANONICAL_SIZE  # 256, 128


def _apply_homography_point(M: np.ndarray, pt: tuple[float, float]) -> tuple[float, float]:
    """Apply a 3x3 perspective matrix to a single 2-D point.

    Args:
        M: 3x3 float64 homography matrix.
        pt: (x, y) input point.

    Returns:
        (x', y') after perspective division.
    """
    import cv2  # type: ignore[import-untyped]

    if "perspectiveTransform" in getattr(cv2, "__dict__", {}):
        src = np.float32([[[pt[0], pt[1]]]])
        dst = cv2.perspectiveTransform(src, M)
        return float(dst[0, 0, 0]), float(dst[0, 0, 1])

    # Manual perspective transform for stub environments.
    p = np.array([pt[0], pt[1], 1.0], dtype=np.float64)
    q = M @ p
    return float(q[0] / q[2]), float(q[1] / q[2])


def _fake_frames(t: int = 5, h: int = H, w: int = W) -> np.ndarray:
    """Return a zero-filled (T, H, W, 3) uint8 array."""
    return np.zeros((t, h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# compute_homography tests
# ---------------------------------------------------------------------------


class TestComputeHomography:
    """Tests for compute_homography().

    These tests require real cv2 because they verify numerical correctness of
    the perspective transform.  The skip guard keeps CI green when cv2 is absent.
    """

    def test_returns_3x3_float64(self) -> None:
        """Output must be a (3, 3) float64 numpy array."""
        corners = [(0, 0), (W, 0), (W, H), (0, H)]
        M = compute_homography(corners, (W, H))
        assert isinstance(M, np.ndarray)
        assert M.shape == (3, 3)
        assert M.dtype == np.float64

    def test_identity_ish_corners_map_centre_to_itself(self) -> None:
        """Axis-aligned corners equal to the canonical rect should map the
        image centre to itself (up to 1 pixel of floating-point error).

        This verifies the identity-like property: when source corners already
        match the canonical rectangle the homography is a scaled identity and
        every point maps approximately to itself.
        """
        corners = [(0, 0), (W, 0), (W, H), (0, H)]
        M = compute_homography(corners, (W, H))

        cx, cy = W / 2.0, H / 2.0
        ox, oy = _apply_homography_point(M, (cx, cy))

        assert abs(ox - cx) < 1.0, f"Expected x ≈ {cx}, got {ox}"
        assert abs(oy - cy) < 1.0, f"Expected y ≈ {cy}, got {oy}"

    def test_identity_ish_corners_map_corner_to_corner(self) -> None:
        """Top-left source corner should warp to top-left of canonical rect."""
        corners = [(0, 0), (W, 0), (W, H), (0, H)]
        M = compute_homography(corners, (W, H))

        ox, oy = _apply_homography_point(M, (0.0, 0.0))
        assert abs(ox) < 1.0 and abs(oy) < 1.0, (
            f"Top-left corner should map to (0, 0), got ({ox}, {oy})"
        )

    def test_wrong_corner_count_raises_value_error(self) -> None:
        """Fewer or more than 4 corners must raise ValueError."""
        with pytest.raises(ValueError, match="4"):
            compute_homography([(0, 0), (W, 0), (W, H)], (W, H))

        with pytest.raises(ValueError, match="4"):
            compute_homography([(0, 0), (W, 0), (W, H), (0, H), (W // 2, H // 2)], (W, H))

    def test_custom_canonical_size_changes_output_mapping(self) -> None:
        """Different canonical_size values must change the destination mapping."""
        corners = [(0, 0), (320, 0), (320, 240), (0, 240)]
        M_default = compute_homography(corners, CANONICAL_SIZE)
        M_custom = compute_homography(corners, (320, 240))

        default_br = _apply_homography_point(M_default, (320.0, 240.0))
        custom_br = _apply_homography_point(M_custom, (320.0, 240.0))

        assert np.allclose(default_br, (W - 1, H - 1), atol=1.0)
        assert np.allclose(custom_br, (319.0, 239.0), atol=1.0)
        assert not np.allclose(default_br, custom_br)

    def test_realistic_non_identity_corners_warp_non_empty_content(self) -> None:
        """A realistic trapezoid should warp into non-empty canonical content.

        Regression guard: when corners are interpreted in the wrong coordinate
        space, the warped clip becomes mostly black/empty.
        """
        source_h = 480
        source_w = 640
        corners = [(120, 80), (520, 100), (560, 360), (90, 340)]

        frame = np.zeros((source_h, source_w, 3), dtype=np.uint8)
        yy, xx = np.indices((source_h, source_w))
        mask = _convex_polygon_mask(source_h, source_w, corners)
        frame[mask, 0] = (xx[mask] % 256).astype(np.uint8)
        frame[mask, 1] = (yy[mask] % 256).astype(np.uint8)
        frame[mask, 2] = 255

        frames = np.stack([frame], axis=0)
        homography = compute_homography(corners, CANONICAL_SIZE)
        warped = warp_clip_to_canonical(frames, homography, CANONICAL_SIZE)

        assert warped.shape == (1, H, W, 3)
        assert int(warped.sum()) > 0, "Warped frame is unexpectedly empty"

        center_patch = warped[0, H // 4 : 3 * H // 4, W // 4 : 3 * W // 4]
        assert center_patch.mean() > 10.0, (
            "Expected substantial non-black content in warped centre region"
        )


# ---------------------------------------------------------------------------
# extract_clip shape and cache tests
# ---------------------------------------------------------------------------


class TestExtractClipShape:
    """extract_clip must return an array with the correct (T, H, W, 3) shape."""

    def test_shape_matches_fps_and_duration(self, tmp_path: Path) -> None:
        """T should equal round((end_s - start_s) * fps_out).

        The inner extraction is mocked so no real video file is needed.
        """
        fps_out = 8
        start_s = 0.0
        end_s = 2.5
        size = (W, H)
        expected_t = max(1, round((end_s - start_s) * fps_out))  # 20 frames

        fake_video = tmp_path / "dummy.mp4"
        fake_video.write_bytes(b"placeholder")

        fake_frames = _fake_frames(t=expected_t, h=H, w=W)

        with (
            patch("ml.video_features._get_cache_dir", return_value=tmp_path),
            patch("ml.video_features._extract_with_ffmpeg", return_value=fake_frames),
        ):
            result = extract_clip(fake_video, start_s, end_s, fps_out, size)

        assert result.ndim == 4, f"Expected 4-D array, got ndim={result.ndim}"
        assert result.shape == (expected_t, H, W, 3), (
            f"Expected shape {(expected_t, H, W, 3)}, got {result.shape}"
        )
        assert result.dtype == np.uint8

    def test_shape_single_frame_minimum(self, tmp_path: Path) -> None:
        """A very short duration should still produce at least 1 frame (T ≥ 1)."""
        fps_out = 8
        start_s = 0.0
        end_s = 0.01  # extremely short clip → max(1, round(0.08)) = 1 frame

        fake_video = tmp_path / "short.mp4"
        fake_video.write_bytes(b"placeholder")
        fake_frames = _fake_frames(t=1)

        with (
            patch("ml.video_features._get_cache_dir", return_value=tmp_path),
            patch("ml.video_features._extract_with_ffmpeg", return_value=fake_frames),
        ):
            result = extract_clip(fake_video, start_s, end_s, fps_out, CANONICAL_SIZE)

        assert result.shape[0] >= 1


class TestExtractClipCache:
    """extract_clip must honour the on-disk .npy cache."""

    def test_second_call_does_not_decode_again(self, tmp_path: Path) -> None:
        """A cache hit must skip _extract_with_ffmpeg entirely.

        The extraction backend is called exactly once on the first call and
        zero additional times on the second call with identical arguments.
        """
        fps_out = 8
        start_s = 1.0
        end_s = 3.0
        size = CANONICAL_SIZE
        expected_t = max(1, round((end_s - start_s) * fps_out))

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"placeholder")
        fake_frames = _fake_frames(t=expected_t)

        with (
            patch("ml.video_features._get_cache_dir", return_value=tmp_path),
            patch(
                "ml.video_features._extract_with_ffmpeg",
                return_value=fake_frames,
            ) as mock_decode,
        ):
            result1 = extract_clip(fake_video, start_s, end_s, fps_out, size)
            result2 = extract_clip(fake_video, start_s, end_s, fps_out, size)

        assert mock_decode.call_count == 1, (
            f"_extract_with_ffmpeg should be called once (cache hit on 2nd call), "
            f"got {mock_decode.call_count}"
        )
        assert np.array_equal(result1, result2), "Cache hit must return identical data"

    def test_different_args_bypass_cache(self, tmp_path: Path) -> None:
        """Different start/end times must produce separate cache entries."""
        fps_out = 8
        size = CANONICAL_SIZE
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"placeholder")

        frames_a = _fake_frames(t=4)
        frames_b = _fake_frames(t=8)
        frames_b[:] = 128  # distinct content

        call_results = [frames_a, frames_b]
        call_idx = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_idx
            result = call_results[call_idx]
            call_idx += 1
            return result

        with (
            patch("ml.video_features._get_cache_dir", return_value=tmp_path),
            patch(
                "ml.video_features._extract_with_ffmpeg",
                side_effect=_side_effect,
            ) as mock_decode,
        ):
            r1 = extract_clip(fake_video, 0.0, 0.5, fps_out, size)
            r2 = extract_clip(fake_video, 2.0, 3.0, fps_out, size)

        assert mock_decode.call_count == 2, (
            "Both calls should decode (different cache keys)"
        )
        assert not np.array_equal(r1, r2)


# ---------------------------------------------------------------------------
# hash_clip_key tests
# ---------------------------------------------------------------------------


class TestGetCanonicalClip:
    """Regression tests for the high-level extract + warp wrapper."""

    def test_uses_native_source_frame_size_for_extraction(self, tmp_path: Path) -> None:
        """Extraction must use the video's native size, not canonical_size.

        This prevents passing source-space court corners into frames that were
        prematurely resized to canonical dimensions.
        """
        source_size = (640, 480)
        corners = [(120, 80), (520, 100), (560, 360), (90, 340)]
        video_path = tmp_path / "native-size.mp4"
        video_path.write_bytes(b"placeholder")

        frame = np.zeros((source_size[1], source_size[0], 3), dtype=np.uint8)
        frame[80:360, 120:560, :] = 200
        extracted = np.stack([frame], axis=0)

        sentinel_homography = np.eye(3, dtype=np.float64)

        def _warp_side_effect(
            frames: np.ndarray,
            homography: np.ndarray,
            canonical_size: tuple[int, int],
        ) -> np.ndarray:
            assert frames.shape == (1, source_size[1], source_size[0], 3)
            assert np.array_equal(frames, extracted)
            assert np.array_equal(homography, sentinel_homography)
            assert canonical_size == CANONICAL_SIZE
            return np.full((1, H, W, 3), 17, dtype=np.uint8)

        with (
            patch("ml.video_features.get_video_frame_size", return_value=source_size),
            patch("ml.video_features.extract_clip", return_value=extracted) as mock_extract,
            patch("ml.video_features.compute_homography", return_value=sentinel_homography) as mock_homography,
            patch("ml.video_features.warp_clip_to_canonical", side_effect=_warp_side_effect) as mock_warp,
        ):
            warped = get_canonical_clip(
                video_path=video_path,
                end_s=2.5,
                corners=corners,
                fps_out=8,
                duration_s=2.5,
                canonical_size=CANONICAL_SIZE,
            )

        assert mock_extract.call_args.args[4] == source_size
        mock_homography.assert_called_once_with(corners, CANONICAL_SIZE)
        mock_warp.assert_called_once()
        assert warped.shape == (1, H, W, 3)
        assert int(warped.sum()) > 0


# ---------------------------------------------------------------------------
# _get_video_frame_size_cached / get_video_frame_size tests
# ---------------------------------------------------------------------------


class TestGetVideoFrameSize:
    """Tests for the tiered native-size probe and its warning behaviour."""

    # Import the cached function directly so we can call .cache_clear().
    from ml.video_features import _get_video_frame_size_cached as _cached_fn

    def _clear(self) -> None:
        """Clear lru_cache to avoid cross-test pollution."""
        from ml.video_features import _get_video_frame_size_cached
        _get_video_frame_size_cached.cache_clear()

    def test_ffprobe_tier_returns_size(self, tmp_path: Path) -> None:
        """When cv2 fails, the ffprobe tier parses 'WxH' and returns (W, H).

        cv2 is forced to fail (isOpened False); a mocked ffprobe subprocess
        returns "1280x720\\n" on stdout → expect (1280, 720).
        """
        self._clear()

        fake_video = tmp_path / "ffprobe_probe_unique.mp4"
        fake_video.write_bytes(b"placeholder")

        # Patch cv2 so the first tier fails (isOpened returns False).
        failing_capture = MagicMock()
        failing_capture.isOpened.return_value = False

        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = b"1280x720\n"

        with (
            patch("ml.video_features.cv2") as mock_cv2,
            patch("ml.video_features.subprocess.run", return_value=fake_proc) as mock_run,
        ):
            mock_cv2.VideoCapture.return_value = failing_capture
            mock_cv2.CAP_PROP_FRAME_WIDTH = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

            self._clear()
            from ml.video_features import _get_video_frame_size_cached
            result = _get_video_frame_size_cached(str(fake_video))
            self._clear()

        assert result == (1280, 720), f"Expected (1280, 720), got {result}"
        assert mock_run.called, "ffprobe subprocess should have been invoked"

    def test_all_tiers_fail_returns_none_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When all probes fail, returns None and emits a WARNING log message."""
        import logging

        self._clear()

        fake_video = tmp_path / "all_fail_unique.mp4"
        fake_video.write_bytes(b"placeholder")

        # cv2 fails (isOpened False) and ffprobe exits non-zero with no output.
        failing_capture = MagicMock()
        failing_capture.isOpened.return_value = False

        fake_proc = MagicMock()
        fake_proc.returncode = 1
        fake_proc.stdout = b""
        fake_proc.stderr = b"ffprobe: could not open"

        with (
            patch("ml.video_features.cv2") as mock_cv2,
            patch("ml.video_features.subprocess.run", return_value=fake_proc),
            caplog.at_level(logging.WARNING, logger="ml.video_features"),
        ):
            mock_cv2.VideoCapture.return_value = failing_capture
            mock_cv2.CAP_PROP_FRAME_WIDTH = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

            self._clear()
            from ml.video_features import _get_video_frame_size_cached
            result = _get_video_frame_size_cached(str(fake_video))
            self._clear()

        assert result is None, f"Expected None when all tiers fail, got {result}"
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Native frame-size probe failed" in str(m) for m in warning_messages
        ), f"Expected a warning about probe failure, got log records: {caplog.records}"


class TestHashClipKey:
    """hash_clip_key must be deterministic and sensitive to all arguments."""

    def test_same_args_produce_same_key(self) -> None:
        """Identical arguments must always yield the same hex string."""
        path = Path("/recordings/game.mp4")
        key1 = hash_clip_key(path, 5.0, 7.5, 8, (256, 128))
        key2 = hash_clip_key(path, 5.0, 7.5, 8, (256, 128))
        assert key1 == key2

    def test_key_is_32_char_hex(self) -> None:
        """Key must be a 32-character lowercase hex MD5 digest."""
        key = hash_clip_key(Path("/vid.mp4"), 0.0, 2.5, 8, (256, 128))
        assert len(key) == 32
        assert key == key.lower()
        int(key, 16)  # raises ValueError if not valid hex

    def test_different_start_time_produces_different_key(self) -> None:
        path = Path("/vid.mp4")
        k1 = hash_clip_key(path, 0.0, 5.0, 8, CANONICAL_SIZE)
        k2 = hash_clip_key(path, 1.0, 5.0, 8, CANONICAL_SIZE)
        assert k1 != k2

    def test_different_end_time_produces_different_key(self) -> None:
        path = Path("/vid.mp4")
        k1 = hash_clip_key(path, 0.0, 5.0, 8, CANONICAL_SIZE)
        k2 = hash_clip_key(path, 0.0, 6.0, 8, CANONICAL_SIZE)
        assert k1 != k2

    def test_different_fps_produces_different_key(self) -> None:
        path = Path("/vid.mp4")
        k1 = hash_clip_key(path, 0.0, 5.0, 8, CANONICAL_SIZE)
        k2 = hash_clip_key(path, 0.0, 5.0, 15, CANONICAL_SIZE)
        assert k1 != k2

    def test_different_size_produces_different_key(self) -> None:
        path = Path("/vid.mp4")
        k1 = hash_clip_key(path, 0.0, 5.0, 8, (256, 128))
        k2 = hash_clip_key(path, 0.0, 5.0, 8, (128, 64))
        assert k1 != k2

    def test_different_path_produces_different_key(self) -> None:
        k1 = hash_clip_key(Path("/a/video.mp4"), 0.0, 5.0, 8, CANONICAL_SIZE)
        k2 = hash_clip_key(Path("/b/video.mp4"), 0.0, 5.0, 8, CANONICAL_SIZE)
        assert k1 != k2
