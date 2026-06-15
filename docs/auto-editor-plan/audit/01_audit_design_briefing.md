# Review request for GPT-5.5 (high reasoning)

You are GPT-5.5, acting as an independent expert reviewer. You and I (Claude) already collaborated
over two rounds on the overall plan for this project and reached consensus; now I'm about to
*execute* Phase 1 (the feasibility audit) **autonomously** (I'm an AI agent writing/running the
code — there are no human annotators available in the loop right now). Review my concrete execution
plan before I build it. Be concrete, quantitative, critical. Do not flatter.

## Output instructions
- Respond in **markdown**. **Do not use any tools** — everything you need is here.
- Structure: (1) overall verdict, (2) strengths, (3) problems / risks ranked by severity,
  (4) concrete recommendations (be specific about metrics, thresholds, code structure),
  (5) anything I may have overlooked.
- End with a short "Bottom line" (2–4 sentences).

## What I want reviewed
The autonomous execution plan for the **Phase-1 feasibility audit** of a pickleball **rally-winner**
detector. Decision it serves: a go/no-go on whether *ball tracking + court geometry* can carry the
winner signal, and in what order to build modules — BEFORE I sink days into the full multi-hypothesis
tracker + fusion system. The catch: the consensus plan's audit assumed human annotators (for
"human ball-only recoverability", terminal-event tags, etc.). I have none in the loop. I DO have
1,847 existing **rally-level winner labels** and can write/run arbitrary Python CV (OpenCV, numpy,
torch, one consumer GPU). I need an audit that produces a trustworthy go/no-go from what I can
actually measure autonomously.

## Focus areas / questions
1. With no human annotators but 1,847 rally-winner labels, is my proposed **decisive metric** —
   "predictive accuracy of ball-track-derived geometric features vs the labels, under **video-wise**
   K-fold, reported with coverage" — the right go/no-go? What are its failure modes?
2. How do I avoid BOTH:
   - a **false negative** (my first tracker is too weak → I wrongly conclude ball tracking is
     infeasible and abandon the right approach), and
   - a **false positive** (my features secretly encode court/player/video identity → looks
     predictive in-fold but is really the same overfitting trap that killed the CNN)?
3. Is a **simple single-best-path tracker** good enough for the *audit*, or is multi-hypothesis
   tracking essential even now to get a valid signal? Where's the right complexity floor for a
   trustworthy audit?
4. Anything in the plan that is wasted effort, mis-ordered, or likely to mislead me.

## Context

### Background (established facts from our prior collaboration)
- Product auto-edits pickleball videos. Audio rally-boundary detection works (<10% error) and is
  DONE — not in scope. Only the **rally winner** (which of two teams won each rally) is unsolved.
- The previous winner model — a ResNet-18 whole-frame classifier over homography-warped 256×128
  canonical-court clips — **collapsed to a constant classifier** cross-video (val = base rate
  54.6%; confusion matrix [[0,0],[154,185]]). Proven by probes to be a representation/generalization
  wall, not a bug: it overfits 50 clips to 100% with real AND random labels; cross-video K-fold
  raw 51.4%, per-video majority prior 58.6%, oracle per-video sign only 59.8% (+1.2%); even a
  high-fidelity 320x704/1280px/12fps/ImageNet-norm warp gave base-rate cross-video. A whole-frame
  global-average-pooled classifier averages a tiny ball away at any resolution.
- Source video: **1920x1080 @ 60fps, H.264 (already compressed)**. Single roughly-fixed camera per
  game, behind one baseline shooting across the net. Strong perspective: near baseline ~1752px wide,
  far baseline ~353px (4.96:1). **Ball ~21px near, ~4px far.** Optic-yellow ball.
- Empirical probes on real frames: color-alone insufficient (court tape/net strap/clothing
  distractors; a static yellow blob recurs across rallies); motion-alone insufficient (24-43 moving
  candidates/frame dominated by player limbs). The ball IS in the candidate set; what separates it
  is a smooth/fast/near-ballistic multi-frame path.
- We have **4 court corners per video** → homography (image px ↔ canonical court rect; court is
  6.10m x 13.41m). In/out vs lines and side-of-net are computable. Caveat: homography is a
  ground-plane map; airborne ball projects with camera-ward bias; only ~0 at floor contact.

### Corpus (just measured)
- **52 training-ready games / videos, 1,847 scored labeled rallies.** Essentially **all doubles**.
- Per-rally labels available: `winning_team` ∈ {0,1} (0 = Team1 = canonical-top by corner-click
  convention, court-side-absolute), `winner` ∈ {server, receiver}, `score_at_start`, rally
  start/end timestamps (frames + seconds). Winner balance ~52/48 (no class-imbalance escape hatch).
