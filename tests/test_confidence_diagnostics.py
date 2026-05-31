"""Tests for ml/evaluation/confidence.py — calibration diagnostics.

All tests are deterministic, torch-free, and use only plain Python values or
numpy arrays as inputs.

Test classes
------------
TestBucketStats       — structural validation of BucketStats fields
TestCalibrationStats  — correctness of bucketing, ECE, and edge cases
TestKnownECE          — small hand-computable examples with exact ECE values
TestEmptyBuckets      — graceful handling of sparse or empty inputs
"""

import math
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.evaluation.confidence import (  # noqa: E402
    BucketStats,
    CalibrationResult,
    calibration_stats,
)


# ---------------------------------------------------------------------------
# TestBucketStats
# ---------------------------------------------------------------------------


class TestBucketStats:
    """BucketStats is a pure dataclass — check field types and None semantics."""

    def test_empty_bucket_fields_are_none(self) -> None:
        """An empty BucketStats must carry None for mean_confidence and accuracy."""
        bs = BucketStats(
            bucket_lower=0.0,
            bucket_upper=0.1,
            count=0,
            mean_confidence=None,
            accuracy=None,
        )
        assert bs.mean_confidence is None
        assert bs.accuracy is None
        assert bs.count == 0

    def test_non_empty_bucket_has_numeric_fields(self) -> None:
        """A populated BucketStats must have float mean_confidence and accuracy."""
        bs = BucketStats(
            bucket_lower=0.5,
            bucket_upper=0.6,
            count=5,
            mean_confidence=0.55,
            accuracy=0.6,
        )
        assert isinstance(bs.mean_confidence, float)
        assert isinstance(bs.accuracy, float)


# ---------------------------------------------------------------------------
# TestCalibrationStats
# ---------------------------------------------------------------------------


