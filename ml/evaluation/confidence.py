"""Confidence / calibration diagnostics for winner predictions.

Buckets predicted probabilities into equal-width bins and computes per-bucket
statistics (count, mean confidence, accuracy) along with the Expected
Calibration Error (ECE).

All inputs are plain Python sequences or numpy arrays — no torch dependency.

Public API
----------
calibration_stats(confidences, correct, n_buckets=10)
    -> CalibrationResult
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


__all__ = [
    "BucketStats",
    "CalibrationResult",
    "calibration_stats",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BucketStats:
    """Statistics for a single confidence bucket.

    Attributes:
        bucket_lower: Lower edge of the confidence interval (inclusive).
        bucket_upper: Upper edge of the confidence interval (exclusive for all
            buckets except the last, which is inclusive).
        count: Number of samples whose predicted confidence falls in this bucket.
        mean_confidence: Average predicted confidence of samples in the bucket.
            None when count == 0.
        accuracy: Fraction of samples in the bucket that were correctly
            classified.  None when count == 0.
    """

    bucket_lower: float
    bucket_upper: float
    count: int
    mean_confidence: float | None
    accuracy: float | None


@dataclass
class CalibrationResult:
    """Full calibration diagnostic result.

    Attributes:
        buckets: Per-bucket statistics in ascending confidence order.
        ece: Expected Calibration Error — the weighted average of
            |accuracy - mean_confidence| across non-empty buckets, weighted
            by the fraction of total samples each bucket contains.
        n_samples: Total number of samples processed.
    """

    buckets: list[BucketStats] = field(default_factory=list)
    ece: float = 0.0
    n_samples: int = 0


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def calibration_stats(
    confidences: "list[float] | np.ndarray",
    correct: "list[bool] | list[int] | np.ndarray",
    n_buckets: int = 10,
) -> CalibrationResult:
    """Compute per-bucket calibration statistics and ECE.

    Partitions predictions into *n_buckets* equal-width intervals over [0, 1]
    and computes mean confidence and accuracy within each bucket.  Empty
    buckets produce BucketStats with mean_confidence=None and accuracy=None
    and contribute zero weight to the ECE.

    Args:
        confidences: Sequence of predicted probabilities for the predicted
            class, each in [0, 1].  Length must equal len(correct).
        correct: Sequence of correctness indicators.  Each element is
            interpreted as a boolean (truthy = correctly classified).  Accepts
            bool, int (0/1), or float.
        n_buckets: Number of equal-width confidence buckets to create.
            Must be >= 1.  Default is 10.

    Returns:
        A CalibrationResult with per-bucket BucketStats and an overall ECE.

    Raises:
        ValueError: If confidences and correct differ in length, if n_buckets
            < 1, or if any confidence value is outside [0, 1].
    """
    confs = np.asarray(confidences, dtype=float)
    corrs = np.asarray(correct, dtype=float)

    if confs.ndim != 1 or corrs.ndim != 1:
        raise ValueError("confidences and correct must be 1-D sequences.")

    if len(confs) != len(corrs):
        raise ValueError(
            f"confidences (len={len(confs)}) and correct (len={len(corrs)}) "
            "must have the same length."
        )

    if n_buckets < 1:
        raise ValueError(f"n_buckets must be >= 1, got {n_buckets}.")

    if len(confs) > 0:
        if float(confs.min()) < 0.0 or float(confs.max()) > 1.0:
            raise ValueError(
                "All confidence values must be in [0, 1].  "
                f"Got range [{float(confs.min()):.4f}, {float(confs.max()):.4f}]."
            )

    n_samples = len(confs)
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    buckets: list[BucketStats] = []
    ece_accumulator = 0.0

    for i in range(n_buckets):
        lower = float(edges[i])
        upper = float(edges[i + 1])

        # Last bucket is right-inclusive to capture confidence == 1.0 exactly.
        if i < n_buckets - 1:
            mask = (confs >= lower) & (confs < upper)
        else:
            mask = (confs >= lower) & (confs <= upper)

        bucket_confs = confs[mask]
        bucket_corrs = corrs[mask]
        count = int(mask.sum())

        if count == 0:
            buckets.append(
                BucketStats(
                    bucket_lower=lower,
                    bucket_upper=upper,
                    count=0,
                    mean_confidence=None,
                    accuracy=None,
                )
            )
            continue

        mean_conf = float(bucket_confs.mean())
        accuracy = float(bucket_corrs.mean())

        buckets.append(
            BucketStats(
                bucket_lower=lower,
                bucket_upper=upper,
                count=count,
                mean_confidence=mean_conf,
                accuracy=accuracy,
            )
        )

        # Weighted absolute gap contributes to ECE.
        if n_samples > 0:
            ece_accumulator += (count / n_samples) * abs(accuracy - mean_conf)

    return CalibrationResult(
        buckets=buckets,
        ece=ece_accumulator,
        n_samples=n_samples,
    )
