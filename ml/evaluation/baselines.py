"""Non-ML baseline winner predictors for the pickleball rally winner task.

Each baseline exposes a uniform interface::

    class Baseline(Protocol):
        name: str
        def predict(self, example: RallyExample) -> int: ...

The majority-class baseline additionally exposes::

        def fit(self, train_examples: list[RallyExample]) -> None: ...

These baselines are intentionally torch-free and operate on individual
:class:`~ml.examples.RallyExample` instances.  They serve as comparison
points when evaluating visual or audio models on the rally winner prediction
task.

**Score-based baselines**

The score string stored in ``score_at_start`` is always announced from the
serving team's perspective (serving_score-receiving_score[-server_num]).  The
leader/trailing-score baselines avoid using any label fields and rely only on
well-formed ``score_parts`` plus the same part-count validation already used
by label backfill.

Public API
----------
AlwaysTeam0Baseline       -- constant predictor, always returns 0
AlwaysTeam1Baseline       -- constant predictor, always returns 1
MajorityClassBaseline     -- majority winning_team from training examples
ScoreLeadBaseline         -- predicts the side currently leading in score_parts
ScoreTrailBaseline        -- predicts the side currently trailing in score_parts
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ml.examples import RallyExample


__all__ = [
    "AlwaysTeam0Baseline",
    "AlwaysTeam1Baseline",
    "MajorityClassBaseline",
    "ScoreLeadBaseline",
    "ScoreTrailBaseline",
    # Factory / catalogue (used by evaluate_winner CLI)
    "make_baselines",
    "ALL_BASELINES",
    "evaluate_baseline",
]


# ---------------------------------------------------------------------------
# Score-part-count guard (mirrors _backfill_game in backfill_winner_labels.py)
# ---------------------------------------------------------------------------

_SINGLES_PART_COUNT = 2
_DOUBLES_PART_COUNT = 3


def _is_valid_score_parts(score_parts: tuple[int, ...]) -> bool:
    """Return True when score_parts has a recognised part count (2 or 3).

    Mirrors the part-count guard in ``_backfill_game``::

        expected_parts = 2 if game_section["type"] == "singles" else 3

    Args:
        score_parts: Tuple of integer score components from a
            :class:`~ml.examples.RallyExample`.

    Returns:
        True for singles (2 parts) or doubles (3 parts); False otherwise.
    """
    return len(score_parts) in (_SINGLES_PART_COUNT, _DOUBLES_PART_COUNT)


def _score_lead_baseline(example: RallyExample) -> int:
    """Return the absolute team currently leading the rally score at start.

    When ``example.serving_team`` is available the score parts are mapped to
    absolute team indices before comparison::

        team_scores[serving_team]     = score_parts[0]  # serving team's score
        team_scores[1 - serving_team] = score_parts[1]  # receiving team's score

    Then the team with the higher absolute score is returned (ties → 0).

    When ``serving_team`` is ``None`` (legacy data without a score snapshot)
    the function falls back to a perspective-relative comparison where
    ``score_parts[0]`` is treated as team 0's score and ``score_parts[1]``
    as team 1's score.  This is only a crude reference on legacy data because
    the serving side alternates between teams across rallies.

    No ``winner`` / ``winning_team`` label fields are consulted.

    Args:
        example: A :class:`~ml.examples.RallyExample`.

    Returns:
        The absolute team index (0 or 1) currently leading, or 0 on a tie or
        unrecognised score format.
    """
    if not _is_valid_score_parts(example.score_parts):
        return 0

    serving_team = example.serving_team
    if serving_team is not None:
        team_scores: list[int] = [0, 0]
        team_scores[serving_team] = example.score_parts[0]
        team_scores[1 - serving_team] = example.score_parts[1]
        return 0 if team_scores[0] >= team_scores[1] else 1

    # Legacy path: no snapshot available; perspective-relative comparison only.
    server_score = example.score_parts[0]
    receiver_score = example.score_parts[1]
    return 0 if server_score >= receiver_score else 1


def _score_trail_baseline(example: RallyExample) -> int:
    """Return the absolute team currently trailing the rally score at start.

    When ``example.serving_team`` is available the score parts are mapped to
    absolute team indices before comparison::

        team_scores[serving_team]     = score_parts[0]  # serving team's score
        team_scores[1 - serving_team] = score_parts[1]  # receiving team's score

    Then the team with the lower absolute score is returned (ties → 0).

    When ``serving_team`` is ``None`` (legacy data without a score snapshot)
    the function falls back to a perspective-relative comparison where
    ``score_parts[0]`` is treated as team 0's score and ``score_parts[1]``
    as team 1's score.  This is only a crude reference on legacy data because
    the serving side alternates between teams across rallies.

    No ``winner`` / ``winning_team`` label fields are consulted.

    Args:
        example: A :class:`~ml.examples.RallyExample`.

    Returns:
        The absolute team index (0 or 1) currently trailing, or 0 on a tie or
        unrecognised score format.
    """
    if not _is_valid_score_parts(example.score_parts):
        return 0

    serving_team = example.serving_team
    if serving_team is not None:
        team_scores2: list[int] = [0, 0]
        team_scores2[serving_team] = example.score_parts[0]
        team_scores2[1 - serving_team] = example.score_parts[1]
        # Return the index of the team with the lower absolute score (ties → 0).
        return 1 if team_scores2[0] > team_scores2[1] else 0

    # Legacy path: no snapshot available; perspective-relative comparison only.
    server_score = example.score_parts[0]
    receiver_score = example.score_parts[1]
    return 1 if server_score > receiver_score else 0


# ---------------------------------------------------------------------------
# Baseline classes
# ---------------------------------------------------------------------------


@dataclass
class AlwaysTeam0Baseline:
    """Constant baseline: always predict team 0 as the winner.

    This is the simplest possible predictor and serves as a lower-bound
    sanity check.  Accuracy on a balanced dataset is 50 %.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "always_team_0"

    def predict(self, example: RallyExample) -> int:
        """Return 0 regardless of the example content.

        Args:
            example: A :class:`~ml.examples.RallyExample` (unused).

        Returns:
            Always 0.
        """
        return 0


