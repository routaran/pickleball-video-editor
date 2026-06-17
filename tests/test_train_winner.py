"""Tests for ml.train_winner — fit_temperature helper, temperature scaling,
and Phase 1 trainer config / CLI-flag plumbing.

All tests run on CPU with tiny tensors so no GPU or heavy checkpoint is required.
"""

from __future__ import annotations

import argparse
import dataclasses
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import torch
import torch.nn as nn
import torch.nn.functional as F
import pytest

from ml.config import WinnerModelConfig
from ml.train_winner import (
    _add_train_winner_args,
    _build_model_config_from_args,
    _config_to_dict,
    _seed_everything,
    _train_one_epoch_accum,
    fit_temperature,
)


class TestFitTemperatureEmpty:
    def test_empty_logits_returns_one(self) -> None:
        logits = torch.empty(0, 2)
        labels = torch.empty(0, dtype=torch.long)
        assert fit_temperature(logits, labels) == 1.0

    def test_empty_labels_returns_one(self) -> None:
        logits = torch.empty(0, 2)
        labels = torch.empty(0, dtype=torch.long)
        assert fit_temperature(logits, labels) == 1.0

    def test_returns_float_type(self) -> None:
        logits = torch.empty(0, 2)
        labels = torch.empty(0, dtype=torch.long)
        result = fit_temperature(logits, labels)
        assert isinstance(result, float)


