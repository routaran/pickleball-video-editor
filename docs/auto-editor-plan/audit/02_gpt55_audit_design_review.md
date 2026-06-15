## 1. Overall verdict

Your decisive metric — **video/group-wise predictive accuracy from ball-track-derived geometric features, reported with coverage** — is the right *end-to-end utility* metric for Phase 1.

But it is **not sufficient as a standalone go/no-go** on ball tracking feasibility.

It can prove a positive result: if clean geometric features predict winners cross-video with meaningful coverage and strong controls, the ball signal is real enough to justify the full tracker.

It cannot prove a negative result unless you also measure at least minimal **candidate recall / tracking quality** on real ball frames. Otherwise a failure could mean:

- the ball cue is not recoverable,
- the candidate detector missed the ball,
- the single-best tracker selected limbs/tape instead,
- the terminal window is wrong,
- the features are wrong despite the ball being present.

So: use the predictive test as the decisive **positive gate**, but add a small real-ball validation set or you risk a false negative.

---

## 2. Strengths

- **Correct abstraction:** evaluating the final useful signal — winner prediction from geometry — is better than only measuring detector aesthetics.
- **Video-wise splitting is mandatory** and you correctly included it.
- **Coverage is included**, which matches the product reality: abstention is acceptable.
- **Full-res detection before homography** is correct. Warping first would destroy the small far-side ball.
- **Caching candidates/tracks/features** is implied by your plan and is important for iteration.
- **Simple model choice is appropriate** for audit. Logistic regression / shallow trees are much safer than another high-capacity CNN failure mode.
- **Terminal-window focus is efficient**. You do not need full-rally tracking to answer the first feasibility question.

---

## 3. Problems / risks ranked by severity

### Severity 1 — A negative result would be uninterpretable without ball-ground-truth

Your current Step 4 conflates:

1. candidate detector recall,
2. tracker path selection,
3. feature extraction,
4. terminal-event interpretation,
5. actual recoverability of winner signal.

If accuracy is 55–60%, you will not know whether the approach is bad or whether your first tracker is bad.

**This is the biggest issue.**

You need at least a small validation set with real ball positions or terminal event tags. Without that, the audit can support “go” but cannot support “no-go.”

---

### Severity 1 — 150–200 rallies is too small for the decisive metric

At 40% coverage on 200 rallies, you evaluate only ~80 covered rallies.

If observed accuracy is 70%, the approximate 95% binomial CI is around:

> 70% ± 10%

That overlaps your 58.6% prior baseline.

So a 200-rally sample is acceptable for development/debugging, but **not enough for the final decision**.

For the decisive test, process as much of the 1,847-rally corpus as possible. At 40% coverage, that gives ~739 predictions. Then 70% accuracy has a CI closer to ±3–4%, which is meaningful.

---

### Severity 1 — Video-wise split may still leak through session/court/player identity

Video-wise K-fold is necessary but may not be sufficient if multiple videos share:

- same recording day,
- same court,
- same players,
- same camera setup,
- same match/session.

If train and test contain different videos from the same session/court/player group, the model may learn stable nuisance correlations.

Use the strongest grouping available:

1. leave-session/date/court out if metadata exists;
2. otherwise leave-video out;
3. additionally report leave-one-recording-date/court stress tests if possible.

The final result should not rely only on ordinary video-wise K-fold.

---

### Severity 2 — “Agent visual inspection” is not a metric

“I visually inspect 30–40 montages” is useful for debugging, but not for evidence unless a reliable human is doing the inspection.

If this is literally an autonomous AI agent looking at overlays, treat it as non-decisive. It can catch obvious bugs, but it should not be part of the go/no-go evidence.

If you personally can annotate, do it. If not, say the audit is positive-only: it can justify continuing, but cannot justify abandoning ball tracking.

---

### Severity 2 — Single-best-path tracking is enough to find positives, not enough to trust negatives

A greedy or single-best tracker can easily lock onto:

- yellow clothing,
- tape,
- paddle flashes,
- limbs,
- static yellow blobs,
- MOG2 ghosts.

If the single best path fails, that does not imply the ball is absent.

For audit, you do not need the full production multi-hypothesis tracker, but you do need at least a **top-K beam / DAG tracker** so you can ask:

> “Was the true ball somewhere among plausible hypotheses?”

Recommended floor:

