# Visual Subsystem Rebuild — Implementation Plan (converged)

> **Working plan — not committed.** Supersedes the "defer the heavy visual build" posture
> in `RICH_VISUAL_SIGNAL_HANDOFF.md`. Reflects the user's mandate (explicit-reconstruction
> backbone, cheap signals first, capability over time-to-build) **as refined by two rounds
> of GPT-5.5 adversarial review** (briefings + responses in
> `$CLAUDE_JOB_DIR/tmp/gpt5-visual-rebuild/round{1,2}_*.md`).
>
> **What the review changed (important):** the original plan was a clean layered perception
> stack (pose → events → fusion → gated ball tracking) whose scoring path would have spent
> months re-discovering the 0.59 wall before attempting line calls that may be *physically
> impossible* on this footage. The converged plan splits into two tracks and **leads with a
> different, stronger software-only scoring lever** that bypasses the fidelity wall: inferring
> the players' **official scoring decisions** from **pre-serve service state**, tied together
> by the **known final score + serve-rotation rules** in a constrained sequence model. Rich
> perception (pose/ball) is retained for analytics, residual disambiguation, and to measure
> the hard line-call ceiling — not as the scoring backbone.
>
> ### 2026-06-22 CORRECTION — the "4px ball / unresolvable line call" premise was FALSE (downscaling artifact)
> Measured the ball myself on **lossless full 1920×1080 frames, no scale filter** (script +
> frames in `$CLAUDE_JOB_DIR/tmp/ballframes/`): the ball is **~10 px** in normal play
> (9–14 px mid-court across 16 consecutive frames; ~10 px on a deep/far shot at y≈380, viewed
> at 8× zoom — a clean bright disk against a dark wall). The prior "**far ball ≈ 4 px / line
> ≈ 2.7 px / sub-pixel**" figures — and GPT-5.5 round-1's physics math built on them — are
> **artifacts of the legacy pipelines downscaling the source**: a 10 px native ball becomes
> 6.7 px at the ≤1280 extraction, **3.3 px at the 640 px winner-clip extraction (≈ "4 px far")**,
> and **1.3 px in the 256-wide top-down warp (≈ "2 px / sub-pixel")**. The ball was never that
> small in the footage. **Consequences:** (a) the "single-camera line calls may be physically
> impossible" ceiling is **RETRACTED** — the ball is plainly visible and trackable; (b) **explicit
> native-res ball tracking was never actually tested** (every prior "fidelity wall" result ran on
> downscaled/warped pixels) and is **re-elevated to a primary path**, not a gated last resort;
> (c) new **hard constraint**: anything touching the ball/terminal event runs at **native
> resolution — no downscaling, ever** (§6). The residual hard problem is *bounce localization*
> (sub-frame timing + occlusion + far-line homography precision), not ball *visibility*.

---

## 0. Framing: two tracks + a capture fork

The hard goal (auto-scoring) and the user's secondary goals (per-shot reconstruction, player
kinematics) are **not the same observability problem** and should not share one pipeline.

- **Track A — Score reconstruction (primary, cheap, software-only).** Don't try to see the
  ball land. Read the **scoreboard transition** from how the players line up for the next
  serve, and tie rallies together with the known final score + side-out serve rules. This
  recovers the *official* score progression and sidesteps invisible far-side line calls. This
  is the strongest path for the **irreplaceable 219 GB backlog**.
- **Track B — Rich perception (analytics, residual, ceiling).** Native-res pose + stable
  identity + shot events + (gated) ball tracking. Delivers the per-shot reconstruction and
  kinematics the user wants, disambiguates the rallies Track A is uncertain about, and
  **quantifies the line-call ceiling** for visual scoring. NB: the ball is ~10 px and clearly
  trackable at native res (see correction above), so this is now a path with real ceiling, not a
  known dead end; the open question is *bounce-localization* precision, not visibility.
- **Capture fork (going forward).** The backlog can't be re-shot, but new sessions could add a
  ~$50 second phone (a second *angle* mainly helps with occlusion and far-line homography, less
  so visibility now) and a ~$30 lav mic (revives score-call ASR). Lower priority than first
  thought given the ball is already visible, but cheap optionality. A decision for the user (§7).

