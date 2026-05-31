"""Tests for ml.review_priority.review_priority().

Covers:
- Each returned priority level ("high", "medium", "low") for both the
  confidence-only path and the combined confidence+margin path.
- Exact boundary values (at-threshold, just-above, just-below) to guard
  against off-by-one errors in the comparison operators.
- The margin-only escalation path: a high-confidence prediction with a
  very low margin must still be escalated.
- ValueError for out-of-range inputs.
- Torch-free: no torch import anywhere in this module.
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so ml/ is importable directly.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.review_priority import (  # noqa: E402
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    MARGIN_HIGH_THRESHOLD,
    MARGIN_MEDIUM_THRESHOLD,
    review_priority,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _just_above(value: float, delta: float = 1e-6) -> float:
    return min(value + delta, 1.0)


def _just_below(value: float, delta: float = 1e-6) -> float:
    return max(value - delta, 0.0)


# ---------------------------------------------------------------------------
# TestReviewPriorityConfidenceOnly — margin not supplied
# ---------------------------------------------------------------------------


class TestReviewPriorityConfidenceOnly:
    """Verify all three levels when only confidence is provided."""

    def test_at_high_threshold_returns_high(self) -> None:
        """Confidence exactly at CONFIDENCE_HIGH_THRESHOLD -> "high"."""
        result = review_priority(CONFIDENCE_HIGH_THRESHOLD)
        assert result == "high", (
            f"Expected 'high' at confidence={CONFIDENCE_HIGH_THRESHOLD}, got {result!r}"
        )

    def test_just_below_high_threshold_returns_high(self) -> None:
        """Confidence just below CONFIDENCE_HIGH_THRESHOLD -> "high"."""
        confidence = _just_below(CONFIDENCE_HIGH_THRESHOLD)
        result = review_priority(confidence)
        assert result == "high", (
            f"Expected 'high' at confidence={confidence}, got {result!r}"
        )

    def test_minimum_confidence_returns_high(self) -> None:
        """confidence=0.0 (random model) -> "high"."""
        assert review_priority(0.0) == "high"

    def test_near_coin_flip_returns_high(self) -> None:
        """confidence=0.51 (barely above random) -> "high"."""
        assert review_priority(0.51) == "high"

    def test_just_above_high_threshold_returns_at_least_medium(self) -> None:
        """Confidence just above CONFIDENCE_HIGH_THRESHOLD -> not "high"."""
        confidence = _just_above(CONFIDENCE_HIGH_THRESHOLD)
        result = review_priority(confidence)
        assert result != "high", (
            f"Expected 'medium' or 'low' at confidence={confidence}, got {result!r}"
        )

    def test_at_medium_threshold_returns_medium(self) -> None:
        """Confidence exactly at CONFIDENCE_MEDIUM_THRESHOLD -> "medium"."""
        result = review_priority(CONFIDENCE_MEDIUM_THRESHOLD)
        assert result == "medium", (
            f"Expected 'medium' at confidence={CONFIDENCE_MEDIUM_THRESHOLD}, got {result!r}"
        )

    def test_just_below_medium_threshold_returns_medium(self) -> None:
        """Confidence just below CONFIDENCE_MEDIUM_THRESHOLD -> "medium" (not "low")."""
        confidence = _just_below(CONFIDENCE_MEDIUM_THRESHOLD)
        # Must be above high threshold to reach medium gate.
        confidence = max(confidence, _just_above(CONFIDENCE_HIGH_THRESHOLD))
        result = review_priority(confidence)
        assert result == "medium", (
            f"Expected 'medium' at confidence={confidence}, got {result!r}"
        )

    def test_just_above_medium_threshold_returns_low(self) -> None:
        """Confidence just above CONFIDENCE_MEDIUM_THRESHOLD -> "low"."""
        confidence = _just_above(CONFIDENCE_MEDIUM_THRESHOLD)
        result = review_priority(confidence)
        assert result == "low", (
            f"Expected 'low' at confidence={confidence}, got {result!r}"
        )

    def test_maximum_confidence_returns_low(self) -> None:
        """confidence=1.0 (perfect certainty) -> "low"."""
        assert review_priority(1.0) == "low"

    def test_very_high_confidence_returns_low(self) -> None:
        """confidence=0.95 (typical confident prediction) -> "low"."""
        assert review_priority(0.95) == "low"


# ---------------------------------------------------------------------------
# TestReviewPriorityWithMargin — margin supplied
# ---------------------------------------------------------------------------


class TestReviewPriorityWithMargin:
    """Verify that margin gates escalate independently of confidence."""

    def test_high_confidence_low_margin_escalates_to_high(self) -> None:
        """High confidence + near-zero margin -> "high".

        This is the adversarial case: a model that concentrates softmax
        mass on one class (high confidence) while the raw score difference
        is tiny (low margin) should still be flagged.
        """
        confidence = _just_above(CONFIDENCE_MEDIUM_THRESHOLD)  # would be "low" alone
        margin = MARGIN_HIGH_THRESHOLD  # at threshold -> "high"
        result = review_priority(confidence, margin)
        assert result == "high", (
            f"Expected 'high' with confidence={confidence}, margin={margin}, got {result!r}"
        )

    def test_high_confidence_just_below_margin_high_threshold_returns_high(self) -> None:
        """margin just below MARGIN_HIGH_THRESHOLD -> "high"."""
        confidence = _just_above(CONFIDENCE_MEDIUM_THRESHOLD)
        margin = _just_below(MARGIN_HIGH_THRESHOLD)
        result = review_priority(confidence, margin)
        assert result == "high", (
            f"Expected 'high' with confidence={confidence}, margin={margin}, got {result!r}"
        )

    def test_high_confidence_at_medium_margin_returns_medium(self) -> None:
        """High confidence + margin at MARGIN_MEDIUM_THRESHOLD -> "medium"."""
        confidence = _just_above(CONFIDENCE_MEDIUM_THRESHOLD)
        margin = MARGIN_MEDIUM_THRESHOLD
        result = review_priority(confidence, margin)
        assert result == "medium", (
            f"Expected 'medium' with confidence={confidence}, margin={margin}, got {result!r}"
        )

    def test_high_confidence_high_margin_returns_low(self) -> None:
        """High confidence + high margin -> "low": both axes clear."""
        confidence = 0.95
        margin = _just_above(MARGIN_MEDIUM_THRESHOLD)
        result = review_priority(confidence, margin)
        assert result == "low", (
            f"Expected 'low' with confidence={confidence}, margin={margin}, got {result!r}"
        )

    def test_low_confidence_overrides_high_margin(self) -> None:
        """Low confidence always wins even with a large margin."""
        confidence = CONFIDENCE_HIGH_THRESHOLD  # <= threshold -> "high"
        margin = 0.99  # would be "low" alone
        result = review_priority(confidence, margin)
        assert result == "high", (
            f"Expected 'high' with confidence={confidence}, margin={margin}, got {result!r}"
        )

    def test_medium_confidence_high_margin_returns_medium(self) -> None:
        """Medium confidence + high margin: confidence gate dominates -> "medium"."""
        confidence = CONFIDENCE_MEDIUM_THRESHOLD  # at medium threshold
        margin = 0.99  # would be "low" alone
        result = review_priority(confidence, margin)
        assert result == "medium"

    def test_none_margin_behaves_as_absent(self) -> None:
        """Passing margin=None is identical to omitting the argument."""
        confidence = 0.95
        assert review_priority(confidence, None) == review_priority(confidence)

    def test_zero_margin_returns_high(self) -> None:
        """margin=0.0 (model is perfectly split) -> "high"."""
        confidence = _just_above(CONFIDENCE_MEDIUM_THRESHOLD)
        result = review_priority(confidence, 0.0)
        assert result == "high"

    def test_full_margin_and_full_confidence_returns_low(self) -> None:
        """margin=1.0, confidence=1.0 -> "low"."""
        assert review_priority(1.0, 1.0) == "low"


# ---------------------------------------------------------------------------
# TestReviewPriorityReturnType
# ---------------------------------------------------------------------------


class TestReviewPriorityReturnType:
    """Verify the return type contract."""

    def test_return_value_is_str(self) -> None:
        """review_priority must return a plain str."""
        result = review_priority(0.8)
        assert isinstance(result, str)

    def test_return_value_is_valid_level(self) -> None:
        """Return value must always be one of the three defined levels."""
        valid = {"high", "medium", "low"}
        for confidence in [0.0, 0.5, CONFIDENCE_HIGH_THRESHOLD,
                           CONFIDENCE_MEDIUM_THRESHOLD, 0.9, 1.0]:
            result = review_priority(confidence)
            assert result in valid, (
                f"review_priority({confidence}) returned {result!r}, "
                f"expected one of {valid}"
            )


# ---------------------------------------------------------------------------
# TestReviewPriorityValidation — invalid inputs
# ---------------------------------------------------------------------------


class TestReviewPriorityValidation:
    """Verify that out-of-range inputs raise ValueError."""

    def test_confidence_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            review_priority(-0.01)

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            review_priority(1.01)

    def test_margin_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="margin"):
            review_priority(0.8, -0.01)

    def test_margin_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="margin"):
            review_priority(0.8, 1.01)

    def test_both_invalid_confidence_checked_first(self) -> None:
        """When both inputs are invalid, confidence is validated first."""
        with pytest.raises(ValueError, match="confidence"):
            review_priority(-1.0, -1.0)
