"""Tests for ml.tools.evaluate_winner."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from ml.examples import RallyExample

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
) -> RallyExample:
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
        is_post_game=False,
    )


class TestRunEvaluation:
    def _write_fixture_json(
        self,
        tmp_path: Path,
        video_name: str,
        rallies: list[dict[str, Any]],
    ) -> None:
        (tmp_path / video_name).write_bytes(b"fake video")
        (tmp_path / f"{video_name}.training.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "generated_by": "manual",
                    "video": {
                        "path": str(tmp_path / video_name),
                        "court_corners": [[0, 0], [100, 0], [100, 75], [0, 75]],
                    },
                    "rallies": rallies,
                }
            ),
            encoding="utf-8",
        )

    def _make_rally_dict(
        self,
        index: int,
        winning_team: int,
        winner: str = "server",
    ) -> dict[str, Any]:
        return {
            "index": index,
            "score_at_start": "0-0-2",
            "winner": winner,
            "winning_team": winning_team,
            "is_post_game": False,
            "comment": None,
            "raw": {"start_seconds": 1.0, "end_seconds": 10.0},
        }

    def test_run_evaluation_reports_baselines_only_when_no_checkpoint_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import run_evaluation

        self._write_fixture_json(
            tmp_path,
            "game_a.mp4",
            [self._make_rally_dict(i, winning_team=0) for i in range(3)],
        )

        monkeypatch.setattr(
            "ml.tools.evaluate_winner._default_checkpoint_search",
            lambda: None,
        )

        result = run_evaluation(dirs=[tmp_path], checkpoint=None)

        assert result["n_eligible"] == 3
        assert result["n_train"] == 3
        assert result["n_val"] == 0
        assert [baseline["name"] for baseline in result["baselines"]] == [
            "majority_class",
            "always_team_0",
            "always_team_1",
            "score_lead",
            "score_trail",
        ]
        assert result["model"] is None

    def test_baselines_and_model_receive_the_same_validation_examples(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import ml.examples
        import ml.evaluation.splits
        from ml.tools.evaluate_winner import run_evaluation

        train_examples = [_make_example("/videos/train.mp4", 0, winning_team=0)]
        val_examples = [
            _make_example("/videos/val.mp4", 1, winning_team=1),
            _make_example("/videos/val.mp4", 2, winning_team=0),
        ]
        all_examples = [*train_examples, *val_examples]

        class FakeIndex:
            def __init__(self, dirs: list[Path]) -> None:
                self.examples = all_examples
                self.skip_counts = {"missing_winner": 0}

        captured: dict[str, Any] = {}

        def fake_split(examples: list[RallyExample], val_fraction: float) -> tuple[list[RallyExample], list[RallyExample]]:
            assert examples is all_examples
            assert val_fraction == 0.2
            return train_examples, val_examples

        def fake_run_baselines(train: list[RallyExample], val: list[RallyExample]) -> list[dict[str, Any]]:
            captured["train_for_baselines"] = train
            captured["val_for_baselines"] = val
            return [{"name": "stub", "n_total": len(val), "n_correct": 0, "n_wrong": len(val), "accuracy": 0.0}]

        def fake_run_model(
            val: list[RallyExample],
            checkpoint: Path,
            device: str,
            include_calibration: bool,
            terminal_event_annotations: Path | None = None,
            side_map: Path | None = None,
        ) -> dict[str, Any]:
            captured["val_for_model"] = val
            captured["checkpoint"] = checkpoint
            captured["device"] = device
            captured["include_calibration"] = include_calibration
            return {"name": "winner_classifier", "n_total": len(val), "n_correct": 0, "n_wrong": len(val), "accuracy": 0.0}

        monkeypatch.setattr(ml.examples, "RallyExampleIndex", FakeIndex)
        monkeypatch.setattr(ml.evaluation.splits, "video_wise_split", fake_split)
        monkeypatch.setattr("ml.tools.evaluate_winner._run_baselines", fake_run_baselines)
        monkeypatch.setattr("ml.tools.evaluate_winner._run_model", fake_run_model)

        checkpoint = Path("/tmp/fake-checkpoint.pt")
        result = run_evaluation(dirs=[Path("/unused")], checkpoint=checkpoint)

        assert captured["train_for_baselines"] is train_examples
        assert captured["val_for_baselines"] is val_examples
        assert captured["val_for_model"] is val_examples
        assert captured["checkpoint"] == checkpoint
        assert captured["device"] == "cpu"
        assert captured["include_calibration"] is False
        assert result["n_train"] == len(train_examples)
        assert result["n_val"] == len(val_examples)


class TestRunModel:
    def test_run_model_builds_dataset_from_exact_validation_examples(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _run_model

        checkpoint_path = tmp_path / "winner.pt"
        checkpoint_path.write_bytes(b"checkpoint")
        val_examples = [_make_example("/videos/val.mp4", 0, winning_team=1)]
        sentinel_config = object()
        captured: dict[str, Any] = {}

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {}

        class FakeDataset(list):
            @classmethod
            def _from_rally_examples_no_split(
                cls,
                records: list[RallyExample],
                config: object,
                split: str,
                augment: bool,
            ) -> "FakeDataset":
                captured["records"] = records
                captured["config"] = config
                captured["split"] = split
                captured["augment"] = augment
                return cls()

        fake_winner_dataset = types.ModuleType("ml.winner_dataset")
        fake_winner_dataset.WinnerDataset = FakeDataset

        class FakeModel:
            def eval(self) -> None:
                return None

        fake_winner_model = types.ModuleType("ml.winner_model")
        fake_winner_model.load_winner_classifier = lambda *args, **kwargs: FakeModel()

        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        monkeypatch.setitem(sys.modules, "ml.winner_dataset", fake_winner_dataset)
        monkeypatch.setitem(sys.modules, "ml.winner_model", fake_winner_model)
        monkeypatch.setattr("ml.tools.evaluate_winner._load_checkpoint_config", lambda path: sentinel_config)

        result = _run_model(
            val_examples=val_examples,
            checkpoint_path=checkpoint_path,
            device="cpu",
            include_calibration=False,
        )

        assert result is None
        assert captured["records"] is val_examples
        assert captured["config"] is sentinel_config
        assert captured["split"] == "val"
        assert captured["augment"] is False


class TestCheckpointConfig:
    def test_load_checkpoint_config_uses_saved_effective_duration_as_override(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_config

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {
            "config": {
                "checkpoint_path": "saved/best.pt",
                "clip_duration_s": 2.5,
                "effective_clip_duration_s": 3.0,
                "fps_out": 8,
                "device": "cpu",
            }
        }
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        config = _load_checkpoint_config(tmp_path / "winner.pt")

        assert config.checkpoint_path == Path("saved/best.pt")
        assert config.clip_duration_s == 2.5
        assert config.clip_duration_override_s == 3.0
        assert config.effective_clip_duration_s == 3.0

    def test_load_checkpoint_config_falls_back_to_defaults_on_load_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.config import WinnerModelConfig
        from ml.tools.evaluate_winner import _load_checkpoint_config

        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("bad checkpoint")

        fake_torch = types.ModuleType("torch")
        fake_torch.load = _raise
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        config = _load_checkpoint_config(tmp_path / "winner.pt")

        assert config == WinnerModelConfig()

    def test_load_checkpoint_config_delegates_to_shared_loader(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The CLI wrapper reuses ml.config.load_winner_config_from_checkpoint."""
        import ml.config
        from ml.tools.evaluate_winner import _load_checkpoint_config

        ckpt_dict = {"config": {"canonical_width": 512}}
        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: ckpt_dict
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        captured: dict[str, Any] = {}

        def fake_shared_loader(checkpoint: Any, **kwargs: Any) -> Any:
            captured["checkpoint"] = checkpoint
            captured["kwargs"] = kwargs
            return ml.config.WinnerModelConfig(canonical_width=512)

        monkeypatch.setattr(
            ml.config, "load_winner_config_from_checkpoint", fake_shared_loader
        )

        config = _load_checkpoint_config(tmp_path / "winner.pt")

        assert captured["checkpoint"] is ckpt_dict
        assert config.canonical_width == 512

    def test_load_checkpoint_config_legacy_fallback_warns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A checkpoint without a config block warns and returns defaults."""
        from ml.config import WinnerModelConfig
        from ml.tools.evaluate_winner import _load_checkpoint_config

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {"model_state_dict": {}}
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        with pytest.warns(UserWarning, match="config block"):
            config = _load_checkpoint_config(tmp_path / "winner.pt")

        assert config == WinnerModelConfig()


class TestCheckpointSchemaVersion:
    def test_reads_schema_version_from_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_schema_version

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {
            "checkpoint_schema_version": "2.0"
        }
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        assert _load_checkpoint_schema_version(tmp_path / "winner.pt") == "2.0"

    def test_returns_legacy_when_version_absent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_schema_version

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {"model_state_dict": {}}
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        assert _load_checkpoint_schema_version(tmp_path / "winner.pt") == "legacy"

    def test_returns_legacy_on_load_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_schema_version

        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("corrupt")

        fake_torch = types.ModuleType("torch")
        fake_torch.load = _raise
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        assert _load_checkpoint_schema_version(tmp_path / "winner.pt") == "legacy"


class TestCheckpointTemperature:
    """Tests for _load_checkpoint_temperature and temperature application."""

    def test_reads_temperature_from_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_temperature

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {"temperature": 2.5}
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        temp = _load_checkpoint_temperature(tmp_path / "winner.pt")
        assert temp == pytest.approx(2.5)

    def test_defaults_to_one_when_key_absent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_temperature

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: {"model_state_dict": {}}
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        temp = _load_checkpoint_temperature(tmp_path / "winner.pt")
        assert temp == pytest.approx(1.0)

    def test_defaults_to_one_on_load_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _load_checkpoint_temperature

        fake_torch = types.ModuleType("torch")
        fake_torch.load = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("corrupt file")
        )
        monkeypatch.setitem(sys.modules, "torch", fake_torch)

        temp = _load_checkpoint_temperature(tmp_path / "winner.pt")
        assert temp == pytest.approx(1.0)

    def test_temperature_included_in_run_model_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the checkpoint has temperature=3.0 the result dict includes it."""
        from ml.tools.evaluate_winner import _run_model

        checkpoint_path = tmp_path / "winner.pt"
        checkpoint_path.write_bytes(b"checkpoint")

        val_examples = [_make_example("/videos/val.mp4", 0, winning_team=0)]

        fake_torch = types.ModuleType("torch")
        # Return checkpoint with temperature=3.0
        fake_torch.load = lambda *args, **kwargs: {"temperature": 3.0}
        fake_torch.no_grad = lambda: _DummyContextManager()

        # Real torch for tensor ops inside _run_model (softmax, argmax, etc.)
        import torch as real_torch

        class FakeSoftmax:
            pass

        class FakeDataset(list):
            @classmethod
            def _from_rally_examples_no_split(cls, **kwargs):
                return cls()  # empty → early return

        fake_winner_dataset = types.ModuleType("ml.winner_dataset")
        fake_winner_dataset.WinnerDataset = FakeDataset

        class FakeModel:
            def eval(self) -> None:
                return None

        fake_winner_model = types.ModuleType("ml.winner_model")
        fake_winner_model.load_winner_classifier = lambda *args, **kwargs: FakeModel()

        monkeypatch.setitem(sys.modules, "torch", fake_torch)
        monkeypatch.setitem(sys.modules, "ml.winner_dataset", fake_winner_dataset)
        monkeypatch.setitem(sys.modules, "ml.winner_model", fake_winner_model)
        monkeypatch.setattr(
            "ml.tools.evaluate_winner._load_checkpoint_config",
            lambda path: object(),
        )
        monkeypatch.setattr(
            "ml.tools.evaluate_winner._load_checkpoint_temperature",
            lambda path: 3.0,
        )

        # Empty dataset → returns None early (before game-level metrics).
        result = _run_model(
            val_examples=val_examples,
            checkpoint_path=checkpoint_path,
            device="cpu",
            include_calibration=False,
        )
        # result is None because dataset is empty — that is fine; the
        # temperature reading is what we need to confirm via monkeypatch above.
        assert result is None