@dataclass
class AlwaysTeam1Baseline:
    """Constant baseline: always predict team 1 as the winner.

    Symmetric counterpart to :class:`AlwaysTeam0Baseline`.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "always_team_1"

    def predict(self, example: RallyExample) -> int:
        """Return 1 regardless of the example content.

        Args:
            example: A :class:`~ml.examples.RallyExample` (unused).

        Returns:
            Always 1.
        """
        return 1


@dataclass
class MajorityClassBaseline:
    """Majority-class baseline: predict the most frequent winning_team in training.

    Must be fitted on training examples before calling :meth:`predict`.
    On ties (equal counts for team 0 and team 1) the baseline predicts 0.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
        majority_class: The majority class learned during :meth:`fit`.
            Defaults to 0 before fitting.
    """

    name: str = "majority_class"
    majority_class: int = field(default=0, init=False)

    def fit(self, train_examples: list[RallyExample]) -> None:
        """Learn the majority winning_team from training examples.

        Args:
            train_examples: Rally examples whose ``winning_team`` labels form the
                training distribution.  An empty list leaves :attr:`majority_class`
                at its default of 0.
        """
        if not train_examples:
            self.majority_class = 0
            return

        count_0 = sum(1 for ex in train_examples if ex.winning_team == 0)
        count_1 = len(train_examples) - count_0

        # Ties resolve to 0 (deterministic, no randomness).
        self.majority_class = 0 if count_0 >= count_1 else 1

    def predict(self, example: RallyExample) -> int:
        """Return the majority class learned during :meth:`fit`.

        Args:
            example: A :class:`~ml.examples.RallyExample` (unused; prediction is
                constant after fitting).

        Returns:
            The majority winning_team (0 or 1).
        """
        return self.majority_class


@dataclass
class ScoreLeadBaseline:
    """Baseline that predicts the absolute team currently leading at rally start.

    Uses ``example.score_parts`` together with ``example.serving_team`` to
    compute absolute team scores before comparing:

    - When ``serving_team`` is not ``None``:
      ``team_scores[serving_team] = score_parts[0]``,
      ``team_scores[1 - serving_team] = score_parts[1]``;
      predicts the team with the higher absolute score (ties → 0).
    - When ``serving_team`` is ``None`` (legacy data without a score snapshot):
      falls back to a perspective-relative comparison where ``score_parts[0]``
      is treated as team 0's score.  Accuracy on legacy data is only a crude
      reference because the serving side alternates across rallies.

    The rule is deterministic and intentionally ignores any label fields.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "score_lead"

    def predict(self, example: RallyExample) -> int:
        """Predict the absolute team currently leading in the start-of-rally score.

        The score-part-count guard confirms the example has a valid score format
        (2 parts for singles, 3 parts for doubles) before applying the rule.

        Args:
            example: A :class:`~ml.examples.RallyExample`.

        Returns:
            Absolute team index (0 or 1) with the higher score, or 0 on tie /
            malformed score formats.
        """
        return _score_lead_baseline(example)