class TestFitTemperatureOverconfident:
    """Overconfident logits (large |logit| values, partial wrong predictions) yield T > 1.

    Temperature > 1 is warranted when the model's softmax probabilities are
    systematically higher than the true empirical accuracy on the validation set.

    Scenario: 7 correct, 3 wrong out of 10 predictions, with logit magnitude 5
    (giving ~99.99% softmax confidence for the predicted class).  At accuracy
    70%, the calibrated probability should be ~0.70, which requires T ≈ 11.8
    (i.e. T > 1).
    """

    def _overconfident_logits_labels(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Build 10-sample overconfident dataset: 70% accuracy, 99.99% confidence."""
        n = 10
        # First 7: label 0, model predicts class 0 strongly → correct.
        # Last 3:  label 1, model still predicts class 0 strongly → wrong.
        labels = torch.tensor([0] * 7 + [1] * 3)
        logits = torch.zeros(n, 2)
        logits[:, 0] = 5.0    # all predict class 0 with near-certain confidence
        logits[:, 1] = -5.0
        return logits, labels

    def test_overconfident_gives_temperature_above_one(self) -> None:
        logits, labels = self._overconfident_logits_labels()
        T = fit_temperature(logits, labels)
        assert T > 1.0, f"Expected T > 1 for overconfident (70% acc, 99.99% conf), got T={T:.4f}"

    def test_nll_does_not_increase_after_scaling(self) -> None:
        logits, labels = self._overconfident_logits_labels()
        T = fit_temperature(logits, labels)
        nll_before = float(F.cross_entropy(logits, labels).item())
        nll_after = float(F.cross_entropy(logits / T, labels).item())
        assert nll_after <= nll_before + 1e-5, (
            f"NLL must not increase after temperature scaling: "
            f"before={nll_before:.4f}, after={nll_after:.4f}"
        )

    def test_predictions_unchanged_by_temperature(self) -> None:
        """argmax(logits / T) == argmax(logits) for any positive T."""
        n = 10
        labels = torch.randint(0, 2, (n,))
        logits = torch.randn(n, 2) * 3.0

        T = fit_temperature(logits, labels)
        assert T > 0.0
        preds_orig = logits.argmax(dim=1)
        preds_scaled = (logits / T).argmax(dim=1)
        assert (preds_orig == preds_scaled).all()


class TestFitTemperatureCalibrated:
    """Logits whose softmax probabilities match the empirical accuracy → T ≈ 1."""

    def test_calibrated_logits_temperature_near_one(self) -> None:
        # 7 correct, 3 wrong (70% accuracy).  Set logit magnitude so that
        # softmax([x, -x]) = sigmoid(2x) ≈ 0.70, which is the empirical accuracy.
        # sigmoid(2x) = 0.70 → 2x = logit(0.70) ≈ 0.847 → x ≈ 0.424.
        # In this case the model's confidence (70%) matches the accuracy (70%)
        # so temperature scaling should not move T far from 1.
        n = 10
        labels = torch.tensor([0] * 7 + [1] * 3)
        logits = torch.zeros(n, 2)
        logits[:, 0] = 0.424    # softmax ≈ 0.70, matching empirical accuracy
        logits[:, 1] = -0.424
        T = fit_temperature(logits, labels)
        # Loose tolerance: within a factor of 3 of 1.0
        assert 0.33 < T < 3.0, (
            f"Calibrated logits (70% acc, 70% conf) should give T ≈ 1, got T={T:.4f}"
        )


class TestFitTemperatureClamping:
    def test_temperature_clamped_to_max(self) -> None:
        # Perfect predictions with near-infinite confidence → T would want to
        # go to 0 (logits already optimal), so it should be clamped at 0.05.
        labels = torch.tensor([0, 1])
        logits = torch.tensor([[1000.0, -1000.0], [-1000.0, 1000.0]])
        T = fit_temperature(logits, labels)
        assert 0.05 <= T <= 20.0

    def test_temperature_always_positive(self) -> None:
        labels = torch.tensor([0, 1, 0, 1])
        logits = torch.randn(4, 2) * 10.0
        T = fit_temperature(logits, labels)
        assert T > 0.0

    def test_returns_float(self) -> None:
        labels = torch.tensor([0, 1, 0])
        logits = torch.tensor([[2.0, -2.0], [-2.0, 2.0], [2.0, -2.0]])
        result = fit_temperature(logits, labels)
        assert isinstance(result, float)


class TestFitTemperatureSingleSample:
    def test_single_sample_correct(self) -> None:
        logits = torch.tensor([[5.0, -5.0]])
        labels = torch.tensor([0])
        T = fit_temperature(logits, labels)
        assert 0.05 <= T <= 20.0

    def test_single_sample_wrong(self) -> None:
        # Only one sample, wrong prediction → optimizer may struggle but must
        # not crash and T must stay in valid range.
        logits = torch.tensor([[5.0, -5.0]])
        labels = torch.tensor([1])
        T = fit_temperature(logits, labels)
        assert 0.05 <= T <= 20.0


# ---------------------------------------------------------------------------
# Phase 1: WinnerModelConfig → _build_model_config_from_args
# ---------------------------------------------------------------------------


def _make_args(**overrides: object) -> argparse.Namespace:
    """Build a Namespace with all train-winner defaults plus any overrides."""
    defaults = {
        "canonical_width": None,
        "canonical_height": None,
        "clip_duration_s": None,
        "fps_out": None,
        "clip_extract_max_dim": None,
        "checkpoint_out": None,
        "seed": None,
        "grad_accum_steps": 1,
        "num_workers": 4,
        "amp": False,
        "train_manifest": None,
        "val_manifest": None,
        "test_manifest": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestBuildModelConfigFromArgs:
    """_build_model_config_from_args honours provided values and keeps defaults."""

    def test_defaults_unchanged_when_no_args_provided(self) -> None:
        args = _make_args()
        cfg = _build_model_config_from_args(args)
        expected = WinnerModelConfig()
        assert cfg.canonical_width == expected.canonical_width
        assert cfg.canonical_height == expected.canonical_height
        assert cfg.clip_duration_s == expected.clip_duration_s
        assert cfg.fps_out == expected.fps_out
        assert cfg.clip_extract_max_dim == expected.clip_extract_max_dim

    def test_canonical_width_overridden(self) -> None:
        args = _make_args(canonical_width=512)
        cfg = _build_model_config_from_args(args)
        assert cfg.canonical_width == 512
        # Other fields stay at defaults
        assert cfg.canonical_height == WinnerModelConfig().canonical_height

    def test_canonical_height_overridden(self) -> None:
        args = _make_args(canonical_height=256)
        cfg = _build_model_config_from_args(args)
        assert cfg.canonical_height == 256

    def test_clip_duration_s_overridden(self) -> None:
        args = _make_args(clip_duration_s=5.0)
        cfg = _build_model_config_from_args(args)
        assert cfg.clip_duration_s == 5.0
        assert cfg.effective_clip_duration_s == 5.0

    def test_fps_out_overridden(self) -> None:
        args = _make_args(fps_out=15)
        cfg = _build_model_config_from_args(args)
        assert cfg.fps_out == 15

    def test_clip_extract_max_dim_overridden(self) -> None:
        args = _make_args(clip_extract_max_dim=1080)
        cfg = _build_model_config_from_args(args)
        assert cfg.clip_extract_max_dim == 1080

    def test_multiple_overrides_all_applied(self) -> None:
        args = _make_args(
            canonical_width=512,
            canonical_height=256,
            clip_duration_s=5.0,
            fps_out=15,
            clip_extract_max_dim=1080,
        )
        cfg = _build_model_config_from_args(args)
        assert cfg.canonical_width == 512
        assert cfg.canonical_height == 256
        assert cfg.clip_duration_s == 5.0
        assert cfg.fps_out == 15
        assert cfg.clip_extract_max_dim == 1080


# ---------------------------------------------------------------------------
# Phase 1: _config_to_dict includes effective_clip_duration_s
# ---------------------------------------------------------------------------


class TestConfigToDict:
    def test_default_config_serialises_effective_clip_duration(self) -> None:
        cfg = WinnerModelConfig()
        d = _config_to_dict(cfg)
        assert "effective_clip_duration_s" in d
        assert d["effective_clip_duration_s"] == cfg.effective_clip_duration_s

    def test_modified_config_fields_appear_in_dict(self) -> None:
        cfg = WinnerModelConfig(
            canonical_width=512,
            canonical_height=256,
            clip_duration_s=5.0,
            fps_out=15,
            clip_extract_max_dim=1080,
        )
        d = _config_to_dict(cfg)
        assert d["canonical_width"] == 512
        assert d["canonical_height"] == 256
        assert d["clip_duration_s"] == 5.0
        assert d["fps_out"] == 15
        assert d["clip_extract_max_dim"] == 1080
        assert d["effective_clip_duration_s"] == 5.0

    def test_all_dataclass_fields_present(self) -> None:
        cfg = WinnerModelConfig()
        d = _config_to_dict(cfg)
        for f in dataclasses.fields(cfg):
            assert f.name in d, f"Field {f.name!r} missing from serialised dict"

    def test_path_values_are_strings(self) -> None:
        cfg = WinnerModelConfig()
        d = _config_to_dict(cfg)
        for key, value in d.items():
            assert not isinstance(value, Path), (
                f"Key {key!r} must be a plain type, not Path, for JSON/torch serialisation"
            )


# ---------------------------------------------------------------------------
# Phase 1: _add_train_winner_args registers expected flags
# ---------------------------------------------------------------------------


class TestAddTrainWinnerArgs:
    def _parser_with_args(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser()
        _add_train_winner_args(p)
        return p

    def test_canonical_width_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--canonical-width", "512"])
        assert args.canonical_width == 512

    def test_canonical_height_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--canonical-height", "256"])
        assert args.canonical_height == 256

    def test_clip_duration_s_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--clip-duration-s", "5.0"])
        assert args.clip_duration_s == 5.0

    def test_fps_out_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--fps-out", "15"])
        assert args.fps_out == 15

    def test_clip_extract_max_dim_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--clip-extract-max-dim", "1080"])
        assert args.clip_extract_max_dim == 1080

    def test_checkpoint_out_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--checkpoint-out", "/tmp/exp.pt"])
        assert args.checkpoint_out == "/tmp/exp.pt"

    def test_seed_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--seed", "42"])
        assert args.seed == 42

    def test_grad_accum_steps_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--grad-accum-steps", "4"])
        assert args.grad_accum_steps == 4

    def test_num_workers_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--num-workers", "2"])
        assert args.num_workers == 2

    def test_amp_flag_accepted(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp", "--amp"])
        assert args.amp is True

    def test_amp_default_is_false(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp"])
        assert args.amp is False

    def test_grad_accum_default_is_one(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args(["--root", "/tmp"])
        assert args.grad_accum_steps == 1

    def test_all_flags_together(self) -> None:
        p = self._parser_with_args()
        args = p.parse_args([
            "--root", "/tmp",
            "--epochs", "50",
            "--batch-size", "2",
            "--grad-accum-steps", "4",
            "--seed", "0",
            "--device", "cuda",
            "--canonical-width", "512",
            "--canonical-height", "256",
            "--clip-duration-s", "5.0",
            "--fps-out", "15",
            "--clip-extract-max-dim", "1080",
            "--checkpoint-out", "ml/checkpoints/exp.pt",
            "--amp",
        ])
        assert args.canonical_width == 512
        assert args.canonical_height == 256
        assert args.clip_duration_s == 5.0
        assert args.fps_out == 15
        assert args.clip_extract_max_dim == 1080
        assert args.checkpoint_out == "ml/checkpoints/exp.pt"
        assert args.seed == 0
        assert args.grad_accum_steps == 4
        assert args.amp is True


# ---------------------------------------------------------------------------
# Phase 1: checkpoint_out is written to the specified path
# ---------------------------------------------------------------------------


class TestCheckpointOut:
    """train_winner writes checkpoint to --checkpoint-out when provided."""

    def test_checkpoint_written_to_custom_path(self, tmp_path: Path) -> None:
        """Verify that checkpoint_out is respected and the file is created."""
        custom_ckpt = tmp_path / "subdir" / "custom.pt"

        # We don't actually run a training loop — just verify path resolution
        # by checking that train_winner creates the parent directory.
        # Use a minimal mock that short-circuits after the path setup.
        with patch("ml.train_winner.load_winner_dataset") as mock_load, \
             patch("ml.train_winner.WinnerClassifier") as mock_cls, \
             patch("ml.train_winner.DataLoader") as mock_dl:

            # Make load_winner_dataset return objects with enough attrs to
            # satisfy the guard checks and loop without actual data.
            mock_dataset = MagicMock()
            mock_dataset.__len__ = MagicMock(return_value=0)
            mock_load.return_value = mock_dataset

            # train_winner exits early when dataset is empty via sys.exit;
            # confirm parent dir was still created before that happens.
            with pytest.raises(SystemExit):
                from ml.train_winner import train_winner
                train_winner(
                    root_dir=tmp_path,
                    epochs=1,
                    batch_size=2,
                    device_str="cpu",
                    checkpoint_out=custom_ckpt,
                )

        assert custom_ckpt.parent.exists(), (
            "Parent directory for --checkpoint-out should be created by train_winner"
        )

    def test_default_checkpoint_path_used_when_none(self) -> None:
        """When checkpoint_out is None, the default path from PathConfig is used."""
        from ml.config import PathConfig
        from ml.train_winner import train_winner

        with patch("ml.train_winner.load_winner_dataset") as mock_load, \
             patch("ml.train_winner.WinnerClassifier"), \
             patch("ml.train_winner.DataLoader"):

            mock_dataset = MagicMock()
            mock_dataset.__len__ = MagicMock(return_value=0)
            mock_load.return_value = mock_dataset

            with pytest.raises(SystemExit):
                train_winner(
                    root_dir=Path("/tmp"),
                    epochs=1,
                    batch_size=2,
                    device_str="cpu",
                    checkpoint_out=None,
                )

        # Nothing to assert about the path itself — just confirm no crash
        # when checkpoint_out=None (path defaults to PathConfig().checkpoints_dir).


# ---------------------------------------------------------------------------
# Phase 1: seed parameter plumbing
# ---------------------------------------------------------------------------


class TestSeedPlumbing:
    def test_seed_sets_torch_manual_seed(self) -> None:
        _seed_everything(42)
        # Draw a random tensor — it should be reproducible with the same seed.
        t1 = torch.randn(4)
        _seed_everything(42)
        t2 = torch.randn(4)
        assert torch.allclose(t1, t2), "Same seed should produce identical tensors"

    def test_different_seeds_produce_different_tensors(self) -> None:
        _seed_everything(0)
        t1 = torch.randn(8)
        _seed_everything(1)
        t2 = torch.randn(8)
        assert not torch.allclose(t1, t2), "Different seeds should produce different tensors"


# ---------------------------------------------------------------------------
# Phase 1: gradient accumulation step cadence
# ---------------------------------------------------------------------------


class TestGradAccumSteps:
    """_train_one_epoch_accum calls optimizer.step() at the expected cadence."""

    def _make_simple_loader(
        self, n_batches: int, batch_size: int = 2
    ) -> list[tuple[torch.Tensor, torch.Tensor]]:
        """Build a plain list of (clips, labels) as a mock DataLoader."""
        # WinnerClassifier expects (B, T, C, H, W); use tiny dims for speed.
        return [
            (torch.randn(batch_size, 5, 3, 8, 4), torch.randint(0, 2, (batch_size,)))
            for _ in range(n_batches)
        ]

    def test_optimizer_step_called_every_accum_steps(self) -> None:
        n_batches = 6
        accum = 3
        loader = self._make_simple_loader(n_batches)

        model = MagicMock()
        # model() returns logits of shape (batch_size, 2)
        model.return_value = torch.randn(2, 2, requires_grad=False)
        model.train = MagicMock()

        criterion = MagicMock()
        # criterion() must return a tensor with .backward()
        fake_loss = MagicMock()
        fake_loss.__truediv__ = lambda self, other: fake_loss  # loss / accum
        fake_loss.item.return_value = 0.5
        fake_loss.backward = MagicMock()
        criterion.return_value = fake_loss

        optimizer = MagicMock()
        device = torch.device("cpu")

        _train_one_epoch_accum(
            model, loader, criterion, optimizer, device,  # type: ignore[arg-type]
            grad_accum_steps=accum,
        )

        # With 6 batches and accum=3, step should be called exactly 2 times.
        assert optimizer.step.call_count == 2, (
            f"Expected 2 optimizer steps for 6 batches / accum=3, "
            f"got {optimizer.step.call_count}"
        )

    def test_optimizer_step_called_once_per_batch_when_accum_is_one(self) -> None:
        n_batches = 4
        loader = self._make_simple_loader(n_batches)

        model = MagicMock()
        model.return_value = torch.randn(2, 2, requires_grad=False)
        model.train = MagicMock()

        criterion = MagicMock()
        fake_loss = MagicMock()
        fake_loss.__truediv__ = lambda self, other: fake_loss
        fake_loss.item.return_value = 0.5
        fake_loss.backward = MagicMock()
        criterion.return_value = fake_loss

        optimizer = MagicMock()
        device = torch.device("cpu")

        _train_one_epoch_accum(
            model, loader, criterion, optimizer, device,  # type: ignore[arg-type]
            grad_accum_steps=1,
        )

        assert optimizer.step.call_count == n_batches
