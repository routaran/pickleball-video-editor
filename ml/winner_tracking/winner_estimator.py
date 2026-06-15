"""Complete calibrated rally-winner estimator — the shippable winner model.

Honest framing (validated across 6 independent approaches): this footage does not
contain enough reliable visual/audio signal to autonomously determine most rally
winners — every approach performs near the per-game prior (~0.59). This estimator is
therefore a **calibrated winner-suggestion + review-prioritization model**, NOT an
autonomous winner detector. It predicts EVERY rally with a confidence that honestly
exposes how weak most predictions are, so the pipeline can auto-fill only the few
high-confidence cases and route the rest to fast human review (ordered by confidence).

Signal it combines (the only things that carry any):
- **Short-rally rule** (strong, tiny coverage): rally < 3.5 s ⇒ the serving side faulted
  quickly ⇒ RECEIVER won (~0.90 precision, date-grouped Wilson [0.78, 0.96]).
- **Final-score prior** (per-game class balance): under side-out scoring the number of
  receiver-wins (side-outs) in a game equals ``N_rallies - total_points``. The known
  final score (one number the user supplies) sets the per-game majority class — which is
  Bayes-optimal for per-rally 0/1 accuracy when no per-rally signal exists (GPT-5.5).
- **Fallback** when no final score is given: short-rally suggestions only; everything
  else is a low-confidence "review-required" weak prior.

Measured (72 games / 2,676 rallies): overall 0.592, monotonically calibrated
(conf 0.50–0.60→0.556, 0.60–0.70→0.626, 0.70–0.85→0.723, 0.85–1.0→0.927).

Confidence tiers: >=0.85 high (auto-fill), 0.65–0.85 medium (suggested, confirm),
<0.65 review-required weak prior. ``winner`` (server/receiver) maps to ``winning_team``
via the deterministically-tracked serving team.
"""

from dataclasses import dataclass

__all__ = ["RallyPrediction", "RallyWinnerEstimator"]


@dataclass(frozen=True)
class RallyPrediction:
    winner_role: str          # "server" | "receiver"
    winning_team: int | None  # court-side team, if serving_team supplied; else None
    confidence: float         # calibrated P(correct)
    source: str               # "short_rally" | "final_score_prior" | "fallback_no_final_score"
    auto_fill: bool           # confidence >= AUTO_FILL_CONF (conservative)
    tier: str                 # "high" | "medium" | "review"


class RallyWinnerEstimator:
    SHORT_RALLY_S = 3.5
    SHORT_RALLY_CONF = 0.90
    AUTO_FILL_CONF = 0.85          # only auto-accept at/above this (conservative)
    MEDIUM_CONF = 0.65
    GLOBAL_RECEIVER_PRIOR = 0.542  # overall receiver-win rate (no-final-score fallback)

    def _tier(self, conf: float) -> tuple[str, bool]:
        if conf >= self.AUTO_FILL_CONF:
            return "high", True
        if conf >= self.MEDIUM_CONF:
            return "medium", False
        return "review", False

    def predict_game(
        self,
        durations: list[float],
        final_score: tuple[int, int] | None = None,
        serving_teams: list[int] | None = None,
    ) -> list[RallyPrediction]:
        """Predict the winner of every rally in a game.

        Args:
            durations: per-rally durations (s), in rally order.
            final_score: (team1_points, team2_points) if known — sets the per-game
                prior. None degrades to short-rally-only + weak fallback.
            serving_teams: per-rally serving team (0/1) if known (from ScoreState),
                used to map server/receiver -> winning_team.
        """
        n = len(durations)
        short = [d < self.SHORT_RALLY_S for d in durations]
        n_short = sum(short)

        resid_rate: float | None = None
        if final_score is not None and n > 0:
            total_points = max(0, int(final_score[0]) + int(final_score[1]))
            k_receiver = max(0, n - total_points)                 # side-outs in the game
            # Residual receiver rate among NON-short rallies, after crediting the
            # short rallies as receiver-wins (GPT-5.5 calibration refinement).
            exp_recv_remaining = max(0.0, k_receiver - n_short)
            n_remaining = max(1, n - n_short)
            resid_rate = min(1.0, exp_recv_remaining / n_remaining)

        preds: list[RallyPrediction] = []
        for i in range(n):
            if short[i]:
                role, conf, source = "receiver", self.SHORT_RALLY_CONF, "short_rally"
            elif resid_rate is not None:
                role = "receiver" if resid_rate >= 0.5 else "server"
                conf = max(resid_rate, 1.0 - resid_rate)
                source = "final_score_prior"
            else:
                role = "receiver" if self.GLOBAL_RECEIVER_PRIOR >= 0.5 else "server"
                conf = max(self.GLOBAL_RECEIVER_PRIOR, 1 - self.GLOBAL_RECEIVER_PRIOR)
                source = "fallback_no_final_score"
            winning_team: int | None = None
            if serving_teams is not None:
                st = serving_teams[i]
                winning_team = st if role == "server" else 1 - st
            tier, auto = self._tier(conf)
            preds.append(RallyPrediction(role, winning_team, float(conf), source, auto, tier))
        return preds