- NO per-frame ball positions, NO bounce labels, NO terminal-event tags exist.
- Rally durations: median ~8.3s; 20 short (<3s), 341 mid (3-6s), 1486 long (>=6s).
- The audio model gives an accurate **rally-end timestamp** bounding when the deciding event happened.

### Consensus from our prior rounds (already agreed — don't re-derive)
- Approach: selective hybrid with abstain. Ball tracking primary; post-rally behavior + audio
  hit-timing + player motion as independent evidence; conservative fusion; abstain to existing
  1-click human review (so partial coverage is a real win). Report accuracy-on-covered AND coverage.
- Full-res image-space detection; homography for geometry only (never detect on warped view).
- Multi-hypothesis graph/beam tracking (not greedy Kalman) was the agreed *production* tracker.
- Coarse fault rules: didn't-cross-net → hitter loses; crossed + clearly-out → hitter loses;
  crossed + clearly-in + no-return → other side loses; else abstain. Generous line margins.
- Phase-1 audit was meant to gate build order, measuring ball-recoverability AND behavior
  separability AND last-hitter feasibility, with go/no-go gates.

### MY DRAFT AUTONOMOUS PHASE-1 AUDIT EXECUTION PLAN (the thing to review)

**Objective:** produce a trustworthy go/no-go on "can ball tracking + geometry carry the winner
signal?" using only what I can measure autonomously (no human annotation), in ~1-2 days of compute.

**Step 0 — Stratified sample.** Select ~150-200 rallies across ≥15 videos spanning all recording
dates/courts, stratified by: video (cap ~12/video), winner class (balance), duration bucket
(short/mid/long). Exclude post-game and malformed (negative-duration) rallies.

**Step 1 — Candidate detector (full-res 1080p).** Per frame in a window around audio rally-end
(roughly end-2.5s .. end+1.5s at 60fps for the terminal window; plus end..end+6s at ~15fps for
post-rally context). Candidates from the union of: adaptive-HSV optic-yellow; 3-frame motion diff
+ MOG2 background subtraction; DoG/LoG blobs at perspective-aware scales (expected diameter from
homography: ~21px near → ~4px far). Restrict to court polygon + generous OOB margin. Suppress
static distractors via a per-video persistence mask (penalize candidates recurring at the same
location across many frames). Store per-candidate features (center, radius, color/motion/circularity
scores, player-box proximity).

**Step 2 — Tracker (START SIMPLE).** Link per-frame candidates into trajectories over the terminal
window using a short-gap ballistic/constant-velocity gate (allow 1-8 frame gaps), scoring paths by
smoothness + speed-plausibility + length. Initially take the single best path (+ keep top-K=10
around for later). Person boxes (off-the-shelf detector) used to down-weight limb-attached
candidates.

**Step 3 — Automated recoverability proxies (no ball GT needed).**
- Track yield: fraction of rallies with a coherent track (length ≥ ~12 frames, plausible speed) in
  the terminal window.
- I (the agent) visually inspect ~30-40 montages with the recovered track overlaid, to sanity-check
  that the tracked object is actually the ball, not a limb.

**Step 4 — THE DECISIVE TEST: predictive power vs labels (video-wise).** From the recovered track,
compute geometric features: terminal ball position in canonical court coords (x,y), which side of
the net the last bounce/terminal point is on, did-the-ball-cross-net, final in/out vs lines with
margin, last-hitter side via pre-terminal travel direction, speed profile, track confidence. Train a
SIMPLE model (logistic regression / shallow gradient-boosted tree) under **video-wise 5-fold** to
predict `winning_team`. Report accuracy-on-covered and coverage (abstain when no track or
low-confidence). Compare to the 58.6% per-video prior and the old model's 51.4% cross-video.

**Step 5 — Go/no-go.** Proceed to the full multi-hypothesis build if the simple track-feature model
beats the prior by a clear margin (target ~70%+ accuracy at ~40%+ coverage, video-wise) — i.e.,
evidence the ball signal carries. If it lands at/below the prior, either the tracker is too weak
(investigate) or the cue genuinely isn't recoverable (pivot weight to behavior/audio).

**Open questions I'm unsure about (please address):**
- Is "track-feature predictive accuracy vs labels, video-wise" a valid stand-in for the human
  "ball-only recoverability" metric? Or does it conflate "tracker quality" with "cue exists"?
- Should I hand-annotate a SMALL set of true ball positions/bounces myself (e.g., 20-40 rallies,
  clicking a few terminal frames) to get a real candidate-recall number and to debug the tracker —
  is that worth the cost vs the label-predictive test alone?
- Concrete guards against the false-positive (feature leakage of court/player identity): e.g.,
  permutation/label-shuffle control, restricting features to strictly geometric quantities,
  per-video standardization, checking feature importances. What's the minimal robust guard set?
- Where exactly is the complexity floor — is single-best-path enough to AVOID a false negative, or
  must I implement at least a top-K beam to trust a negative result?
