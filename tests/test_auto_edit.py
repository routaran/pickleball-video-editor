"""Integration tests for the auto_edit pipeline.

All tests use mocking — no real video files or trained checkpoints are
required.

Strategy for torch-free environments
--------------------------------------
``ml.auto_edit`` imports ``ml.predict`` and ``ml.predict_winner`` at module
load time, and those modules unconditionally import ``torch``.  To allow
collecting this test file when torch is not installed, we pre-populate
``sys.modules`` with lightweight ``MagicMock`` stubs for all torch-bearing
sub-modules *before* ``ml.auto_edit`` is imported.  Once the stubs are in
place, the real ``ml.auto_edit`` module is imported and can be patched
through the normal ``unittest.mock.patch`` machinery.

Mock patch paths used in each test (names bound inside ``ml.auto_edit``)
-------------------------------------------------------------------------
    ml.auto_edit.predict_video   — from ml.predict import predict_video
    ml.auto_edit.predict_winners — from ml.predict_winner import predict_winners
    ml.auto_edit.probe_video     — from src.video.probe import probe_video
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-stub torch and every ml.* sub-module that would pull it in.
# Must happen before any ml.auto_edit import.
# ---------------------------------------------------------------------------

# Only stub torch & friends if the real torch is unavailable. When torch *is*
# installed (normal dev/CI case), do nothing — leaving the real modules in
# sys.modules so downstream test files that import torch get the real thing.
# If torch is missing, install lightweight MagicMock stubs so this file can
# still be collected (those environments cannot run any other torch test
# either, so the global pollution is moot).
try:
    import torch  # noqa: F401
except ImportError:
    _TORCH_DEPENDENT_MODULES = [
        "torch", "torch.nn", "torch.nn.functional", "torch.utils", "torch.utils.data",
        "torchaudio", "torchvision", "numpy",
        "ml.predict", "ml.predict_winner", "ml.winner_model",
        "ml.video_features", "ml.model", "ml.dataset",
    ]
    for _name in _TORCH_DEPENDENT_MODULES:
        if _name not in sys.modules:
            sys.modules[_name] = MagicMock()

# ml.predict and ml.predict_winner are now stubs; ensure ml.auto_edit is
# freshly importable with those stubs in place.
if "ml.auto_edit" in sys.modules:
    del sys.modules["ml.auto_edit"]

import ml.auto_edit  # noqa: E402 — intentional late import
from ml.auto_edit import auto_edit, AutoEditResult, AutoEditSetup  # noqa: E402

# VideoInfo lives in src/ (no PyQt dep).
from src.video.probe import VideoInfo  # noqa: E402


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_FAKE_INTERVALS_5: list[dict[str, float]] = [
    {"start_seconds": 1.0, "end_seconds": 5.0, "duration_seconds": 4.0},
    {"start_seconds": 6.0, "end_seconds": 10.0, "duration_seconds": 4.0},
    {"start_seconds": 11.0, "end_seconds": 15.0, "duration_seconds": 4.0},
    {"start_seconds": 16.0, "end_seconds": 20.0, "duration_seconds": 4.0},
    {"start_seconds": 21.0, "end_seconds": 25.0, "duration_seconds": 4.0},
]

# Index 2 has confidence 0.6 — deliberately below the default 0.75 threshold.
_FAKE_WINNERS_5: list[tuple[int, float]] = [
    (0, 0.9),
    (1, 0.85),
    (0, 0.6),
    (1, 0.9),
    (0, 0.8),
]


def _make_video_info(video_path: Path) -> VideoInfo:
    return VideoInfo(
        path=str(video_path),
        width=1920,
        height=1080,
        fps=30.0,
        duration=30.0,
        codec_name="h264",
        codec_long_name="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def video_path(tmp_path: Path) -> Path:
    """Empty video file so path.exists() checks pass."""
    p = tmp_path / "game.mp4"
    p.touch()
    return p


@pytest.fixture()
def checkpoint_path(tmp_path: Path) -> Path:
    """Empty checkpoint file so FileNotFoundError is not raised."""
    p = tmp_path / "best_winner.pt"
    p.touch()
    return p


@pytest.fixture()
def corners() -> list[tuple[int, int]]:
    return [(100, 200), (800, 200), (800, 600), (100, 600)]


@pytest.fixture()
def doubles_setup() -> AutoEditSetup:
    return AutoEditSetup(
        game_type="doubles",
        victory_rule="11",
        team1_players=["Alice", "Bob"],
        team2_players=["Carol", "Dave"],
    )


# ---------------------------------------------------------------------------
# Helper: build four stacked patches for the standard 5-rally scenario.
#
# KdenliveGenerator has its own probe_video import (lazily called via the
# video_info property), so it must be patched independently of the
# ml.auto_edit.probe_video reference.
# ---------------------------------------------------------------------------


def _patches_5_rally(video_path: Path):
    """Return a tuple of four context managers ready for ``with`` unpacking."""
    fake_info = _make_video_info(video_path)
    return (
        patch("ml.auto_edit.predict_video", return_value=_FAKE_INTERVALS_5),
        patch("ml.auto_edit.predict_winners", return_value=_FAKE_WINNERS_5),
        patch("ml.auto_edit.probe_video", return_value=fake_info),
        patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
    )


# ---------------------------------------------------------------------------
# Test 1 – correct rally count
# ---------------------------------------------------------------------------


class TestRallyCount:
    """auto_edit.predicted_rally_count matches the audio-model interval count."""

    def test_correct_rally_count(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        p1, p2, p3, p4 = _patches_5_rally(video_path)
        with p1, p2, p3, p4:
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert result.predicted_rally_count == 5


# ---------------------------------------------------------------------------
# Test 2 – low-confidence flagging
# ---------------------------------------------------------------------------


class TestLowConfidenceFlagging:
    """Rallies below the 0.75 default threshold are listed in low_confidence_rally_indices."""

    def test_rally_index_2_flagged(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        # _FAKE_WINNERS_5[2] has confidence 0.6, which is below 0.75.
        p1, p2, p3, p4 = _patches_5_rally(video_path)
        with p1, p2, p3, p4:
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert result.low_confidence_rally_indices == [2]

    def test_no_flags_when_all_high_confidence(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        all_high: list[tuple[int, float]] = [(0, 0.9)] * 5
        fake_info = _make_video_info(video_path)
        with (
            patch("ml.auto_edit.predict_video", return_value=_FAKE_INTERVALS_5),
            patch("ml.auto_edit.predict_winners", return_value=all_high),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert result.low_confidence_rally_indices == []


# ---------------------------------------------------------------------------
# Test 3 – output files created
# ---------------------------------------------------------------------------


class TestOutputFilesCreated:
    """All three output files exist on disk after a successful pipeline run."""

    def _run(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> AutoEditResult:
        p1, p2, p3, p4 = _patches_5_rally(video_path)
        with p1, p2, p3, p4:
            return auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

    def test_kdenlive_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = self._run(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.kdenlive_path.exists()

    def test_ass_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = self._run(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.ass_path.exists()

    def test_training_json_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = self._run(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.training_json_path.exists()


# ---------------------------------------------------------------------------
# Test 4 – training JSON schema correctness
# ---------------------------------------------------------------------------


class TestTrainingJsonSchema:
    """The .training.json file satisfies the expected schema contract."""

    def _run_and_load(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> tuple[AutoEditResult, dict]:
        p1, p2, p3, p4 = _patches_5_rally(video_path)
        with p1, p2, p3, p4:
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )
        data = json.loads(result.training_json_path.read_text(encoding="utf-8"))
        return result, data

    def test_schema_version(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        _, data = self._run_and_load(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert data["schema_version"] == "1.1"

    def test_generated_by(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        _, data = self._run_and_load(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert data["generated_by"] == "auto_edit"

    def test_rallies_count_does_not_exceed_predicted(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result, data = self._run_and_load(
            tmp_path, video_path, checkpoint_path, corners, doubles_setup
        )
        # The JSON may have fewer entries than predicted_rally_count if the
        # game ended before all predicted rallies were processed.
        assert len(data["rallies"]) <= result.predicted_rally_count


# ---------------------------------------------------------------------------
# Test 5 – game-over truncation
# ---------------------------------------------------------------------------


class TestGameOverTruncation:
    """Score simulation stops as soon as a team satisfies the victory condition."""

    def test_game_ends_before_all_rallies_processed(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # Build 10 rally intervals that extend well beyond any win condition.
        n = 10
        intervals: list[dict[str, float]] = [
            {
                "start_seconds": float(i * 4 + 1),
                "end_seconds": float(i * 4 + 4),
                "duration_seconds": 3.0,
            }
            for i in range(n)
        ]

        # winning_team == 0 for every rally (team 0 perspective from the
        # winner model).  auto_edit maps winning_team == serving_team to
        # "server wins" and scores accordingly.  Using victory_rule="9"
        # guarantees the game ends in ≤ 9 rally-wins for one team, which
        # is well within our 10 available rallies.
        winners_all_0: list[tuple[int, float]] = [(0, 0.9)] * n

        setup_to9 = AutoEditSetup(
            game_type="doubles",
            victory_rule="9",
            team1_players=["Alice", "Bob"],
            team2_players=["Carol", "Dave"],
        )

        fake_info = VideoInfo(
            path=str(video_path),
            width=1920,
            height=1080,
            fps=30.0,
            duration=40.0,
            codec_name="h264",
            codec_long_name="H.264",
        )

        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners_all_0),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=setup_to9,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        # predicted_rally_count must equal n (audio model saw 10 rallies).
        assert result.predicted_rally_count == n

        # The training JSON must have fewer scored rallies than predicted.
        data = json.loads(result.training_json_path.read_text(encoding="utf-8"))
        assert len(data["rallies"]) < n


# ---------------------------------------------------------------------------
# Test 6 – score simulation correctness: initial doubles score
# ---------------------------------------------------------------------------


class TestScoreSimulationCorrectness:
    """The score_at_start of the first rally equals the doubles opening score."""

    def test_first_rally_score_at_start_is_initial_doubles_score(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # Three rallies: team 0 wins first two, team 1 wins the third.
        intervals: list[dict[str, float]] = [
            {"start_seconds": 1.0, "end_seconds": 5.0, "duration_seconds": 4.0},
            {"start_seconds": 6.0, "end_seconds": 10.0, "duration_seconds": 4.0},
            {"start_seconds": 11.0, "end_seconds": 15.0, "duration_seconds": 4.0},
        ]
        winners: list[tuple[int, float]] = [(0, 0.9), (0, 0.9), (1, 0.9)]

        setup = AutoEditSetup(
            game_type="doubles",
            victory_rule="11",
            team1_players=["Alice", "Bob"],
            team2_players=["Carol", "Dave"],
        )

        fake_info = VideoInfo(
            path=str(video_path),
            width=1920,
            height=1080,
            fps=30.0,
            duration=20.0,
            codec_name="h264",
            codec_long_name="H.264",
        )

        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        data = json.loads(result.training_json_path.read_text(encoding="utf-8"))
        assert len(data["rallies"]) >= 1

        # Doubles starts at 0-0-2: team 0 serves, server number 2.
        first_rally = data["rallies"][0]
        assert first_rally["score_at_start"] == "0-0-2"
