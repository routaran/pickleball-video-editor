"""Tests for WinnerDataset.from_rally_examples alternate constructor.

All tests skip gracefully when torch is not installed via
``pytest.importorskip("torch")``.

Test classes
------------
TestFromRallyExamplesInternalState
    Verifies that the dataset's internal ``_records`` list is built correctly
    from RallyExample objects — without decoding any video frames.  This covers:

    - Label / field mapping (winning_team, end_seconds, corners, video_path)
    - Per-rally eligibility filtering (post_game, missing timestamps)
    - Video-wise train/val split determinism
    - Parity with the JSON-scanning constructor for the same data

All tests use tmp_path fixtures and synthetic .training.json files (no real
video files required) so the suite runs on any CI machine.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

torch = pytest.importorskip("torch")

from ml.config import WinnerModelConfig  # noqa: E402
from ml.examples import RallyExample, RallyExampleIndex  # noqa: E402
from ml.winner_dataset import (  # noqa: E402
    WinnerDataset,
    _RallyRecord,
    _horizontal_flip_frames,
)


# ---------------------------------------------------------------------------
# Shared constants & helpers
# ---------------------------------------------------------------------------

_CORNERS = [[10, 20], [310, 20], [310, 220], [10, 220]]
_CORNERS_TUPLE: tuple[tuple[int, int], ...] = tuple(
    (int(c[0]), int(c[1])) for c in _CORNERS
)

_DEFAULT_CONFIG = WinnerModelConfig()


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_training_json(
    tmp_path: Path,
    *,
    video_path: str = "/fake/video_a.mp4",
    name: str = "game.training.json",
    rallies: list | None = None,
) -> Path:
    """Write a minimal schema-1.1 training JSON and return its path."""
    if rallies is None:
        rallies = [
            {
                "index": 0,
                "score_at_start": "0-0-2",
                "winner": "server",
                "winning_team": 0,
                "is_post_game": False,
                "comment": None,
                "raw": {"start_seconds": 10.0, "end_seconds": 20.5},
            },
            {
                "index": 1,
                "score_at_start": "1-0-1",
                "winner": "receiver",
                "winning_team": 1,
                "is_post_game": False,
                "comment": None,
                "raw": {"start_seconds": 30.0, "end_seconds": 40.0},
            },
        ]

    data = {
        "schema_version": "1.1",
        "generated_by": "manual",
        "video": {
            "path": video_path,
            "court_corners": _CORNERS,
        },
        "rallies": rallies,
    }
    p = tmp_path / name
    _write_json(p, data)
    return p


def _examples_from_json(json_path: Path) -> list[RallyExample]:
    """Load all eligible RallyExample records from a single training JSON."""
    index = RallyExampleIndex(files=[json_path])
    return index.examples


# ---------------------------------------------------------------------------
# TestFromRallyExamplesInternalState
# ---------------------------------------------------------------------------


class TestFromRallyExamplesInternalState:
    """Verify internal _records state built by from_rally_examples."""

    # ------------------------------------------------------------------
    # Basic field mapping
    # ------------------------------------------------------------------

    def test_record_count_matches_eligible_rallies(self, tmp_path: Path) -> None:
        """from_rally_examples builds one _RallyRecord per eligible RallyExample."""
        json_path = _make_training_json(tmp_path)
        examples = _examples_from_json(json_path)
        assert len(examples) == 2  # sanity check fixture

        ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        # val_fraction=0.0 → all videos go to train; n_val is clamped to 0 for
        # a single-video case (n_videos < 2 → n_val=0).
        assert len(ds) == 2

    def test_labels_match_winning_team(self, tmp_path: Path) -> None:
        """_records[i].winning_team matches the original RallyExample.winning_team."""
        json_path = _make_training_json(tmp_path)
        examples = _examples_from_json(json_path)

        ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        record_labels = [r.winning_team for r in ds._records]
        example_labels = [e.winning_team for e in examples]
        assert sorted(record_labels) == sorted(example_labels)

    def test_end_seconds_mapped_from_raw_end(self, tmp_path: Path) -> None:
        """_RallyRecord.end_seconds is set from RallyExample.raw_end."""
        json_path = _make_training_json(tmp_path)
        examples = _examples_from_json(json_path)

        ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        record_ends = sorted(r.end_seconds for r in ds._records)
        example_ends = sorted(e.raw_end for e in examples)
        assert record_ends == pytest.approx(example_ends)

    def test_corners_mapped_correctly(self, tmp_path: Path) -> None:
        """_RallyRecord.corners matches the court_corners from the RallyExample."""
        json_path = _make_training_json(tmp_path)
        examples = _examples_from_json(json_path)

        ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        expected_corners = list(_CORNERS_TUPLE)
        for record in ds._records:
            assert record.corners == expected_corners

    def test_video_path_mapped_correctly(self, tmp_path: Path) -> None:
        """_RallyRecord.video_path matches the RallyExample.video_path."""
        json_path = _make_training_json(tmp_path, video_path="/fake/vid.mp4")
        examples = _examples_from_json(json_path)

        ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        for record in ds._records:
            assert record.video_path == Path("/fake/vid.mp4")

    # ------------------------------------------------------------------
    # Per-rally eligibility filtering
    # ------------------------------------------------------------------

    def test_post_game_rallies_filtered(self, tmp_path: Path) -> None:
        """Rallies with is_post_game=True are excluded from _records."""
        json_path = _make_training_json(
            tmp_path,
            rallies=[
                {
                    "index": 0,
                    "score_at_start": "11-9-2",
                    "winner": "server",
                    "winning_team": 0,
                    "is_post_game": True,
                    "comment": None,
                    "raw": {"start_seconds": 5.0, "end_seconds": 10.0},
                },
                {
                    "index": 1,
                    "score_at_start": "0-0-2",
                    "winner": "receiver",
                    "winning_team": 1,
                    "is_post_game": False,
                    "comment": None,
                    "raw": {"start_seconds": 20.0, "end_seconds": 30.0},
                },
            ],
        )
        # RallyExampleIndex already filters post_game; get examples manually to
        # include the post-game rally for testing the dataset filter directly.
        # We build a raw RallyExample for the post-game rally and pass both in.
        eligible_examples = _examples_from_json(json_path)
        assert len(eligible_examples) == 1  # index already strips post_game

        # Manually construct a post-game RallyExample to test dataset filtering
        postgame_ex = RallyExample.from_rally_dict(
            source_json_path=json_path,
            video_path=Path("/fake/video_a.mp4"),
            court_corners=_CORNERS_TUPLE,
            schema_version="1.1",
            generated_by="manual",
            rally_dict={
                "index": 0,
                "score_at_start": "11-9-2",
                "winner": "server",
                "winning_team": 0,
                "is_post_game": True,
                "comment": None,
                "raw": {"start_seconds": 5.0, "end_seconds": 10.0},
            },
        )

        all_examples = [postgame_ex] + eligible_examples
        ds = WinnerDataset.from_rally_examples(
            all_examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        # Only the non-post-game rally should appear
        assert len(ds) == 1
        assert ds._records[0].winning_team == 1

    def test_zero_timestamp_rally_filtered(self, tmp_path: Path) -> None:
        """Rallies with raw_end == raw_start == 0.0 are treated as missing raw."""
        # Construct a RallyExample that has both timestamps as 0.0
        json_path = _make_training_json(tmp_path)
        zero_ex = RallyExample.from_rally_dict(
            source_json_path=json_path,
            video_path=Path("/fake/video_a.mp4"),
            court_corners=_CORNERS_TUPLE,
            schema_version="1.1",
            generated_by="manual",
            rally_dict={
                "index": 0,
                "score_at_start": "0-0-2",
                "winner": "server",
                "winning_team": 0,
                "is_post_game": False,
                "comment": None,
                "raw": {"start_seconds": 0.0, "end_seconds": 0.0},
            },
        )

        ds = WinnerDataset.from_rally_examples(
            [zero_ex],
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.0,
            augment=False,
        )

        assert len(ds) == 0

    def test_empty_records_list(self) -> None:
        """Passing an empty list produces a dataset of length zero."""
        ds = WinnerDataset.from_rally_examples(
            [],
            _DEFAULT_CONFIG,
            split="train",
            augment=False,
        )
        assert len(ds) == 0

    def test_invalid_split_raises(self, tmp_path: Path) -> None:
        """Passing an unknown split value raises ValueError."""
        with pytest.raises(ValueError, match="split must be"):
            WinnerDataset.from_rally_examples(
                [],
                _DEFAULT_CONFIG,
                split="test",  # invalid
            )

    # ------------------------------------------------------------------
    # Train/val split behaviour
    # ------------------------------------------------------------------

    def test_single_video_all_in_train(self, tmp_path: Path) -> None:
        """With one video, n_val=0 and all records land in the train split."""
        json_path = _make_training_json(tmp_path)
        examples = _examples_from_json(json_path)

        train_ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )
        val_ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="val",
            val_fraction=0.2,
            augment=False,
        )

        # One video → n_val=0 → all records in train, none in val
        assert len(train_ds) == 2
        assert len(val_ds) == 0

    def test_two_videos_split_deterministically(self, tmp_path: Path) -> None:
        """Two videos split 80/20: one goes to val, one to train."""
        json_a = _make_training_json(
            tmp_path,
            video_path="/fake/alpha.mp4",
            name="alpha.training.json",
        )
        json_b = _make_training_json(
            tmp_path,
            video_path="/fake/beta.mp4",
            name="beta.training.json",
        )

        examples_a = _examples_from_json(json_a)
        examples_b = _examples_from_json(json_b)
        all_examples = examples_a + examples_b

        train_ds = WinnerDataset.from_rally_examples(
            all_examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )
        val_ds = WinnerDataset.from_rally_examples(
            all_examples,
            _DEFAULT_CONFIG,
            split="val",
            val_fraction=0.2,
            augment=False,
        )

        # 2 videos → n_val = max(1, floor(2*0.2)) = 1 → 1 train, 1 val
        assert len(train_ds) == 2
        assert len(val_ds) == 2
        # Total equals all eligible rallies
        assert len(train_ds) + len(val_ds) == len(all_examples)

    def test_train_val_records_are_disjoint(self, tmp_path: Path) -> None:
        """Train and val record sets share no overlapping (video, end_seconds) pairs."""
        json_a = _make_training_json(
            tmp_path,
            video_path="/fake/alpha.mp4",
            name="alpha.training.json",
        )
        json_b = _make_training_json(
            tmp_path,
            video_path="/fake/beta.mp4",
            name="beta.training.json",
        )
        all_examples = _examples_from_json(json_a) + _examples_from_json(json_b)

        train_ds = WinnerDataset.from_rally_examples(
            all_examples, _DEFAULT_CONFIG, split="train", augment=False
        )
        val_ds = WinnerDataset.from_rally_examples(
            all_examples, _DEFAULT_CONFIG, split="val", augment=False
        )

        train_keys = {
            (str(r.video_path), r.end_seconds) for r in train_ds._records
        }
        val_keys = {
            (str(r.video_path), r.end_seconds) for r in val_ds._records
        }

        assert train_keys.isdisjoint(val_keys), (
            "Train and val share records — data leakage detected"
        )

    # ------------------------------------------------------------------
    # Parity with the JSON-scanning constructor
    # ------------------------------------------------------------------

    def test_parity_with_json_constructor_record_count(self, tmp_path: Path) -> None:
        """from_rally_examples produces the same number of records as __init__."""
        json_path = _make_training_json(tmp_path)

        # JSON-scanning path (video existence check skipped because the fake
        # path "/fake/video_a.mp4" does not exist — but WinnerDataset.__init__
        # checks video_path.exists() and skips missing videos).
        # Write a real tmp video stub so __init__ does not skip it.
        fake_video = tmp_path / "video_a.mp4"
        fake_video.write_bytes(b"")  # empty stub; only existence is checked

        # Patch the video path in the JSON to point at the stub.
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["video"]["path"] = str(fake_video)
        _write_json(json_path, data)

        # Rebuild examples from the updated JSON
        examples = _examples_from_json(json_path)

        json_ds = WinnerDataset(
            training_json_paths=[json_path],
            config=_DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )
        ex_ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )

        assert len(json_ds) == len(ex_ds)

    def test_parity_with_json_constructor_labels(self, tmp_path: Path) -> None:
        """from_rally_examples and __init__ produce identical sorted label lists."""
        json_path = _make_training_json(tmp_path)

        fake_video = tmp_path / "video_a.mp4"
        fake_video.write_bytes(b"")

        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["video"]["path"] = str(fake_video)
        _write_json(json_path, data)

        examples = _examples_from_json(json_path)

        json_ds = WinnerDataset(
            training_json_paths=[json_path],
            config=_DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )
        ex_ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )

        json_labels = sorted(r.winning_team for r in json_ds._records)
        ex_labels = sorted(r.winning_team for r in ex_ds._records)
        assert json_labels == ex_labels

    def test_parity_with_json_constructor_end_seconds(self, tmp_path: Path) -> None:
        """from_rally_examples and __init__ produce identical sorted end_seconds."""
        json_path = _make_training_json(tmp_path)

        fake_video = tmp_path / "video_a.mp4"
        fake_video.write_bytes(b"")

        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["video"]["path"] = str(fake_video)
        _write_json(json_path, data)

        examples = _examples_from_json(json_path)

        json_ds = WinnerDataset(
            training_json_paths=[json_path],
            config=_DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )
        ex_ds = WinnerDataset.from_rally_examples(
            examples,
            _DEFAULT_CONFIG,
            split="train",
            val_fraction=0.2,
            augment=False,
        )

        json_ends = sorted(r.end_seconds for r in json_ds._records)
        ex_ends = sorted(r.end_seconds for r in ex_ds._records)
        assert json_ends == pytest.approx(ex_ends)


class TestGetItemAugmentationSemantics:
    """Regression tests for __getitem__ augmentation label semantics."""

    def _make_dataset(
        self,
        *,
        winning_team: int = 1,
        augment: bool = True,
    ) -> WinnerDataset:
        ds = WinnerDataset.__new__(WinnerDataset)
        ds._config = WinnerModelConfig()
        ds._split = "train"
        ds._do_augment = augment
        ds._records = [
            _RallyRecord(
                video_path=Path("/fake/video.mp4"),
                end_seconds=12.5,
                corners=list(_CORNERS_TUPLE),
                winning_team=winning_team,
                raw_start_seconds=10.0,
            )
        ]
        return ds

    @staticmethod
    def _asymmetric_frames() -> np.ndarray:
        frames = np.zeros((2, 4, 6, 3), dtype=np.uint8)
        frames[:, :, :2, 0] = 255
        frames[:, :, 4:, 1] = 128
        frames[:, 1:3, 2:4, 2] = 64
        return frames

    def test_horizontal_flip_mirrors_pixels_without_swapping_label(self) -> None:
        """Horizontal mirroring must not change the winning-team label.

        Court left/right mirroring preserves which side of the net won, so only
        pixel orientation should change.

        The mock returns a 2-frame array (arr_len=2 <= T=20 for default config),
        so __getitem__ takes the short-video path and random.randint is not
        invoked — the whole array is used as-is before flipping.
        """
        ds = self._make_dataset(winning_team=1, augment=True)
        frames = self._asymmetric_frames()
        expected_tensor = torch.from_numpy(_horizontal_flip_frames(frames)).permute(0, 3, 1, 2).float().div(255.0)

        with (
            patch("ml.winner_dataset._fetch_clip_tensor", return_value=frames),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda clip, **_: clip),
            patch("ml.winner_dataset.random.randint", return_value=0),
            patch("ml.winner_dataset.random.random", return_value=0.0),
        ):
            clip_tensor, winning_team = ds[0]

        assert winning_team == 1
        assert torch.equal(clip_tensor, expected_tensor)

    def test_no_flip_leaves_pixels_and_label_unchanged(self) -> None:
        """When the flip branch is not taken, __getitem__ must preserve both.

        The mock returns a 2-frame array (arr_len=2 <= T=20 for default config),
        so __getitem__ takes the short-video path and random.randint is not
        invoked — the whole array is used as-is.
        """
        ds = self._make_dataset(winning_team=0, augment=True)
        frames = self._asymmetric_frames()
        expected_tensor = torch.from_numpy(frames).permute(0, 3, 1, 2).float().div(255.0)

        with (
            patch("ml.winner_dataset._fetch_clip_tensor", return_value=frames),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda clip, **_: clip),
            patch("ml.winner_dataset.random.randint", return_value=0),
            patch("ml.winner_dataset.random.random", return_value=0.9),
        ):
            clip_tensor, winning_team = ds[0]

        assert winning_team == 0
        assert torch.equal(clip_tensor, expected_tensor)


class TestGetItemTemporalJitter:
    """Tests for the frame-index temporal jitter and cache-stable extraction."""

    # Small config: fps_out=2, clip_duration_s=1.0
    # → T = round(1.0 * 2) = 2, J = max(1, round(0.2 * 2)) = 1
    # → extended array: T + 2*J = 4 frames; nominal clip at [1:3]
    _SMALL_CONFIG = WinnerModelConfig(fps_out=2, clip_duration_s=1.0, device="cpu")

    def _make_augmenting_dataset(self, winning_team: int = 1) -> WinnerDataset:
        ds = WinnerDataset.__new__(WinnerDataset)
        ds._config = self._SMALL_CONFIG
        ds._split = "train"
        ds._do_augment = True
        ds._records = [
            _RallyRecord(
                video_path=Path("/fake/video.mp4"),
                end_seconds=12.5,
                corners=list(_CORNERS_TUPLE),
                winning_team=winning_team,
                raw_start_seconds=10.0,
            )
        ]
        return ds

    def test_extract_clip_called_with_stable_cache_key(self) -> None:
        """Augmented __getitem__ calls extract_clip with identical (start_s, end_s) every time.

        With fps_out=2, clip_duration_s=1.0, J=1:
          pad_s   = 1/2 = 0.5
          start_s = max(0, 12.5 - 1.0 - 0.5) = 11.0
          end_s   = 12.5 + 0.5               = 13.0

        These are fully deterministic regardless of the randint offset used for
        the frame-index jitter, so the disk-cache key is stable.
        """
        ds = self._make_augmenting_dataset()
        recorded_calls: list[tuple[float, float]] = []

        def fake_extract(path, start_s, end_s, fps, size, policy_tag=None):
            recorded_calls.append((start_s, end_s))
            # Return a 4-frame (T+2J) dummy array that passes the slicing path.
            return np.zeros((4, 128, 256, 3), dtype=np.uint8)

        with (
            patch("ml.winner_dataset.extract_clip", side_effect=fake_extract),
            patch("ml.winner_dataset.get_video_frame_size", return_value=(256, 128)),
            patch("ml.winner_dataset.compute_homography", return_value=np.eye(3)),
            patch("ml.winner_dataset.warp_clip_to_canonical", side_effect=lambda f, h, s: f),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda f, **_: f),
            patch("ml.winner_dataset.random.random", return_value=0.9),
        ):
            for _ in range(5):
                ds[0]

        assert len(recorded_calls) == 5
        first = recorded_calls[0]
        for call_args in recorded_calls[1:]:
            assert call_args == pytest.approx(first), (
                f"Cache key drifted: {first!r} vs {call_args!r}"
            )

    def test_jitter_offset_produces_different_frame_slices(self) -> None:
        """Different randint offsets (-J and +J) yield different frame windows.

        With J=1:
          offset = -1 → base_start=1, start=max(0,min(0,2))=0 → slice [0:2]
          offset = +1 → base_start=1, start=max(0,min(2,2))=2 → slice [2:4]

        The extended array is constructed so that [0:2] and [2:4] have
        distinguishable pixel content.
        """
        ds = self._make_augmenting_dataset(winning_team=0)

        # Mark the two possible windows with different R-channel values.
        extended = np.zeros((4, 4, 6, 3), dtype=np.uint8)
        extended[0:2, :, :, 0] = 50    # early window  — R = 50
        extended[2:4, :, :, 0] = 200   # late window   — R = 200

        common_patches = [
            patch("ml.winner_dataset._fetch_clip_tensor", return_value=extended),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda f, **_: f),
            patch("ml.winner_dataset.random.random", return_value=0.9),  # no flip
        ]

        with (
            patch("ml.winner_dataset._fetch_clip_tensor", return_value=extended),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda f, **_: f),
            patch("ml.winner_dataset.random.random", return_value=0.9),
            patch("ml.winner_dataset.random.randint", return_value=-1),
        ):
            tensor_early, _ = ds[0]

        with (
            patch("ml.winner_dataset._fetch_clip_tensor", return_value=extended),
            patch("ml.winner_dataset._apply_color_jitter", side_effect=lambda f, **_: f),
            patch("ml.winner_dataset.random.random", return_value=0.9),
            patch("ml.winner_dataset.random.randint", return_value=1),
        ):
            tensor_late, _ = ds[0]

        assert not torch.equal(tensor_early, tensor_late), (
            "Different randint offsets must produce different frame slices"
        )

    def test_eval_path_is_deterministic(self) -> None:
        """No-augment (val) dataset produces the same clip tensor on every call."""
        ds = WinnerDataset.__new__(WinnerDataset)
        ds._config = self._SMALL_CONFIG
        ds._split = "val"
        ds._do_augment = False
        ds._records = [
            _RallyRecord(
                video_path=Path("/fake/video.mp4"),
                end_seconds=12.5,
                corners=list(_CORNERS_TUPLE),
                winning_team=1,
                raw_start_seconds=10.0,
            )
        ]

        # Extended array with content distinguishable across windows.
        extended = np.zeros((4, 4, 6, 3), dtype=np.uint8)
        extended[1:3, :, :, 0] = 100  # nominal window (offset=0) — R = 100

        with patch("ml.winner_dataset._fetch_clip_tensor", return_value=extended):
            t1, label1 = ds[0]
            t2, label2 = ds[0]
            t3, label3 = ds[0]

        assert label1 == label2 == label3 == 1
        assert torch.equal(t1, t2), "Eval path must be deterministic"
        assert torch.equal(t1, t3), "Eval path must be deterministic"
