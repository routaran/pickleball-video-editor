"""Tests for Phase 4 winner clip-window clamping, padding, and cache-key versioning.

Covers:
- ``clamp_to_rally_start_v1`` clamp behaviour (never starts before the rally),
- the ``repeat_first_frame_v1`` padding policy applied inside ``_fetch_clip_tensor``,
- the policy-tagged cache key change (clamped vs unclamped variants differ),
- ``_RallyRecord.raw_start_seconds`` round-trips through both construction paths,
- the new policy fields serialise into / load back out of a checkpoint config.

All tests run on CPU with mocked video I/O so no GPU or real video is required.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

torch = pytest.importorskip("torch")

from ml.config import (  # noqa: E402
    CHECKPOINT_SCHEMA_VERSION,
    DEFAULT_CLIP_WINDOW_POLICY,
    DEFAULT_PADDING_POLICY,
    WinnerModelConfig,
    load_winner_config_from_checkpoint,
)
from ml.examples import RallyExample, RallyExampleIndex  # noqa: E402
from ml.video_features import hash_clip_key  # noqa: E402
from ml.winner_dataset import (  # noqa: E402
    WinnerDataset,
    _RallyRecord,
    _clip_policy_cache_tag,
    _fetch_clip_tensor,
    _pad_repeat_first_frame_v1,
    clamp_to_rally_start_v1,
)


_CORNERS = [[10, 20], [310, 20], [310, 220], [10, 220]]
_CORNERS_TUPLE: tuple[tuple[int, int], ...] = tuple((int(c[0]), int(c[1])) for c in _CORNERS)


# ---------------------------------------------------------------------------
# clamp_to_rally_start_v1
# ---------------------------------------------------------------------------


class TestClampToRallyStart:
    def test_long_clip_on_short_rally_clamps_to_rally_start(self) -> None:
        """A 5s window on a rally that started 2s before the end clamps to the start."""
        # end=100, rally started at 98 → a 5s window would naively start at 95,
        # but must clamp to 98 so it never reaches into the previous point.
        start = clamp_to_rally_start_v1(98.0, 100.0, 5.0)
        assert start == 98.0

    def test_clip_shorter_than_rally_uses_duration_window(self) -> None:
        """When the rally is longer than the clip, the window keeps full duration."""
        # rally started at 90; a 5s window from end=100 starts at 95, which is
        # after raw_start, so the duration window wins.
        start = clamp_to_rally_start_v1(90.0, 100.0, 5.0)
        assert start == 95.0

    def test_result_never_negative(self) -> None:
        """A rally near t=0 still produces a non-negative seek offset."""
        start = clamp_to_rally_start_v1(-3.0, 1.0, 5.0)
        assert start == 0.0

    def test_clamp_equals_duration_boundary(self) -> None:
        """When raw_start exactly equals the duration boundary, both agree."""
        start = clamp_to_rally_start_v1(95.0, 100.0, 5.0)
        assert start == 95.0


# ---------------------------------------------------------------------------
# repeat_first_frame_v1 padding
# ---------------------------------------------------------------------------


class TestRepeatFirstFramePadding:
    def test_pads_short_clip_to_target_length(self) -> None:
        frames = np.zeros((2, 4, 6, 3), dtype=np.uint8)
        frames[0, :, :, 0] = 10
        frames[1, :, :, 0] = 20
        padded = _pad_repeat_first_frame_v1(frames, target_len=5)
        assert padded.shape == (5, 4, 6, 3)

    def test_padding_repeats_first_frame_at_front(self) -> None:
        frames = np.zeros((2, 1, 1, 3), dtype=np.uint8)
        frames[0, 0, 0, 0] = 10  # first frame marker
        frames[1, 0, 0, 0] = 20  # last frame marker
        padded = _pad_repeat_first_frame_v1(frames, target_len=4)
        # Two pad frames at the front, each a copy of the original first frame.
        assert padded[0, 0, 0, 0] == 10
        assert padded[1, 0, 0, 0] == 10
        assert padded[2, 0, 0, 0] == 10  # original first frame
        assert padded[3, 0, 0, 0] == 20  # original last frame

    def test_no_padding_when_already_long_enough(self) -> None:
        frames = np.zeros((5, 2, 2, 3), dtype=np.uint8)
        out = _pad_repeat_first_frame_v1(frames, target_len=3)
        assert out.shape == (5, 2, 2, 3)
        assert out is frames  # no-op returns the same array

    def test_empty_clip_is_unchanged(self) -> None:
        frames = np.zeros((0, 2, 2, 3), dtype=np.uint8)
        out = _pad_repeat_first_frame_v1(frames, target_len=4)
        assert out.shape == (0, 2, 2, 3)

    def test_padding_is_stable_across_calls(self) -> None:
        frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
        frames[0, 0, 0, 0] = 7
        a = _pad_repeat_first_frame_v1(frames, target_len=4)
        b = _pad_repeat_first_frame_v1(frames, target_len=4)
        np.testing.assert_array_equal(a, b)


# ---------------------------------------------------------------------------
# _fetch_clip_tensor: clamp + padding integration
# ---------------------------------------------------------------------------


class TestFetchClipTensorWindowing:
    # fps_out=2, clip_duration_s=1.0 → T=2, J=1, pad_s=0.5 → extended target = 4.
    _CONFIG = WinnerModelConfig(fps_out=2, clip_duration_s=1.0, device="cpu")

    def _record(self, *, raw_start: float, end: float) -> _RallyRecord:
        return _RallyRecord(
            video_path=Path("/fake/video.mp4"),
            end_seconds=end,
            corners=list(_CORNERS_TUPLE),
            winning_team=0,
            raw_start_seconds=raw_start,
        )

    def test_clip_does_not_start_before_raw_start(self) -> None:
        """The extract window start is never earlier than raw_start_seconds."""
        record = self._record(raw_start=99.5, end=100.0)
        recorded: dict[str, float] = {}

        def fake_extract(path, start_s, end_s, fps, size, policy_tag=None):
            recorded["start_s"] = start_s
            recorded["end_s"] = end_s
            return np.zeros((4, 4, 6, 3), dtype=np.uint8)

        with (
            patch("ml.winner_dataset.extract_clip", side_effect=fake_extract),
            patch("ml.winner_dataset.get_video_frame_size", return_value=(256, 128)),
            patch("ml.winner_dataset.compute_homography", return_value=np.eye(3)),
            patch("ml.winner_dataset.warp_clip_to_canonical", side_effect=lambda f, h, s: f),
        ):
            _fetch_clip_tensor(record, self._CONFIG)

        # raw_start=99.5 clamps the 1s window (would-be start 99.0) to 99.5,
        # and the jitter pad cannot pull it earlier than raw_start either.
        assert recorded["start_s"] >= 99.5

    def test_short_window_is_padded_to_extended_target(self) -> None:
        """A clamped window that yields too few frames is padded to T + 2*J."""
        record = self._record(raw_start=99.8, end=100.0)

        # Simulate ffmpeg returning only 1 frame for the tiny clamped window.
        def fake_extract(path, start_s, end_s, fps, size, policy_tag=None):
            return np.zeros((1, 4, 6, 3), dtype=np.uint8)

        with (
            patch("ml.winner_dataset.extract_clip", side_effect=fake_extract),
            patch("ml.winner_dataset.get_video_frame_size", return_value=(256, 128)),
            patch("ml.winner_dataset.compute_homography", return_value=np.eye(3)),
            patch("ml.winner_dataset.warp_clip_to_canonical", side_effect=lambda f, h, s: f),
        ):
            out = _fetch_clip_tensor(record, self._CONFIG)

        # T=2, J=1 → target extended length = 4.
        assert out.shape[0] == 4

    def test_extract_called_with_policy_tag(self) -> None:
        """The clip-window/padding policy tag is passed to extract_clip."""
        record = self._record(raw_start=90.0, end=100.0)
        recorded_tag: dict[str, object] = {}

        def fake_extract(path, start_s, end_s, fps, size, policy_tag=None):
            recorded_tag["tag"] = policy_tag
            return np.zeros((4, 4, 6, 3), dtype=np.uint8)

        with (
            patch("ml.winner_dataset.extract_clip", side_effect=fake_extract),
            patch("ml.winner_dataset.get_video_frame_size", return_value=(256, 128)),
            patch("ml.winner_dataset.compute_homography", return_value=np.eye(3)),
            patch("ml.winner_dataset.warp_clip_to_canonical", side_effect=lambda f, h, s: f),
        ):
            _fetch_clip_tensor(record, self._CONFIG)

        assert recorded_tag["tag"] == _clip_policy_cache_tag(self._CONFIG)


# ---------------------------------------------------------------------------
# Cache-key versioning
# ---------------------------------------------------------------------------


class TestCacheKeyVersioning:
    def test_policy_tag_changes_cache_key(self) -> None:
        """A non-None policy tag changes the cache key vs the legacy (None) key."""
        path = Path("/vid.mp4")
        legacy = hash_clip_key(path, 95.0, 100.0, 8, (256, 128))
        tagged = hash_clip_key(
            path, 95.0, 100.0, 8, (256, 128), "clamp_to_rally_start_v1+repeat_first_frame_v1"
        )
        assert legacy != tagged

    def test_legacy_key_unchanged_when_tag_omitted(self) -> None:
        """Omitting the tag reproduces the historical byte-for-byte key."""
        path = Path("/vid.mp4")
        explicit_none = hash_clip_key(path, 95.0, 100.0, 8, (256, 128), None)
        positional = hash_clip_key(path, 95.0, 100.0, 8, (256, 128))
        assert explicit_none == positional

    def test_different_policies_produce_different_keys(self) -> None:
        """Two different policy tags never collide for the same time range."""
        path = Path("/vid.mp4")
        a = hash_clip_key(path, 95.0, 100.0, 8, (256, 128), "policy_a")
        b = hash_clip_key(path, 95.0, 100.0, 8, (256, 128), "policy_b")
        assert a != b

    def test_clamped_vs_unclamped_window_differ(self) -> None:
        """Clamped (start=98) and unclamped (start=95) windows yield distinct keys."""
        path = Path("/vid.mp4")
        tag = "clamp_to_rally_start_v1+repeat_first_frame_v1"
        clamped = hash_clip_key(path, 98.0, 100.0, 8, (256, 128), tag)
        unclamped = hash_clip_key(path, 95.0, 100.0, 8, (256, 128), tag)
        assert clamped != unclamped

    def test_policy_cache_tag_combines_both_policies(self) -> None:
        cfg = WinnerModelConfig()
        tag = _clip_policy_cache_tag(cfg)
        assert cfg.clip_window_policy in tag
        assert cfg.padding_policy in tag


# ---------------------------------------------------------------------------
# raw_start_seconds round-trip through both construction paths
# ---------------------------------------------------------------------------


def _make_training_json(tmp_path: Path) -> Path:
    data = {
        "schema_version": "1.1",
        "generated_by": "manual",
        "video": {"path": "/fake/video_a.mp4", "court_corners": _CORNERS},
        "rallies": [
            {
                "index": 0,
                "score_at_start": "0-0-2",
                "winner": "server",
                "winning_team": 0,
                "is_post_game": False,
                "raw": {"start_seconds": 12.0, "end_seconds": 20.5},
            },
            {
                "index": 1,
                "score_at_start": "1-0-1",
                "winner": "receiver",
                "winning_team": 1,
                "is_post_game": False,
                "raw": {"start_seconds": 33.0, "end_seconds": 40.0},
            },
        ],
    }
    p = tmp_path / "game.training.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestRawStartRoundTrip:
    def test_json_path_populates_raw_start_seconds(self, tmp_path: Path) -> None:
        json_path = _make_training_json(tmp_path)
        # The JSON-scanning constructor verifies the referenced video exists;
        # the fixture points at a fake path, so patch exists() to True (no frames
        # are decoded — we only inspect the parsed _records).
        with patch("ml.winner_dataset.Path.exists", return_value=True):
            ds = WinnerDataset(
                training_json_paths=[json_path],
                config=WinnerModelConfig(),
                split="train",
                val_fraction=0.0,
                augment=False,
            )
        starts = sorted(r.raw_start_seconds for r in ds._records)
        assert starts == pytest.approx([12.0, 33.0])

    def test_from_rally_examples_populates_raw_start_seconds(self, tmp_path: Path) -> None:
        json_path = _make_training_json(tmp_path)
        examples = RallyExampleIndex(files=[json_path]).examples
        ds = WinnerDataset.from_rally_examples(
            examples,
            WinnerModelConfig(),
            split="train",
            val_fraction=0.0,
            augment=False,
        )
        record_starts = sorted(r.raw_start_seconds for r in ds._records)
        example_starts = sorted(e.raw_start for e in examples)
        assert record_starts == pytest.approx(example_starts)

    def test_no_split_path_populates_raw_start_seconds(self, tmp_path: Path) -> None:
        json_path = _make_training_json(tmp_path)
        examples = RallyExampleIndex(files=[json_path]).examples
        ds = WinnerDataset._from_rally_examples_no_split(
            records=examples,
            config=WinnerModelConfig(),
            split="val",
            augment=False,
        )
        record_starts = sorted(r.raw_start_seconds for r in ds._records)
        example_starts = sorted(e.raw_start for e in examples)
        assert record_starts == pytest.approx(example_starts)

    def test_default_raw_start_is_zero(self) -> None:
        """Omitting raw_start_seconds yields the safe 0.0 default."""
        record = _RallyRecord(
            video_path=Path("/fake/v.mp4"),
            end_seconds=10.0,
            corners=list(_CORNERS_TUPLE),
            winning_team=0,
        )
        assert record.raw_start_seconds == 0.0


# ---------------------------------------------------------------------------
# Policy fields checkpoint round-trip
# ---------------------------------------------------------------------------


class TestPolicyFieldCheckpointRoundTrip:
    def test_config_defaults_carry_policy_names(self) -> None:
        cfg = WinnerModelConfig()
        assert cfg.clip_window_policy == DEFAULT_CLIP_WINDOW_POLICY
        assert cfg.padding_policy == DEFAULT_PADDING_POLICY

    def test_policy_fields_serialise_and_load_back(self) -> None:
        from ml.train_winner import _config_to_dict

        original = WinnerModelConfig(
            clip_window_policy="clamp_to_rally_start_v1",
            padding_policy="repeat_first_frame_v1",
        )
        raw = _config_to_dict(original)
        assert raw["clip_window_policy"] == "clamp_to_rally_start_v1"
        assert raw["padding_policy"] == "repeat_first_frame_v1"

        checkpoint = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "config": raw,
        }
        loaded = load_winner_config_from_checkpoint(checkpoint)
        assert loaded.clip_window_policy == original.clip_window_policy
        assert loaded.padding_policy == original.padding_policy
