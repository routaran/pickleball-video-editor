"""Game-level score-sequence metrics for the pickleball ML pipeline.

This module evaluates rally winner predictions at the game level by replaying
predicted and ground-truth winning-team sequences through the deterministic
pickleball scorer (:class:`~src.core.score_state.ScoreState`).

**Rationale:**
Per-rally winner accuracy alone is insufficient: 90% per-rally accuracy is
compatible with ~0% of games having a fully correct score sequence because
early divergences compound.  By replaying winner sequences through the scorer
we obtain a metric that directly captures whether the pipeline would produce
the correct commentary score-string at every point during a game.

**Key observation:**
Because the score state is deterministic, the winning-team sequence fully
determines the score-string sequence given the same initial state.  Comparing
winning-team sequences element-wise is therefore sound as a primary metric,
and the score strings are included in the return payload for human inspection
and richer diagnostics (not for a second independent comparison).

Typical usage::

    from ml.evaluation.game_metrics import game_score_sequence_metrics, aggregate_game_metrics

    per_game = []
    for predicted_teams, gt_teams in game_pairs:
        m = game_score_sequence_metrics(predicted_teams, gt_teams)
        per_game.append(m)

    agg = aggregate_game_metrics(per_game)
    print(f"Exact sequence: {agg['pct_exact_sequence']:.1%}")
    print(f"Mean rally accuracy: {agg['mean_rally_winner_accuracy']:.1%}")
"""

from typing import Any

__all__ = [
    "game_score_sequence_metrics",
    "aggregate_game_metrics",
]

# Default player names used when replaying sequences through ScoreState.
# These are arbitrary and do not affect scoring; they satisfy the constructor
# requirement that player_names dicts be provided.
_SINGLES_PLAYER_NAMES: dict[str, list[str]] = {
    "team1": ["P1"],
    "team2": ["P2"],
}
_DOUBLES_PLAYER_NAMES: dict[str, list[str]] = {
    "team1": ["P1", "P2"],
    "team2": ["P3", "P4"],
}


def _replay_sequence(
    winning_teams: list[int],
    game_type: str,
    victory_rules: str,
) -> list[str]:
    """Replay a list of winning teams through a fresh ScoreState.

    The score string is captured via ``get_score_string()`` **before** applying
    each rally outcome, so the returned list has the same length as
    ``winning_teams``.

    Args:
        winning_teams: Sequence of absolute team indices (0 or 1) that won
            each rally.
        game_type: ``"singles"`` or ``"doubles"``.
        victory_rules: ``"11"``, ``"9"``, or ``"timed"``.

    Returns:
        List of score strings, one per rally, captured before the rally
        outcome was applied.
    """
    # Import is deferred here so the module remains importable without
    # the full src package on the path.  In test and CLI contexts the
    # src package is always available.
    from src.core.score_state import ScoreState

    player_names = (
        _DOUBLES_PLAYER_NAMES if game_type == "doubles" else _SINGLES_PLAYER_NAMES
    )
    state = ScoreState(game_type, victory_rules, player_names)

    score_strings: list[str] = []
    for team in winning_teams:
        score_strings.append(state.get_score_string())
        if team == state.serving_team:
            state.server_wins()
        else:
            state.receiver_wins()

    return score_strings


