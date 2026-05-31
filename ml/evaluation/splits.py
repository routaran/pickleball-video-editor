"""Deterministic video-wise train/val split utility.

Splits a list of :class:`~ml.examples.RallyExample` objects by video so that
no rally from a validation video appears in the training set.  The split rule
reproduces the logic used by :class:`~ml.winner_dataset.WinnerDataset` exactly,
ensuring evaluation splits stay identical to production training splits.

Split rule (mirrors WinnerDataset.__init__)
-------------------------------------------
1. Collect distinct video paths (via ``str(example.video_path)``).
2. Sort them lexicographically (the same sort used by WinnerDataset).
3. Compute ``n_val``:
   - If ``n_videos >= 2``: ``n_val = max(1, floor(n_videos * val_fraction))``.
   - If ``n_videos < 2``:  ``n_val = 0`` (single video stays in train).
4. The **last** ``n_val`` videos (in sorted order) form the val set; the rest
   are train.

This module is torch-free.

Public API
----------
video_wise_split  -- return ``(train_examples, val_examples)``
"""

import math
from pathlib import Path

from ml.examples import RallyExample

__all__ = ["video_wise_split"]


def video_wise_split(
    examples: list[RallyExample],
    val_fraction: float = 0.2,
) -> tuple[list[RallyExample], list[RallyExample]]:
    """Split *examples* by video into train and val subsets.

    No rally from a val video will appear in the train list, and vice versa.
    The result is fully deterministic: given the same *examples* and
    *val_fraction* the function always produces the same partition.

    The sort key, ``n_val`` formula, and boundary are identical to those used
    by :class:`~ml.winner_dataset.WinnerDataset` so that evaluation code and
    training code operate on the same video partition.

    Args:
        examples: Flat list of :class:`~ml.examples.RallyExample` objects.
            May be empty.
        val_fraction: Fraction of distinct videos to reserve for validation.
            Must be in ``[0.0, 1.0]``.  Ignored (treated as 0) when there is
            only one distinct video.

    Returns:
        A 2-tuple ``(train_examples, val_examples)`` where each element is a
        list of :class:`~ml.examples.RallyExample` objects.  Both lists
        preserve the relative order of their examples as grouped by sorted video
        key (i.e. sorted by ``str(video_path)`` then by original list order
        within each video).

    Raises:
        ValueError: If *val_fraction* is not in ``[0.0, 1.0]``.
    """
    if not (0.0 <= val_fraction <= 1.0):
        raise ValueError(
            f"val_fraction must be in [0.0, 1.0], got {val_fraction!r}"
        )

    if not examples:
        return [], []

    # Group examples by video key, preserving encounter order within each group.
    # Key is str(video_path), matching WinnerDataset's rallies_by_video dict.
    groups: dict[str, list[RallyExample]] = {}
    for ex in examples:
        key = str(ex.video_path)
        if key not in groups:
            groups[key] = []
        groups[key].append(ex)

    # Sort video keys lexicographically — identical to:
    #   all_video_keys = sorted(rallies_by_video.keys())
    all_video_keys = sorted(groups.keys())
    n_videos = len(all_video_keys)

    # Compute n_val using the exact WinnerDataset formula.
    if n_videos >= 2:
        n_val = max(1, math.floor(n_videos * val_fraction))
    else:
        n_val = 0

    n_train = n_videos - n_val

    train_keys = all_video_keys[:n_train]
    val_keys = all_video_keys[n_train:]

    train_examples: list[RallyExample] = []
    for key in train_keys:
        train_examples.extend(groups[key])

    val_examples: list[RallyExample] = []
    for key in val_keys:
        val_examples.extend(groups[key])

    return train_examples, val_examples
