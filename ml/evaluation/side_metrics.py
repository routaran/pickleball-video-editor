"""Side/event metrics for the winner classifier (Phase 5).

This module measures the user-reported failure mode correctly: whether the model
mis-predicts when the rally-ending action happened on the *far* side of the
court.  That requires terminal-event-side annotations — labels for *where the
final action occurred*, which is NOT the same as which side won (a far-side
error makes the near side win, inverting any "winner side" metric).

Two metric families are provided:

1. **Primary** (decision-grade): terminal-event-side accuracy, available only
   when a terminal-event annotation file is supplied.
2. **Secondary** (explicitly non-decisive): winner-side diagnostics derived from
   a per-rally/per-segment camera-near-team side map.  These are clearly labelled
   as *not* a far-side visibility metric.

Always-available team metrics (per-team accuracy, confusion matrix, balanced
accuracy) are also exposed.

This module is torch-free: numpy + stdlib only.

Annotation schemas
------------------
Terminal-event annotations (Phase 0A)::

    {
      "schema_version": "1.0",
      "annotations": [
        {"video_path": "...", "rally_index": 17,
         "terminal_event_side": "far", "terminal_event_team": 1, ...}
      ]
    }

Side map (Phase 0B)::

    {
      "schema_version": "1.0",
      "segments": [
        {"video_path": "...", "start_seconds": 0.0, "end_seconds": 742.0,
         "camera_near_team": 0}
      ],
      "rallies": [
        {"video_path": "...", "rally_index": 17, "camera_near_team": 1}
      ]
    }

Public API
----------
SideMetricBucket                      -- per-bucket accuracy summary
TerminalEventAnnotation               -- one parsed terminal-event annotation
SideMetricsError                      -- malformed annotation/side-map error
load_terminal_event_annotations       -- parse a terminal-event annotation file
load_side_map                         -- parse a side-map file -> RallyKey -> team
compute_team_metrics                  -- per-team / confusion / balanced accuracy
compute_terminal_event_side_metrics   -- primary near/far terminal-event metric
compute_winner_side_diagnostics       -- secondary (non-decisive) winner-side
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "RallyKey",
    "SideMetricBucket",
    "TerminalEventAnnotation",
    "SideMetricsError",
    "WINNER_SIDE_DISCLAIMER",
    "load_terminal_event_annotations",
    "load_side_map",
    "compute_team_metrics",
    "compute_terminal_event_side_metrics",
    "compute_winner_side_diagnostics",
]


# A rally is keyed by (absolute video path string, rally index).
RallyKey = tuple[str, int]

_VALID_SIDES: frozenset[str] = frozenset({"near", "far", "unknown"})

WINNER_SIDE_DISCLAIMER: str = (
    "Winner-side diagnostics only. Not a terminal-event-side metric and not "
    "valid for far-side visibility decisions."
)


class SideMetricsError(ValueError):
    """Raised when a terminal-event annotation or side-map file is malformed."""


@dataclass(frozen=True)
class SideMetricBucket:
    """Accuracy summary for one group of rallies.

    Attributes:
        name: Bucket label (e.g. ``"near"``, ``"far"``, ``"team_0"``).
        n_total: Number of rallies in the bucket.
        n_correct: Number correctly predicted.
        accuracy: ``n_correct / n_total`` or ``None`` when the bucket is empty.
        base_rate: Optional positive-class base rate for the bucket.
        balanced_accuracy: Optional balanced accuracy for the bucket.
    """

    name: str
    n_total: int
    n_correct: int
    accuracy: float | None
    base_rate: float | None = None
    balanced_accuracy: float | None = None


@dataclass(frozen=True)
class TerminalEventAnnotation:
    """One parsed terminal-event-side annotation.

    Attributes:
        video_path: Absolute path string of the source video.
        rally_index: Zero-based rally index within the source file.
        terminal_event_side: ``"near" | "far" | "unknown"``.
        terminal_event_team: ``0 | 1`` or ``None`` when not tied to a team.
        event_type: Optional event-type tag (e.g. ``"losing_error"``).
        confidence: Optional annotator confidence (``"high" | "medium" | "low"``).
    """

    video_path: str
    rally_index: int
    terminal_event_side: str
    terminal_event_team: int | None = None
    event_type: str | None = None
    confidence: str | None = None

    @property
    def key(self) -> RallyKey:
        """The ``(video_path, rally_index)`` key for joining to predictions."""
        return (self.video_path, self.rally_index)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _accuracy(n_correct: int, n_total: int) -> float | None:
    """Return ``n_correct / n_total`` or ``None`` when the bucket is empty."""
    if n_total <= 0:
        return None
    return n_correct / n_total


def _balanced_accuracy(labels: list[int], preds: list[int]) -> float | None:
    """Return the mean of per-true-class recall over the classes present.

    Balanced accuracy is robust to class imbalance because it averages recall
    across classes rather than counting raw correct predictions.

    Args:
        labels: Ground-truth class labels.
        preds: Predicted class labels (same length as *labels*).

    Returns:
        The unweighted mean per-class recall, or ``None`` when *labels* is empty.
    """
    if not labels:
        return None

    classes = sorted(set(labels))
    recalls: list[float] = []
    for cls in classes:
        n_cls = sum(1 for label in labels if label == cls)
        if n_cls == 0:
            continue
        n_hit = sum(
            1 for label, pred in zip(labels, preds) if label == cls and pred == cls
        )
        recalls.append(n_hit / n_cls)

    if not recalls:
        return None
    return sum(recalls) / len(recalls)


def _confusion_matrix_2x2(labels: list[int], preds: list[int]) -> list[list[int]]:
    """Return a 2x2 confusion matrix ``conf[true][pred]`` for binary labels.

    Args:
        labels: Ground-truth labels in ``{0, 1}``.
        preds: Predicted labels in ``{0, 1}``.

    Returns:
        Nested ``[[c00, c01], [c10, c11]]`` integer counts.
    """
    conf = [[0, 0], [0, 0]]
    for label, pred in zip(labels, preds):
        if label in (0, 1) and pred in (0, 1):
            conf[label][pred] += 1
    return conf


# ---------------------------------------------------------------------------
# Annotation / side-map loading
# ---------------------------------------------------------------------------


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load *path* as a JSON object, raising :class:`SideMetricsError` on failure."""
    if not path.exists():
        raise SideMetricsError(f"Annotation file not found: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SideMetricsError(f"Annotation file is not valid JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SideMetricsError(
            f"Annotation root must be a JSON object, got {type(data).__name__}: {path}"
        )
    return data


def load_terminal_event_annotations(path: Path) -> dict[RallyKey, TerminalEventAnnotation]:
    """Parse a terminal-event annotation file into a ``RallyKey -> annotation`` map.

    Args:
        path: Path to the annotation JSON file.

    Returns:
        Mapping of ``(video_path, rally_index)`` to the parsed annotation.  A
        later duplicate for the same key overrides an earlier one.

    Raises:
        SideMetricsError: If the file is missing/malformed, an entry lacks a
            ``video_path`` or ``rally_index``, or ``terminal_event_side`` is not
            one of ``"near" | "far" | "unknown"``.
    """
    data = _load_json_object(path)

    raw_annotations = data.get("annotations")
    if not isinstance(raw_annotations, list):
        raise SideMetricsError(
            f"Terminal-event file '{path}' must contain an 'annotations' list."
        )

    result: dict[RallyKey, TerminalEventAnnotation] = {}
    for position, raw in enumerate(raw_annotations):
        if not isinstance(raw, dict):
            raise SideMetricsError(
                f"Terminal-event file '{path}' annotation #{position} must be an object."
            )

        video_path = raw.get("video_path")
        if not isinstance(video_path, str) or not video_path.strip():
            raise SideMetricsError(
                f"Terminal-event file '{path}' annotation #{position} is missing "
                "a non-empty 'video_path'."
            )

        rally_index = raw.get("rally_index")
        if not isinstance(rally_index, int) or isinstance(rally_index, bool):
            raise SideMetricsError(
                f"Terminal-event file '{path}' annotation #{position} is missing "
                "an integer 'rally_index'."
            )

        side = raw.get("terminal_event_side")
        if side not in _VALID_SIDES:
            raise SideMetricsError(
                f"Terminal-event file '{path}' annotation #{position} has invalid "
                f"'terminal_event_side' {side!r}; expected one of {sorted(_VALID_SIDES)}."
            )

        team_value = raw.get("terminal_event_team")
        team: int | None
        if isinstance(team_value, int) and not isinstance(team_value, bool):
            team = team_value
        else:
            team = None

        event_type = raw.get("event_type")
        event_type_str = event_type if isinstance(event_type, str) else None
        confidence = raw.get("confidence")
        confidence_str = confidence if isinstance(confidence, str) else None

        annotation = TerminalEventAnnotation(
            video_path=video_path.strip(),
            rally_index=rally_index,
            terminal_event_side=side,
            terminal_event_team=team,
            event_type=event_type_str,
            confidence=confidence_str,
        )
        result[annotation.key] = annotation

    return result


def load_side_map(path: Path) -> dict[RallyKey, int]:
    """Parse a side-map file into a per-rally ``RallyKey -> camera_near_team`` map.

    Only the per-rally ``"rallies"`` block is consumed here: segment-level
    mapping needs a rally timestamp to resolve and is intentionally left to a
    higher layer.  Per-rally mapping is the safest unit and overrides segment
    mapping per the side-map design.

    Args:
        path: Path to the side-map JSON file.

    Returns:
        Mapping of ``(video_path, rally_index)`` to ``camera_near_team`` (0 or 1).

    Raises:
        SideMetricsError: If the file is missing/malformed, or a rally entry
            lacks a ``video_path`` / ``rally_index`` / ``camera_near_team``.
    """
    data = _load_json_object(path)

    raw_rallies = data.get("rallies")
    if raw_rallies is None:
        return {}
    if not isinstance(raw_rallies, list):
        raise SideMetricsError(
            f"Side-map file '{path}' 'rallies' must be a list when present."
        )

    result: dict[RallyKey, int] = {}
    for position, raw in enumerate(raw_rallies):
        if not isinstance(raw, dict):
            raise SideMetricsError(
                f"Side-map file '{path}' rally #{position} must be an object."
            )

        video_path = raw.get("video_path")
        if not isinstance(video_path, str) or not video_path.strip():
            raise SideMetricsError(
                f"Side-map file '{path}' rally #{position} is missing a "
                "non-empty 'video_path'."
            )

        rally_index = raw.get("rally_index")
        if not isinstance(rally_index, int) or isinstance(rally_index, bool):
            raise SideMetricsError(
                f"Side-map file '{path}' rally #{position} is missing an integer "
                "'rally_index'."
            )

        near_team = raw.get("camera_near_team")
        if near_team not in (0, 1):
            raise SideMetricsError(
                f"Side-map file '{path}' rally #{position} has invalid "
                f"'camera_near_team' {near_team!r}; expected 0 or 1."
            )

        result[(video_path.strip(), rally_index)] = near_team

    return result


# ---------------------------------------------------------------------------
# Metric computations
# ---------------------------------------------------------------------------


def compute_team_metrics(labels: list[int], preds: list[int]) -> dict[str, Any]:
    """Compute per-team accuracy, the confusion matrix, and balanced accuracy.

    These metrics are always reportable — they need no annotations.

    Args:
        labels: Ground-truth winning-team labels in ``{0, 1}``.
        preds: Predicted winning-team labels in ``{0, 1}`` (same length).

    Returns:
        Dict with overall/team accuracies, base rate, balanced accuracy, the
        2x2 confusion matrix, and per-team :class:`SideMetricBucket` summaries.

    Raises:
        SideMetricsError: When *labels* and *preds* differ in length.
    """
    if len(labels) != len(preds):
        raise SideMetricsError(
            f"labels ({len(labels)}) and preds ({len(preds)}) must be the same length."
        )

    n_total = len(labels)
    n_correct = sum(1 for label, pred in zip(labels, preds) if label == pred)

    team_buckets: dict[str, SideMetricBucket] = {}
    for team in (0, 1):
        idx = [i for i, label in enumerate(labels) if label == team]
        n_team = len(idx)
        n_team_correct = sum(1 for i in idx if preds[i] == labels[i])
        team_buckets[f"team_{team}"] = SideMetricBucket(
            name=f"team_{team}",
            n_total=n_team,
            n_correct=n_team_correct,
            accuracy=_accuracy(n_team_correct, n_team),
        )

    base_rate = (
        sum(1 for label in labels if label == 1) / n_total if n_total > 0 else None
    )

    return {
        "n_total": n_total,
        "n_correct": n_correct,
        "overall_accuracy": _accuracy(n_correct, n_total),
        "balanced_accuracy": _balanced_accuracy(labels, preds),
        "base_rate_team1": base_rate,
        "confusion_matrix": _confusion_matrix_2x2(labels, preds),
        "team_0": _bucket_to_dict(team_buckets["team_0"]),
        "team_1": _bucket_to_dict(team_buckets["team_1"]),
    }


def compute_terminal_event_side_metrics(
    labels: list[int],
    preds: list[int],
    keys: list[RallyKey],
    annotations: dict[RallyKey, TerminalEventAnnotation],
) -> dict[str, Any]:
    """Compute the **primary** near/far terminal-event-side accuracy metric.

    Each prediction is grouped by the terminal-event side of its rally (looked
    up via *keys*).  Rallies without an annotation are counted as ``unmapped``
    and excluded from the near/far/unknown buckets.

    Args:
        labels: Ground-truth winning-team labels.
        preds: Predicted winning-team labels.
        keys: Per-prediction ``(video_path, rally_index)`` keys, aligned with
            *labels* / *preds*.
        annotations: Parsed terminal-event annotations keyed by rally.

    Returns:
        Dict with near/far/unknown :class:`SideMetricBucket` summaries, the
        confusion matrix by side, balanced accuracy by side, and mapped/unmapped
        counts.  This is the only metric valid for far-side decisions.

    Raises:
        SideMetricsError: When *labels*, *preds*, and *keys* differ in length.
    """
    if not (len(labels) == len(preds) == len(keys)):
        raise SideMetricsError(
            "labels, preds, and keys must all be the same length "
            f"({len(labels)}, {len(preds)}, {len(keys)})."
        )

    side_indices: dict[str, list[int]] = {"near": [], "far": [], "unknown": []}
    n_unmapped = 0
    for i, key in enumerate(keys):
        annotation = annotations.get(key)
        if annotation is None:
            n_unmapped += 1
            continue
        side_indices[annotation.terminal_event_side].append(i)

    side_results: dict[str, Any] = {}
    for side in ("near", "far", "unknown"):
        idx = side_indices[side]
        side_labels = [labels[i] for i in idx]
        side_preds = [preds[i] for i in idx]
        n_correct = sum(1 for lab, pred in zip(side_labels, side_preds) if lab == pred)
        bucket = SideMetricBucket(
            name=side,
            n_total=len(idx),
            n_correct=n_correct,
            accuracy=_accuracy(n_correct, len(idx)),
            balanced_accuracy=_balanced_accuracy(side_labels, side_preds),
        )
        result = _bucket_to_dict(bucket)
        result["confusion_matrix"] = _confusion_matrix_2x2(side_labels, side_preds)
        side_results[side] = result

    n_mapped = len(labels) - n_unmapped
    return {
        "metric_kind": "terminal_event_side",
        "n_mapped": n_mapped,
        "n_unmapped": n_unmapped,
        "near": side_results["near"],
        "far": side_results["far"],
        "unknown": side_results["unknown"],
    }


def compute_winner_side_diagnostics(
    labels: list[int],
    preds: list[int],
    keys: list[RallyKey],
    camera_near_by_rally: dict[RallyKey, int],
) -> dict[str, Any]:
    """Compute **secondary, non-decisive** winner-side diagnostics.

    Groups predictions by whether the *winning* team was the camera-near or
    camera-far team.  This is explicitly NOT a terminal-event-side metric: a
    far-side error makes the near side win, so this view cannot answer the
    far-side visibility question.  The returned dict carries an explicit
    ``disclaimer`` so callers never present it as a far-side decision metric.

    Args:
        labels: Ground-truth winning-team labels.
        preds: Predicted winning-team labels.
        keys: Per-prediction ``(video_path, rally_index)`` keys.
        camera_near_by_rally: ``RallyKey -> camera_near_team`` side map.

    Returns:
        Dict with near-winner / far-winner accuracy buckets, mapped/unmapped
        counts, and the non-decisive disclaimer string.

    Raises:
        SideMetricsError: When *labels*, *preds*, and *keys* differ in length.
    """
    if not (len(labels) == len(preds) == len(keys)):
        raise SideMetricsError(
            "labels, preds, and keys must all be the same length "
            f"({len(labels)}, {len(preds)}, {len(keys)})."
        )

    winner_near_idx: list[int] = []
    winner_far_idx: list[int] = []
    n_unmapped = 0
    for i, key in enumerate(keys):
        near_team = camera_near_by_rally.get(key)
        if near_team is None:
            n_unmapped += 1
            continue
        # The winning team (ground truth) is near when it equals camera_near_team.
        if labels[i] == near_team:
            winner_near_idx.append(i)
        else:
            winner_far_idx.append(i)

    def _bucket(name: str, idx: list[int]) -> dict[str, Any]:
        n_correct = sum(1 for i in idx if preds[i] == labels[i])
        return _bucket_to_dict(
            SideMetricBucket(
                name=name,
                n_total=len(idx),
                n_correct=n_correct,
                accuracy=_accuracy(n_correct, len(idx)),
            )
        )

    n_mapped = len(labels) - n_unmapped
    return {
        "metric_kind": "winner_side_diagnostic",
        "disclaimer": WINNER_SIDE_DISCLAIMER,
        "n_mapped": n_mapped,
        "n_unmapped": n_unmapped,
        "winner_near": _bucket("winner_near", winner_near_idx),
        "winner_far": _bucket("winner_far", winner_far_idx),
    }


def _bucket_to_dict(bucket: SideMetricBucket) -> dict[str, Any]:
    """Convert a :class:`SideMetricBucket` to a JSON-serialisable dict."""
    return {
        "name": bucket.name,
        "n_total": bucket.n_total,
        "n_correct": bucket.n_correct,
        "accuracy": bucket.accuracy,
        "base_rate": bucket.base_rate,
        "balanced_accuracy": bucket.balanced_accuracy,
    }