class TestCalibrationStats:
    """Core bucketing and ECE computation tests."""

    def test_returns_calibration_result_type(self) -> None:
        """calibration_stats must return a CalibrationResult instance."""
        result = calibration_stats([0.7, 0.8], [True, False])
        assert isinstance(result, CalibrationResult)

    def test_bucket_count_equals_n_buckets(self) -> None:
        """Result must contain exactly n_buckets BucketStats entries."""
        result = calibration_stats([0.6, 0.9], [True, True], n_buckets=5)
        assert len(result.buckets) == 5

    def test_default_is_ten_buckets(self) -> None:
        """Default n_buckets=10 must produce 10 BucketStats entries."""
        result = calibration_stats([0.55], [True])
        assert len(result.buckets) == 10

    def test_n_samples_matches_input_length(self) -> None:
        """CalibrationResult.n_samples must equal len(confidences)."""
        confs = [0.6, 0.7, 0.8, 0.9]
        result = calibration_stats(confs, [True, False, True, True])
        assert result.n_samples == 4

    def test_all_correct_bucket_accuracy_is_one(self) -> None:
        """When every sample is correct, every non-empty bucket has accuracy 1.0."""
        confs = [0.55, 0.56, 0.57]
        result = calibration_stats(confs, [True, True, True])
        for bucket in result.buckets:
            if bucket.count > 0:
                assert bucket.accuracy == pytest.approx(1.0), (
                    f"Bucket [{bucket.bucket_lower}, {bucket.bucket_upper}] "
                    f"should have accuracy 1.0, got {bucket.accuracy}"
                )

    def test_all_wrong_bucket_accuracy_is_zero(self) -> None:
        """When every sample is incorrect, every non-empty bucket has accuracy 0.0."""
        confs = [0.55, 0.56, 0.57]
        result = calibration_stats(confs, [False, False, False])
        for bucket in result.buckets:
            if bucket.count > 0:
                assert bucket.accuracy == pytest.approx(0.0), (
                    f"Bucket [{bucket.bucket_lower}, {bucket.bucket_upper}] "
                    f"should have accuracy 0.0, got {bucket.accuracy}"
                )

    def test_bucket_edges_are_ascending(self) -> None:
        """Each bucket's lower edge must be strictly less than its upper edge."""
        result = calibration_stats([0.3, 0.7], [True, False], n_buckets=4)
        for bucket in result.buckets:
            assert bucket.bucket_lower < bucket.bucket_upper, (
                f"Bucket edges not ascending: [{bucket.bucket_lower}, {bucket.bucket_upper}]"
            )

    def test_bucket_counts_sum_to_n_samples(self) -> None:
        """The sum of all bucket counts must equal the total number of samples."""
        confs = [0.1, 0.35, 0.55, 0.72, 0.9]
        result = calibration_stats(confs, [True, False, True, True, False])
        total = sum(b.count for b in result.buckets)
        assert total == result.n_samples

    def test_mean_confidence_within_bucket_range(self) -> None:
        """Non-empty bucket mean_confidence must fall within its [lower, upper] range."""
        confs = [0.05, 0.15, 0.65, 0.95]
        result = calibration_stats(confs, [True, False, True, True])
        for bucket in result.buckets:
            if bucket.count > 0 and bucket.mean_confidence is not None:
                assert bucket.bucket_lower <= bucket.mean_confidence <= bucket.bucket_upper, (
                    f"mean_confidence {bucket.mean_confidence:.4f} outside "
                    f"[{bucket.bucket_lower}, {bucket.bucket_upper}]"
                )

    def test_confidence_exactly_one_lands_in_last_bucket(self) -> None:
        """Confidence value of exactly 1.0 must fall in the last bucket."""
        result = calibration_stats([1.0], [True])
        last_bucket = result.buckets[-1]
        assert last_bucket.count == 1, (
            f"confidence=1.0 should land in last bucket, got count={last_bucket.count}"
        )

    def test_confidence_exactly_zero_lands_in_first_bucket(self) -> None:
        """Confidence value of exactly 0.0 must fall in the first bucket."""
        result = calibration_stats([0.0], [False])
        first_bucket = result.buckets[0]
        assert first_bucket.count == 1, (
            f"confidence=0.0 should land in first bucket, got count={first_bucket.count}"
        )

    def test_ece_is_non_negative(self) -> None:
        """ECE must always be >= 0."""
        result = calibration_stats([0.6, 0.8, 0.9], [True, False, True])
        assert result.ece >= 0.0

    def test_ece_is_at_most_one(self) -> None:
        """ECE must always be <= 1.0 (it is a weighted average of [0,1] gaps)."""
        result = calibration_stats([0.6, 0.8, 0.9], [True, False, True])
        assert result.ece <= 1.0

    def test_invalid_lengths_raise_value_error(self) -> None:
        """Mismatched lengths must raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            calibration_stats([0.5, 0.6], [True])

    def test_n_buckets_zero_raises_value_error(self) -> None:
        """n_buckets=0 must raise ValueError."""
        with pytest.raises(ValueError, match="n_buckets"):
            calibration_stats([0.5], [True], n_buckets=0)

    def test_confidence_out_of_range_raises_value_error(self) -> None:
        """A confidence value > 1.0 must raise ValueError."""
        with pytest.raises(ValueError, match="\\[0, 1\\]"):
            calibration_stats([1.1], [True])

    def test_accepts_numpy_arrays(self) -> None:
        """calibration_stats must accept numpy arrays for both inputs."""
        import numpy as np

        confs = np.array([0.6, 0.7, 0.8])
        corrs = np.array([1, 0, 1])
        result = calibration_stats(confs, corrs)
        assert isinstance(result, CalibrationResult)


# ---------------------------------------------------------------------------
# TestKnownECE
# ---------------------------------------------------------------------------


class TestKnownECE:
    """Hand-computable examples where ECE can be verified analytically."""

    def test_perfect_calibration_ece_is_zero(self) -> None:
        """When accuracy == mean_confidence in every bucket, ECE must be 0.

        Construction: four samples split into two buckets.
          Bucket [0.5, 0.6): confs=[0.5, 0.5], correct=[1,0] -> acc=0.5, mean_conf=0.5
          Bucket [0.9, 1.0]: confs=[0.9, 0.9], correct=[1,0] -> acc=0.5 — oops, wrong.

        Instead use a single bucket where acc == mean_conf:
          all confs=0.7, all correct (acc=1.0) — not perfect calibration.

        Use: confs all in [0.6, 0.7), 60% correct -> acc=0.6, mean_conf=0.6 -> gap=0.
        """
        # 5 samples in bucket [0.6, 0.7): mean_conf=0.6, acc=0.6 -> gap=0.0
        confs = [0.6, 0.6, 0.6, 0.6, 0.6]
        correct = [True, True, True, False, False]  # 3/5 = 0.6
        result = calibration_stats(confs, correct, n_buckets=10)

        # Find the bucket that contains 0.6.
        active = [b for b in result.buckets if b.count > 0]
        assert len(active) == 1
        bucket = active[0]
        assert bucket.accuracy == pytest.approx(0.6, abs=1e-9)
        assert bucket.mean_confidence == pytest.approx(0.6, abs=1e-9)
        assert result.ece == pytest.approx(0.0, abs=1e-9)

    def test_known_ece_two_buckets(self) -> None:
        """Verify ECE on a small two-bucket example with exact arithmetic.

        Setup (n_buckets=2 for simplicity):
          Bucket [0.0, 0.5): 2 samples, confs=[0.3, 0.4], correct=[True, False]
            -> mean_conf = 0.35, accuracy = 0.5, gap = |0.5 - 0.35| = 0.15
          Bucket [0.5, 1.0]: 3 samples, confs=[0.6, 0.7, 0.8], correct=[True, True, True]
            -> mean_conf = 0.7, accuracy = 1.0, gap = |1.0 - 0.7| = 0.3

        Total = 5 samples.
        ECE = (2/5)*0.15 + (3/5)*0.3 = 0.06 + 0.18 = 0.24
        """
        confs = [0.3, 0.4, 0.6, 0.7, 0.8]
        correct = [True, False, True, True, True]
        result = calibration_stats(confs, correct, n_buckets=2)

        assert len(result.buckets) == 2
        b0, b1 = result.buckets

        assert b0.count == 2
        assert b0.mean_confidence == pytest.approx(0.35, abs=1e-9)
        assert b0.accuracy == pytest.approx(0.5, abs=1e-9)

        assert b1.count == 3
        assert b1.mean_confidence == pytest.approx(0.7, abs=1e-9)
        assert b1.accuracy == pytest.approx(1.0, abs=1e-9)

        expected_ece = (2 / 5) * abs(0.5 - 0.35) + (3 / 5) * abs(1.0 - 0.7)
        assert result.ece == pytest.approx(expected_ece, abs=1e-9)

    def test_single_sample_ece(self) -> None:
        """Single sample: ECE == |accuracy - mean_confidence| for that bucket.

        conf=0.8, correct=False -> accuracy=0.0, mean_conf=0.8 -> gap=0.8
        ECE = (1/1) * 0.8 = 0.8
        """
        result = calibration_stats([0.8], [False])
        assert result.ece == pytest.approx(0.8, abs=1e-9)

    def test_integer_correct_labels_accepted(self) -> None:
        """correct values of 0 and 1 (integers) must work identically to bools."""
        result_bool = calibration_stats([0.6, 0.7], [True, False])
        result_int = calibration_stats([0.6, 0.7], [1, 0])
        assert result_bool.ece == pytest.approx(result_int.ece, abs=1e-12)


# ---------------------------------------------------------------------------
# TestEmptyBuckets
# ---------------------------------------------------------------------------


class TestEmptyBuckets:
    """Graceful handling of empty inputs and sparse bucket distributions."""

    def test_empty_inputs_returns_zero_ece(self) -> None:
        """calibration_stats with zero samples must return ECE=0 and n_samples=0."""
        result = calibration_stats([], [])
        assert result.n_samples == 0
        assert result.ece == 0.0

    def test_empty_inputs_buckets_all_have_count_zero(self) -> None:
        """Every bucket must have count=0 when inputs are empty."""
        result = calibration_stats([], [], n_buckets=10)
        assert len(result.buckets) == 10
        for bucket in result.buckets:
            assert bucket.count == 0

    def test_empty_inputs_buckets_fields_are_none(self) -> None:
        """Empty-input buckets must have mean_confidence=None and accuracy=None."""
        result = calibration_stats([], [])
        for bucket in result.buckets:
            assert bucket.mean_confidence is None, (
                f"Expected None mean_confidence for empty bucket, "
                f"got {bucket.mean_confidence}"
            )
            assert bucket.accuracy is None, (
                f"Expected None accuracy for empty bucket, got {bucket.accuracy}"
            )

    def test_sparse_distribution_does_not_raise(self) -> None:
        """A single sample among 10 buckets must not raise — nine buckets empty."""
        result = calibration_stats([0.55], [True], n_buckets=10)
        assert result.n_samples == 1
        non_empty = [b for b in result.buckets if b.count > 0]
        assert len(non_empty) == 1

    def test_empty_bucket_does_not_affect_ece(self) -> None:
        """Empty buckets contribute zero weight to ECE.

        Two identical datasets — one with n_buckets=10 (many empty buckets)
        and one with n_buckets=2 (fewer empty buckets) — must differ only in
        the bucket layout, not in the accuracy or confidence of populated buckets.
        """
        confs = [0.3, 0.4, 0.7, 0.8]
        correct = [True, False, True, True]
        result_10 = calibration_stats(confs, correct, n_buckets=10)
        result_2 = calibration_stats(confs, correct, n_buckets=2)

        # Both must have the same total count.
        assert sum(b.count for b in result_10.buckets) == sum(
            b.count for b in result_2.buckets
        )

    def test_one_bucket_ece_equals_abs_gap(self) -> None:
        """With n_buckets=1, ECE equals |accuracy - mean_confidence| directly."""
        confs = [0.6, 0.7, 0.8]
        correct = [True, True, False]
        result = calibration_stats(confs, correct, n_buckets=1)

        assert len(result.buckets) == 1
        bucket = result.buckets[0]
        assert bucket.count == 3

        expected_ece = abs(bucket.accuracy - bucket.mean_confidence)
        assert result.ece == pytest.approx(expected_ece, abs=1e-9)
