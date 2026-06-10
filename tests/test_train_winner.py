"""Tests for ml.train_winner — fit_temperature helper and temperature scaling.

All tests run on CPU with tiny tensors so no GPU or heavy checkpoint is required.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
import pytest

from ml.train_winner import fit_temperature


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
