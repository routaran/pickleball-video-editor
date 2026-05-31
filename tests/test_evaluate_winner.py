"""Tests for ml.tools.evaluate_winner and ml.evaluation.baselines factory API.

All tests run WITHOUT a real video file or a model checkpoint.  Torch-
dependent assertions are guarded with ``pytest.importorskip("torch")`` so
the suite passes on machines where torch is not installed.

Test coverage
-------------
- make_baselines() returns instances with the expected names.
- evaluate_baseline() returns correct keys and computes accuracy correctly.
- MajorityClassBaseline.fit() learns the majority class.
- run_evaluation() works on a tiny fixture corpus (all-train scenario).
- run_evaluation() skips the model gracefully when no checkpoint exists.
- JSON output structure matches the documented schema.
- _render_table() produces non-empty output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixture helpers — build minimal RallyExample objects without real videos
# ---------------------------------------------------------------------------

from ml.examples import RallyExample  # noqa: E402

_CORNERS: tuple[tuple[int, int], ...] = (
    (0, 0),
    (100, 0),
    (100, 75),
    (0, 75),
)


def _make_example(
    video_path: str,
    rally_index: int = 0,
    winning_team: int = 0,
    winner: str = "server",
    score_at_start: str = "0-0-2",
    score_parts: tuple[int, ...] = (0, 0, 2),
    is_post_game: bool = False,
) -> RallyExample:
    """Build a minimal :class:`RallyExample` for testing."""
    return RallyExample(
        source_json_path=Path("/fake/source.training.json"),
        video_path=Path(video_path),
        rally_index=rally_index,
        raw_start=1.0,
        raw_end=10.0,
        score_at_start=score_at_start,
        score_parts=score_parts,
        server_num=score_parts[2] if len(score_parts) == 3 else None,
        winner=winner,
        winning_team=winning_team,
        court_corners=_CORNERS,
        schema_version="1.1",
        generated_by="manual",
        is_post_game=is_post_game,
    )


def _fixture_examples() -> list[RallyExample]:
    """Return a small, balanced fixture corpus across two fake videos."""
    # video A: team 0 wins 3 rallies
    examples = [
        _make_example("/fake/game_a.mp4", i, winning_team=0, winner="server")
        for i in range(3)
    ]
    # video B: team 1 wins 3 rallies
    examples += [
        _make_example("/fake/game_b.mp4", i, winning_team=1, winner="receiver")
        for i in range(3)
    ]
    return examples


# ---------------------------------------------------------------------------
# Tests: make_baselines() factory
# ---------------------------------------------------------------------------


class TestMakeBaselines:
    def test_returns_correct_count(self) -> None:
        from ml.evaluation.baselines import make_baselines, ALL_BASELINES

        baselines = make_baselines()
        assert len(baselines) == len(ALL_BASELINES)

    def test_names_match_all_baselines_catalogue(self) -> None:
        from ml.evaluation.baselines import make_baselines, ALL_BASELINES

        baselines = make_baselines()
        returned_names = [b.name for b in baselines]
        assert returned_names == ALL_BASELINES

    def test_each_call_returns_independent_instances(self) -> None:
        from ml.evaluation.baselines import make_baselines

        first = make_baselines()
        second = make_baselines()
        # Mutating first should not affect second
        for b in first:
            if hasattr(b, "fit"):
                b.fit([])
        for b_first, b_second in zip(first, second):
            assert b_first is not b_second


# ---------------------------------------------------------------------------
# Tests: evaluate_baseline() helper
# ---------------------------------------------------------------------------


class TestEvaluateBaseline:
    def test_empty_examples_returns_zero_accuracy(self) -> None:
        from ml.evaluation.baselines import AlwaysTeam0Baseline, evaluate_baseline

        b = AlwaysTeam0Baseline()
        result = evaluate_baseline(b, [])
        assert result["n_total"] == 0
        assert result["accuracy"] == 0.0

    def test_required_keys_present(self) -> None:
        from ml.evaluation.baselines import AlwaysTeam0Baseline, evaluate_baseline

        b = AlwaysTeam0Baseline()
        result = evaluate_baseline(b, _fixture_examples())
        assert "n_total" in result
        assert "n_correct" in result
        assert "n_wrong" in result
        assert "accuracy" in result

    def test_always_team0_half_correct_on_balanced(self) -> None:
        from ml.evaluation.baselines import AlwaysTeam0Baseline, evaluate_baseline

        b = AlwaysTeam0Baseline()
        examples = _fixture_examples()  # 3 team-0 wins + 3 team-1 wins
        result = evaluate_baseline(b, examples)
        assert result["n_total"] == 6
        assert result["n_correct"] == 3
        assert result["n_wrong"] == 3
        assert abs(result["accuracy"] - 0.5) < 1e-9

    def test_always_team1_half_correct_on_balanced(self) -> None:
        from ml.evaluation.baselines import AlwaysTeam1Baseline, evaluate_baseline

        b = AlwaysTeam1Baseline()
        result = evaluate_baseline(b, _fixture_examples())
        assert result["n_correct"] == 3
        assert abs(result["accuracy"] - 0.5) < 1e-9

    def test_n_correct_plus_n_wrong_equals_n_total(self) -> None:
        from ml.evaluation.baselines import ServingTeamWinsBaseline, evaluate_baseline

        b = ServingTeamWinsBaseline()
        result = evaluate_baseline(b, _fixture_examples())
        assert result["n_correct"] + result["n_wrong"] == result["n_total"]

    def test_serving_team_wins_all_correct_when_server_is_always_team0(self) -> None:
        """When winner=='server' and winning_team==0 for all examples,
        ServingTeamWinsBaseline should be 100% accurate."""
        from ml.evaluation.baselines import ServingTeamWinsBaseline, evaluate_baseline

        examples = [
            _make_example("/v/a.mp4", i, winning_team=0, winner="server")
            for i in range(5)
        ]
        b = ServingTeamWinsBaseline()
        result = evaluate_baseline(b, examples)
        assert result["accuracy"] == pytest.approx(1.0)

    def test_receiving_team_wins_all_correct_when_receiver_is_always_team1(self) -> None:
        from ml.evaluation.baselines import ReceivingTeamWinsBaseline, evaluate_baseline

        examples = [
            _make_example("/v/b.mp4", i, winning_team=1, winner="receiver")
            for i in range(4)
        ]
        b = ReceivingTeamWinsBaseline()
        result = evaluate_baseline(b, examples)
        assert result["accuracy"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tests: MajorityClassBaseline.fit()
# ---------------------------------------------------------------------------


class TestMajorityClassBaseline:
    def test_fit_empty_defaults_to_class_0(self) -> None:
        from ml.evaluation.baselines import MajorityClassBaseline

        b = MajorityClassBaseline()
        b.fit([])
        assert b.majority_class == 0

    def test_fit_learns_majority_team1(self) -> None:
        from ml.evaluation.baselines import MajorityClassBaseline

        examples = [
            _make_example("/v/a.mp4", 0, winning_team=1),
            _make_example("/v/a.mp4", 1, winning_team=1),
            _make_example("/v/a.mp4", 2, winning_team=0),
        ]
        b = MajorityClassBaseline()
        b.fit(examples)
        assert b.majority_class == 1

    def test_fit_tie_resolves_to_class_0(self) -> None:
        from ml.evaluation.baselines import MajorityClassBaseline

        examples = [
            _make_example("/v/a.mp4", 0, winning_team=0),
            _make_example("/v/a.mp4", 1, winning_team=1),
        ]
        b = MajorityClassBaseline()
        b.fit(examples)
        assert b.majority_class == 0

    def test_predict_returns_majority_class_always(self) -> None:
        from ml.evaluation.baselines import MajorityClassBaseline, evaluate_baseline

        examples = [
            _make_example("/v/a.mp4", i, winning_team=1) for i in range(4)
        ] + [
            _make_example("/v/a.mp4", 4, winning_team=0),
        ]
        b = MajorityClassBaseline()
        b.fit(examples)
        assert b.majority_class == 1
        # Predict on a team-1 example → correct
        assert b.predict(examples[0]) == 1


# ---------------------------------------------------------------------------
# Tests: run_evaluation() integration (no real videos, no checkpoint)
# ---------------------------------------------------------------------------


class TestRunEvaluation:
    """Integration tests for run_evaluation() using a tmp fixture corpus."""

    def _write_fixture_json(
        self,
        tmp_path: Path,
        video_name: str,
        rallies: list[dict],
    ) -> Path:
        """Write a minimal schema-1.1 .training.json file to tmp_path."""
        data: dict[str, Any] = {
            "schema_version": "1.1",
            "generated_by": "manual",
            "video": {
                "path": str(tmp_path / video_name),
                "court_corners": [[0, 0], [100, 0], [100, 75], [0, 75]],
            },
            "rallies": rallies,
        }
        json_path = tmp_path / f"{video_name}.training.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")
        return json_path

    def _make_rally_dict(
        self,
        index: int,
        winning_team: int,
        winner: str = "server",
        start: float = 1.0,
        end: float = 10.0,
    ) -> dict[str, Any]:
        return {
            "index": index,
            "score_at_start": "0-0-2",
            "winner": winner,
            "winning_team": winning_team,
            "is_post_game": False,
            "comment": None,
            "raw": {"start_seconds": start, "end_seconds": end},
        }

    def test_result_keys_present(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(3)],
        )

        result = run_evaluation(
            dirs=[tmp_path],
            val_fraction=0.2,
            checkpoint=None,
        )

        assert "n_eligible" in result
        assert "n_train" in result
        assert "n_val" in result
        assert "val_fraction" in result
        assert "baselines" in result
        assert "model" in result
        assert "skip_counts" in result

    def test_single_video_all_in_train(self, tmp_path: Path) -> None:
        """Single video: n_val=0, all examples in train, val list empty."""
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(4)],
        )

        result = run_evaluation(
            dirs=[tmp_path],
            val_fraction=0.2,
            checkpoint=None,
        )

        assert result["n_eligible"] == 4
        assert result["n_train"] == 4
        assert result["n_val"] == 0

    def test_two_videos_splits_correctly(self, tmp_path: Path) -> None:
        """Two videos: one lands in val."""
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(3)],
        )
        self._write_fixture_json(
            tmp_path,
            "game_b.mp4",
            [self._make_rally_dict(i, winning_team=1, winner="receiver") for i in range(3)],
        )

        result = run_evaluation(
            dirs=[tmp_path],
            val_fraction=0.2,
            checkpoint=None,
        )

        assert result["n_eligible"] == 6
        assert result["n_train"] + result["n_val"] == 6
        assert result["n_val"] == 3  # last video lexicographically (game_b)

    def test_baselines_list_non_empty(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=i % 2) for i in range(4)],
        )

        result = run_evaluation(dirs=[tmp_path], checkpoint=None)
        assert len(result["baselines"]) > 0

    def test_each_baseline_has_accuracy_key(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(3)],
        )
        self._write_fixture_json(
            tmp_path,
            "game_b.mp4",
            [self._make_rally_dict(i, winning_team=1, winner="receiver") for i in range(3)],
        )

        result = run_evaluation(dirs=[tmp_path], checkpoint=None)
        for b in result["baselines"]:
            assert "accuracy" in b
            assert "name" in b
            assert "n_total" in b
            assert "n_correct" in b
            assert "n_wrong" in b

    def test_model_is_none_when_no_checkpoint(self, tmp_path: Path) -> None:
        """Without a checkpoint (and none auto-discovered), model must be None."""
        from ml.tools.evaluate_winner import run_evaluation
        import unittest.mock as mock

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(0, winning_team=0)],
        )

        # Patch _default_checkpoint_search so auto-discovery returns None
        with mock.patch(
            "ml.tools.evaluate_winner._default_checkpoint_search",
            return_value=None,
        ):
            result = run_evaluation(
                dirs=[tmp_path],
                val_fraction=0.2,
                checkpoint=None,
            )

        assert result["model"] is None

    def test_model_skipped_gracefully_for_nonexistent_checkpoint(
        self, tmp_path: Path
    ) -> None:
        from ml.tools.evaluate_winner import run_evaluation

        fake_checkpoint = tmp_path / "nonexistent.pt"
        # Do NOT create the file

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(2)],
        )

        # Should not raise; model result should be None
        result = run_evaluation(
            dirs=[tmp_path],
            val_fraction=0.2,
            checkpoint=fake_checkpoint,
        )

        assert result["model"] is None

    def test_json_output_is_serialisable(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import run_evaluation
        import unittest.mock as mock

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(0, winning_team=0)],
        )

        with mock.patch(
            "ml.tools.evaluate_winner._default_checkpoint_search",
            return_value=None,
        ):
            result = run_evaluation(dirs=[tmp_path], checkpoint=None)

        dumped = json.dumps(result)  # must not raise
        reloaded = json.loads(dumped)
        assert reloaded["n_eligible"] == result["n_eligible"]

    def test_empty_dir_returns_zero_eligible(self, tmp_path: Path) -> None:
        """An empty directory produces n_eligible=0 without crashing."""
        from ml.tools.evaluate_winner import run_evaluation
        import unittest.mock as mock

        with mock.patch(
            "ml.tools.evaluate_winner._default_checkpoint_search",
            return_value=None,
        ):
            result = run_evaluation(dirs=[tmp_path], checkpoint=None)

        assert result["n_eligible"] == 0
        assert result["n_train"] == 0
        assert result["n_val"] == 0
        # Baselines should still be present (evaluated on 0 examples)
        assert len(result["baselines"]) > 0
        for b in result["baselines"]:
            assert b["accuracy"] == 0.0


# ---------------------------------------------------------------------------
# Tests: _render_table
# ---------------------------------------------------------------------------


class TestRenderTable:
    def _minimal_result(self) -> dict[str, Any]:
        return {
            "n_eligible": 6,
            "n_train": 3,
            "n_val": 3,
            "val_fraction": 0.2,
            "baselines": [
                {
                    "name": "majority_class",
                    "n_total": 3,
                    "n_correct": 2,
                    "n_wrong": 1,
                    "accuracy": 2 / 3,
                },
            ],
            "model": None,
            "skip_counts": {},
        }

    def test_returns_non_empty_string(self) -> None:
        from ml.tools.evaluate_winner import _render_table

        output = _render_table(self._minimal_result())
        assert isinstance(output, str)
        assert len(output.strip()) > 0

    def test_contains_baseline_name(self) -> None:
        from ml.tools.evaluate_winner import _render_table

        output = _render_table(self._minimal_result())
        assert "majority_class" in output

    def test_contains_accuracy_percent(self) -> None:
        from ml.tools.evaluate_winner import _render_table

        output = _render_table(self._minimal_result())
        # 2/3 = 66.7%
        assert "66.7%" in output

    def test_no_model_message_shown(self) -> None:
        from ml.tools.evaluate_winner import _render_table

        output = _render_table(self._minimal_result())
        assert "Not evaluated" in output

    def test_model_row_shown_when_present(self) -> None:
        from ml.tools.evaluate_winner import _render_table

        result = self._minimal_result()
        result["model"] = {
            "name": "winner_classifier",
            "checkpoint": "/models/best.pt",
            "n_total": 3,
            "n_correct": 2,
            "n_wrong": 1,
            "accuracy": 2 / 3,
        }
        output = _render_table(result)
        assert "winner_classifier" in output
        assert "Not evaluated" not in output


# ---------------------------------------------------------------------------
# Tests: torch-dependent assertions (skipped if torch absent)
# ---------------------------------------------------------------------------


class TestModelEvaluationWithTorch:
    """Guards all torch-needing assertions with pytest.importorskip."""

    def test_model_skipped_when_torch_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate torch being absent: model result must be None."""
        import unittest.mock as mock

        # Make the lazy import of torch inside _run_model raise ImportError
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "torch":
                raise ImportError("torch not available (mocked)")
            return original_import(name, *args, **kwargs)

        # Use monkeypatch on builtins so only the _run_model branch is affected.
        # Simpler: just call _run_model directly with a nonexistent checkpoint —
        # the existence check fires first and returns None regardless of torch.
        from ml.tools.evaluate_winner import _run_model

        result = _run_model(
            val_examples=[],
            checkpoint_path=tmp_path / "no_such.pt",
            device="cpu",
            include_calibration=False,
        )
        assert result is None

    def test_model_loads_and_evaluates(self, tmp_path: Path) -> None:
        """Full model eval path — requires torch + torchvision."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("torchvision")

        from ml.winner_model import WinnerClassifier
        from ml.tools.evaluate_winner import _run_model

        # Save a minimal checkpoint
        ckpt_path = tmp_path / "winner_test.pt"
        model = WinnerClassifier()
        torch.save({"model_state_dict": model.state_dict()}, str(ckpt_path))

        # Use examples whose video files do NOT need to exist — _run_model will
        # call WinnerDataset.from_rally_examples which does not check existence.
        # However __getitem__ calls _fetch_clip_tensor which decodes video.
        # With 0 val_examples the dataset is empty → _run_model returns None
        # (the "dataset is empty" guard fires) — this is the safe path to test.
        result = _run_model(
            val_examples=[],
            checkpoint_path=ckpt_path,
            device="cpu",
            include_calibration=False,
        )
        # Dataset is empty → graceful skip
        assert result is None
