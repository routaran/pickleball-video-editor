## 1. My read of the convergence

Yes: the convergence is strong and unfavorable.

Three independent signal families — ball appearance, ball geometry, and post-rally behavior — all collapse to roughly the same story:

- The models can often infer **which team/side is generally stronger in that video**.
- They do **not** reliably infer **who won this specific rally** in a way that transfers across dates/videos.
- Even with **oracle per-video sign**, the lift over per-video majority prior is only about **+1–4%**.
- Behavior being strongly below chance, then recoverable by sign flips, is especially diagnostic: it is learning real nuisance structure, but that structure is not stable.

So I agree with your current read: this is not “one model underfit.” This is three different probes failing in the same way.

The only reason not to stop immediately is hypothesis 2: a within-video court-side/team-label break would poison all three modalities and would not be fixed by oracle per-video sign.

## 2. The decision

Do **not** keep doing more behavior or ball engineering right now.

The responsible endgame is:

1. Run one cheap, direct end-switch / label-side consistency audit.
2. Run one quick audio audit.
3. If neither shows a real deployable signal, conclude that **fully automatic rally-winner detection from this footage/setup is not currently feasible**.

“Not feasible” here means: not product-grade, not worth further modeling effort on this corpus, and not honestly deliverable as “a model that determines who won the point” without human review.

If the end-switch bug is found, fix the side mapping and rerun the existing probes before inventing new models. If it is not found, stop.

## 3. Cheap high-value tests before concluding, ranked

### 1. Direct visual end-switch audit

Most decisive.

You do not need per-rally side GT. For each video, make a contact sheet from sampled rally starts/ends:

- early game,
- middle game,
- late game,
- especially around likely switch scores.

Use player clothing/body identity and court half. Ask: **did the same two players switch physical court ends within this video?**

Outcomes:

- If many bad videos have clear end switches and your Team1↔court-side mapping stays fixed, you found a real bug.
- If end switches are rare or already handled, hypothesis 2 mostly dies.
- If switches happen but only in a small subset, exclude/fix those and see whether the metrics materially improve.

This is better than another classifier because it directly tests the suspected failure mode.

### 2. Score/rule-driven side-switch consistency check

Use ScoreState to identify expected end-switch moments if the game format implies them.

Then check whether model sign, side-feature correlation, or prediction residuals flip near those indices.

This is useful, but less decisive than visual audit because casual games may not follow formal switching rules, and the format may vary.

### 3. Within-video changepoint test on court-side features

Take the strongest court-side feature/logit you already have and fit:

- one sign for the whole video,
- versus two signs with one changepoint.

If a two-phase sign model dramatically improves fit and the changepoint aligns with score/rally midpoint, that supports the end-switch bug.

This is more informative than plain random within-video CV. Random within-video CV can hide the issue because train/test may contain both regimes.

### 4. Blocked within-video CV

Train on early rallies, test on late rallies; then reverse.

Interpretation:

- early→late collapse with late→early collapse suggests within-video nonstationarity,
- random within-video success but blocked failure suggests sign/identity drift,
- random and blocked both poor suggests either label noise or no usable signal.

Helpful, but not decisive alone.

### 5. Quick audio audit

Audio is the only genuinely untested modality, so it deserves one cheap pass.

Do not build a large audio system. Run a small grouped-CV probe on terminal audio windows, e.g.:

- last 1–3 seconds before rally boundary,
- maybe 1 second after,
- date/video grouped split,
- compare to deployable baselines.

Continue only if audio gives either:

- meaningful grouped lift, say >5–10 points over a fair baseline, or
- high-precision abstaining behavior, e.g. >85–90% accuracy on a useful subset.

If audio also collapses to prior/nuisance, stop.

## 4. What I would deliver to the user

I would not deliver a fully automatic winner model unless the side-switch or audio test changes the evidence.

I would deliver a **human-in-the-loop rally winner review system**:

- automatic rally boundary detection,
- deterministic ScoreState validation,
- one-click confirm/flip,
- cascading score correction,
- flags for impossible/inconsistent score sequences,
- confidence-ranked review order,
- optional suggested winner,
- abstention by default when confidence is low.

I would describe the model honestly as an **assistive review tool**, not an autonomous winner detector.

A per-game stronger-side prior can be used to prefill or sort review only if clearly labeled as a prior. I would not sell majority-side prediction as winner detection; it predicts game imbalance, not rally outcome.

If the user insists on “a model,” the honest version is a calibrated abstaining model:

> returns a winner only on cases where validation shows high precision; otherwise requires human confirmation.

If no high-precision subset exists, abstain-everything is more honest than pretending 68% majority-prior behavior solves the task.

## 5. Anything you may be missing

A few things are still worth checking before the final call:

- Make sure labels mean **rally winner**, not “team that scored a point.” In pickleball side-out scoring, those differ.
- Audit a small hand-cleaned subset for boundary and label noise. Bad terminal boundaries would hurt all modalities.
- Compare against a human upper bound on short terminal clips. If humans need full context/replay/score to decide, automation from raw video is unlikely.
- Be careful with the per-video prior: it is not always deployable unless final score/class balance is known.
- Date-grouped CV has only 9 dates, so exact percentages have uncertainty, but the cross-method pattern is still compelling.

## Bottom line

Yes, the convergence makes a fully automatic rally-winner model unlikely. Stop further ball/behavior engineering and run only the cheap side-consistency audit plus a quick audio probe. If those do not reveal a fixable bug or a high-precision abstaining signal, conclude that automatic winner detection from this setup is infeasible. The valuable deliverable is the human-in-the-loop scoring/review product with calibrated suggestions, not an autonomous winner classifier.