def game_score_sequence_metrics(
    predicted_winning_teams: list[int],
    ground_truth_winning_teams: list[int],
    game_type: str = "doubles",
    victory_rules: str = "11",
) -> dict[str, Any]:
    """Compute game-level metrics by replaying winner sequences through the scorer.

    Both sequences are replayed from the same initial state (game start).  The
    score string is captured before each rally so the sequence reflects what
    would be announced at the start of each rally.

    ``first_divergence_rally`` is the first index at which the predicted and
    ground-truth winning teams differ.  Because the scorer is deterministic,
    this is also the rally at which score strings first diverge.  It is ``None``
    when both sequences are identical up to the length of the shorter one.

    ``rally_winner_accuracy`` is computed over the overlapping prefix
    (``min(n_predicted, n_ground_truth)`` rallies).  It is ``0.0`` when either
    sequence is empty.

    ``exact_sequence`` requires identical lengths AND identical score-string
    sequences.  It implies zero divergence AND equal rally counts.

    Args:
        predicted_winning_teams: Predicted absolute team indices (0 or 1) for
            each rally.
        ground_truth_winning_teams: Ground-truth absolute team indices (0 or 1)
            for each rally.
        game_type: ``"singles"`` or ``"doubles"`` (default: ``"doubles"``).
        victory_rules: ``"11"``, ``"9"``, or ``"timed"`` (default: ``"11"``).

    Returns:
        Dictionary with the following keys:

        - ``"exact_sequence"`` — ``True`` when both sequences have the same
          length and produce identical score strings at every rally.
        - ``"first_divergence_rally"`` — zero-based index of the first rally
          where ``predicted_winning_teams[i] != ground_truth_winning_teams[i]``,
          or ``None`` if they are identical up to the length of the shorter.
        - ``"n_rallies_predicted"`` — length of ``predicted_winning_teams``.
        - ``"n_rallies_ground_truth"`` — length of ``ground_truth_winning_teams``.
        - ``"rally_winner_accuracy"`` — fraction of the overlapping prefix
          where predicted and ground-truth winning teams agree.
        - ``"predicted_score_sequence"`` — list of score strings produced by
          replaying ``predicted_winning_teams`` through a fresh scorer.
        - ``"ground_truth_score_sequence"`` — list of score strings produced by
          replaying ``ground_truth_winning_teams`` through a fresh scorer.
    """
    pred_scores = _replay_sequence(predicted_winning_teams, game_type, victory_rules)
    gt_scores = _replay_sequence(ground_truth_winning_teams, game_type, victory_rules)

    n_pred = len(predicted_winning_teams)
    n_gt = len(ground_truth_winning_teams)
    min_len = min(n_pred, n_gt)

    # First divergence: first index where winning teams differ.
    first_divergence: int | None = None
    for i in range(min_len):
        if predicted_winning_teams[i] != ground_truth_winning_teams[i]:
            first_divergence = i
            break

    # Rally-level accuracy over the overlapping prefix.
    if min_len > 0:
        n_correct = sum(
            1
            for i in range(min_len)
            if predicted_winning_teams[i] == ground_truth_winning_teams[i]
        )
        rally_winner_accuracy = n_correct / min_len
    else:
        rally_winner_accuracy = 0.0

    # Exact sequence: same length AND score strings match at every position.
    exact_sequence = n_pred == n_gt and pred_scores == gt_scores

    return {
        "exact_sequence": exact_sequence,
        "first_divergence_rally": first_divergence,
        "n_rallies_predicted": n_pred,
        "n_rallies_ground_truth": n_gt,
        "rally_winner_accuracy": rally_winner_accuracy,
        "predicted_score_sequence": pred_scores,
        "ground_truth_score_sequence": gt_scores,
    }


def aggregate_game_metrics(per_game: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-game metrics across multiple games.

    Args:
        per_game: List of per-game dicts as returned by
            :func:`game_score_sequence_metrics`.

    Returns:
        Dictionary with the following keys:

        - ``"n_games"``                  — total number of games.
        - ``"pct_exact_sequence"``       — fraction of games with
          ``exact_sequence == True`` (``0.0`` when ``n_games == 0``).
        - ``"mean_first_divergence"``    — mean ``first_divergence_rally``
          across games that diverge (``None`` when no game diverges, or
          ``None`` when ``n_games == 0``).
        - ``"mean_rally_winner_accuracy"`` — mean ``rally_winner_accuracy``
          across all games (``0.0`` when ``n_games == 0``).
    """
    n_games = len(per_game)
    if n_games == 0:
        return {
            "n_games": 0,
            "pct_exact_sequence": 0.0,
            "mean_first_divergence": None,
            "mean_rally_winner_accuracy": 0.0,
        }

    n_exact = sum(1 for g in per_game if g["exact_sequence"])
    pct_exact = n_exact / n_games

    diverging = [
        g["first_divergence_rally"]
        for g in per_game
        if g["first_divergence_rally"] is not None
    ]
    mean_first_divergence: float | None = (
        sum(diverging) / len(diverging) if diverging else None
    )

    mean_accuracy = sum(g["rally_winner_accuracy"] for g in per_game) / n_games

    return {
        "n_games": n_games,
        "pct_exact_sequence": pct_exact,
        "mean_first_divergence": mean_first_divergence,
        "mean_rally_winner_accuracy": mean_accuracy,
    }