@dataclass
class ScoreTrailBaseline:
    """Baseline that predicts the absolute team currently trailing at rally start.

    Uses ``example.score_parts`` together with ``example.serving_team`` to
    compute absolute team scores before comparing:

    - When ``serving_team`` is not ``None``:
      ``team_scores[serving_team] = score_parts[0]``,
      ``team_scores[1 - serving_team] = score_parts[1]``;
      predicts the team with the lower absolute score (ties → 0).
    - When ``serving_team`` is ``None`` (legacy data without a score snapshot):
      falls back to a perspective-relative comparison where ``score_parts[0]``
      is treated as team 0's score.  Accuracy on legacy data is only a crude
      reference because the serving side alternates across rallies.

    The rule is deterministic and intentionally ignores any label fields.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "score_trail"

    def predict(self, example: RallyExample) -> int:
        """Predict the absolute team currently trailing in the start-of-rally score.

        The score-part-count guard confirms the example has a valid score format
        (2 parts for singles, 3 parts for doubles) before applying the rule.

        Args:
            example: A :class:`~ml.examples.RallyExample`.

        Returns:
            Absolute team index (0 or 1) with the lower score, or 0 on tie /
            malformed score formats.
        """
        return _score_trail_baseline(example)


# ---------------------------------------------------------------------------
# Unified factory API (used by evaluate_winner CLI and tests)
# ---------------------------------------------------------------------------

#: Names of all built-in baselines in display order.
ALL_BASELINES: list[str] = [
    "majority_class",
    "always_team_0",
    "always_team_1",
    "score_lead",
    "score_trail",
]


def make_baselines() -> list[
    "MajorityClassBaseline | AlwaysTeam0Baseline | AlwaysTeam1Baseline "
    "| ScoreLeadBaseline | ScoreTrailBaseline"
]:
    """Return a fresh list of all built-in baseline instances.

    The :class:`MajorityClassBaseline` is included but NOT yet fitted; callers
    must call ``baseline.fit(train_examples)`` before evaluating it.

    Each call creates new instances so that fitting one set does not
    contaminate another evaluation run.

    Returns:
        List of baseline instances in the same order as :data:`ALL_BASELINES`.
    """
    return [
        MajorityClassBaseline(),
        AlwaysTeam0Baseline(),
        AlwaysTeam1Baseline(),
        ScoreLeadBaseline(),
        ScoreTrailBaseline(),
    ]


def evaluate_baseline(
    baseline: (
        "MajorityClassBaseline | AlwaysTeam0Baseline | AlwaysTeam1Baseline "
        "| ScoreLeadBaseline | ScoreTrailBaseline"
    ),
    examples: list[RallyExample],
) -> dict[str, int | float]:
    """Evaluate a **fitted** baseline on *examples*.

    Args:
        baseline: A baseline instance that has already been fitted (if it has
                  a :meth:`fit` method) or is stateless.
        examples: Examples to evaluate; may be empty.

    Returns:
        Dictionary with keys:

        - ``"n_total"``   — total number of examples evaluated.
        - ``"n_correct"`` — number of correctly predicted examples.
        - ``"n_wrong"``   — number of incorrectly predicted examples.
        - ``"accuracy"``  — fraction correct in ``[0.0, 1.0]``; ``0.0``
          when *examples* is empty.
    """
    if not examples:
        return {"n_total": 0, "n_correct": 0, "n_wrong": 0, "accuracy": 0.0}

    n_correct = sum(
        1 for ex in examples if baseline.predict(ex) == ex.winning_team
    )
    n_total = len(examples)
    n_wrong = n_total - n_correct
    accuracy = n_correct / n_total

    return {
        "n_total": n_total,
        "n_correct": n_correct,
        "n_wrong": n_wrong,
        "accuracy": accuracy,
    }
