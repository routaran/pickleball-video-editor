# Rally-Winner Detection — Findings & Shippable Result

**Date:** 2026-06-14. **Author:** Claude (autonomous), in collaboration with **GPT-5.5 (high
reasoning)** via `/gpt5-review` at every step. Full transcripts: `docs/auto-editor-plan/audit/`
(`01`–`10`). Code: `ml/winner_tracking/`. Plans: `winner-detection-consensus-plan.md`,
`winner-ball-tracking-plan.md`.

> **Verdict:** Fully automatic rally-winner detection from this single-camera footage is **not
> feasible at production-useful accuracy.** Three independent visual/behavioral methods converge to
> ≤ ~4% over the per-video prior even with an oracle per-video sign; end-switching is ruled out as a
> confound. The one **deployable** signal is rally **duration** → a high-precision suggestion on the
> ~2–4% of rallies that are very short. The honest deliverable is an **abstaining winner-suggestion
> model** on top of the existing human-in-the-loop review — not an autonomous classifier.
>
> The audio-cut (rally boundary) model is unaffected and remains good; this is only about the winner.

## The question
Determine, per rally, **which team won** — to feed the deterministic `ScoreState` engine and produce
the score overlay. Labels: 1,846 human-labeled scored rallies / 51 videos / 9 recording dates;
essentially all doubles; single roughly-fixed camera per game; 1080p60; balanced classes.

## Methods tried and the convergence (date-grouped CV)
"Oracle per-video sign" = the upper bound *if* we knew which physical side each team is on per video.

| approach | leave-date-out | leave-video-out | oracle per-video sign | per-video prior | lift |
|---|---|---|---|---|---|
| ball-appearance CNN (warped clip, prior session) | 0.51 | — | 0.598 | 0.586 | +1.2% |
| classical ball-geometry (detect→track→court rules) | 0.558 | 0.533 | 0.721 | 0.685 | +3.6% |
| classical ball-geometry + player suppression | 0.457 | 0.467 | — | — | — |
| post-rally player behavior (person boxes) | 0.370 | 0.430 | 0.690 | 0.675 | +1.5% |

**A fourth modality — audio rally-dynamics — was also tested** (2026-06-14, the loop-closer GPT-5.5
sanctioned): paddle-"pock" onset detection → hit count, **hit-count parity (who hit last)**, terminal
gap/energy, put-away strength, predicting the court-side-independent `winner` field on the **full
1,846-rally corpus**. Result: **leave-date-out 0.527, BELOW the 0.542 prior**; never beats the prior at
any coverage. So hit-count parity and terminal acoustics add **nothing** beyond the short-rally pocket
that duration already captures.