Both tracks are **feasibility-gated first** with concrete decision rules, and both **abstain
+ defer to the existing human-in-the-loop scorer** rather than guessing.

---

## 1. What we are replacing, and the wall we must respect

Old visual path = YOLOv8n + ByteTrack @ 10 fps, ≤1280 px → **player foot-points** on a court
plane. It ships the **rally detector** (audio+visual fusion, LOSO interval F1 ≈ 0.75) — that
**stays**. What it cannot do is scoring.

### Settled empirically — do NOT re-attempt (see `project_winner_model_diagnosis`)
- Top-down court-warp winner CNN → **dead at every resolution** (zero cross-court transfer).
- Cheap winner from foot-position + audio → **chance** under LOSO.
- Classical-CV ball tracking (color/motion heuristics) → **clutter-dominated** (needs a
  *learned* multi-frame model — NOT a resolution problem; the ball is ~10 px and visible).
- Player *speed* as a feature → **anti-signal**. Score-call ASR on the **far-field mic** →
  ~4 % speech captured (a *mic* problem, not an ASR problem — revisit with a closer mic).
- Random splits → **always LOSO** by `YYYYMMDD` session prefix.

**The diagnosis that drives this plan:** the rally winner is decided by a **terminal ball
event (in/out/net)** that the *coarse downscaled foot-point* features can't encode. The ball
itself **is plainly visible (~10 px native, trackable)** — the prior "sub-resolvable" claim was
a downscaling artifact (see correction at top). The residual hardness is **bounce localization**
(sub-frame timing — the ball moves ~15–30 px between 30 fps frames — plus occlusion and far-line
homography precision), not ball visibility. Two complementary responses: **Track A** sidesteps
the bounce entirely by reading the *consequence* (the next serve's score state); **Track B**
attacks the bounce directly with native-res learned ball tracking (now a primary path).

---

## 2. Track A — Service-state → constrained score reconstruction (PRIMARY)

### 2.1 The idea
Pickleball side-out doubles makes the pre-serve tableau a near-deterministic readout of the
hidden score:
- **Server court half encodes parity**: the serving player stands on the even/right court when
  the serving team's score is even, odd/left when odd. This is a **gross whole-body cue at the
  baseline** (tens of px even far-side) — cheaper still than the ~10 px ball, and free of any
  bounce-timing problem.
- **Transitions between consecutive serves reveal the previous rally's outcome**:
  same team + parity flip → server won; same team + parity unchanged → first-server fault
  (receiver won); serving team changes → side-out (receiver won). The final rally is pinned by
  the **known final score** boundary.

This recovers the **official scoring decision**, which is exactly what the rule engine needs —
and it is invariant to whether anyone (human or model) could actually see the ball land.

### 2.2 Why this is uniquely well-positioned here (an asset the review didn't know)
`score_at_start` ("Sscore-Rscore-serverNum") + `winner` are **labeled on 100 % of rallies**. So
the service-state detector is **fully supervised with labels we already have** — no scratch
labeling — and the HMM is **directly validatable** against known score sequences under LOSO.

**Truth is derived directly from labels, NOT from a serve-order seed** (round-3 fix — avoids
circularity): per rally `serving_team = winning_team if winner=="server" else 1-winning_team`;
`serving_score, server_number = score_at_start.split("-")[0], [2]`; `expected_parity =
serving_score % 2`. The shipped `ScoreState` (`src/core/score_state.py`) is used only as a
**consistency audit** (replay both possible initial-server seeds; flag mismatches), never as the
source of truth.

**Court-half mapping is side-dependent and MUST flip for the far team** (round-3 fix — a single
sign error tanks the probe; needs a deterministic unit test). With canonical x = image-left→right:
near/bottom team → even/right = image-right; **far/top team → even/right = image-LEFT** (they
face the opposite way). Evaluate near-side and far-side metrics **separately**.

**Evaluate both physical sides independently, then compare the labeled serving side** — do NOT
use the labeled serving team to *select* which side to read, or the probe looks artificially
easier than real inference (round-3 fix).

### 2.3 Honest limits (from the review — design for them)
- **Final score + serve rules alone do NOT identify the sequence** (an 11–7 game has
  millions+ of legal paths). They are a *prior*; the per-rally observations must do the work.
- **Coverage compounds**: at 80 % per-rally observation only 0.8² = 64 % of *adjacent
  transitions* are doubly-constrained; ~90 % coverage + ~95 % precision is the "genuinely
  strong" regime. Measure before trusting.
- **Brittle to rally-segmentation errors**: one missing/extra/ replay rally shifts the whole
  chain into a "beautifully legal but wrong" path. Needs explicit null/replay states, top-k
  paths, posterior confidence, abstention, and manual-correction hooks.
- **Recovers official, not objective, score**: players mis-score / correct verbally / the
  user mis-enters the final score. Final score = strong boundary, **not** unquestionable; the
  model must be able to say "no high-probability legal path fits."
- **Circularity is manageable**: court-half is read from calibration + serving team + server
  location (no score needed); the HMM predicts expected parity, the detector emits a
  likelihood — standard HMM emission.
- **#1 RESIDUAL RISK = pre-serve server *identity*** (no longer ball visibility). Doubles
  **stacking** does not break the parity rule but breaks "baseline-most player = server"; far-
  side perspective + occlusion compound it. Mitigations: multiple pre-serve frames + median,
  foot/bbox-bottom (not bbox-center), require margin from centerline, **abstain** when two
  same-side players are close/overlapping. False-confident parity is the danger; low coverage is
  fine early.
- **Mid-game side switches are a DATA-QUALITY GATE, not an architecture problem** (round-3 — the
  hardest under-specified risk). `Team1 = far` holds only at video start; if players switch ends
  the absolute-team→physical-side map breaks. First increment: log the physical side per rally,
  detect switches, segment or abstain past a switch — do not bury it in code.

### 2.4 The model
- **State**: `(score_a, score_b, serving_team, server_number, [server_identity])`.
- **Transitions**: side-out doubles rules (incl. first-server exception, win-by-2, singles
  variant, timeouts/side-switches) as a constrained Markov chain.
- **Emissions** (per rally, all probabilistic + abstaining): server court-half/parity
  (primary), rally duration (short→receiver tail, already validated 0.90 P@2 %), last-hitter
  side, optional terminal-event confidence (from Track B), **optional re-checked score-call
  audio** (see §5).
- **Boundary**: known final score (soft).
- **Inference**: constrained Viterbi → best path + top-k + posterior; ambiguous spans → review.

---

## 3. Track B — Rich perception (analytics, residual disambiguation, ceiling)

A layered, native-res perception stack. Serves the user's per-shot-reconstruction and
kinematics goals, feeds optional emissions into Track A, and measures the line-call ceiling.

```
native 1080p → L0 decode + dedup (fake-60fps → real ~30fps)
                 ├─ L1 player pose + court-quadrant identity (4 players, 17 kpts)
                 ├─ L2 shot events (audio pock × pose-velocity → shots[], last-hitter, serve)
                 └─ L3 ball / terminal-event (GATED — feasibility-first; see §4)
                         → L4 analytics + residual-rally disambiguation head (abstains)
```

- **L0–L2** are cheap, mostly model-assisted, and independently useful. They are **not** the
  scoring gate (the kill-list already showed cheap visual signals don't transfer for winner).
- **L3 ball** runs at **native resolution (no downscaling — the ~10 px ball is the whole point;
  see correction at top)** and is a **primary path**, not a gated last resort. It is approached
  first as a **terminal-event** problem (the ±2 s window that decides the point) before full-
  rally tracking. Tooling is benchmarked, **not pre-committed**: TrackNet-style heatmap **vs**
  point trackers (CoTracker3 / TAPIR) **vs** temporal-difference / motion-tube accumulation /
  matched spatio-temporal filters, with **self-supervised pretraining on the 219 GB** of same-
  court footage to attack the cross-court transfer failure. The residual hard problem is
  *bounce localization* (sub-frame timing, occlusion, far-line homography), not visibility.
- The rich **scene cache** (versioned, model-version-stamped) stores structured outputs
  (keypoints, shots, sparse ball points) — not pixels; the 219 GB source is untouched.

### Scene cache schema (Track B artifact)
```
SceneCache (per video, per rally; versioned)
  meta:    { video, fps_analysis, dedup_map, schema_version, model_versions{...} }
  players[4]: { keypoints (T,17,3), court_xy (T,2), present (T,) }   # stable quadrant role
  shots[]:    { t_seconds, player_id, is_serve, audio_conf }
  audio:      { onsets[], mel_summary }
  ball:       (L3, gated) { xy (T,2), visible (T,), traj_fit }
  labels:     (optional human) { winner, last_hitter, end_reason, shots[].type, ball[] }
```

---

## 4. Feasibility-first sequencing (the gate is split and front-loaded)

Run the two feasibility probes **in parallel, first**. Do not build either full stack until its
probe passes.

### Phase 0 — Labelability / observability audit (cheap, human-only, ~1 week)
Stratified sample (~20–30 games, 200–500 rallies; near/far, clean/messy, occluded, multiple
days/players). For each rally, a human records: rally boundary quality; **serving team +
server court-half labelable? (Track A gate)**; terminal outcome human-visible? near/far/
baseline/sideline/occluded (Track B ceiling); score transition known.
**Decision rules:**
- Track A proceeds if humans can label serving-team + court-half on ≥90–95 % of clean-game
  rallies (≥80–85 % overall backlog). *If a human can't read it, the model won't.*
- Track B ceiling = the measured fraction of terminal events a human can call from native-res
  frames (the ball is visible at ~10 px; the question is whether the *bounce in/out* is callable
  given sub-frame timing + occlusion). Whatever a human can't call is declared **out of scope**
  (abstain → human), explicitly — but do NOT pre-assume far-side is impossible; measure it.

### Phase 1 — Two prototype probes in parallel
- **1A Service-state detector** (Track A): homography + player tracks + pre-serve frame
  sampling → serving-team + court-half/parity classifier with calibrated confidence.
  **Supervised by the existing `score_at_start` labels.** Pass: held-out (LOSO) high-confidence
  precision ≥92–95 % at ≥75–85 % coverage. If ~80–85 % precision, it is **not** a scoring
  backbone — demote to an assist.
- **1B Terminal-event feasibility** (Track B): terminal-window labeling only (±2 s around rally
  end, the 200–500 clips), benchmark the candidate ball/event methods on **terminal-event
  coverage**, not full-rally tracking. Pass: a stratum where ball-based winner recovery clears
  ≥95 % precision at ≥30 % coverage of currently-manual rallies.

### Phase 2 — Constrained Viterbi/HMM scorer (if 1A passes)
Build the §2.4 model; consume 1A observations + final-score boundary (+ optional 1B terminal
confidence + §5 audio). Explicit null/replay/first-server/mismatch handling; top-k + abstention.
**Ship-as-automatic decision rule:** exact score-sequence precision on *accepted* games ≥95 %,
accepted-game coverage ≥30–50 % of backlog, **and** ≥50 % manual-correction-time reduction vs
today's scorer. Otherwise ship as an **assistive** scorer (prefill + abstain), which is likely
the right backlog product regardless.

### Phase 3 — Track B build-out (analytics + residual), gated by 1B
Full pose/identity/shot reconstruction (the user's secondary goals) + ball tracking **only
where it adds value**: terminal-event confirmation, analytics, highlights, and the ambiguous
gaps Track A flags. Self-supervised pretraining on the 219 GB to fight cross-court transfer.

### Phase 4 — Human-in-the-loop integration
Wire both tracks into `ml/auto_edit.py` / `review_mode.py`: inferred score path + confidence +
ambiguous-rally ranges + one-click correction + final-score-mismatch warning + honest "cannot
infer reliably" abstention. Keep the **correction → retrain flywheel** (reuse the shipped
rally-combiner retrain pattern). This is the product even if full automation isn't reached.

### Phase 5 — Capture protocol for future footage (if user opts in; §7)

---

## 5. Re-open score-call audio (cheap, was prematurely closed)
The prior ASR kill was a **far-field-mic** result (~4 % speech captured). But players *do* call
the score aloud before serving, and even **noisy** score-call detection is a strong Track-A
emission. Two cheap moves: (a) re-run a score-call detector on **pre-serve windows specifically**
(not whole-rally) on existing audio — it may clear the bar even at low recall since the HMM only
needs occasional anchors; (b) a closer mic on future captures likely makes it strong. Low cost,
high optionality.

---

## 6. Hard constraints (must respect)
- **NATIVE RESOLUTION for anything touching the ball / terminal event — NO downscaling, EVER.**
  This is the load-bearing lesson of 2026-06-22: every prior "the ball is sub-resolvable /
  fidelity wall" conclusion was an artifact of the legacy ≤1280 / 640 / 256-warp extraction
  shrinking a real ~10 px ball to 1–4 px. Ball/terminal models decode full 1920×1080 frames
  (lossless, no `scale=` filter). The *foot-point rally detector* may keep its downscaled path
  (it never needs the ball), but it is the ONLY component allowed to downscale.
- **GUI never loads heavy ML in-process** (mpv segfault) — all perception + HMM inference runs
  in `.venv-motion` / subprocess; GUI stays `opencv-python-headless` + numpy-only where it
  touches the player loop (`predict_joint` precedent). The HMM is tiny — numpy-only is trivial.
- **Single RTX 3500, 12 GB; 62 GB RAM, 0 swap.** Small models; offline batch fine.
- **DataLoader gotcha:** `num_workers>0` leaked ~116 GB phantom disk; `pkill -9 -f`, prefer
  `num_workers=0` + RAM-materialized batches; never `torch.stack` a 30 GB tensor.
- **Dedup → analyze at real ~30 fps;** keep 60 fps source for slow-mo.
- **LOSO for every claim;** `winner_probe.py` stays the standing yardstick.
- **Don't regress the shipped rally detector** — build `ml/perception/` alongside `ml/motion/`.
- **Never `git add`** the root planning docs (this file included).

---

## 7. Decision for the user — the capture fork (downgraded by the ball-size correction)
The original capture pitch leaned on "the far ball is 4 px → need a second camera to see it."
That premise is **gone**: the ball is ~10 px and visible at native res. So capture is now
**optional optionality**, not a necessity:
- a second **angle** still helps the things visibility doesn't fix — **occlusion** (player/paddle
  blocking the bounce) and **far-line homography precision** for in/out calls,
- a **closer mic** still revives score-call ASR and hit/bounce localization (genuinely useful,
  cheap),
- but it is no longer "the real unlock" — native-res software on the existing footage is now the
  main event, and the backlog is fully in play.

**Recommendation:** treat a closer mic as a cheap win for future sessions; treat a second camera
as a *nice-to-have* for far-line/occlusion edge cases, not a prerequisite. Decide later, after
the Phase-1 native-res probes quantify how much the single camera actually leaves on the table.

---

## 8. First increment — agreed with GPT-5.5 (round 3). LEAN: 2 tools, no package, 3–4 games.
**Principle (agreed): prove/kill Track A observability with the least code before building any
`ml/perception/` package.** No `decode/scene/extract_runner/service_state` modules yet, no trained
classifier, no scene cache — those are premature until the numbers justify them. Native-res only.

0. **DONE 2026-06-22 — native-res ball-size probe:** ~10 px ball confirmed; "4 px" premise retired
   (`$CLAUDE_JOB_DIR/tmp/ballframes/`). Native-resolution is now a hard constraint (§6).
1. **`ml/tools/build_service_truth.py`** — per-rally supervised truth, **label-derived** (not
   seed-derived): `serving_team = winning_team if winner=="server" else 1-winning_team`;
   `serving_score/server_number` from `score_at_start`; `expected_parity = serving_score % 2`.
   `ScoreState` replay (both seeds) only as a **consistency audit**, flagging mismatches.
   Emit JSONL per non-post-game rally. **Gate 0:** rows generated, parity parsed, audit
   mismatches reported & explainable.
2. **`ml/tools/service_state_probe.py`** — crude native-res probe, two modes:
   - `--export-contact-sheet`: pre-serve native-res frames → human glance set. **Gate H
     (human observability):** pass ≥95 % precision / ≥85 % coverage on a few hundred samples;
     **kill/deprioritize Track A** if humans can't reach ~90 % / ~70 % after excluding bad clips,
     side switches, ambiguous frames. (This subsumes the old Phase-0 audit — answer to "is it
     even observable.")
   - `--run-yolo-rule`: YOLO persons out-of-process → foot-points through homography → read
     court-half for **both physical sides independently**, **far-team half flipped**, abstain near
     centerline / under same-side crowding. Compare the labeled serving side *after* observing.
     **Gate 1A (crude automation):** continue if ≥90 % precision / ≥60–70 % coverage with mostly
     fixable errors; **kill Track A** if best high-confidence automation ≤85 % precision with
     *systematic* (non-abstainable) failures → ship the existing manual scorer instead.
3. **Tiny deterministic test** (`tests/.../test_service_state_truth.py`): winner→serving_team
   logic; parity→court-half; **far-side flip** (synthetic court points). A sign error here is the
   single most likely way to make the probe look falsely bad.
   - Scope: **3–4 deliberately chosen games** (≥1 near-heavy, ≥1 far-heavy, ≥1 visually hard),
     not all 80. Find sign/side-mapping/stacking/decode bugs cheaply first.
4. **Only after Gate 1A passes**: expand to LOSO across sessions (target 92–95 % / 75–85 %),
   then build the HMM (§2.4) and the `ml/perception/` package. **Track B** (terminal-clip export
   + native-res ball-method bench) + the **pre-serve score-call audio** re-probe (§5) run in
   parallel but must NOT delay proving/killing Track A.

---

## Appendix — review trail
- Round 1 (briefing/response): inverted the gate (feasibility-first), separated
  observability/trackability/line-callability, terminal-window labeling, broadened tools
  (point trackers, temporal-difference, self-supervised pretrain, Bayesian abstention),
  flagged the capture blind spot.
- Round 2 (briefing/response): confirmed the globally-constrained **service-state HMM** is
  "the strongest software-only path for the backlog" (not a mirage), but **split the gate**
  (service-state probe *and* terminal-event probe in parallel), exposed segmentation
  brittleness + coverage-compounding math + official-vs-objective-score, confirmed the
  **backlog-vs-capture fork**, and reopened **score-call audio** as a cheap emission.
- Files: `$CLAUDE_JOB_DIR/tmp/gpt5-visual-rebuild/round{1,2}_{briefing,response}.md`.
- **Post-review empirical correction (2026-06-22):** user flagged that the ball is clearly
  visible and not 2 px. Measured on lossless native 1920×1080 frames → **~10 px ball**. This
  invalidated round-1's "4 px / line ≈ 2.7 px / physically impossible" physics (it was fed the
  bogus downscaled number) and the round-2 "sidestep the invisible ball" framing weakens to
  "sidestep the *bounce-timing* problem." Ball tracking re-elevated to a primary native-res path;
  native-resolution added as a hard constraint. Frames: `$CLAUDE_JOB_DIR/tmp/ballframes/`.
- Round 3 (briefing/response): converged on the **lean first increment** (§8). Confirmed
  service-state stays the first scoring bet (ball back on the table as a Track-B probe, not
  co-primary). Three pipeline fixes: **label-derived truth** (no serve seed → no circularity),
  **far-team court-half flip** (needs a unit test), **evaluate both sides then compare** (don't
  let labels pick the side). Cut `ml/perception/` until numbers justify it; minimum = 2 tools +
  a tiny test on 3–4 games. New #1 risk = pre-serve server *identity* (stacking/occlusion), and
  **mid-game side switches** as a data-quality gate. Files: `round3_{briefing,response}.md`.
