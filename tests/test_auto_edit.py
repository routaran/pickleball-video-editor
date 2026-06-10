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
    ml.auto_edit.torch.load      — used for checkpoint pre-validation
"""

import json
import pickle
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

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
        "torchaudio", "torchvision",
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
from ml.auto_edit import (  # noqa: E402
    auto_edit,
    AutoEditResult,
    AutoEditCancelled,
    AutoEditSetup,
    SHORT_RALLY_REVIEW_SECONDS,
)

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

# A valid checkpoint dict that satisfies the pre-validation check.
_VALID_CHECKPOINT_DICT: dict = {
    "model_state_dict": {},
    "config": {},
}


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
    """Empty checkpoint file so FileNotFoundError is not raised.

    torch.load is patched in all tests, so the file content is irrelevant.
    """
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
# Helper: build five stacked patches for the standard 5-rally scenario.
#
# KdenliveGenerator has its own probe_video import (lazily called via the
# video_info property), so it must be patched independently of the
# ml.auto_edit.probe_video reference.
#
# torch.load is patched to return a valid checkpoint dict so the
# pre-validation step passes without reading a real .pt file.
# The audio checkpoint existence check is bypassed by patching PathConfig so
# its best_model_path points to a file that exists (the checkpoint_path).
# ---------------------------------------------------------------------------


def _patches_5_rally(video_path: Path, checkpoint_path: Path):
    """Return a tuple of five context managers ready for ``with`` unpacking."""
    fake_info = _make_video_info(video_path)
    return (
        patch("ml.auto_edit.predict_video", return_value=_FAKE_INTERVALS_5),
        patch("ml.auto_edit.predict_winners", return_value=_FAKE_WINNERS_5),
        patch("ml.auto_edit.probe_video", return_value=fake_info),
        patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
        patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
        patch(
            "ml.auto_edit.PathConfig.best_model_path",
            new_callable=lambda: property(lambda self: checkpoint_path),
        ),
    )


def _run_5_rally(
    tmp_path: Path,
    video_path: Path,
    checkpoint_path: Path,
    corners: list[tuple[int, int]],
    doubles_setup: AutoEditSetup,
) -> AutoEditResult:
    """Run auto_edit with the standard 5-rally scenario."""
    p1, p2, p3, p4, p5, p6 = _patches_5_rally(video_path, checkpoint_path)
    with p1, p2, p3, p4, p5, p6:
        return auto_edit(
            video_path=video_path,
            setup=doubles_setup,
            corners=corners,
            output_dir=tmp_path,
            checkpoint_path=checkpoint_path,
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
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.predicted_rally_count == 5

    def test_n_detected_equals_predicted_rally_count(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.n_detected == result.predicted_rally_count


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
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert 2 in result.low_confidence_rally_indices

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
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
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

    def test_kdenlive_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.kdenlive_path.exists()

    def test_ass_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.ass_path.exists()

    def test_training_json_path_exists(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
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
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
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
        # The JSON includes all rallies (scored + post-game).
        assert len(data["rallies"]) <= result.predicted_rally_count


# ---------------------------------------------------------------------------
# Test 5 – game-over: post-game rallies (F7)
# ---------------------------------------------------------------------------


class TestGameOverPostGame:
    """After game over all remaining rallies are present with is_post_game=True.

    This replaces the old TestGameOverTruncation behaviour where remaining
    rallies were silently discarded.  Now they are kept but tagged as
    post-game with a frozen score.
    """

    def _run_game_over(
        self,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        tmp_path: Path,
        n_intervals: int = 10,
        victory_rule: str = "9",
    ) -> tuple[AutoEditResult, dict]:
        """Run a scenario where the game ends well before all intervals are used."""
        intervals: list[dict[str, float]] = [
            {
                "start_seconds": float(i * 4 + 1),
                "end_seconds": float(i * 4 + 4),
                "duration_seconds": 3.0,
            }
            for i in range(n_intervals)
        ]
        # Team 0 wins every rally → game ends as soon as victory_rule score is reached.
        winners_all_0: list[tuple[int, float]] = [(0, 0.9)] * n_intervals

        setup = AutoEditSetup(
            game_type="doubles",
            victory_rule=victory_rule,
            team1_players=["Alice", "Bob"],
            team2_players=["Carol", "Dave"],
        )

        fake_info = VideoInfo(
            path=str(video_path),
            width=1920,
            height=1080,
            fps=30.0,
            duration=float(n_intervals * 4 + 5),
            codec_name="h264",
            codec_long_name="H.264",
        )

        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners_all_0),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        data = json.loads(result.training_json_path.read_text(encoding="utf-8"))
        return result, data

    def test_n_detected_equals_all_intervals(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        result, _ = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        assert result.n_detected == 10

    def test_n_scored_plus_n_post_game_equals_n_detected(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        result, _ = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        assert result.n_scored + result.n_post_game == result.n_detected

    def test_n_post_game_is_positive(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """With 10 intervals and victory at 9, there must be at least 1 post-game rally."""
        result, _ = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        assert result.n_post_game > 0

    def test_n_scored_matches_expected_win_count(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """With victory_rule=9 and team 0 winning every rally, n_scored should be ≤ 9."""
        result, _ = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        # The game ends at ≤ 9 wins for team 0 (fewer possible due to serve-rotation).
        assert result.n_scored <= 9

    def test_all_rallies_present_in_json(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """Training JSON should include EVERY rally (scored + post-game)."""
        result, data = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        assert len(data["rallies"]) == result.n_detected

    def test_post_game_rallies_have_is_post_game_flag(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        result, data = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        # The last n_post_game entries must be flagged is_post_game=True.
        post_game_entries = data["rallies"][result.n_scored :]
        assert len(post_game_entries) == result.n_post_game
        for entry in post_game_entries:
            assert entry["is_post_game"] is True

    def test_scored_rallies_not_flagged(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        result, data = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        for entry in data["rallies"][: result.n_scored]:
            assert entry["is_post_game"] is False

    def test_post_game_rallies_have_frozen_score(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """All post-game rallies must share the same frozen score_at_start."""
        result, data = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        post_game_entries = data["rallies"][result.n_scored :]
        assert len(post_game_entries) > 0
        frozen_score = post_game_entries[0]["score_at_start"]
        for entry in post_game_entries:
            assert entry["score_at_start"] == frozen_score

    def test_simulated_final_score_unchanged_by_post_game(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """simulated_final_score must equal the score at the LAST SCORED rally."""
        result, data = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        assert result.simulated_final_score is not None
        # The final score must be the game-winning score, not some post-game fiction.
        t1, t2 = result.simulated_final_score
        # One team must have won with victory_rule=9.
        assert t1 == 9 or t2 == 9

    def test_post_game_rallies_not_in_low_confidence(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """Post-game rallies must NOT be added to low_confidence_rally_indices."""
        result, _ = self._run_game_over(video_path, checkpoint_path, corners, tmp_path)
        # All post-game indices are >= n_scored; none should appear in low_confidence.
        for idx in result.low_confidence_rally_indices:
            assert idx < result.n_scored, (
                f"Post-game rally index {idx} leaked into low_confidence_rally_indices"
            )


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
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
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


# ---------------------------------------------------------------------------
# Test 7 – predicted_team and prediction_confidence stamped on every rally (F6)
# ---------------------------------------------------------------------------


class TestPredictionStamping:
    """predicted_team and prediction_confidence must be set on every rally."""

    def test_predicted_team_and_confidence_on_scored_rallies(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        rallies = result.session_state.rallies
        assert len(rallies) == 5
        for i, rally in enumerate(rallies):
            expected_team, expected_conf = _FAKE_WINNERS_5[i]
            assert rally.predicted_team == expected_team, (
                f"Rally {i}: expected predicted_team={expected_team}, got {rally.predicted_team}"
            )
            assert rally.prediction_confidence == expected_conf, (
                f"Rally {i}: expected prediction_confidence={expected_conf}, "
                f"got {rally.prediction_confidence}"
            )

    def test_predicted_team_stamped_on_post_game_rallies(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        """Post-game rallies must also have predicted_team set."""
        n = 10
        intervals: list[dict[str, float]] = [
            {"start_seconds": float(i * 4 + 1), "end_seconds": float(i * 4 + 4),
             "duration_seconds": 3.0}
            for i in range(n)
        ]
        winners: list[tuple[int, float]] = [(0, 0.9)] * n
        fake_info = VideoInfo(
            path=str(video_path), width=1920, height=1080, fps=30.0, duration=45.0,
            codec_name="h264", codec_long_name="H.264",
        )
        setup = AutoEditSetup(
            game_type="doubles", victory_rule="9",
            team1_players=["A", "B"], team2_players=["C", "D"],
        )
        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        ):
            result = auto_edit(
                video_path=video_path, setup=setup, corners=corners,
                output_dir=tmp_path, checkpoint_path=checkpoint_path,
            )

        rallies = result.session_state.rallies
        # Every rally (scored and post-game) must have predicted_team set.
        for rally in rallies:
            assert rally.predicted_team == 0
            assert rally.prediction_confidence == 0.9


# ---------------------------------------------------------------------------
# Test 8 – short rally flagging (F8)
# ---------------------------------------------------------------------------


class TestShortRallyFlagging:
    """Scored rallies under SHORT_RALLY_REVIEW_SECONDS are added to low_confidence."""

    def _run_with_intervals(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        intervals: list[dict[str, float]],
        winners: list[tuple[int, float]],
    ) -> AutoEditResult:
        fake_info = VideoInfo(
            path=str(video_path), width=1920, height=1080, fps=30.0, duration=60.0,
            codec_name="h264", codec_long_name="H.264",
        )
        setup = AutoEditSetup(
            game_type="doubles", victory_rule="11",
            team1_players=["A", "B"], team2_players=["C", "D"],
        )
        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        ):
            return auto_edit(
                video_path=video_path, setup=setup, corners=corners,
                output_dir=tmp_path, checkpoint_path=checkpoint_path,
            )

    def test_short_rally_flagged(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # Rally 0: 1.5s (< 3.0 → should be flagged)
        # Rally 1: 4.0s (>= 3.0 → must NOT be flagged by duration alone)
        intervals = [
            {"start_seconds": 1.0, "end_seconds": 2.5, "duration_seconds": 1.5},
            {"start_seconds": 5.0, "end_seconds": 9.0, "duration_seconds": 4.0},
        ]
        winners: list[tuple[int, float]] = [(0, 0.9), (1, 0.9)]
        result = self._run_with_intervals(
            tmp_path, video_path, checkpoint_path, corners, intervals, winners
        )
        assert 0 in result.low_confidence_rally_indices

    def test_long_rally_not_flagged_by_duration(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # Rally 0: 1.5s (flagged), Rally 1: 4.0s (must NOT be in list)
        intervals = [
            {"start_seconds": 1.0, "end_seconds": 2.5, "duration_seconds": 1.5},
            {"start_seconds": 5.0, "end_seconds": 9.0, "duration_seconds": 4.0},
        ]
        winners: list[tuple[int, float]] = [(0, 0.9), (1, 0.9)]
        result = self._run_with_intervals(
            tmp_path, video_path, checkpoint_path, corners, intervals, winners
        )
        assert 1 not in result.low_confidence_rally_indices

    def test_exactly_at_threshold_not_flagged(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # A rally of exactly SHORT_RALLY_REVIEW_SECONDS must NOT be flagged.
        intervals = [
            {
                "start_seconds": 1.0,
                "end_seconds": 1.0 + SHORT_RALLY_REVIEW_SECONDS,
                "duration_seconds": SHORT_RALLY_REVIEW_SECONDS,
            },
        ]
        winners: list[tuple[int, float]] = [(0, 0.9)]
        result = self._run_with_intervals(
            tmp_path, video_path, checkpoint_path, corners, intervals, winners
        )
        assert 0 not in result.low_confidence_rally_indices

    def test_no_duplicate_indices(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
    ) -> None:
        # Rally 0: short AND low-confidence → index 0 must appear exactly once.
        intervals = [
            {"start_seconds": 1.0, "end_seconds": 2.5, "duration_seconds": 1.5},
        ]
        winners: list[tuple[int, float]] = [(0, 0.6)]  # below confidence threshold too
        result = self._run_with_intervals(
            tmp_path, video_path, checkpoint_path, corners, intervals, winners
        )
        assert result.low_confidence_rally_indices.count(0) == 1


# ---------------------------------------------------------------------------
# Test 9 – strict zip raises on mismatched lengths
# ---------------------------------------------------------------------------


class TestStrictZip:
    """zip(strict=True) must raise when intervals and winner_results differ in length."""

    def test_mismatched_lengths_raise(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        # 3 intervals but only 2 winner results → strict zip must raise.
        intervals = _FAKE_INTERVALS_5[:3]
        winners_short: list[tuple[int, float]] = [(0, 0.9), (1, 0.9)]
        fake_info = _make_video_info(video_path)

        with (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners_short),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
            pytest.raises((ValueError, StopIteration)),
        ):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )


# ---------------------------------------------------------------------------
# Test 10 – checkpoint pre-validation raises before predict_video runs
# ---------------------------------------------------------------------------


class TestCheckpointPreValidation:
    """The winner checkpoint is validated before the expensive Stage 1 runs."""

    def _predict_video_call_recorder(self) -> tuple[list, MagicMock]:
        """Return (call_log, mock) so we can assert predict_video was never called."""
        calls: list = []

        def _recorder(*args, **kwargs):
            calls.append(args)
            return []

        return calls, _recorder

    def test_missing_winner_checkpoint_raises_before_predict_video(
        self,
        tmp_path: Path,
        video_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        nonexistent = tmp_path / "does_not_exist.pt"
        calls, recorder = self._predict_video_call_recorder()

        with (
            patch("ml.auto_edit.predict_video", side_effect=recorder),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: video_path),  # reuse existing file
            ),
            pytest.raises(FileNotFoundError, match="winner checkpoint"),
        ):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=nonexistent,
            )

        assert calls == [], "predict_video must NOT have been called before checkpoint validation"

    def test_garbage_winner_checkpoint_raises_before_predict_video(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """A loadable-but-wrong checkpoint raises ValueError before Stage 1."""
        calls, recorder = self._predict_video_call_recorder()

        # Patch torch.load to return a dict missing both required keys.
        garbage_dict: dict = {"something_else": 1}

        with (
            patch("ml.auto_edit.predict_video", side_effect=recorder),
            patch("ml.auto_edit.torch.load", return_value=garbage_dict),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
            pytest.raises(ValueError, match="unusable winner checkpoint"),
        ):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert calls == [], "predict_video must NOT have been called when checkpoint is unusable"

    def test_unloadable_winner_checkpoint_raises_before_predict_video(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """torch.load raising an exception causes pre-validation to fail."""
        calls, recorder = self._predict_video_call_recorder()

        def _bad_load(*args, **kwargs):
            raise RuntimeError("corrupt file")

        with (
            patch("ml.auto_edit.predict_video", side_effect=recorder),
            patch("ml.auto_edit.torch.load", side_effect=_bad_load),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
            pytest.raises(ValueError, match="unusable winner checkpoint"),
        ):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert calls == [], "predict_video must NOT have been called when torch.load fails"

    def test_missing_audio_checkpoint_raises_before_predict_video(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """Missing Stage-1 audio checkpoint raises before predict_video."""
        nonexistent_audio = tmp_path / "no_audio_model.pt"
        calls, recorder = self._predict_video_call_recorder()

        with (
            patch("ml.auto_edit.predict_video", side_effect=recorder),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: nonexistent_audio),
            ),
            pytest.raises(FileNotFoundError, match="audio checkpoint"),
        ):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
            )

        assert calls == [], "predict_video must NOT have been called when audio checkpoint is missing"


# ---------------------------------------------------------------------------
# Test 11 – cooperative cancellation hook (F optional)
# ---------------------------------------------------------------------------


class TestCancellationHook:
    """cancel_check() returning True raises AutoEditCancelled with no files written."""

    def _base_patches(self, video_path: Path, checkpoint_path: Path, intervals, winners):
        fake_info = _make_video_info(video_path)
        return (
            patch("ml.auto_edit.predict_video", return_value=intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        )

    def test_cancel_before_stage4_writes_no_files(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """cancel_check returning True just before Stage 4 must write no output files."""
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        call_count = [0]

        def _cancel() -> bool:
            call_count[0] += 1
            # Return False for Stage 1 and Stage 2 checks, True at Stage 3→4 boundary.
            return call_count[0] >= 3

        p1, p2, p3, p4, p5, p6 = self._base_patches(
            video_path, checkpoint_path, _FAKE_INTERVALS_5, _FAKE_WINNERS_5
        )
        with p1, p2, p3, p4, p5, p6, pytest.raises(AutoEditCancelled):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=output_dir,
                checkpoint_path=checkpoint_path,
                cancel_check=_cancel,
            )

        # No output files should have been written.
        written = list(output_dir.iterdir())
        assert written == [], f"Expected no output files; found: {written}"

    def test_cancel_after_stage1_raises(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """cancel_check returning True after Stage 1 raises AutoEditCancelled."""
        call_count = [0]

        def _cancel() -> bool:
            call_count[0] += 1
            return call_count[0] >= 1  # Cancel immediately on first check (after Stage 1)

        p1, p2, p3, p4, p5, p6 = self._base_patches(
            video_path, checkpoint_path, _FAKE_INTERVALS_5, _FAKE_WINNERS_5
        )
        with p1, p2, p3, p4, p5, p6, pytest.raises(AutoEditCancelled):
            auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
                cancel_check=_cancel,
            )

    def test_none_cancel_check_runs_normally(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """cancel_check=None (the default) runs the pipeline to completion."""
        result = _run_5_rally(tmp_path, video_path, checkpoint_path, corners, doubles_setup)
        assert result.predicted_rally_count == 5
        assert result.kdenlive_path.exists()


# ---------------------------------------------------------------------------
# Test 12 – threshold unification (confidence_threshold=None)
# ---------------------------------------------------------------------------


class TestThresholdUnification:
    """confidence_threshold=None uses WinnerModelConfig.confidence_threshold."""

    def test_none_threshold_uses_winner_model_config_default(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """When confidence_threshold is None, WinnerModelConfig.confidence_threshold (0.75) is used.

        Verify by injecting a confidence of exactly 0.74 (below 0.75 but above 0.7,
        the old default) and asserting that rally is flagged.
        """
        from ml.config import WinnerModelConfig

        expected_threshold = WinnerModelConfig().confidence_threshold  # 0.75
        assert expected_threshold == 0.75

        # All 5 rallies above threshold except rally 2 which is at 0.74.
        winners_near_threshold: list[tuple[int, float]] = [
            (0, 0.9),
            (1, 0.9),
            (0, 0.74),   # just below 0.75
            (1, 0.9),
            (0, 0.9),
        ]
        # Use long enough intervals so short-rally detection does not fire.
        long_intervals: list[dict[str, float]] = [
            {"start_seconds": float(i * 6 + 1), "end_seconds": float(i * 6 + 5),
             "duration_seconds": 4.0}
            for i in range(5)
        ]
        fake_info = _make_video_info(video_path)

        with (
            patch("ml.auto_edit.predict_video", return_value=long_intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners_near_threshold),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
                confidence_threshold=None,  # explicit None → use config default
            )

        assert 2 in result.low_confidence_rally_indices, (
            "Rally 2 (confidence=0.74) must be flagged when using the default threshold of 0.75"
        )

    def test_explicit_threshold_overrides_config(
        self,
        tmp_path: Path,
        video_path: Path,
        checkpoint_path: Path,
        corners: list[tuple[int, int]],
        doubles_setup: AutoEditSetup,
    ) -> None:
        """An explicit confidence_threshold value takes precedence over the config default."""
        # Rally 2 has confidence 0.74: below 0.75 but above 0.70.
        # With explicit threshold=0.70, it should NOT be flagged for confidence.
        winners: list[tuple[int, float]] = [
            (0, 0.9),
            (1, 0.9),
            (0, 0.74),   # above explicit 0.70 threshold
            (1, 0.9),
            (0, 0.9),
        ]
        long_intervals: list[dict[str, float]] = [
            {"start_seconds": float(i * 6 + 1), "end_seconds": float(i * 6 + 5),
             "duration_seconds": 4.0}
            for i in range(5)
        ]
        fake_info = _make_video_info(video_path)

        with (
            patch("ml.auto_edit.predict_video", return_value=long_intervals),
            patch("ml.auto_edit.predict_winners", return_value=winners),
            patch("ml.auto_edit.probe_video", return_value=fake_info),
            patch("src.output.kdenlive_generator.probe_video", return_value=fake_info),
            patch("ml.auto_edit.torch.load", return_value=_VALID_CHECKPOINT_DICT),
            patch(
                "ml.auto_edit.PathConfig.best_model_path",
                new_callable=lambda: property(lambda self: checkpoint_path),
            ),
        ):
            result = auto_edit(
                video_path=video_path,
                setup=doubles_setup,
                corners=corners,
                output_dir=tmp_path,
                checkpoint_path=checkpoint_path,
                confidence_threshold=0.70,  # explicit value lower than config default
            )

        assert 2 not in result.low_confidence_rally_indices, (
            "Rally 2 (confidence=0.74) must NOT be flagged with explicit threshold=0.70"
        )