**A fifth avenue — spoken score-call recognition — was also tested and failed.** In pickleball the
server calls the score aloud before each serve, so the score is in principle *spoken* in the recording
(differencing consecutive calls → every rally winner). Ran Wav2Vec2 ASR on the pre-serve audio window
across 45 rallies / 3 videos: **0/45 windows contained any recognizable number-word, and only ~4% had
any detectable speech at all.** The score calls are not captured by the far-field camera mic (the
problem is absent/inaudible speech, not ASR weakness — a heavier model won't fix missing audio). So the
most *direct* signal — the announced score — is unrecoverable from these recordings.

**Court-seen vs court-unseen** (the recurring-venue question): with the court SEEN in training (random/
ungrouped CV), the hand-crafted features STILL sit at the prior (ball-geometry 0.548, behavior 0.425,
audio→role 0.52–0.55). The only method that ever beat chance within-court was the appearance CNN
trained+tested on the *exact same video* (63%) — useless for deployment, since you'd need labels for the
very video you're trying to label. So a per-recurring-court model is **not** a viable shortcut either.

**A sixth avenue — the final-score constraint — was also tested and failed.** In side-out scoring the
number of receiver-wins (side-outs) per game equals `N_rallies − total_points`, so the *known final
score* gives the EXACT count of each outcome per game. But knowing the count doesn't localize *which*
rallies: assigning the shortest-K rallies as receiver-wins scores 0.526 (≈ the 0.521 random-assignment
control, BELOW the 0.589 per-game majority). The count constraint just reproduces the per-game prior;
duration carries no ordering signal to place the side-outs.

**All six modalities — appearance, ball-geometry, behavior, audio-dynamics, score-call ASR, and the
final-score constraint — reach at most ~the per-video/per-game majority prior (~0.59).** The per-rally
winner is not recoverable from this footage in any form tested.** What is "predictable" is *which team is stronger this game* (the per-video class balance), not
who won a *specific* rally. The behavior model's below-chance raw score (0.370) is the per-video
structure with an inverted sign (permutation p=1.00; nuisance-only 0.495 — clean), i.e. real nuisance
structure that does not transfer. Player suppression *lowering* the ball-geometry score is the control
working: it exposed that the "signal" was largely tracks coincidentally following players.

### Why each failure is genuine, not a bug
- **Capacity/pipeline** (prior session): the CNN overfits 50 clips to 100% with real AND random labels.
- **Resolution** (prior session): a 320×704/1280px/12fps/ImageNet-norm warp still gave base-rate
  cross-video. A whole-frame global-average-pooled classifier averages a 4–21 px ball away at any
  resolution.
- **Tracker quality** (this session): overlays show the classical tracker locking onto players, not
  the ball; we cannot validate/tune it without ball ground truth (a 4–21 px ball is unjudgeable from
  downscaled stills — needs a human watching the video).
- **End-switching ruled out:** rendered early-vs-late frames per video; teams do NOT swap court ends
  within a game (casual single-game-to-11). So the once-per-video corner calibration is consistent and
  is not the cause.
- **Controls throughout:** date- and video-grouped CV, label-permutation null, nuisance-only model,
  same-covered-subset baselines, selective accuracy/coverage curves.

## The one deployable signal: rally dynamics → server/receiver
Mono audio + rally dynamics have **zero court-side information**, so they cannot predict `winning_team`
(court-side) — but they *can* predict the court-side-independent `winner` field (server vs receiver),
which the pipeline maps to `winning_team` via the deterministically-tracked serving team.

Rally **duration** vs `winner` (date-grouped, Wilson 95% CIs):

| threshold | coverage | precision (receiver wins) | Wilson CI | per-date robustness |
|---|---|---|---|---|
| < 3.0 s | 1.0% | 1.00 | [0.83, 1.00] | 3/3 dates ≥0.75 |
| **< 3.5 s** | **2.3%** | **0.905** | **[0.78, 0.96]** | 5/5 dates ≥0.75 |
| < 4.0 s | 4.3% | 0.863 | [0.77, 0.92] | 7/8 dates ≥0.75 |

A very short rally ⇒ the serving side faulted quickly (missed serve / return error) ⇒ **receiver
won**. Rallies ≥ 5 s (≈90% of the data) sit at the ~0.54 prior — no signal. The 4–5 s server-lean
pocket (0.40 receiver) is real but only ~60% precision — **not** deployable.

## Shippable deliverable — the complete winner model

`ml/winner_tracking/winner_estimator.py` (`RallyWinnerEstimator`) — a **complete, calibrated
winner-suggestion + review-prioritization model** (GPT-5.5-reviewed). It predicts the winner of
**every** rally with honest confidence, combining the only signals that carry information:
- **Short-rally rule**: rally < 3.5 s → receiver (validated ~0.90, Wilson [0.78, 0.96]).
- **Final-score prior**: side-out scoring ⇒ receiver-wins per game = `N_rallies − total_points`, so the
  known final score (one number the user enters) sets the per-game majority class — Bayes-optimal for
  per-rally accuracy when no per-rally signal exists. (Count-*ranking* was tested and dropped: 0.526 <
  majority 0.589.)
- **Fallback** (no final score): short-rally suggestions + a low-confidence weak prior → review.

Measured on 72 games / 2,676 rallies: **overall 0.592**, monotonically calibrated; tiers —
**high ≥0.85: acc 0.927 (2.1%, auto-fill)**, medium 0.65–0.85: acc 0.684 (9.2%, suggest+confirm),
review <0.65: acc 0.575 (88.7%, weak prior → human review). `winner`(server/receiver) → `winning_team`
via the tracked serving team. Tests: `tests/test_winner_estimator.py` (6 pass).

**Honest framing (do not overstate):** the footage does not contain enough reliable signal to
autonomously determine *most* rally winners — full-coverage accuracy (~0.59) is essentially the
per-game prior. This model is for **triage and review reduction**: it auto-fills only the small
high-confidence tier, suggests the medium tier, and routes the weak-prior majority to fast 1-click
review (ordered by confidence). It is NOT an autonomous winner detector.

### Integration recipe (replace the dead CNN; left un-applied per "ship as-is")
In `ml/auto_edit.py`: add optional `final_score: tuple[int,int] | None` to `AutoEditSetup`; in Stage 3,
replace the constant-classifier CNN (`predict_winners`) with
`RallyWinnerEstimator().predict_game(durations, final_score)` (role is duration/score-derived,
independent of serving_team; map to `winning_team` with the loop's current `serving_team`). Stamp
`predicted_team` / `prediction_confidence` / `source` per rally; auto-fill only `tier=="high"`; flag the
rest for review sorted by confidence. Drop the winner-checkpoint requirement (the CNN adds no signal).
Update `tests/test_auto_edit.py` accordingly. **Before production:** re-validate the 3.5 s threshold on
the audio model's *detected* durations, and confirm the scoring-format/overtime assumptions of the
`final_score → count` formula.

---

## Earlier deliverable (subsumed by the estimator)
`ml/winner_tracking/winner_dynamics.py` — a **calibrated abstaining winner-*suggestion***:
- Predicts `winner` (server/receiver) from duration; emits a suggestion ONLY on very short rallies
  (default T=3.5 s, ~90% precision), maps to `winning_team` via `serving_team`, and **abstains on
  ≈97% of rallies**, which keep going to the existing 1-click confirm/flip review.
- Honest framing: "high-precision, low-coverage winner suggestions for obvious short-rally cases, with
  abstention elsewhere." It reduces review effort on the easy cases; it does not solve the task.
- **Deployment caveat (must validate before trusting):** durations were measured on manual rally
  boundaries; in production they come from the audio boundary model. Short rallies are exactly where
  boundary detection is least certain, so re-validate the threshold on the audio model's *detected*
  boundaries.

### How to wire the suggestion into `auto_edit` (one contained change, when ready)
The pipeline currently calls the winner CNN (`predict_winners`) — a constant classifier, useless. To
use the validated dynamics suggestion instead, in `ml/auto_edit.py` Stage 3, inside the per-rally loop
(where `score_state.serving_team` is current), replace the CNN's `winning_team` with:

```python
from ml.winner_tracking.winner_dynamics import suggest_winning_team
dyn_team, dyn_conf = suggest_winning_team(end_s - start_s, score_state.serving_team)
if dyn_team is not None:                      # confident only on very short rallies
    winning_team, confidence = dyn_team, dyn_conf
# else: keep the existing (non-authoritative) value; the rally is flagged for review anyway
```

This only changes behavior for rallies < 3.5 s (the high-precision pocket); everything else still
abstains to human review exactly as today. It removes reliance on the dead CNN checkpoint for those
cases. (Left unwired here per the "ship as-is, no further winner-model work" decision; the 37
`test_auto_edit.py` tests pass with the pipeline untouched. Apply + update tests when you want it live.)

**Before trusting it in production:** re-validate the 3.5 s threshold on the audio boundary model's
*detected* rally durations (not the manual labels used here) — short rallies are where boundary
detection is least certain.

### What to ship as the product
Per GPT-5.5 and Claude consensus: the **human-in-the-loop scoring/review tool** (already built) —
automatic rally boundaries + ScoreState validation/cascade + 1-click confirm/flip + impossible-score
flags + confidence-ranked review order + the short-rally auto-suggest above. Do **not** ship any
court-side visual winner model; it does not work.

## What was NOT pursued, and why
- **Fuller audio model** (impact-onset → hit-count → who-hit-last; terminal silence): not built —
  duration already captures the obvious short-rally signal and ≥5 s rallies are at prior, so EV is low.
  Optionally do a cheap *oracle* hit-count probe later before any audio build.
- **Learned tiny-ball detector (TrackNet-style)** and **human ball-GT set (~30 rallies)**: parked.
  Only worth revisiting if the product needs higher winner coverage AND someone provides ball ground
  truth; even then the cross-video convergence is a strong prior against success on this camera setup.
- **Multi-camera / better camera placement**: the single highest-leverage *data-side* change for any
  future ball-based attempt (shrinks the 5:1 near/far perspective; far ball is ~4 px today).

## Honest bottom line
Autonomous rally-winner classification from this footage failed across three independent methods; the
evidence is strong and the failure mode is consistent. A small, high-precision, abstaining dynamics
suggestion is production-worthy and ships on top of the human review loop. The right product is an
*assistive* scorer, not an *autonomous* one.
