"""Review priority scoring for winner-prediction uncertainty triage.

Assigns a human-review priority level to a single rally based on how
uncertain the winner classifier was about its prediction.  Uncertain
predictions — those whose softmax confidence is low, or whose winning
margin over the competing class is narrow — are escalated for human
review so editors can verify or correct them before score simulation
runs.

Public API
----------
review_priority(confidence, margin) -> str

Returned levels
---------------
"high"   – editor should review before accepting the prediction
"medium" – borderline; review recommended but not critical
"low"    – model is confident; safe to accept automatically

Threshold constants (module-level, tune without code changes)
-------------------------------------------------------------
CONFIDENCE_HIGH_THRESHOLD   float  Confidence at or below this value -> "high"
CONFIDENCE_MEDIUM_THRESHOLD float  Confidence at or below this value -> "medium"
MARGIN_HIGH_THRESHOLD       float  Margin at or below this value -> "high"
MARGIN_MEDIUM_THRESHOLD     float  Margin at or below this value -> "medium"

Decision logic (both confidence and margin are considered)
----------------------------------------------------------
The function promotes a rally to the most severe level triggered by
either input.  A rally is "high" if confidence <= CONFIDENCE_HIGH_THRESHOLD
OR margin (when provided) <= MARGIN_HIGH_THRESHOLD, and so on.  This
ensures that a model whose softmax is artificially concentrated (high
confidence, low margin) is still caught by the margin gate, and vice
versa.

Typical values with WinnerModelConfig.confidence_threshold = 0.70
------------------------------------------------------------------
confidence=0.95, margin=0.90  -> "low"
confidence=0.75, margin=0.55  -> "medium"
confidence=0.52, margin=0.04  -> "high"
"""

from typing import Literal


__all__ = [
    "review_priority",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    "MARGIN_HIGH_THRESHOLD",
    "MARGIN_MEDIUM_THRESHOLD",
    "Priority",
]


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

# Confidence thresholds (softmax probability of the predicted class).
# A model that outputs 0.55 for its top class is barely better than a
# coin flip; anything at or below 0.60 warrants mandatory review.
CONFIDENCE_HIGH_THRESHOLD: float = 0.60
CONFIDENCE_MEDIUM_THRESHOLD: float = 0.75

# Margin thresholds (|p_winner - p_loser| == 2*p_winner - 1 for binary).
# A margin of 0.10 means the winner class was only 5 pp ahead; anything
# at or below 0.15 is effectively ambiguous.
MARGIN_HIGH_THRESHOLD: float = 0.15
MARGIN_MEDIUM_THRESHOLD: float = 0.40


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Priority = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def review_priority(
    confidence: float,
    margin: float | None = None,
) -> Priority:
    """Return a human-review priority for a single winner prediction.

    Parameters
    ----------
    confidence:
        Softmax probability of the predicted (winning) class.  Must be in
        [0.0, 1.0].  This is the single most important uncertainty signal:
        values near 0.5 indicate the model is barely guessing.
    margin:
        Optional absolute difference between the predicted-class probability
        and the runner-up probability (|p_winner - p_other|).  For a binary
        classifier this equals 2*confidence - 1, but callers may supply the
        raw value from multi-class output.  Must be in [0.0, 1.0] when
        provided.  When omitted the margin gate is skipped and only
        confidence is used.

    Returns
    -------
    Priority
        "high"   – confidence or margin signals high uncertainty
        "medium" – moderate uncertainty; borderline case
        "low"    – model is confident on both axes

    Raises
    ------
    ValueError
        If confidence is outside [0.0, 1.0] or margin (when provided) is
        outside [0.0, 1.0].  Invalid inputs indicate a caller bug and must
        not silently produce a misleading priority.
    """
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(
            f"confidence must be in [0.0, 1.0], got {confidence!r}"
        )
    if margin is not None and not (0.0 <= margin <= 1.0):
        raise ValueError(
            f"margin must be in [0.0, 1.0], got {margin!r}"
        )

    # Promote to "high" if either signal crosses the high-uncertainty gate.
    if confidence <= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if margin is not None and margin <= MARGIN_HIGH_THRESHOLD:
        return "high"

    # Promote to "medium" if either signal crosses the medium-uncertainty gate.
    if confidence <= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    if margin is not None and margin <= MARGIN_MEDIUM_THRESHOLD:
        return "medium"

    return "low"
