"""Abstaining rally-winner *suggestion* from rally dynamics (the shippable result).

Background: court-side visual/behavioral winner detection from this single-camera
footage does NOT work — three independent methods (appearance CNN, ball geometry,
post-rally behavior) all collapse to within ~4% of the per-video prior even with an
oracle per-video sign, and end-switching was ruled out as a confound.  See
``docs/auto-editor-plan/WINNER_DETECTION_FINDINGS.md``.

What DOES carry a deployable signal is rally **duration**, predicting the
court-side-INDEPENDENT ``winner`` field (server vs receiver wins): a very short
rally means the serving side faulted quickly (missed serve / return error), so the
**receiver** won.  Validated date-grouped on 1,846 labeled rallies:

    threshold   coverage   precision (receiver)   Wilson 95% CI
    < 3.0 s       1.0%          1.00               [0.83, 1.00]
    < 3.5 s       2.3%          0.905              [0.78, 0.96]   <- default
    < 4.0 s       4.3%          0.863              [0.77, 0.92]

Per-date precision is 0.80-1.00 across all 9 recording dates at T=3.5 s.

This is a HIGH-PRECISION, LOW-COVERAGE suggestion: it pre-fills the obvious
short-rally cases and ABSTAINS on everything else (≈97% of rallies), which go to the
existing 1-click human review.  It is NOT an autonomous winner classifier.

DEPLOYMENT CAVEAT: this was validated on the manually-labelled rally boundaries.
In production the duration comes from the audio boundary model, so the threshold
MUST be re-validated against the audio model's *detected* short-rally boundaries
(short rallies are exactly where boundary detection is least certain) before relying
on the auto-suggest.
"""

from dataclasses import dataclass

__all__ = ["WinnerSuggestion", "suggest_winner_role", "suggest_winning_team",
           "DEFAULT_THRESHOLD_S", "CALIBRATION"]

DEFAULT_THRESHOLD_S = 3.5

# Empirical precision of "short rally -> receiver won", date-grouped validation.
# Maps threshold (s) -> (coverage, precision, wilson_lo, wilson_hi).
CALIBRATION: dict[float, tuple[float, float, float, float]] = {
    3.0: (0.010, 1.000, 0.83, 1.00),
    3.5: (0.023, 0.905, 0.78, 0.96),
    4.0: (0.043, 0.863, 0.77, 0.92),
}


@dataclass(frozen=True)
class WinnerSuggestion:
    """A non-authoritative winner suggestion the human review confirms or flips."""

    winner_role: str | None       # "receiver" | "server" | None (abstain)
    confidence: float             # validated precision for this suggestion, or 0.0
    abstain: bool
    reason: str


def suggest_winner_role(
    duration_s: float, threshold_s: float = DEFAULT_THRESHOLD_S
) -> WinnerSuggestion:
    """Suggest the rally ``winner`` (server/receiver) from duration, or abstain.

    Only very short rallies get a suggestion ("receiver" — the serving side faulted
    quickly).  Everything else abstains to human review.
    """
    if duration_s < threshold_s:
        # Use the calibrated precision at the nearest defined threshold <= the one used.
        prec = next((CALIBRATION[t][1] for t in sorted(CALIBRATION) if duration_s < t),
                    CALIBRATION[threshold_s][1] if threshold_s in CALIBRATION else 0.86)
        return WinnerSuggestion(
            winner_role="receiver",
            confidence=float(prec),
            abstain=False,
            reason=f"short rally ({duration_s:.1f}s < {threshold_s:.1f}s): serving side "
                   f"likely faulted quickly -> receiver won",
        )
    return WinnerSuggestion(
        winner_role=None, confidence=0.0, abstain=True,
        reason=f"rally {duration_s:.1f}s >= {threshold_s:.1f}s: no deployable dynamics "
               f"signal -> defer to human review",
    )


def suggest_winning_team(
    duration_s: float, serving_team: int, threshold_s: float = DEFAULT_THRESHOLD_S
) -> tuple[int | None, float]:
    """Map a winner-role suggestion to a court-side ``winning_team`` via serving_team.

    Returns (winning_team, confidence) or (None, 0.0) when abstaining.  The pipeline
    tracks ``serving_team`` deterministically through ScoreState, so this conversion
    is exact given the role suggestion.
    """
    s = suggest_winner_role(duration_s, threshold_s)
    if s.abstain or s.winner_role is None:
        return None, 0.0
    winning_team = serving_team if s.winner_role == "server" else 1 - serving_team
    return winning_team, s.confidence
