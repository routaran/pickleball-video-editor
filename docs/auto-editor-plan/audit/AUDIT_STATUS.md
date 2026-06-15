# Winner-Tracking Phase-1 Audit — Status

> **SUPERSEDED — see [`../WINNER_DETECTION_FINDINGS.md`](../WINNER_DETECTION_FINDINGS.md) for the final
> conclusion.** This file records the mid-investigation snapshot (ball-tracking phase). The investigation
> continued through behavior + audio modalities and concluded: autonomous rally-winner detection is not
> feasible from this footage; shipped deliverable = abstaining short-rally suggestion + human-in-the-loop.


**Updated:** 2026-06-14. Autonomous build by Claude, collaborating with GPT-5.5 (`/gpt5-review`).
Transcripts: `01`–`04` in this folder. Module: `ml/winner_tracking/`.

## What was built
A full ball-tracking feasibility pipeline (Qt-free, system-ffmpeg only):
- `corpus.py` — 1,846 training-ready scored+labeled rallies / 51 videos / **9 recording-date groups**; stratified dev sampler.
- `clip_io.py` — full-res (1080p60) terminal-window frame extraction (no fixed-N resample).
- `detect.py` — per-frame candidates = optic-yellow HSV ∪ 3-frame motion, court-masked, **static-yellow persistence suppression**, top-40/frame.
- `track.py` — top-K beam DP; **motion+smoothness** objective (speed reward, acceleration gate, straightness filter) after a length-rewarding version locked onto players.
- `features.py` — strictly-geometric features in canonical court space (Team1=top, net=mid); track-quality kept separate (abstain/nuisance only).
- `audit.py` / `evaluate.py` — per-rally caching; date- & video-grouped CV; same-covered baselines; label-permutation + nuisance-only controls; selective accuracy/coverage curve.
- `annotate.py` — renders candidate-overlay + clean terminal frames for a candidate-recall audit.

## Result (200-rally dev sample, balanced, coverage 98.5%)
| metric | value |
|---|---|
| global majority prior (covered) | 0.503 |
| per-date oracle majority | 0.558 |
| per-video oracle majority | 0.685 |
| **geometric model, leave-DATE-out** | **0.558** (= permutation 95th pct) |
| geometric model, leave-VIDEO-out | 0.533 |
| label-permutation p (within date) | **0.057** (fails p<0.01) |
| nuisance-only model | 0.543 |
| selective acc @ 60% / 40% coverage | 0.619 / 0.615 (vs subset prior ~0.51) |

## Verdict (Claude + GPT-5.5 agree)
**Outcome 2 of 3 — "tracker-not-good-enough" (ambiguous). NOT a valid no-go, NOT a build signal.**
Decisive diagnostic: overlays show the best track frequently follows **players (limbs/paddles), not the ball**. Coverage 98.5% just means "a track was found", not "the ball was found", so features are mostly computed off the wrong object. The faint ~10pp edge over same-subset prior at 40–60% coverage is the only positive hint; permutation p=0.057 is borderline.

## GPT-5.5's decision tree for the next move (the gating measurement is candidate recall)
```
ball candidate recall LOW          -> fix detection (resolution / bg-subtraction / learned detector)
recall HIGH but tracker misses     -> player suppression + RANSAC/trajectory reranking
recall HIGH + oracle geom predicts -> BUILD
recall HIGH + oracle geom doesn't  -> real no-go for geometry-only
```
Right now the branch-deciding measurement (candidate recall via a small ball-ground-truth set) is **missing**. GPT recommends a **30–50 rally ball-GT set (10–20 terminal frames each)** measuring: candidate recall @ {4,8,12}px, candidate rank within top-40, HSV-vs-motion source, **fraction of true balls inside person boxes** (hard vs soft suppression), oracle trackability, and oracle winner-signal-from-GT-geometry. Human annotation preferred over agent self-marking (agent self-marking from downscaled stills proved unreliable for a 4–21 px ball).

## Next actions
1. **(autonomous, in progress)** Person-detector soft-suppression: Faster R-CNN MobileNetV3 (downloaded, CUDA) → down-weight candidates inside player boxes; re-run audit; check overlays + predictive signal. Targets the proven player-locking failure.
2. **(recommended, needs human)** A ~30-rally ball-GT set for the decisive candidate-recall + oracle-geometry measurement — the branch-decider above. Tooling (`annotate.py`) is ready.
3. Keep date-grouped CV primary; re-run all controls after any change; report singles/doubles + camera-quality slices.