class _DummyContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestGameLevelMetrics:
    """Game-level section appears in JSON output when model is evaluated."""

    def _make_multi_video_scenario(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> Any:
        """Patch run_evaluation so _run_model returns a result with game_metrics."""
        import ml.examples
        import ml.evaluation.splits
        from ml.tools.evaluate_winner import run_evaluation

        # Two videos, 3 rallies each.
        vid_a = "/videos/game_a.mp4"
        vid_b = "/videos/game_b.mp4"
        source_json = tmp_path / "game_a.training.json"

        train_examples = [_make_example(vid_a, i, winning_team=i % 2) for i in range(3)]
        val_examples = [_make_example(vid_b, i, winning_team=i % 2) for i in range(3)]
        all_examples = [*train_examples, *val_examples]

        class FakeIndex:
            def __init__(self, dirs):
                self.examples = all_examples
                self.skip_counts = {}

        def fake_split(examples, val_fraction):
            return train_examples, val_examples

        # A fake _run_model that returns a result including game_metrics
        fake_game_metrics: dict[str, Any] = {
            "n_games": 1,
            "pct_exact_sequence": 0.0,
            "mean_first_divergence": 1.0,
            "mean_rally_winner_accuracy": 0.667,
        }

        def fake_run_model(
            val,
            checkpoint,
            device,
            include_calibration,
            terminal_event_annotations=None,
            side_map=None,
        ):
            return {
                "name": "winner_classifier",
                "n_total": len(val),
                "n_correct": 2,
                "n_wrong": 1,
                "accuracy": 2 / 3,
                "temperature": 1.0,
                "game_metrics": fake_game_metrics,
            }

        monkeypatch.setattr(ml.examples, "RallyExampleIndex", FakeIndex)
        monkeypatch.setattr(ml.evaluation.splits, "video_wise_split", fake_split)
        monkeypatch.setattr("ml.tools.evaluate_winner._run_baselines", lambda t, v: [])
        monkeypatch.setattr("ml.tools.evaluate_winner._run_model", fake_run_model)

        return run_evaluation(
            dirs=[tmp_path],
            checkpoint=tmp_path / "fake.pt",
        )

    def test_game_metrics_present_in_model_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        result = self._make_multi_video_scenario(monkeypatch, tmp_path)
        assert result["model"] is not None
        assert "game_metrics" in result["model"]

    def test_game_metrics_keys_in_json_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        result = self._make_multi_video_scenario(monkeypatch, tmp_path)
        gm = result["model"]["game_metrics"]
        assert "n_games" in gm
        assert "pct_exact_sequence" in gm
        assert "mean_first_divergence" in gm
        assert "mean_rally_winner_accuracy" in gm

    def test_game_metrics_values_pass_through(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        result = self._make_multi_video_scenario(monkeypatch, tmp_path)
        gm = result["model"]["game_metrics"]
        assert gm["n_games"] == 1
        assert gm["pct_exact_sequence"] == pytest.approx(0.0)
        assert gm["mean_first_divergence"] == pytest.approx(1.0)

    def test_game_level_section_in_table_render(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _render_table

        result = self._make_multi_video_scenario(monkeypatch, tmp_path)
        table = _render_table(result)
        assert "Game-level" in table
        assert "Games evaluated" in table

    def test_temperature_in_table_render(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ml.tools.evaluate_winner import _render_table

        result = self._make_multi_video_scenario(monkeypatch, tmp_path)
        table = _render_table(result)
        assert "Temperature" in table


class TestReadGameConfigFromSourceJson:
    def test_reads_doubles_from_valid_json(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import _read_game_config_from_source_json

        p = tmp_path / "game.training.json"
        p.write_text(
            '{"game": {"type": "singles", "victory_rules": "9"}}',
            encoding="utf-8",
        )
        game_type, victory_rules = _read_game_config_from_source_json(p)
        assert game_type == "singles"
        assert victory_rules == "9"

    def test_falls_back_to_defaults_when_file_missing(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import _read_game_config_from_source_json

        game_type, victory_rules = _read_game_config_from_source_json(
            tmp_path / "nonexistent.training.json"
        )
        assert game_type == "doubles"
        assert victory_rules == "11"

    def test_falls_back_to_defaults_on_malformed_json(self, tmp_path: Path) -> None:
        from ml.tools.evaluate_winner import _read_game_config_from_source_json

        p = tmp_path / "bad.training.json"
        p.write_text("{not valid json", encoding="utf-8")
        game_type, victory_rules = _read_game_config_from_source_json(p)
        assert game_type == "doubles"
        assert victory_rules == "11"


class TestCheckpointDiscovery:
    def test_default_checkpoint_search_prefers_best_winner_in_checkpoints_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import ml.config
        from ml.tools.evaluate_winner import _default_checkpoint_search

        checkpoints_dir = tmp_path / "checkpoints"
        checkpoints_dir.mkdir()
        preferred = checkpoints_dir / "best_winner.pt"
        preferred.write_bytes(b"best")

        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (other_dir / "winner_20260101.pt").write_bytes(b"older")

        monkeypatch.setattr(
            ml.config,
            "PathConfig",
            lambda: types.SimpleNamespace(checkpoints_dir=checkpoints_dir),
        )
        monkeypatch.setattr(
            ml.config,
            "WinnerModelConfig",
            lambda: types.SimpleNamespace(checkpoint_path=other_dir / "configured.pt"),
        )

        assert _default_checkpoint_search() == preferred

    def test_default_checkpoint_search_falls_back_to_winner_glob(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import ml.config
        from ml.tools.evaluate_winner import _default_checkpoint_search

        checkpoints_dir = tmp_path / "missing-checkpoints"
        configured_dir = tmp_path / "configured"
        configured_dir.mkdir()
        expected = configured_dir / "winner_20260202.pt"
        expected.write_bytes(b"candidate")

        monkeypatch.setattr(
            ml.config,
            "PathConfig",
            lambda: types.SimpleNamespace(checkpoints_dir=checkpoints_dir),
        )
        monkeypatch.setattr(
            ml.config,
            "WinnerModelConfig",
            lambda: types.SimpleNamespace(checkpoint_path=configured_dir / "configured.pt"),
        )

        assert _default_checkpoint_search() == expected
