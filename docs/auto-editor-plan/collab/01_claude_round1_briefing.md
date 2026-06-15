# Collaboration request — pickleball rally-winner detection (Round 1 of 2)

You are GPT-5.5 (high reasoning). I am Claude, working with a human engineer on a real
computer-vision problem. The human wants us (two reasoning models) to collaborate over
**two rounds** and converge on a concrete plan. This is **Round 1**: critique my analysis,
then either harden my proposed approach or propose a fundamentally better one.

**Output instructions:** Respond with your complete analysis in **markdown**. Do **not** use
any tools, do not try to read the filesystem — everything you need is in this document. Be
concrete, quantitative, and critical. If you think my approach is wrong, say so plainly and
give a better algorithm. End with a short "Round-1 position summary" I can respond to.

---

## The product

A desktop app auto-edits raw pickleball match videos into a highlight cut + score overlays.
The pipeline: (1) detect rally start/end from **audio** (works well, <10% boundary error);
(2) **detect which team won each rally** (THE PROBLEM); (3) feed per-rally winners into a
deterministic pickleball scoring engine (`ScoreState`, provably correct) that produces the
running score. We only need a reliable **per-rally winner** (binary: which of the two teams
won the rally). The scoring rules are already solved — do not re-derive them.

## What failed

The winner detector was a **ResNet-18 whole-frame classifier** over the last 2.5 s of each
rally. Each frame was perspective-**warped via a homography** (from 4 user-clicked court
corners) into a canonical 256×128 top-down court view, sampled at 8 fps (20 frames),
fed as (B, T=20, 3, 128, 256) → ResNet-18 (fc→Identity, global-average-pooled to 512/frame)
→ Conv1d temporal head → 2-class softmax.

It **trains to ~97% train accuracy but collapses to the validation base rate (~54.6%) on
held-out videos** — literally a constant classifier (confusion matrix [[0,0],[154,185]],
predicts one class for every val clip; calibration temperature blew up to ~12).

## Evidence it is a representation/generalization wall, not a bug (each probe kills one hypothesis)

- **Capacity/pipeline:** model overfits 50 clips to 100% with BOTH real and random labels →
  architecture + pipeline are fine; it can memorize anything.
- **Labels:** court-side-aligned by construction (Team 1 → canonical top in every video via
  corner click order). A prior label-ordering bug was found and fixed. Per-video class
  balance healthy. Not a label bug.
- **Augmentation:** turning it off doesn't change cross-video collapse.
- **Cross-video K-fold (every video held out once, 1,847 rallies / 51 videos):**
  raw model fixed-sign = **51.4%** (chance); per-video majority prior = **58.6%**; ORACLE
  per-video sign (upper bound if we could perfectly flip each video) = **59.8%** → only
  **+1.2%** over the prior. The cue does not transfer to unseen courts.
- **Fidelity ladder (decisive):** rebuilt clips at 320×704 portrait, 1280-px extraction,
  12 fps, ImageNet-normalized, trained cross-video → best val = **54.6% = base rate**, zero
  lift. More resolution did NOT help within the warped-classifier paradigm.
- **Architecture argument for why even native 1080p won't save THIS classifier:** ResNet-18
  ends in global average pooling, collapsing every frame to one 512-vector averaged over all
  spatial cells. At 1080p the ball is ≈0.017% of the frame (near) / ≈0.0006% (far); the
  stride-32 pre-pool map is ~60×34 ≈ 2,040 cells, so the ball is <1 cell and GAP divides its
  signal by ~2,040. A GAP classifier washes a tiny ball away at any resolution; it falls back
  on global court/player cues that don't generalize across ~40 courts.

## The physical reality (measured on real footage)

- Source video: **1920×1080 @ 60 fps, H.264 (already compressed)**. Single, roughly-fixed
  camera per game, mounted behind one baseline shooting across the net.
- **Strong perspective:** near baseline ≈1,752 px wide, far baseline ≈353 px wide (**4.96:1**).
  Estimated **ball diameter ≈21 px near, ≈4 px far**. The ball is the standard optic-yellow.
- **Color alone is insufficient:** HSV optic-yellow thresholding inside the court returns many
  distractors every frame — court-edge tape markers, the net center strap, players' light
  clothing. A near-static yellow blob even recurs across different rallies (a fixed object).
- **Motion alone is insufficient:** 3-frame differencing inside the court returns 24–43 moving
  candidates per frame, dominated by players' arms, paddles, and shadows.
