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

**Serving-team derivation**

The score string stored in ``score_at_start`` is always announced from the
serving team's perspective (serving_score-receiving_score[-server_num]).
Because ``RallyExample`` does not carry the absolute serving-team index (0 or 1)
without replaying the full game sequence, the serving/receiving baselines use
the ``winner`` field (``"server"`` or ``"receiver"``) together with the
score-part-count guard (2 parts = singles, 3 parts = doubles) from
``ml.tools.backfill_winner_labels._backfill_game``.  Team 0 is treated as the
serving team when no further context is available; this assumption is correct
for the first rally of every game and degrades gracefully for later rallies.

The score-part-count guard is replicated exactly as in ``_backfill_game``::

    expected_parts = 2 if game_type == "singles" else 3

so singles and doubles examples are both handled correctly.

Public API
----------
AlwaysTeam0Baseline       -- constant predictor, always returns 0
AlwaysTeam1Baseline       -- constant predictor, always returns 1
MajorityClassBaseline     -- majority winning_team from training examples
ServingTeamWinsBaseline   -- predict team 0 when server wins, team 1 otherwise
ReceivingTeamWinsBaseline -- predict team 1 when receiver wins, team 0 otherwise
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ml.examples import RallyExample


__all__ = [
    "AlwaysTeam0Baseline",
    "AlwaysTeam1Baseline",
    "MajorityClassBaseline",
    "ServingTeamWinsBaseline",
    "ReceivingTeamWinsBaseline",
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


def _serving_team_wins(example: RallyExample) -> int:
    """Return the predicted winning_team under the "server wins" assumption.

    The score string is from the serving team's perspective.  Without replaying
    the full game sequence the absolute serving-team index (0 or 1) cannot be
    known from a single example.  This function treats team 0 as the serving
    team (valid for the first rally of every game) and uses the score-part-count
    guard to confirm the score format is valid before applying the rule.

    If the score format is unrecognised (neither 2 nor 3 parts) the function
    falls back to returning 0.

    Args:
        example: A :class:`~ml.examples.RallyExample`.

    Returns:
        0 if ``example.winner == "server"`` and the score is valid, 1 otherwise.
        Falls back to 0 for unrecognised score formats.
    """
    if not _is_valid_score_parts(example.score_parts):
        return 0

    # Server wins → predict team 0 (serving team by convention).
    # Receiver wins → predict team 1 (receiving team by convention).
    return 0 if example.winner == "server" else 1


def _receiving_team_wins(example: RallyExample) -> int:
    """Return the predicted winning_team under the "receiver wins" assumption.

    The inverse of :func:`_serving_team_wins`: always predicts that the
    receiving team wins.  Uses the same score-part-count guard and team-0-serves
    convention.

    Args:
        example: A :class:`~ml.examples.RallyExample`.

    Returns:
        1 if ``example.winner == "receiver"`` and the score is valid, 0 otherwise.
        Falls back to 0 for unrecognised score formats.
    """
    if not _is_valid_score_parts(example.score_parts):
        return 0

    # Receiver wins → predict team 1 (receiving team by convention).
    # Server wins → predict team 0 (serving team by convention).
    return 1 if example.winner == "receiver" else 0


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
class ServingTeamWinsBaseline:
    """Baseline that predicts the serving team wins every rally.

    Uses the score-part-count guard (2 parts = singles, 3 parts = doubles) to
    confirm the score format is valid, then predicts team 0 as the winner when
    the rally ``winner`` field is ``"server"`` and team 1 when it is
    ``"receiver"``.

    Team 0 is treated as the serving team by convention — this is accurate for
    the first rally of every game.  The baseline degrades gracefully for later
    rallies where team 1 may be serving, making it a meaningful (though
    imperfect) upper bound for rule-based serving-team inference.

    The score-part-count guard is replicated from
    ``ml.tools.backfill_winner_labels._backfill_game`` precisely::

        expected_parts = 2 if game_type == "singles" else 3

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "serving_team_wins"

    def predict(self, example: RallyExample) -> int:
        """Predict team 0 if the server won, team 1 if the receiver won.

        The score-part-count guard confirms the example has a valid score format
        (2 parts for singles, 3 parts for doubles) before applying the rule.
        Falls back to 0 for malformed or empty ``score_parts``.

        Args:
            example: A :class:`~ml.examples.RallyExample`.

        Returns:
            0 when ``example.winner == "server"`` (server = team 0 by convention).
            1 when ``example.winner == "receiver"`` (receiver = team 1).
            0 as a fallback for unrecognised score formats.
        """
        return _serving_team_wins(example)


@dataclass
class ReceivingTeamWinsBaseline:
    """Baseline that predicts the receiving team wins every rally.

    The inverse of :class:`ServingTeamWinsBaseline`: predicts team 1 as the
    winner when the rally ``winner`` field is ``"receiver"`` and team 0 when it
    is ``"server"``.  Uses the same score-part-count guard.

    Attributes:
        name: Human-readable identifier used in evaluation reports.
    """

    name: str = "receiving_team_wins"

    def predict(self, example: RallyExample) -> int:
        """Predict team 1 if the receiver won, team 0 if the server won.

        The score-part-count guard confirms the example has a valid score format
        before applying the rule.  Falls back to 0 for unrecognised score formats.

        Args:
            example: A :class:`~ml.examples.RallyExample`.

        Returns:
            1 when ``example.winner == "receiver"`` (receiver = team 1 by convention).
            0 when ``example.winner == "server"`` (server = team 0).
            0 as a fallback for unrecognised score formats.
        """
        return _receiving_team_wins(example)


# ---------------------------------------------------------------------------
# Unified factory API (used by evaluate_winner CLI and tests)
# ---------------------------------------------------------------------------

#: Names of all built-in baselines in display order.
ALL_BASELINES: list[str] = [
    "majority_class",
    "always_team_0",
    "always_team_1",
    "serving_team_wins",
    "receiving_team_wins",
]


def make_baselines() -> list[
    "MajorityClassBaseline | AlwaysTeam0Baseline | AlwaysTeam1Baseline "
    "| ServingTeamWinsBaseline | ReceivingTeamWinsBaseline"
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
        ServingTeamWinsBaseline(),
        ReceivingTeamWinsBaseline(),
    ]


def evaluate_baseline(
    baseline: (
        "MajorityClassBaseline | AlwaysTeam0Baseline | AlwaysTeam1Baseline "
        "| ServingTeamWinsBaseline | ReceivingTeamWinsBaseline"
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
