# Review request for GPT-5.5 (high reasoning) — Phase-1 audit RESULTS + next move

You are GPT-5.5, continuing our collaboration on the pickleball **rally-winner** detector.
You already reviewed and hardened my Phase-1 audit design (I adopted your changes: top-K beam
tracker, date-grouped CV, dev-vs-final split, false-positive controls, three-outcome framing).
I've now BUILT and RUN the audit on a 200-rally dev sample. I need your read on the results and a
decision on the highest-ROI next move. Be concrete and critical; don't flatter.

## Output instructions
- Markdown. **No tools.** Structure: (1) your read of the result (which of the three outcomes is
  this), (2) the single highest-ROI next move + why, (3) ranked alternatives, (4) concrete specifics
  for the recommended move, (5) anything I'm missing. End with a 3-4 sentence "Bottom line".

## What I built (as agreed)
Full-res (1080p60) pipeline over each rally's terminal window (end-2.5s .. end+1.0s, 60fps):
- **Detector:** per-frame candidates = union of optic-yellow HSV ∪ 3-frame motion diff, inside the
  court polygon + margin, with a per-clip static-yellow persistence mask (kills tape/net-strap), top
  40 candidates/frame by a color+motion+shape score. NO person detector yet (deferred).
- **Tracker:** top-K beam DP over candidates. After failing with length-rewarding cost (locked onto
  players), I switched to motion+smoothness scoring: per-step reward for ball-like speed, an
  **acceleration gate** (|Δv| ≤ 18 px/frame, kills jitter), gap penalty, plus a **straightness**
  (net_disp/path_len) filter and a ballistic re-rank. Returns top-K tracks; track[0] feeds features.
- **Features (strictly geometric, via the homography → canonical court where Team1=top, net=mid):**
  terminal canonical (x,y), side of net, signed vertical travel (last-hitter proxy), crossed-net,
  min/max depth, out-of-bounds margins past baselines/sidelines, plus top-K aggregates
  (ballistic-weighted fraction/mean of terminal side). Track-quality (reward/straightness/len/n) is
  kept SEPARATE and used only for the nuisance-control and abstention, never as a predictive feature.
- **Eval:** GroupKFold by recording DATE (9 groups) and by VIDEO (49), simple LogisticRegression
  (standardized, C=0.5, balanced), same-covered-subset baselines, label-permutation null (within
  date groups), nuisance-only control, selective accuracy/coverage curve.

## RESULTS (200 dev rallies, balanced 99/98, coverage 98.5%)
```
baselines (same covered subset): global majority 0.503 | per-date oracle 0.558 | per-video oracle 0.685
geometric model: leave-DATE-out acc = 0.558 (balanced 0.559)
                 leave-VIDEO-out acc = 0.533 (balanced 0.533)
permutation null (within date): mean 0.495, 95th pct 0.558, max 0.624 -> real 0.558 => p = 0.057
nuisance-only model (quality fields, no geometry): leave-date-out 0.543
selective accuracy vs coverage (leave-date-out, abstain by model confidence):
  cov 100% n197 acc 0.558 (subset prior 0.503)
  cov  80% n157 acc 0.573 (subset prior 0.510)
  cov  60% n118 acc 0.619 (subset prior 0.517)
  cov  50% n98  acc 0.602 (subset prior 0.510)
  cov  40% n78  acc 0.615 (subset prior 0.513)
  cov  30% n59  acc 0.610 (subset prior 0.576)
  cov  20% n39  acc 0.641 (subset prior 0.692)
```

## CRITICAL diagnostic context (don't ignore)
- **The tracker is NOT reliably tracking the ball.** I overlaid the best track on real frames: it
  frequently locks onto **players** (limbs/bodies/paddles), not the ball. Coverage of 98.5% just
  means "a track was found," NOT "the ball was found." So the geometric features are largely
  computed off the wrong object.
- **Detection produces high-recall clutter** (~37-40 candidates/frame at the cap), dominated by
  player motion. I have NOT verified candidate RECALL of the true ball (no ball ground truth exists;
  only 1,847 rally-level winner labels).
- **Camera angles vary wildly across the 51 videos**: some are far back; some have a huge foreground
  player occluding much of the court; near baseline ball ~21px, far baseline ~4px (5:1 perspective).
- So per our three-outcome framing, I read this as **"tracker-not-good-enough" (ambiguous)**, NOT a
  valid "ball-signal-weak" no-go — because candidate recall + tracking quality are unverified and the
  tracker is visibly mis-locking. The faint ~10pp edge over same-subset prior at 40-60% coverage is
  the only positive hint, and the permutation p=0.057 is borderline.

## My proposed next move (pressure-test this)
The observed failure is specifically **player-locking**. So the highest-leverage fix is **explicit
player-region suppression**: run an off-the-shelf person detector (YOLO/ultralytics) per frame (sparse
+ interpolate), exclude candidates inside player boxes, and have the tracker prefer candidates OUTSIDE
players. Secondarily, replace/augment the velocity-gated DP with **gravity-parabola RANSAC** (fit
constant-acceleration arcs to candidate sets; the ball is the object whose trajectory fits a parabola
with low residual) to isolate true ball flights. Re-run the same audit + controls. Only if recall/
tracking then look good AND predictive accuracy is still ~baseline would I call it a real no-go.

## Specific questions
1. Do you agree this is "tracker-not-good-enough" (ambiguous), and that the result so far neither
   justifies a full build nor a no-go? Or do you read the numbers differently?
2. Is **player-suppression + parabola-RANSAC** the right highest-ROI next move, or would you first
   spend the effort on a small **ball-ground-truth set** to measure candidate recall and actually
   know whether the ball is detectable at all? I'm an autonomous agent — I CAN attempt to self-mark
   the ball in a handful of clearly-visible terminal frames (imperfect), or I can ask the human to
   annotate ~30 rallies. Which is the better use of effort right now, and in what order?
3. Is there a fundamentally smarter detection/tracking idea for a 4-21px ball under heavy player
   clutter and a single heterogeneous camera that I'm not considering (e.g., learned tiny-object/
   TrackNet-style detector bootstrapped how; background-stabilized differencing; trajectory-from-
   motion without per-frame detection)?
4. Given the camera heterogeneity, should I keep the audit on ALL videos, or first prove feasibility
   on the subset of "good geometry" videos (camera farther back, less foreground occlusion) and only
   then generalize?
