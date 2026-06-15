"""Tests for the complete calibrated rally-winner estimator.

The estimator is the shippable winner model: it predicts every rally with calibrated
confidence (short-rally rule + final-score per-game prior + honest fallback), and maps
server/receiver -> winning_team via the tracked serving team.
"""

from ml.winner_tracking.winner_estimator import RallyWinnerEstimator


def test_short_rally_predicts_receiver_high_confidence():
    est = RallyWinnerEstimator()
    preds = est.predict_game([2.0], final_score=None)
    assert preds[0].winner_role == "receiver"
    assert preds[0].source == "short_rally"
    assert preds[0].confidence >= est.AUTO_FILL_CONF
    assert preds[0].tier == "high" and preds[0].auto_fill is True


def test_no_final_score_long_rally_is_review_tier():
    est = RallyWinnerEstimator()
    preds = est.predict_game([9.0], final_score=None)
    assert preds[0].source == "fallback_no_final_score"
    assert preds[0].tier == "review" and preds[0].auto_fill is False


def test_final_score_sets_per_game_majority():
    est = RallyWinnerEstimator()
    # 10 rallies, final score totalling 2 points -> 8 receiver-wins (side-outs):
    # the per-game majority is "receiver".
    durs = [9.0] * 10
    preds = est.predict_game(durs, final_score=(2, 0))
    assert all(p.source == "final_score_prior" for p in preds)
    assert all(p.winner_role == "receiver" for p in preds)
    assert preds[0].confidence > 0.5

    # Inverted: 10 rallies, 9 points -> only 1 side-out -> majority "server".
    preds2 = est.predict_game(durs, final_score=(9, 0))
    assert all(p.winner_role == "server" for p in preds2)


def test_winning_team_mapping_via_serving_team():
    est = RallyWinnerEstimator()
    # short rally -> receiver; serving_team 0 -> winning_team 1; serving_team 1 -> 0
    p0 = est.predict_game([2.0], serving_teams=[0])[0]
    p1 = est.predict_game([2.0], serving_teams=[1])[0]
    assert p0.winner_role == "receiver" and p0.winning_team == 1
    assert p1.winner_role == "receiver" and p1.winning_team == 0


def test_short_rally_overrides_final_score_majority():
    est = RallyWinnerEstimator()
    # Even in a server-majority game, a very short rally is still receiver.
    preds = est.predict_game([2.0, 9.0], final_score=(9, 0))
    assert preds[0].winner_role == "receiver" and preds[0].source == "short_rally"
    assert preds[1].winner_role == "server"


def test_confidence_tiers_are_monotonic():
    est = RallyWinnerEstimator()
    assert est._tier(0.90) == ("high", True)
    assert est._tier(0.70) == ("medium", False)
    assert est._tier(0.55) == ("review", False)
