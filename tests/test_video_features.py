"""Tests for ml/video_features.py.

No real video file is required.  cv2 and decord are patched out at the module
boundary so the tests run in environments where those native libraries are not
installed.

Test coverage:
- compute_homography: identity-like transform, shape guarantee, validation
- extract_clip: shape contract, disk cache hit (no second decode), cache miss path
- hash_clip_key: determinism and sensitivity to arguments
"""

import sys
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
    _CV2_AVAILABLE = False

if "cv2" not in sys.modules:
    _cv2_stub = MagicMock(name="cv2")
    if _CV2_AVAILABLE:
        # Use real math functions so homography tests are numerically meaningful.
        _cv2_stub.getPerspectiveTransform = _cv2_real.getPerspectiveTransform
        _cv2_stub.perspectiveTransform = _cv2_real.perspectiveTransform
    _cv2_stub.warpPerspective.side_effect = lambda frame, M, dsize: frame
    _cv2_stub.resize.side_effect = lambda frame, dsize: np.zeros(
        (dsize[1], dsize[0], 3), dtype=np.uint8
    )
    sys.modules["cv2"] = _cv2_stub


# ---------------------------------------------------------------------------
# decord stub
#
# extract_clip does `import decord` inside the function body to probe
# availability, then calls _extract_with_decord.  We inject a minimal stub
# so the probe succeeds and the tests can patch _extract_with_decord cleanly
# without ever touching _extract_with_torchvision.
# ---------------------------------------------------------------------------

if "decord" not in sys.modules:
    _decord_stub = MagicMock(name="decord")
    sys.modules["decord"] = _decord_stub


# ---------------------------------------------------------------------------
# Import the module under test (after making cv2 and decord available).
# ---------------------------------------------------------------------------

from ml.video_features import (  # noqa: E402 — must come after stubs
    CANONICAL_SIZE,
    compute_homography,
    extract_clip,
    hash_clip_key,
    warp_clip_to_canonical,
)


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
    if _CV2_AVAILABLE:
        src = np.float32([[[pt[0], pt[1]]]])
        import cv2  # type: ignore[import-untyped]
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


@pytest.mark.skipif(not _CV2_AVAILABLE, reason="cv2 not installed")
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

    def test_custom_canonical_size_changes_matrix(self) -> None:
        """Different canonical_size values must produce different matrices."""
        corners = [(0, 0), (320, 0), (320, 240), (0, 240)]
        M_default = compute_homography(corners, CANONICAL_SIZE)
        M_custom = compute_homography(corners, (320, 240))
        assert not np.allclose(M_default, M_custom)


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
            patch("ml.video_features._extract_with_decord", return_value=fake_frames),
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
            patch("ml.video_features._extract_with_decord", return_value=fake_frames),
        ):
            result = extract_clip(fake_video, start_s, end_s, fps_out, CANONICAL_SIZE)

        assert result.shape[0] >= 1


class TestExtractClipCache:
    """extract_clip must honour the on-disk .npy cache."""

    def test_second_call_does_not_decode_again(self, tmp_path: Path) -> None:
        """A cache hit must skip _extract_with_decord entirely.

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
                "ml.video_features._extract_with_decord",
                return_value=fake_frames,
            ) as mock_decode,
        ):
            result1 = extract_clip(fake_video, start_s, end_s, fps_out, size)
            result2 = extract_clip(fake_video, start_s, end_s, fps_out, size)

        assert mock_decode.call_count == 1, (
            f"_extract_with_decord should be called once (cache hit on 2nd call), "
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
                "ml.video_features._extract_with_decord",
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
