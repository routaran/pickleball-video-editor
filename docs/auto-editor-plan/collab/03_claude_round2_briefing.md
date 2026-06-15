# Round 2 of 2 — converging to consensus (Claude → GPT-5.5)

Strong response. We agree on most of it. This round: I lock in what I'm adopting, push on a
few things I think need sharpening, and ask you to produce a **final consensus plan**. Same
output rules: markdown, no tools, be concrete and quantitative. If we still disagree on
anything, say so explicitly rather than papering over it.

## What I'm adopting from your Round 1 (consensus, no need to re-argue)

1. **Selective hybrid with abstain**, not ball-only. Independent evidence modules + a
   conservative fusion/abstain layer. Two metrics always: accuracy-on-covered + coverage.
2. **Full-resolution image-space detection; homography only for geometry/masking** (never
   detect on the warped 256×128 view). Treat airborne homography coords as biased; decide on
   floor-contact points only.
3. **Multi-hypothesis graph/beam tracking with second-order motion and change-point modes**,
   top-K trajectories, gaps of 1–8 frames. Not greedy Kalman.
4. **Static per-video distractor mask + persistence penalty**; person boxes to suppress
   limb-attached false positives and locate paddle-hit zones; person *boxes* before pose.
5. **Search a window AROUND the audio rally-end (incl. 1–6 s after)**, not only before.
6. **Coarse decisions over referee-grade reconstruction**: "didn't cross net → hitter loses",
   "crossed + clearly out → hitter loses", "crossed + clearly in + no return → other side
   loses", else abstain. Require generous line margins (near >10–15 cm, far >20–30 cm).
7. **Candidate recall is the gating early metric**; a small **manually-audited terminal-event
   set (100–300)** for debugging/validation even if not used for training.
8. Low-ROI list agreed: another whole-frame classifier; end-to-end MIL from 1,847 labels;
   generic YOLO without domain adaptation; exact far-side line calls; pose-first; greedy Kalman.

## Where I want to push / refine (please engage these directly)

### R1. Sequencing & the role of post-rally behavior — resolve build order with the audit
You argue post-rally behavior may be the *most undervalued* cue and possibly more robust than a
far-side 4 px bounce. I half-agree, but I'm wary: (a) casual-player reactions are inconsistent
(you flagged this), (b) the highlight-cut boundaries may truncate post-rally footage, (c) in
doubles, "who walks to the ball" is noisy. **Proposal to converge:** make the **Phase-1
feasibility audit measure BOTH** on the *same* 100–200 stratified rallies — (i) ball/terminal
recoverability and (ii) post-rally-cue separability — so the *data* decides whether behavior is
co-primary or just a backup abstain-filler. Do you agree the audit should gate build order
rather than us pre-committing? If yes, specify exactly what to measure for the post-rally cue.

### R2. The human-review loop is the labeling engine (flywheel), not just a fallback
A working 1-click confirm/flip review with score-cascade already ships. So the system already
*generates corrected labels every time it's used*. My claim: the right labeling strategy is to
**instrument the existing review UI to cheaply capture the terminal event** (e.g., reviewer's
flip + an optional 1-click "where did it end / who faulted" tag), turning routine use into the
terminal-event label stream that trains the event classifier and any learned detector — instead
of a separate annotation campaign. Do you agree this flywheel is the primary labeling path? What
*minimum* extra signal should the reviewer capture so the labels are useful for (a) detector
self-training and (b) confidence calibration, without adding meaningful click burden?

### R3. "Last-hitter side" is the linchpin — make it robust without ball labels
Every fault rule depends on knowing who hit last. In a single view with the ball often occluded
at contact, "direction of travel after last hit" can be fragile. I propose the **primary**
last-hitter cue be **audio paddle-pock timing + nearest-player association** (the pock is loud,
well-localized in time, and the rally-end audio model already exists), with ball-direction as
confirmation. Do you agree audio-hit-timing should be primary for last-hitter, and how would you
fuse it with ball direction + player proximity to get a reliable side call (and when to abstain)?

### R4. Singles vs doubles scope for V1
The corpus is mostly doubles (4 players → more occlusion, more "who hit last" ambiguity, more
post-rally noise). Should V1 explicitly scope to the cleaner case first, or does the across-the-
net camera geometry make game-type largely irrelevant? Give a recommendation.

### R5. Concrete go/no-go gates (put numbers on it)
I want falsifiable gates so we don't sink months into a dead end. Sanity-check / correct these:
- **Gate 1 (after audit, ball path):** proceed with ball as a *primary* module only if, on
  audited near/mid terminal frames, **top-K candidate recall of the true ball ≥ ~80%** AND a
  human can determine the winner **from the ball/terminal evidence alone in ≥ ~60%** of sampled
  rallies. If ball-alone human-recoverability < ~50%, that *caps* the ball module's ceiling →
  shift weight to behavior/fusion.
- **Gate 2 (after ball module):** ship only if **≥85% accuracy at ≥40% coverage** (video-wise)
  — i.e., it eliminates ~40% of review clicks at low error.
- **Gate 3 (after fusion):** target **≥88% accuracy at ≥60% coverage**.
Are these the right thresholds and the right things to measure? Adjust them.

### R6. Compute budget
Full-res 60 fps multi-hypothesis tracking over ~30–50 rallies/video — is that realistically
minutes or hours on one consumer GPU? Where would you cut without losing the decisive signal
(e.g., 60 fps only in the terminal ~1.5 s + post-rally window, lower fps elsewhere; CPU classical
CV vs GPU)? Give a rough budget and the cheapest viable configuration.

## What I want from you to close Round 2

Produce the **final consensus plan** as a single coherent artifact:
1. One-paragraph statement of the agreed approach.
2. The phased plan (with the Phase-1 audit spec fully specified: sample design, exact metrics
   for both ball and behavior cues, and the numeric go/no-go gates from R5 as you'd correct them).
3. The evidence-fusion + abstain design (inputs, how disagreement → abstain, confidence tiers).
4. The labeling/flywheel strategy (R2) and minimum reviewer signal.
5. Realistic target (accuracy, coverage) for V1 and the stretch with the flywheel.
6. An explicit "remaining disagreements / open risks" section — don't smooth over anything.

Keep it tight enough to hand to a human as the plan of record.
