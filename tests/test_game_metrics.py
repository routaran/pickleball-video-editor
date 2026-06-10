"""Tests for ml.evaluation.game_metrics.

Covers:
- Identical sequences → exact_sequence True, no divergence
- Divergence at a known index
- Different-length sequences (no exact match, accuracy only over prefix)
- Accuracy math
- aggregate_game_metrics: pct_exact, mean divergence, mean accuracy
- Both singles and doubles rules (uses real ScoreState via game_metrics)
"""

from __future__ import annotations

import pytest

from ml.evaluation.game_metrics import aggregate_game_metrics, game_score_sequence_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doubles_kwargs() -> dict:
    return {"game_type": "doubles", "victory_rules": "11"}


def _singles_kwargs() -> dict:
    return {"game_type": "singles", "victory_rules": "11"}


# ---------------------------------------------------------------------------
# game_score_sequence_metrics — identical sequences
# ---------------------------------------------------------------------------


class TestIdenticalSequences:
    def test_both_empty(self) -> None:
        m = game_score_sequence_metrics([], [], **_doubles_kwargs())
        assert m["exact_sequence"] is True
        assert m["first_divergence_rally"] is None
        assert m["n_rallies_predicted"] == 0
        assert m["n_rallies_ground_truth"] == 0
        assert m["rally_winner_accuracy"] == 0.0

    def test_short_identical_doubles(self) -> None:
        # Replay: team 0 is the initial server. Serve 0 wins rally 0.
        # Exact same sequence → exact.
        seq = [0, 1, 0, 0, 1]
        m = game_score_sequence_metrics(seq, seq[:], **_doubles_kwargs())
        assert m["exact_sequence"] is True
        assert m["first_divergence_rally"] is None
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)
        assert len(m["predicted_score_sequence"]) == len(seq)
        assert len(m["ground_truth_score_sequence"]) == len(seq)
        # Score strings must be the same
        assert m["predicted_score_sequence"] == m["ground_truth_score_sequence"]

    def test_short_identical_singles(self) -> None:
        seq = [0, 0, 1, 1, 0]
        m = game_score_sequence_metrics(seq, seq[:], **_singles_kwargs())
        assert m["exact_sequence"] is True
        assert m["first_divergence_rally"] is None
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# game_score_sequence_metrics — divergence at known index
# ---------------------------------------------------------------------------


