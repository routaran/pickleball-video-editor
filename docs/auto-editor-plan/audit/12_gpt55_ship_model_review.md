## 1. Is shipping this honest?

Yes — **if you ship it as a calibrated best-effort winner suggestion model**, not as a model that visually “solves” point winners.

Be blunt with yourself: the full-coverage accuracy is essentially the per-game prior.

- Proposed model: `0.592`
- Per-game prior / majority baseline: `~0.589`

So the complete model is **not meaningfully determining winners from footage** for most rallies. Its real value is:

1. It gives a prediction for every rally.
2. It is calibrated enough to expose uncertainty honestly.
3. It has a small genuinely useful short-rally tier.
4. It integrates with review workflow better than a dead CNN.

The danger is user trust. A complete model at 59% accuracy can be worse than no model if the UI implies correctness. A user may assume “auto-filled winner” means “probably right,” but for the dominant bucket you have only `0.556` accuracy — barely better than chance.

So: shipping is honest only if low-confidence predictions are treated as **review suggestions**, not authoritative labels.

## 2. Is the design right / refine it

The design is directionally right.

### Majority-class is the right hard-label choice

Dropping count-ranking was correct for per-rally accuracy.

If the only known information is the final class balance, then predicting the majority class for every ambiguous rally is Bayes-optimal under per-rally 0/1 accuracy. A constrained assignment that forces exactly `K` receiver wins must choose specific minority/majority slots without knowing where they occurred; that naturally degrades toward random placement, which explains the `0.526`.

So:

- For **per-rally winner accuracy**: majority prediction is right.
- For **score-consistent reconstruction**: count-constrained inference may be useful, but it optimizes a different goal.

Do not mix those goals silently.

### Refine the final-score use

Instead of only global majority + hard short override, I would model it as:

- Let `K = N_rallies - total_points` receiver wins.
- Use final score to establish the per-game receiver prior.
- Use short-rally likelihood as an evidence term.
- Calibrate the resulting chosen-label confidence.

One refinement: after assigning high-probability short-rally receiver wins, recompute the residual prior for the remaining rallies. Example:

```text
remaining_receiver_rate =
  (expected_receiver_wins_total - expected_receiver_wins_short_rallies)
  / remaining_non_short_rallies
```

Then use that for non-short confidence. This may improve calibration even if it barely changes hard-label accuracy.

### Be careful with “high confidence”

`conf >= 0.65` at `0.711` accuracy is not high-confidence in a product sense. That is still almost 3 wrong out of 10.

I would call tiers something like:

- `>= 0.85`: high-confidence suggestion
- `0.65–0.85`: medium-confidence suggestion
- `< 0.65`: review-required weak prior

Your `0.85–1.00` bucket is genuinely useful, but tiny: `55 / 2676`.

## 3. Should it integrate into the pipeline replacing the dead CNN?

Yes, replace the dead CNN path — but not with a silently authoritative auto-winner.

Best integration:

- Remove or bypass the constant CNN winner model.
- Add a calibrated `winner_suggestion` component.
- Add optional `final_score` / `total_points` to `AutoEditSetup`.
- Store per-rally:
  - predicted winner: `server` / `receiver`
  - confidence
  - reason/source: `final_score_prior`, `short_rally`, `fallback_no_final_score`, etc.
- Auto-fill only above a conservative threshold.
- Route the rest to 1-click review sorted by expected error / uncertainty.

Without final score, it should degrade honestly:

- short-rally suggestions where applicable;
- everything else marked low-confidence/review-required.

Do not keep the CNN as if it contributes signal. If it is a constant classifier, leaving it in the pipeline is misleading technical debt.

## 4. How to frame it truthfully to the user

Do not say:

> “We built a model that determines who won each point.”

That overstates it.

Say something like:

> “The footage does not contain enough reliable visual/audio signal to automatically determine most rally winners. I tested multiple independent approaches, and they all perform near the game-level prior. I’m shipping the best honest model: it predicts every rally with calibrated confidence, uses the final score to set the game-level prior, detects a small class of short rallies with high reliability, and sends uncertain rallies to fast review.”

Also be explicit:

> “Most predictions are weak suggestions, not reliable automatic labels. The model is useful for triage and reducing some review effort, not for fully autonomous winner detection.”

That is the right level of honesty.

## 5. Anything missing

Main things to watch:

- Validate that the final-score formula matches the actual scoring format. Side-out scoring assumptions must be explicit.
- “One number” may not be enough unless the winning score/target is fixed and overtime cases are handled.
- Rally segmentation errors will break the final-score-derived class balance.
- Serving-team tracking errors will directly corrupt `server/receiver -> winning_team`.
- Calibration should be evaluated out-of-fold/nested, not tuned and reported on the same folds.
- If exact score consistency matters, consider a separate constrained sequence output, but do not optimize per-rally accuracy with it.
- Do not label `0.65` confidence as high-confidence for auto-acceptance.

A constrained HMM/DP using serve legality, short-rally anchors, and final score could be worth testing, but I would not expect a meaningful jump above `0.59` unless it introduces new observable signal. It may improve consistency, not true per-rally accuracy.

## Bottom line

Ship it, but ship it as a **calibrated winner-suggestion and review-prioritization model**, not as an autonomous winner detector. Replace the dead CNN because it adds no value, but make confidence and review flow central to the product behavior. The complete model is honest only if the user is told that most full-coverage predictions are weak prior-based guesses. The real deliverable is not “we solved winner detection”; it is “we proved the visual signal is insufficient and integrated the best calibrated fallback safely.”