- keep top 20–50 candidates/frame after NMS;
- allow gaps of 1–10 frames;
- score edges by motion smoothness, speed plausibility, candidate quality, gap penalty;
- keep top K paths, e.g. K=20;
- select one label-blind best path for the predictive model;
- use top-K diagnostics for false-negative analysis.

Single-best-only is too brittle for a no-go.

---

### Severity 2 — Coverage/accuracy can be gamed accidentally

If the classifier confidence threshold is tuned on the same folds/results, accuracy-on-covered can look better than it is.

For abstention:

- define tracker-confidence coverage thresholds label-blind, or
- tune thresholds only on training folds,
- report the full accuracy-coverage curve,
- compare baselines on the **same covered subset**.

Do not compare 70% accuracy on a cherry-picked covered subset against a 58.6% whole-corpus prior unless you also compute the prior on that covered subset.

---

### Severity 2 — Feature leakage through non-geometric features

Be careful with features such as:

- track confidence,
- candidate count,
- radius,
- image-space position,
- player-box proximity,
- color score,
- motion score,
- timestamp,
- rally duration,
- score,
- server/receiver,
- video-specific calibration quality.

Some of these can encode visibility, court, player identity, camera side, or team strength.

For the decisive ball-geometry model, initially restrict to:

- canonical terminal position,
- signed distance to court lines,
- side of net,
- did-cross-net proxy,
- direction of terminal travel,
- speed/acceleration in canonical or normalized image space,
- in/out margin,
- track length/confidence only for abstention, not as a predictive feature.

Then run ablations.

---

## 4. Concrete recommendations

### A. Split the audit into development and final evaluation

Use 150–200 rallies only for development.

Then run the final frozen pipeline on all feasible rallies.

Recommended structure:

1. **Dev set:** ~200 rallies across many videos/sessions.
   - Tune detector thresholds.
   - Tune tracker gates.
   - Debug overlays.
   - Decide feature set.
2. **Final evaluation:** remaining rallies, ideally all 1,847.
   - No manual tuning after seeing final results.
   - Report grouped CV and/or lockbox result.

If possible, create a lockbox by video/session:

- 70% videos for development/CV,
- 30% videos held out once.

---

### B. Add a small real-ball annotation set if at all possible

Yes, it is worth the cost.

Minimum useful annotation:

- 30–50 rallies,
- across at least 10–15 videos,
- stratified by near/far side, duration, winner class,
- annotate 5–10 frames per rally in the terminal 2–3 seconds,
- include at least:
  - ball center when visible,
  - “not visible / occluded / out of frame,”
  - approximate terminal event frame if obvious,
  - optional terminal side/in/out if visible.

That is roughly 300–500 point labels. This is small but enough to avoid fooling yourself.

Useful metrics:

- **Candidate recall:** ball within candidate set within radius tolerance.
  - Target: ≥85–90% on visible annotated frames.
- **Top-N candidate recall:** ball in top 20 or top 50 candidates/frame.
  - Target: ≥90% top-50.
- **Single-best track precision:** selected path follows ball for meaningful segment.
  - Target for audit: ≥50–60% on annotated terminal windows.
- **Top-K track recall:** one of top K paths follows the ball.
  - Target: ≥70–80% for K=20.

If these fail, do not conclude “ball tracking infeasible.” Conclude “current detector/tracker insufficient.”

---

### C. Use stronger controls against false positives

Minimum guard set:

#### 1. Grouped split

Prefer:

- GroupKFold by session/date/court/player group if available;
- otherwise video-wise K-fold;
- additionally report leave-one-court/date stress test if possible.

#### 2. Label permutation control

Run 100+ permutations where labels are shuffled within reasonable constraints, e.g.:

- within duration buckets,
- within videos or sessions,
- preserving class balance.

The real result should be clearly outside the null distribution.

For example:

> Real covered accuracy = 72%; permutation mean = 52%, 95th percentile = 60%.

If the real result is inside the permutation distribution, it is not evidence.

#### 3. Time-shift / wrong-window control

Extract the same features from a wrong temporal window, e.g.:

- end - 6s to end - 3s,
- or a neighboring rally’s terminal window.

Accuracy should collapse toward baseline.

If wrong-window features also predict winner, you are learning nuisance correlations.

#### 4. Nuisance-only model

Train a model using only non-ball quality/context features:

- track length,
- confidence,
- number of candidates,
- mean candidate score,
- rally duration,
- video/court-derived visibility stats.

This should perform near baseline. If it performs similarly to the geometry model, your result is suspect.

#### 5. Same-covered-subset baselines

For each coverage threshold, report:

- model accuracy,
- global majority baseline on same covered set,
- fold-training majority baseline,
- per-video oracle majority baseline on same covered set,
- score/server heuristic if available.

---

### D. Report uncertainty correctly

For final decision, report:

- accuracy-on-covered,
- balanced accuracy,
- coverage,
- coverage per video/session,
- number of covered rallies,
- cluster bootstrap CI by video/session,
- accuracy-coverage curve,
- confusion matrix on covered examples.

Do not report only aggregate accuracy.

Useful go criterion:

> Proceed if, at ≥40% coverage, grouped-CV balanced accuracy is ≥70%, and the lower 95% cluster-bootstrap CI exceeds the strongest relevant baseline by ≥5 percentage points, with permutation p < 0.01.

If coverage is lower but accuracy is very high, it may still be useful:

- ≥80% accuracy at ≥25–30% coverage may justify a selective product path.

---

### E. Complexity floor for the tracker

Do not build the full production tracker yet.

But do implement a minimal top-K tracker now.

Suggested audit tracker:

```text
Detector output:
  frame_id, x, y, radius, candidate_score, color_score, motion_score, blob_score

Graph:
  nodes = candidates
  edges = candidate_i -> candidate_j if dt in [1, 10] frames and speed plausible

Edge score:
  - distance/speed plausibility
  - acceleration smoothness
  - direction consistency
  - gap penalty
  - candidate quality
  - static-distractor penalty

Output:
  top K paths per rally, K = 20
  best label-blind path
  path confidence margin = score(best) - score(second_best)
```

Use the single best path for the main predictive feature model to avoid label-driven hypothesis selection.

Use top-K for diagnostics and false-negative protection.

---

### F. Keep model complexity low

For the decisive model, prefer:

1. hand-coded physics/rule baseline,
2. regularized logistic regression,
3. shallow tree with depth ≤2–3,
4. gradient boosting only as secondary sensitivity analysis.

Avoid flexible GBDTs as the main result unless you have enough covered examples and strict nested tuning.

Feature set should be frozen before final evaluation.

---

### G. Reframe the go/no-go categories

Do not make the decision binary based only on predictive accuracy.

Use three outcomes:

#### Clear go

- geometry features beat baselines strongly,
- controls pass,
- coverage useful,
- annotation/diagnostics show the tracker is really tracking the ball.

#### Tracker-not-good-enough

- predictive result weak,
- but annotation shows candidate recall or top-K tracking is poor.

This means improve tracker, not abandon ball.

#### Ball-signal weak / deprioritize

Only conclude this if:

- candidate recall is good,
- top-K tracking is good,
- terminal geometry is correctly extracted,
- grouped predictive accuracy remains near baseline,
- controls show no hidden signal.

That is the only defensible “no-go” for ball-primary.

---

## 5. Anything overlooked

### Label semantics may cap accuracy

Verify that `winning_team` is truly aligned with canonical court side for every rally, especially if:

- teams switch ends,
- games span side changes,
- corner-click convention differs by video,
- Team1/Team2 means roster identity rather than court side.

A side-mapping bug would destroy the audit.

---

### Terminal timestamp alignment matters

Your end-2.5s to end+1.5s window may be too narrow for some rallies.

Run a development-only window sensitivity check:

- end-4s to end+1s,
- end-3s to end+1s,
- end-2s to end+1s.

Freeze one before final evaluation.

---

### Ground-plane homography is only valid near bounce/contact

Do not over-trust canonical coordinates for airborne balls. Use generous margins and avoid hard in/out calls unless the terminal point is likely near the ground.

For audit features, signed distances and side-of-net are useful; binary “out” labels may be noisy.

---

### Post-rally behavior should stay separate

Your Phase-1 question is whether **ball tracking + geometry** carries the signal. Do not mix post-rally body behavior into the decisive ball-only metric. Evaluate it separately later.

---

### Person detector may be wasted effort early

Off-the-shelf person boxes can help suppress limbs, but they can also add runtime and failure modes. Make it optional. Do not let it block the detector/tracker audit.

---

## Bottom line

Your predictive-accuracy metric is a good positive feasibility test, but it is not a valid negative test unless you add a small real-ball validation set or equivalent recall measurement. Process the 150–200 rallies for development, but run the decisive grouped evaluation on as much of the 1,847-rally corpus as possible. Implement a minimal top-K beam tracker now; single-best tracking is acceptable for proving signal exists, but too brittle for concluding it does not.
