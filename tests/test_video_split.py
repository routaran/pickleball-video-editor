"""Tests for ml.evaluation.splits.video_wise_split.

Covers:
- 0 examples (empty input)
- 1 distinct video  -> all train, empty val
- 2 distinct videos -> n_val formula; no leakage
- 3+ distinct videos -> n_val formula; no leakage
- determinism (two calls with the same input produce the same output)
- val_fraction boundary validation

All tests are torch-free.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.evaluation.splits import video_wise_split  # noqa: E402
from ml.examples import RallyExample  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_CORNERS: tuple[tuple[int, int], ...] = (
    (10, 20),
    (310, 20),
    (310, 220),
    (10, 220),
)


def _make_example(video_path: str, rally_index: int = 0) -> RallyExample:
    """Build a minimal RallyExample for a given video path string."""
    return RallyExample(
        source_json_path=Path("/fake/source.training.json"),
        video_path=Path(video_path),
        rally_index=rally_index,
        raw_start=0.0,
        raw_end=10.0,
        score_at_start="0-0-2",
        score_parts=(0, 0, 2),
        server_num=2,
        winner="server",
        winning_team=0,
        court_corners=_CORNERS,
        schema_version="1.1",
        generated_by="manual",
        is_post_game=False,
    )


def _video_set(examples: list[RallyExample]) -> set[str]:
    """Return the set of video path strings present in *examples*."""
    return {str(ex.video_path) for ex in examples}


# ---------------------------------------------------------------------------
# Edge cases: 0 videos, 1 video
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_input_returns_two_empty_lists(self) -> None:
        train, val = video_wise_split([], val_fraction=0.2)
        assert train == []
        assert val == []

    def test_single_video_all_train_empty_val(self) -> None:
        """With only 1 distinct video n_val must be 0 regardless of val_fraction."""
        examples = [
            _make_example("/video/game_a.mp4", 0),
            _make_example("/video/game_a.mp4", 1),
            _make_example("/video/game_a.mp4", 2),
        ]
        train, val = video_wise_split(examples, val_fraction=0.5)
        assert len(val) == 0
        assert len(train) == 3

    def test_single_video_n_val_is_zero(self) -> None:
        """n_val formula: n_videos < 2 -> n_val = 0."""
        examples = [_make_example("/video/only.mp4")]
        train, val = video_wise_split(examples, val_fraction=1.0)
        assert len(val) == 0
        assert len(train) == 1


# ---------------------------------------------------------------------------
# Two-video case
# ---------------------------------------------------------------------------

class TestTwoVideos:
    def _make_two_video_examples(self) -> list[RallyExample]:
        return [
            _make_example("/video/alpha.mp4", 0),
            _make_example("/video/alpha.mp4", 1),
            _make_example("/video/beta.mp4", 0),
            _make_example("/video/beta.mp4", 1),
        ]

    def test_n_val_is_one_for_two_videos(self) -> None:
        """floor(2 * 0.2) = 0, max(1, 0) = 1 -> 1 val video."""
        examples = self._make_two_video_examples()
        train, val = video_wise_split(examples, val_fraction=0.2)
        train_videos = _video_set(train)
        val_videos = _video_set(val)
        assert len(val_videos) == 1
        assert len(train_videos) == 1

    def test_no_video_leaks_two_videos(self) -> None:
        examples = self._make_two_video_examples()
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert _video_set(train).isdisjoint(_video_set(val))

    def test_last_video_in_sorted_order_is_val(self) -> None:
        """The LAST video in lexicographic order forms the val set."""
        examples = self._make_two_video_examples()
        _, val = video_wise_split(examples, val_fraction=0.2)
        # Sorted: ["/video/alpha.mp4", "/video/beta.mp4"] -> val = "beta"
        assert _video_set(val) == {"/video/beta.mp4"}

    def test_all_examples_accounted_for(self) -> None:
        examples = self._make_two_video_examples()
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert len(train) + len(val) == len(examples)


# ---------------------------------------------------------------------------
# Multi-video case (3+ videos)
# ---------------------------------------------------------------------------

class TestMultipleVideos:
    def _make_n_video_examples(self, n: int) -> list[RallyExample]:
        """Create 2 rallies per video for n distinct videos."""
        examples = []
        for i in range(n):
            path = f"/video/game_{i:03d}.mp4"
            examples.append(_make_example(path, 0))
            examples.append(_make_example(path, 1))
        return examples

    def test_n_val_formula_five_videos(self) -> None:
        """floor(5 * 0.2) = 1, max(1, 1) = 1 -> 1 val video."""
        examples = self._make_n_video_examples(5)
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert len(_video_set(val)) == 1
        assert len(_video_set(train)) == 4

    def test_n_val_formula_ten_videos(self) -> None:
        """floor(10 * 0.2) = 2, max(1, 2) = 2 -> 2 val videos."""
        examples = self._make_n_video_examples(10)
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert len(_video_set(val)) == 2
        assert len(_video_set(train)) == 8

    def test_n_val_formula_three_videos_large_fraction(self) -> None:
        """floor(3 * 0.5) = 1, max(1, 1) = 1 -> 1 val video."""
        examples = self._make_n_video_examples(3)
        train, val = video_wise_split(examples, val_fraction=0.5)
        assert len(_video_set(val)) == 1
        assert len(_video_set(train)) == 2

    def test_no_video_leaks_many_videos(self) -> None:
        examples = self._make_n_video_examples(7)
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert _video_set(train).isdisjoint(_video_set(val))

    def test_all_examples_present(self) -> None:
        n = 9
        examples = self._make_n_video_examples(n)
        train, val = video_wise_split(examples, val_fraction=0.2)
        assert len(train) + len(val) == n * 2

    def test_last_n_val_videos_are_val(self) -> None:
        """Val set must be the LAST n_val videos in sorted order."""
        import math
        n = 6
        val_fraction = 0.2
        examples = self._make_n_video_examples(n)
        _, val = video_wise_split(examples, val_fraction=val_fraction)

        n_val = max(1, math.floor(n * val_fraction))
        all_keys = sorted(
            {str(ex.video_path) for ex in examples}
        )
        expected_val_videos = set(all_keys[-n_val:])
        assert _video_set(val) == expected_val_videos


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_calls_identical_output(self) -> None:
        examples = []
        for i in range(8):
            examples.append(_make_example(f"/video/game_{i}.mp4", 0))
            examples.append(_make_example(f"/video/game_{i}.mp4", 1))

        train1, val1 = video_wise_split(examples, val_fraction=0.2)
        train2, val2 = video_wise_split(examples, val_fraction=0.2)

        assert [str(ex.video_path) for ex in train1] == [str(ex.video_path) for ex in train2]
        assert [str(ex.video_path) for ex in val1] == [str(ex.video_path) for ex in val2]

    def test_input_order_independence(self) -> None:
        """Reversing the input list must produce the same split."""
        examples = [_make_example(f"/video/vid_{i}.mp4") for i in range(6)]
        reversed_examples = list(reversed(examples))

        _, val1 = video_wise_split(examples, val_fraction=0.2)
        _, val2 = video_wise_split(reversed_examples, val_fraction=0.2)

        assert _video_set(val1) == _video_set(val2)


# ---------------------------------------------------------------------------
# val_fraction boundary validation
# ---------------------------------------------------------------------------

class TestValFractionValidation:
    def test_zero_fraction_all_train(self) -> None:
        """val_fraction=0.0 with 2+ videos: floor(n*0)=0, max(1,0)=1 -> 1 val video."""
        # Note: even at 0.0 fraction the formula enforces at least 1 val video
        # when n_videos >= 2, matching WinnerDataset behaviour.
        examples = [
            _make_example("/video/a.mp4"),
            _make_example("/video/b.mp4"),
        ]
        train, val = video_wise_split(examples, val_fraction=0.0)
        assert len(_video_set(val)) == 1

    def test_fraction_one_all_val(self) -> None:
        """val_fraction=1.0: floor(n*1)=n, max(1,n)=n -> all videos in val."""
        examples = [_make_example(f"/video/v{i}.mp4") for i in range(4)]
        train, val = video_wise_split(examples, val_fraction=1.0)
        assert len(train) == 0
        assert len(val) == 4

    def test_invalid_fraction_raises(self) -> None:
        with pytest.raises(ValueError, match="val_fraction"):
            video_wise_split([], val_fraction=1.5)

    def test_negative_fraction_raises(self) -> None:
        with pytest.raises(ValueError, match="val_fraction"):
            video_wise_split([], val_fraction=-0.1)