class TestDivergence:
    def test_diverges_at_index_0(self) -> None:
        pred = [1, 0, 0]  # pred says team 1 wins rally 0
        gt = [0, 0, 0]    # gt says team 0 wins rally 0
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["first_divergence_rally"] == 0
        assert m["exact_sequence"] is False

    def test_diverges_at_index_2(self) -> None:
        pred = [0, 1, 1, 0]  # differs at index 2
        gt = [0, 1, 0, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["first_divergence_rally"] == 2
        assert m["exact_sequence"] is False

    def test_diverges_at_last_index(self) -> None:
        pred = [0, 0, 1]
        gt = [0, 0, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["first_divergence_rally"] == 2

    def test_score_sequence_diverges_after_winner_divergence(self) -> None:
        """Once winning teams diverge the resulting score strings diverge."""
        pred = [0, 0, 1]  # rally 2 different
        gt = [0, 0, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        # Score strings at positions 0 and 1 must match (same history)
        assert m["predicted_score_sequence"][0] == m["ground_truth_score_sequence"][0]
        assert m["predicted_score_sequence"][1] == m["ground_truth_score_sequence"][1]
        # Score string AT position 2 still reflects state before rally 2 → same
        assert m["predicted_score_sequence"][2] == m["ground_truth_score_sequence"][2]

    def test_score_sequence_available_in_payload(self) -> None:
        seq = [0, 1, 0]
        m = game_score_sequence_metrics(seq, seq, **_doubles_kwargs())
        # Score strings must be non-empty and match known doubles start
        assert m["predicted_score_sequence"][0] == "0-0-2"
        assert m["ground_truth_score_sequence"][0] == "0-0-2"


# ---------------------------------------------------------------------------
# game_score_sequence_metrics — different lengths
# ---------------------------------------------------------------------------


class TestDifferentLengths:
    def test_predicted_shorter(self) -> None:
        pred = [0, 1]
        gt = [0, 1, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["n_rallies_predicted"] == 2
        assert m["n_rallies_ground_truth"] == 3
        assert m["exact_sequence"] is False  # different lengths
        assert m["first_divergence_rally"] is None  # prefix is identical
        # Accuracy over prefix of length 2
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)

    def test_predicted_longer(self) -> None:
        pred = [0, 1, 0, 0]
        gt = [0, 1, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["exact_sequence"] is False
        assert m["first_divergence_rally"] is None
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)

    def test_different_lengths_with_divergence(self) -> None:
        pred = [0, 1, 1]
        gt = [0, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["first_divergence_rally"] == 1
        assert m["exact_sequence"] is False


# ---------------------------------------------------------------------------
# game_score_sequence_metrics — accuracy math
# ---------------------------------------------------------------------------


class TestAccuracyMath:
    def test_all_wrong(self) -> None:
        pred = [1, 1, 1]
        gt = [0, 0, 0]
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["rally_winner_accuracy"] == pytest.approx(0.0)
        assert m["first_divergence_rally"] == 0

    def test_partial_accuracy(self) -> None:
        # 2 correct out of 4
        pred = [0, 1, 1, 0]
        gt = [0, 0, 0, 0]  # differs at indices 1 and 2
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        assert m["rally_winner_accuracy"] == pytest.approx(2 / 4)
        assert m["first_divergence_rally"] == 1

    def test_single_rally_correct(self) -> None:
        m = game_score_sequence_metrics([0], [0], **_doubles_kwargs())
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)

    def test_single_rally_wrong(self) -> None:
        m = game_score_sequence_metrics([1], [0], **_doubles_kwargs())
        assert m["rally_winner_accuracy"] == pytest.approx(0.0)
        assert m["first_divergence_rally"] == 0

    def test_accuracy_over_min_length_prefix(self) -> None:
        """When lengths differ, accuracy is computed over the shorter prefix."""
        pred = [0, 0, 0, 0]  # 4 rallies
        gt = [0, 0]           # 2 rallies (both correct)
        m = game_score_sequence_metrics(pred, gt, **_doubles_kwargs())
        # 2 correct out of min(4,2)=2
        assert m["rally_winner_accuracy"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# game_score_sequence_metrics — real ScoreState integration
# ---------------------------------------------------------------------------


class TestScoreStateIntegration:
    def test_doubles_initial_score_string(self) -> None:
        """Doubles starts at 0-0-2 per official rules."""
        m = game_score_sequence_metrics([0], [0], game_type="doubles", victory_rules="11")
        assert m["predicted_score_sequence"][0] == "0-0-2"

    def test_singles_initial_score_string(self) -> None:
        """Singles starts at 0-0."""
        m = game_score_sequence_metrics([0], [0], game_type="singles", victory_rules="11")
        assert m["predicted_score_sequence"][0] == "0-0"

    def test_server_wins_advances_score(self) -> None:
        """Server wins should increment the serving team's score."""
        # In doubles: initial serving_team=0, server_num=2.
        # Team 0 wins → score becomes 1 → next score string "1-0-2".
        m = game_score_sequence_metrics([0, 0], [0, 0], **_doubles_kwargs())
        scores = m["predicted_score_sequence"]
        assert scores[0] == "0-0-2"
        assert scores[1] == "1-0-2"

    def test_nines_victory_rules(self) -> None:
        """victory_rules='9' should not raise and must produce valid score strings."""
        seq = [0, 1, 0]
        m = game_score_sequence_metrics(seq, seq, game_type="doubles", victory_rules="9")
        assert m["exact_sequence"] is True
        assert all("-" in s for s in m["predicted_score_sequence"])


# ---------------------------------------------------------------------------
# aggregate_game_metrics
# ---------------------------------------------------------------------------


class TestAggregateGameMetrics:
    def test_empty_input(self) -> None:
        agg = aggregate_game_metrics([])
        assert agg["n_games"] == 0
        assert agg["pct_exact_sequence"] == 0.0
        assert agg["mean_first_divergence"] is None
        assert agg["mean_rally_winner_accuracy"] == 0.0

    def test_all_exact(self) -> None:
        seq = [0, 1, 0]
        per_game = [
            game_score_sequence_metrics(seq, seq, **_doubles_kwargs()),
            game_score_sequence_metrics(seq, seq, **_doubles_kwargs()),
        ]
        agg = aggregate_game_metrics(per_game)
        assert agg["n_games"] == 2
        assert agg["pct_exact_sequence"] == pytest.approx(1.0)
        assert agg["mean_first_divergence"] is None  # no diverging game
        assert agg["mean_rally_winner_accuracy"] == pytest.approx(1.0)

    def test_none_exact(self) -> None:
        pred = [0, 1]
        gt = [1, 0]  # both wrong
        per_game = [game_score_sequence_metrics(pred, gt, **_doubles_kwargs())]
        agg = aggregate_game_metrics(per_game)
        assert agg["pct_exact_sequence"] == 0.0
        assert agg["mean_first_divergence"] == pytest.approx(0.0)

    def test_partial_exact(self) -> None:
        seq = [0, 1, 0]
        # diverges at index 0 — causes score strings to diverge from position 1
        # because the initial state response differs (team 1 wins from team 0's serve
        # at 0-0-2 → immediate side-out, changing score string at pos 1)
        diverging_pred = [1, 1, 0]
        per_game = [
            game_score_sequence_metrics(seq, seq, **_doubles_kwargs()),
            game_score_sequence_metrics(diverging_pred, seq, **_doubles_kwargs()),
        ]
        agg = aggregate_game_metrics(per_game)
        assert agg["n_games"] == 2
        assert agg["pct_exact_sequence"] == pytest.approx(0.5)
        # Divergence at index 0 (only one diverging game)
        assert agg["mean_first_divergence"] == pytest.approx(0.0)

    def test_mean_accuracy_math(self) -> None:
        # Game 1: all 3 correct → acc=1.0
        # Game 2: 1 of 2 correct → acc=0.5
        seq3 = [0, 1, 0]
        pred2 = [0, 1]
        gt2 = [0, 0]  # index 1 differs
        per_game = [
            game_score_sequence_metrics(seq3, seq3, **_doubles_kwargs()),
            game_score_sequence_metrics(pred2, gt2, **_doubles_kwargs()),
        ]
        agg = aggregate_game_metrics(per_game)
        assert agg["mean_rally_winner_accuracy"] == pytest.approx((1.0 + 0.5) / 2)

    def test_mean_first_divergence_average(self) -> None:
        # Game 1 diverges at 0, game 2 diverges at 4
        g1 = game_score_sequence_metrics([1], [0], **_doubles_kwargs())
        g2_pred = [0, 0, 0, 0, 1]
        g2_gt = [0, 0, 0, 0, 0]
        g2 = game_score_sequence_metrics(g2_pred, g2_gt, **_doubles_kwargs())
        agg = aggregate_game_metrics([g1, g2])
        assert agg["mean_first_divergence"] == pytest.approx((0 + 4) / 2)

    def test_none_divergence_when_all_exact(self) -> None:
        seq = [0, 0]
        per_game = [game_score_sequence_metrics(seq, seq, **_doubles_kwargs())]
        agg = aggregate_game_metrics(per_game)
        assert agg["mean_first_divergence"] is None