- The ball IS present in the candidate sets as a small, fairly circular, yellowish, MOVING
  blob; what separates it from distractors is that its path across frames is smooth/fast/
  near-ballistic while limb motion is erratic and player-anchored.

## Assets & constraints (important for any proposal)

- **We have the 4 court corners per video** → a homography mapping image pixels ↔ a canonical
  court rectangle (pickleball court = 6.10 m × 13.41 m). In/out vs. lines and which side of the
  net the ball is on are computable geometrically.
- **Labels available:** ~**1,847 rally-level winner labels** across ~51 games / ~40 distinct
  courts. **We have NO per-frame ball-position labels** and no bounce labels. Labeling those is
  possible but costly.
- The audio model already gives an accurate **rally end timestamp** (bounds when the deciding
  event happened).
- **A human-in-the-loop fallback already ships**: every rally is a 1-click confirm/flip with
  automatic score cascade. So **abstaining is acceptable** — a detector that is highly accurate
  on a subset and abstains on the rest is a real win (it shrinks review clicks). We track two
  metrics: accuracy-on-non-abstained, and coverage (non-abstain rate).
- Constraints: must run on the user's single machine (one consumer GPU), Python, system-ffmpeg
  decoding only (no in-process video libs). Inference time per video should be tolerable
  (minutes, not hours).
- Pickleball ground truth: a rally ends on a **fault**; the faulting side loses. Terminal
  events: ball lands out (hitter loses), ball into net (hitter loses), ball bounces twice on
  one side (that side loses / failed to return).

## My proposed approach (critique this)

Replace the warped-classifier Stage 2 with **ball tracking + court geometry + rules**, same
output contract `(winning_team, confidence)` with an explicit abstain:

1. **Detect** ball candidates per frame at full resolution over the rally's last ~2–4 s
   (color ∪ motion ∪ perspective-aware size prior; restricted to court polygon + OOB margin).
2. **Associate** candidates across frames into a smooth ballistic **trajectory** (classical:
   Kalman / constant-velocity+gravity gating, or global min-cost path over a candidate graph;
   à la tennis/badminton trackers). This is the disambiguator vs. player-motion clutter.
   No new labels needed. Escalate to a learned TrackNet-style heatmap detector ONLY if
   classical coverage is too low (bootstrap its labels from the classical tracker + human fix).
3. **Map** the track pixel→court metres via the existing homography (handle the air-projection
   bias: decide on floor-contact/bounce points where the ground-plane bias ≈ 0).
4. **Detect the terminal event** (last bounce = vertical-trajectory minimum / velocity change;
   net contact near the net plane; out = terminal bounce maps outside the lines). Audio rally-
   end bounds the search window.
5. **Apply fault rules** (who hit last via pre-terminal travel direction + bounce location →
   who faulted → winner).
6. **Confidence/abstain** from track quality, candidate ambiguity, distance-from-camera (far
   = less trustworthy), and rule margin. Abstain liberally; humans handle the rest.

Validate with the **video-wise K-fold yardstick** against the 1,847 labels: beat the 58.6%
prior decisively on covered rallies, report coverage too. Slice by near/far terminal location.

## What I want from you in Round 1

1. **Is my approach sound, or is there a fundamentally better algorithm** given: single fixed
   camera, no ball labels, ~40 courts, 4-px far ball, 1,847 rally-level labels, abstain allowed?
2. **Hardest failure modes** of my plan and how you'd de-risk them (rank them).
3. Specifically consider alternatives I may be undervaluing, e.g.:
   - Weakly/self-supervised learning that uses the **1,847 rally-level labels** as the only
     supervision (multiple-instance learning, attention over detected ball/player tracks,
     learned bounce/event detector trained from rally outcomes).
   - **Player-centric** cues instead of/with ball (pose, who lunges/reaches/stops, body
     orientation, the "give-up" posture, who walks to pick up the ball afterward).
   - Using the **post-rally seconds** (players' reactions, ball rolling to a stop, who retrieves
     it, who walks back to serve) — often a stronger signal than the terminal hit itself.
   - **Audio** beyond boundaries (last paddle pock side, net-cord sound, silence pattern).
   - Off-the-shelf detectors (YOLO-class ball/person, pose estimators) vs. bespoke classical CV.
4. If you'd keep ball tracking, give the **most robust concrete tracking algorithm** you'd use
   for a 4–21 px ball with heavy player clutter and only a single view, and how to detect the
   bounce/in-out reliably enough to decide a fault.
5. Be explicit about what is **likely to work vs. likely to disappoint**, and what the
   realistic ceiling on (accuracy, coverage) is.

End with a concise "Round-1 position summary."
