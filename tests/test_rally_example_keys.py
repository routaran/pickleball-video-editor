"""Tests for example_key stability and sensitivity.

All tests are torch-free.  WinnerModelConfig is imported only to verify that
clip-config parameters are correctly folded into the hash; the import guard
keeps this module working even when ml.config is unavailable for some reason.

Test classes
------------
TestExampleKeyStability    — same inputs always produce the same key
TestExampleKeySensitivity  — changing any keyed input changes the key
TestExampleKeyConfigParam  — config=None vs WinnerModelConfig behaviour
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.examples import RallyExample, example_key  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_CORNERS: tuple[tuple[int, int], ...] = (
    (10, 20),
    (310, 20),
    (310, 220),
    (10, 220),
)


def _make_example(
    *,
    video_path: str = "/fake/video.mp4",
    raw_start: float = 10.0,
    raw_end: float = 20.5,
    rally_index: int = 0,
    court_corners: tuple[tuple[int, int], ...] = _CORNERS,
    score_at_start: str = "0-0-2",
    winner: str = "server",
    winning_team: int = 0,
    source_json_path: str = "/fake/game.training.json",
    schema_version: str = "1.1",
    generated_by: str = "manual",
    is_post_game: bool = False,
) -> RallyExample:
    """Construct a RallyExample directly via from_rally_dict."""
    return RallyExample.from_rally_dict(
        source_json_path=Path(source_json_path),
        video_path=Path(video_path),
        court_corners=court_corners,
        schema_version=schema_version,
        generated_by=generated_by,
        rally_dict={
            "index": rally_index,
            "score_at_start": score_at_start,
            "winner": winner,
            "winning_team": winning_team,
            "is_post_game": is_post_game,
            "comment": None,
            "raw": {"start_seconds": raw_start, "end_seconds": raw_end},
        },
    )


# ---------------------------------------------------------------------------
# TestExampleKeyStability
# ---------------------------------------------------------------------------


class TestExampleKeyStability:
    """Same inputs must always yield the same key."""

    def test_key_is_string(self) -> None:
        ex = _make_example()
        k = example_key(ex)
        assert isinstance(k, str)

    def test_key_length_16(self) -> None:
        """Key is exactly 16 hex characters (first 8 bytes of SHA-256)."""
        ex = _make_example()
        k = example_key(ex)
        assert len(k) == 16

    def test_key_is_hex(self) -> None:
        """Key contains only lowercase hex digits."""
        ex = _make_example()
        k = example_key(ex)
        assert all(c in "0123456789abcdef" for c in k)

    def test_same_example_same_key(self) -> None:
        """Calling example_key twice on the same object returns identical strings."""
        ex = _make_example()
        assert example_key(ex) == example_key(ex)

    def test_two_identical_examples_same_key(self) -> None:
        """Two independently constructed examples with identical inputs share a key."""
        ex1 = _make_example()
        ex2 = _make_example()
        assert example_key(ex1) == example_key(ex2)

    def test_key_stable_with_config_none(self) -> None:
        """config=None key is stable across two calls."""
        ex = _make_example()
        assert example_key(ex, config=None) == example_key(ex, config=None)

    def test_config_same_params_same_key(self) -> None:
        """Two WinnerModelConfig objects with identical clip params yield the same key."""
        from ml.config import WinnerModelConfig

        cfg1 = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        cfg2 = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        ex = _make_example()

        assert example_key(ex, config=cfg1) == example_key(ex, config=cfg2)

    def test_override_honoured_in_key(self) -> None:
        """clip_duration_override_s is used (effective_clip_duration_s) when set."""
        from ml.config import WinnerModelConfig

        cfg_base = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        cfg_override = WinnerModelConfig(
            fps_out=8, clip_duration_s=2.5, clip_duration_override_s=2.5
        )
        ex = _make_example()

        # Override value equals base — keys should be equal
        assert example_key(ex, cfg_base) == example_key(ex, cfg_override)

    def test_source_json_path_not_hashed(self) -> None:
        """source_json_path is NOT in the hash — only video_path matters."""
        ex1 = _make_example(source_json_path="/path/a.training.json")
        ex2 = _make_example(source_json_path="/path/b.training.json")
        # Different source files, same video data -> same key
        assert example_key(ex1) == example_key(ex2)

    def test_non_keyed_fields_dont_affect_key(self) -> None:
        """Fields not in the hash (schema_version, generated_by, winner) are ignored."""
        ex1 = _make_example(schema_version="1.1", generated_by="manual", winner="server")
        ex2 = _make_example(schema_version="2.0", generated_by="tool", winner="receiver")
        assert example_key(ex1) == example_key(ex2)


# ---------------------------------------------------------------------------
# TestExampleKeySensitivity
# ---------------------------------------------------------------------------


class TestExampleKeySensitivity:
    """Changing any keyed input must change the key."""

    def _base(self) -> RallyExample:
        return _make_example()

    def test_video_path_changes_key(self) -> None:
        base = self._base()
        other = _make_example(video_path="/fake/other_video.mp4")
        assert example_key(base) != example_key(other)

    def test_raw_start_changes_key(self) -> None:
        base = self._base()
        other = _make_example(raw_start=10.1)
        assert example_key(base) != example_key(other)

    def test_raw_end_changes_key(self) -> None:
        base = self._base()
        other = _make_example(raw_end=21.0)
        assert example_key(base) != example_key(other)

    def test_rally_index_changes_key(self) -> None:
        base = self._base()
        other = _make_example(rally_index=5)
        assert example_key(base) != example_key(other)

    def test_court_corners_changes_key(self) -> None:
        base = self._base()
        other_corners: tuple[tuple[int, int], ...] = (
            (0, 0),
            (320, 0),
            (320, 240),
            (0, 240),
        )
        other = _make_example(court_corners=other_corners)
        assert example_key(base) != example_key(other)

    def test_fps_out_changes_key(self) -> None:
        from ml.config import WinnerModelConfig

        ex = self._base()
        cfg_8 = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        cfg_12 = WinnerModelConfig(fps_out=12, clip_duration_s=2.5)
        assert example_key(ex, cfg_8) != example_key(ex, cfg_12)

    def test_clip_duration_changes_key(self) -> None:
        from ml.config import WinnerModelConfig

        ex = self._base()
        cfg_25 = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        cfg_30 = WinnerModelConfig(fps_out=8, clip_duration_s=3.0)
        assert example_key(ex, cfg_25) != example_key(ex, cfg_30)

    def test_config_none_vs_config_changes_key(self) -> None:
        """Providing config vs None produces different keys."""
        from ml.config import WinnerModelConfig

        ex = self._base()
        cfg = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        assert example_key(ex, config=None) != example_key(ex, config=cfg)

    def test_clip_override_changes_key(self) -> None:
        """A non-default clip_duration_override_s changes the effective key."""
        from ml.config import WinnerModelConfig

        ex = self._base()
        cfg_base = WinnerModelConfig(fps_out=8, clip_duration_s=2.5)
        cfg_override = WinnerModelConfig(
            fps_out=8, clip_duration_s=2.5, clip_duration_override_s=1.0
        )
        assert example_key(ex, cfg_base) != example_key(ex, cfg_override)

    def test_single_corner_change_changes_key(self) -> None:
        """Changing even one pixel in court_corners changes the key."""
        base = self._base()
        one_off: tuple[tuple[int, int], ...] = (
            (10, 20),
            (311, 20),  # x shifted by 1
            (310, 220),
            (10, 220),
        )
        other = _make_example(court_corners=one_off)
        assert example_key(base) != example_key(other)


# ---------------------------------------------------------------------------
# TestExampleKeyConfigParam
# ---------------------------------------------------------------------------


class TestExampleKeyConfigParam:
    """Verify config parameter handling."""

    def test_unknown_config_type_falls_back_gracefully(self) -> None:
        """Passing an unknown object as config logs a warning but returns a key."""

        class FakeConfig:
            pass

        ex = _make_example()
        # Should not raise; falls back to no-clip-params behaviour
        k = example_key(ex, config=FakeConfig())
        assert len(k) == 16

    def test_unknown_config_matches_none(self) -> None:
        """Unknown config object produces the same key as config=None."""

        class FakeConfig:
            pass

        ex = _make_example()
        assert example_key(ex, config=None) == example_key(ex, config=FakeConfig())
