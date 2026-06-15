# Review request for GPT-5.5 (high reasoning) — strategic fork after 2 audit runs

You are GPT-5.5, continuing our collaboration on the pickleball **rally-winner** detector. You've
reviewed the audit design and the first results. I now have an A/B result and I think we're at a
strategic fork. I need a decisive recommendation, not reassurance. Be blunt.

## Output instructions
- Markdown. **No tools.** Structure: (1) your read of the A/B result, (2) the decision — push ball
  tracking further, get ball GT, or pivot to behavior — with clear reasoning, (3) if pivot: concrete
  behavior-feature design + how to avoid the same traps, (4) what to do about ball tracking, (5)
  anything I'm missing. End with a 3-4 sentence "Bottom line".

## Recap of the agreed approach
Selective hybrid, abstain allowed (human review already ships). Decisive metric: date-grouped CV
accuracy of a SIMPLE model on features, vs the per-date prior (0.558) and chance, with permutation +
nuisance controls. Three-outcome framing (go / tracker-not-good-enough / ball-signal-weak).

## What I did since last time
Built classical ball detection (color∪motion, court-masked, static-yellow suppression) + a top-K
beam tracker (motion+smoothness objective, accel gate, straightness filter) + strictly-geometric
features (terminal canonical position, side of net, vertical-travel/last-hitter proxy, out-of-bounds
margins, top-K aggregates) + date/video-grouped CV with permutation & nuisance controls. Then I added
**player suppression**: a torchvision Faster R-CNN MobileNet person detector tags candidates inside
(shrunk) player boxes; the tracker penalizes steps landing in a player body.

## A/B RESULTS (200 dev rallies, balanced, coverage 98.5%, date-grouped CV)
```
                         leave-DATE-out   leave-VIDEO-out   permutation-p   nuisance-only
no player suppression        0.558            0.533             0.057           0.543
WITH player suppression      0.457            0.467             0.873           0.538
per-date prior 0.558 | per-video oracle 0.685 | global prior 0.503
```
- Neither run beats the per-date prior (0.558). No suppression = borderline-null (p=0.057);
  WITH suppression = pure noise (0.457, p=0.87), i.e. suppression made it WORSE.
- Interpretation: the faint signal in the no-suppression run was probably tracks coincidentally
  following PLAYERS (whose court-side weakly correlates with winner); removing players removed it.
  The tracker is not reliably following the ball, and the geometric features mostly describe the
  wrong object.

## The impasse (be realistic with me)
- Classical ball tracking of a **4-21px ball** (5:1 perspective; far ball ~4px) under heavy player
  clutter on a **single, heterogeneous camera** (angles vary wildly across 51 videos; some have a
  huge foreground player occluding half the court) is proving very hard.
- The person detector only finds 2-3 of 4 players (far-side players too small for the 320px detector),
  so suppression is partial.
- **I cannot validate or tune the tracker without ball ground truth, and I cannot reliably produce
  that GT myself** — a 4-21px ball is unjudgeable from downscaled stills; a human watching the video
  could mark it trivially, but the user has asked me to work autonomously. So I'm in the blind-tuning
  trap you warned about, and more tracker tuning has low expected value without GT.

## The pivot I'm proposing (pressure-test this)
The user's GOAL is to DELIVER a winner model — not specifically a ball-tracking one. I now have a
working person detector. The **post-rally behavior signal** (who walks to retrieve the dead ball, who
resets to serve, which side stops moving / disengages, movement asymmetry) is measurable RIGHT NOW
from person boxes + the existing 1,847 rally-winner labels, with **NO ball ground truth needed**. You
earlier said post-rally behavior may be MORE robust than far-side ball tracking and is undervalued.

Proposed next move: build a **behavior-feature audit** using the SAME video-wise framework and the
SAME controls: extract per-player tracks in the window [rally_end .. rally_end + ~3-5s], map to
canonical court via the homography, compute behavior features (per-side player count near baseline vs
net, net displacement toward each baseline = "going to pick up the ball", which side moves first/most,
who walks to serve position), train the same simple model, report date-grouped accuracy/coverage vs
the 0.558 prior with permutation + nuisance controls. Keep ball tracking parked pending optional
human GT.

## Specific questions
1. Given the A/B result, do you agree classical ball-tracking-geometry is not the near-term path to a
   DELIVERED model, and that I should pivot effort to the behavior signal now (it needs no ball GT)?
   Or is that giving up too early on the highest-signal cue?
2. If pivot: what's the most robust, leak-resistant **behavior feature set** from person boxes only
   (doubles, single heterogeneous camera, post-rally window possibly truncated by the highlight cut)?
   What are the failure modes and how do I avoid them (e.g., the post-rally window not existing,
   players walking off, far-side players undetected, camera-specific person-detector biases leaking)?
3. Is there a meaningfully better idea than both that I'm missing — something that uses the existing
   labels + a person detector + audio, no ball GT, and could plausibly deliver ≥0.70 at useful
   coverage on this data?
4. Should I STILL invest in a small human ball-GT set in parallel (to keep the ball path alive), or
   fully commit to behavior+audio until/unless that path stalls too?
