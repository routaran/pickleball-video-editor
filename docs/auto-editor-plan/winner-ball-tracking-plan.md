# Winner Detection via Ball Tracking + Court Geometry — Diagnosis & Plan

**Status:** Design / brainstorm. **No implementation yet.**
**Date:** 2026-06-14
**Author:** investigation session (deep dive requested after first end-to-end auto-edit run)

> **TL;DR**
> - The **rally-boundary (audio) model works** — first real run had <10% boundary error. Keep it.
> - The **winner ("scoring") model did not fail to *run*** — it produced a checkpoint. It **failed to *generalize***: on held-out videos it collapsed to a constant classifier (predicts one class for every clip), val accuracy = the base rate (54.6%).
> - **Root cause (multiply confirmed):** the deciding visual cue — where the ball went out / who missed — is destroyed by the 256×128 / 8 fps top-down "canonical warp." It is **not a label bug, not a code bug, not a data-volume bug.** Even a genuine high-fidelity warp (320×704, 1280-px extraction, 12 fps, ImageNet-normalized) still gave base-rate cross-video accuracy.
> - **The fix the user is asking for is the right one:** stop trying to read the winner from an anonymized whole-court image. Instead **track the bright-yellow ball in full-resolution video, map it to court coordinates via the homography we already compute, and reason about where/how the rally ended.**
> - This document records the diagnosis with evidence, an empirical feasibility probe on real footage, a staged technical plan, a validation strategy against the existing **1,847 labeled rallies**, and explicit decision gates / fallbacks.

---

## Part 1 — Why the scoring (winner) model failed to train

### 1.1 What actually happened

The most recent training run *did* complete and *did* write `ml/checkpoints/best_winner.pt` (45 MB, 2026-06-13 19:33). The checkpoint metadata is the smoking gun:

| Field | Value | Meaning |
|---|---|---|
| `epoch` | 3 | Early-stopped almost immediately (val never improved). |
| `val_accuracy` | 0.5457 | Exactly the validation **base rate**. |
| `confusion_matrix` | `[[0,0],[154,185]]` | **Predicted class 1 for *every* validation clip.** Zero class-0 predictions. |
| `val_per_class_recall` | `[0.0, 1.0]` | Degenerate constant classifier. |
| `temperature` | 11.94 | Calibration had to divide logits by ~12 — the signature of a model wildly overconfident on train but random on val. |

So "failed to train" = **the model learned nothing that transfers to an unseen court.** It memorized the training videos (≈97% train acc historically) and on new videos defaulted to guessing the majority class.

### 1.2 The cause is the representation, proven by elimination

A prior diagnostic session (probes preserved in `/tmp/pb_diag/`) ran the right experiments. Each one removes a candidate explanation:

- **Capacity / pipeline / label sanity** (`run.log`, "overfit-50" test): the model overfits 50 clips to **100%** train accuracy with **both real labels and random labels**. → The pipeline works and the architecture has capacity. A model that can fit random labels but can't generalize real ones has a **data/representation** problem, not a bug.
- **Label correctness**: labels are court-side-aligned by construction (Team 1 → canonical top in every video, enforced by corner click order in `court_calibrator.py` + `compute_homography`). The `serving_team_at_start` snapshot-ordering bug was already fixed (see `review-fixes.md` #1). Per-video class balance is healthy (no single-class videos; min-balance mostly 0.4–0.5). → Not a label bug.
- **Augmentation**: turning augmentation off does not change the cross-video collapse. → Augmentation exonerated.
- **Cross-video yardstick** (`sign.log`, 5-fold, every video held out once, 1,847 rallies / 51 videos):
  - raw model, fixed sign: **51.4%** (chance)
  - per-video majority prior: **58.6%**
  - **oracle** per-video sign (best case if we could perfectly flip each video): **59.8%** → only **+1.2%** over the prior.
  - 23/51 videos sat *below* chance with a global sign.
  → Even a perfect per-video correction barely beats "always guess this video's majority." The cue **does not transfer** to unseen courts.
- **Fidelity is not the lever** (`hifi_ram.log`, the decisive test): rebuilt the entire clip representation at **320×704 portrait, 1280-px extraction, 12 fps, ImageNet-normalized**, trained cross-video. Best val accuracy over all epochs = **54.6% = base rate**. Oracle sign = 60.8% = the prior. **Zero lift.**

**Conclusion:** at any practical warp resolution, the winner-deciding event is not recoverable from the anonymized top-down court image. The model has nothing reliable to latch onto, so it collapses to the base rate. This is a **representation-fidelity wall**, and — critically — **more warp resolution does not climb it.**

### 1.3 Why the *boundary* model works but the *winner* model doesn't

They are different problems. Rally **boundaries** come from **audio** (the *pock* of paddle hits and the gaps between them) — a strong, resolution-independent, court-independent signal. Rally **winners** require reading a subtle, spatially tiny, late-in-the-rally *visual* event (ball lands out by a few cm; ball clips the net; a player whiffs). Audio tells you *when* a rally ended, not *who won it*.

### 1.4 What this means for the path forward

The winner signal lives in **the ball and its relationship to the court lines**, not in a whole-court texture. To read it we must:
1. Keep the ball at **full pixel fidelity** (do **not** squish it into a 256-px canvas), and
2. Use the **court geometry** (lines, net, bounds) explicitly rather than hoping a CNN re-derives it.

That is exactly the ball-tracking + court-boundary approach requested.

### 1.5 "Why not just train on full 1080p frames instead of compressing them down?"

A natural question (the source is already H.264-compressed, so the warp+downscale feels like throwing away the last of the detail). It won't fix the winner model on its own, for three layered reasons:

1. **Downscale ≠ warp.** Two lossy steps happen, not one. The downscale shrinks pixels; the **homography warp** maps the near baseline (~1,752 px) *and* the far baseline (~353 px) both to one canonical width — downsampling the near ball and *upsampling* the far ball (interpolation can't recover detail compression already removed). The hi-fi probe already tested 320×704 / 1280-px / 12 fps / ImageNet-norm and got **base rate** cross-video — much of the "more resolution" hypothesis is already spent.
2. **A global-average-pooled classifier averages the ball away at *any* resolution.** The model is a whole-frame ResNet-18 ending in global average pooling → every frame collapses to one 512-vector averaged over all spatial cells. At true 1080p the ball is ≈0.017% of the frame (near) / ≈0.0006% (far); ResNet-18's stride-32 pre-pool map is ~60×34 ≈ 2,040 cells, so the ball occupies <1 cell and GAP divides its contribution by ~2,040. Even with infinite resolution this architecture structurally cannot route a 4–21 px ball to the decision head — it falls back on global court/player cues that don't transfer. **Resolution helps detectors/heatmap models, not GAP classifiers.**
3. **More pixels widen the generalization gap.** Overfit-50 proved the model memorizes *any* labels (real and random) to 100% — capacity was never the issue. More resolution gives more handles to fingerprint individual training clips (players, court scuffs, lighting). With only ~40 distinct courts, the bottleneck is **court/condition diversity, not pixels per clip**, and higher res tends to make cross-video overfitting *worse*.

**Reframe:** feeding full-res frames and hoping the model finds the ball is ~80% of the way to a ball detector, done badly (no localization supervision, tiny data). The ball-tracking plan keeps the ball at full fidelity *and* uses an architecture that localizes it *and* reuses the homography — strictly the better use of those 1080p pixels.

**The one untested variant** is *full-res, court-cropped, no warp* into a higher-res / localization-aware model. Prediction: ≤59% cross-video (≤ the per-video prior). If we want certainty rather than argument, run it through the §4 video-wise K-fold yardstick (cost: a few GPU-hours + a large native-res cache rebuild; mind the `num_workers` disk-leak / OOM gotchas) before investing further. A result at/below the prior confirms the pivot to tracking.

---

## Part 2 — Empirical feasibility probe (run on real footage)

Before committing to a plan I tested the central assumption — *can we actually find the yellow ball?* — on real frames from `20260611_213043_compressed.mp4` (a manually-labeled game). Findings:

### 2.1 The source video is good; the warp was the problem
- Source is **1920×1080 @ 60 fps, H.264**. Plenty of raw fidelity. The winner pipeline was throwing it away by extracting at 640 px and warping to 256×128.

### 2.2 Strong perspective is the dominant constraint
The camera sits behind one baseline shooting across the net. Measured from this game's corners:

| | Near baseline | Far baseline | Ratio |
|---|---|---|---|
| Court width in pixels | ~1,752 px | ~353 px | **4.96:1** |
| Pixels per metre | 287 | 58 | |
| **Estimated ball diameter** (7.4 cm) | **~21 px** | **~4 px** | |

→ The ball is **very trackable on the near half (~21 px)** and **marginal on the far half (~4 px)**. Any plan must treat near-side and far-side events asymmetrically, and must allow **abstaining** when the deciding event happens far from the camera.

### 2.3 Color alone is NOT sufficient
HSV optic-yellow thresholding (`H∈[22,55], S≥70, V≥120`) inside the court polygon returns **multiple candidates every frame**: court-edge tape markers, the net center strap, and players' yellow/light clothing all pass. A near-static yellow blob recurred at ~(1015, 475) across *different* rallies — a fixed object, not the ball. **A pure color detector cannot disambiguate the ball.**

### 2.4 Motion alone is NOT sufficient
3-frame motion differencing inside the court returns **24–43 moving candidates per frame** — dominated by players' arms, paddles, and shadows. Annotated montages show the candidate circles cluster on players, not the ball.

### 2.5 The ball *is* present; isolating it needs temporal trajectory association
In both the color and motion candidate sets, the ball does appear as a small, fairly circular, yellowish, *moving* blob. What separates it from every distractor is that **its position across frames forms a smooth, fast, near-ballistic path**, whereas limb/paddle/shadow motion is erratic and spatially anchored to a player. This is the well-studied "small fast ball in racquet sports" problem; the proven solutions all rely on **multi-frame trajectory reasoning**, not single-frame detection.

**Feasibility verdict:** Tracking is feasible on the near ~⅔ of the court with classical CV; far-baseline events are marginal and should trigger an abstain-to-human. This is a real but bounded engineering build — *not* a wall like the warp-classifier was.

Artifacts: `/tmp/pb_diag/ball/{r15,r25}.jpg` (color), `/tmp/pb_diag/ball/{r15,r25}_motion.jpg` (motion). Probe scripts: `/tmp/pb_diag/ball_probe.py`, `/tmp/pb_diag/motion_probe.py`.

---

## Part 3 — Proposed approach: track the ball, reason about the court

### 3.1 Pipeline shape (replaces Stage 2 "Winner Classify")

The contract is unchanged, so this drops into the existing orchestrator. `ml/predict_winner.predict_winners(...)` currently returns `list[(winning_team:int, confidence:float)]` where `winning_team` is a **court-side team index** (0 = canonical-top = Team 1), compared against `score_state.serving_team` in `auto_edit.py:389`. A ball-tracking winner detector produces the **same output type** — including an explicit **low confidence / abstain** so the existing human-review path handles the rest.

```
For each rally interval (start_s, end_s) from the audio model:
  A. Detect ball candidates per frame   (color ∪ motion, full-res, inside court+margin)
  B. Link candidates into a trajectory   (ballistic gating / Kalman / min-cost path)
  C. Map trajectory pixel→court metres    (existing homography from the 4 corners)
  D. Detect the terminal event            (last bounce / net contact / out-of-bounds)
  E. Apply pickleball end-of-rally rules  (who committed the fault → who won)
  F. Emit (winning_team, confidence)       (abstain when the track/terminal event is unreliable)
```

Stages C–E are *deterministic geometry + rules* — the same philosophy that makes the existing `ScoreState` engine reliable. Only A–B are "perception," and unlike the warp-classifier they operate on full-resolution pixels where the ball actually exists.

### 3.2 Stage A — Ball candidate detection (full resolution)
- Operate on native 1080p frames at high temporal density (≥30 fps; the source is 60 fps) over the last ~2–4 s of the rally — the ball is fast, so frame rate matters more than it did for the classifier.
- Candidate generators (union, then score):
  - **Color prior:** optic-yellow HSV mask, but used as a *weight*, not a gate (§2.3).
  - **Motion prior:** background subtraction (MOG2) or 3-frame differencing to favor moving pixels.
  - **Shape prior:** small area + high circularity + size consistent with the *local* perspective scale (use the homography to predict expected ball px-size at each court location — ~21 px near, ~4 px far).
- Restrict to the court polygon **plus a generous out-of-bounds margin** (an "out" ball lands *outside* the lines — the margin is where the deciding event often is).

### 3.3 Stage B — Trajectory association (the crux)
This is where the ball is separated from the player-motion clutter. Two routes, in ROI order:

- **B1 — Classical multi-frame tracker (start here; needs no new labels).**
  Link per-frame candidates into tracks using a constant-velocity/gravity motion model with gating (Kalman filter or a global min-cost path over a candidate graph, à la the trajectory-optimization trackers used for tennis/badminton). Score tracks by smoothness, speed, and length; keep the single best ballistic track per rally segment. Player-limb candidates won't sustain a long smooth fast path and fall away.
- **B2 — Learned heatmap detector (escalate only if B1 coverage is too low).**
  A TrackNet-style CNN that consumes a few stacked frames and regresses a ball-position heatmap is the SOTA for tiny/blurry racquet-sport balls and is far more robust on the far half. **Cost:** it needs **per-frame ball-position labels, which we do not currently have** (the corpus has rally *winner* labels only). Bootstrap path: use B1 to auto-propose tracks, have a human correct them in a lightweight tool, then train B2 on the corrected tracks. Only pay this cost if B1's confident-coverage is too small to be useful.

### 3.4 Stage C — Pixel→court mapping (already solved)
`ml/video_features.compute_homography(corners)` already yields the 3×3 transform from source pixels to the canonical court rectangle; the corners are stored per video in the training JSON (`video.court_corners`). Apply it to ball-track points to get **court-relative coordinates in metres** (pickleball court = 6.10 m × 13.41 m). This gives exact in/out vs. the lines and which side of the net the ball is on — no learning required. (One caveat to handle: the homography is a *ground-plane* mapping; a ball in the air projects to a court point that is biased toward the camera. For bounce/in-out decisions we care about the ball *at floor contact*, where the bias is ~0, so this is acceptable — but it must be accounted for, not ignored.)

### 3.5 Stage D — Terminal-event detection
The rally outcome is decided by the **last meaningful ball event**. From a clean track:
- **Bounce:** local minimum of the ball's vertical image trajectory / sharp velocity change → a floor contact. The *last* bounce and its court location matter most.
- **Net contact:** trajectory decelerates/stops near the net plane (known from the homography mid-line).
- **Out:** terminal bounce maps to a court coordinate outside the lines (+ tolerance).
- The audio boundary model already pins *when* the rally ended, which bounds the search window for the terminal event — a useful cross-check.

### 3.6 Stage E — Winner inference rules
Pickleball: a rally ends on a **fault**; the faulting side loses. Map terminal events to faults:

| Terminal event | Who faulted (loses) |
|---|---|
| Ball bounces twice in-bounds on side X, no return | Side X (failed to return) |
| Ball lands **out** of bounds | The side that **last hit it** (use pre-terminal travel direction to identify) |
| Ball hits the **net** and doesn't cross | The side that hit into the net |
| Ambiguous / no clean terminal event / far-side & low track quality | **Abstain → human review** |

Direction of travel just before the terminal event identifies who hit last, which (with the bounce location) resolves the in-vs-out / net cases. This is encodable as deterministic rules over the track — and like `ScoreState`, it should be unit-tested against hand-constructed trajectories.

### 3.7 Stage F — Confidence & abstain
Emit a calibrated confidence from concrete track-quality signals: track length/continuity, candidate ambiguity, distance of the terminal event from the camera (far = less trustworthy, per §2.2), and rule-margin (clear out vs. on-the-line). **Abstain liberally** at first: the human-review loop already exists (`auto_edit.py` flags every scored rally today), so the realistic near-term win is **shrinking** review load by auto-confirming the high-confidence near-court cases, not eliminating review.

---

## Part 4 — Validation strategy (use the data we already have)

We do **not** need new winner labels to validate this — the corpus already has **1,847 manually-labeled rallies across ~51 games** (52 training-ready JSONs: schema 1.1 + `court_corners` + `winning_team`, `generated_by != auto_edit`).

- **Yardstick to beat** (from `sign.log`, the honest cross-video numbers):
  - chance / current warp-model: **51.4%**
  - per-video majority prior: **58.6%**
  - A ball-tracking detector is only worth shipping if **accuracy-on-non-abstained rallies** is well above this (target ≥85–90% on the rallies it *doesn't* abstain on), at a **coverage** (non-abstain rate) high enough to meaningfully cut review work.
- **Two metrics, always reported together:** (1) accuracy on non-abstained rallies, (2) coverage (fraction not abstained). A detector that's 95% accurate on 30% of rallies is a real win; 70% on 100% is not.
- **Video-wise evaluation only** (never rally-wise) — reuse the existing K-fold harness shape from `/tmp/pb_diag/sign_consistency_probe.py` and the `ml/evaluation/` splits utilities. There is no per-video "sign" to fit here (geometry is absolute), which is itself an advantage over the classifier.
- **Slice the metrics by near/far terminal-event location** to confirm the §2.2 prediction (near should be strong, far weak) and to set the abstain threshold empirically.
- **Stage-A/B intrinsic check:** on a handful of rallies, overlay the recovered track on the video and eyeball it. Tracking quality is the gating risk; verify it directly before trusting downstream rules.

---

## Part 5 — Risks, unknowns, and fallbacks

| Risk | Likelihood | Mitigation / fallback |
|---|---|---|
| Far-baseline ball (~4 px) untrackable | High (measured) | Abstain on far-side terminal events; rely on human review there. Camera-placement guidance for future recordings (see §7). |
| Player clothing / court tape / net strap fool color | High (observed) | Trajectory association (§3.3) is the disambiguator; color is only a weight. |
| Bounce vs. low ball ambiguity from a single view | Medium | Use velocity-profile + audio cross-check; abstain when unresolved. |
| Homography air-projection bias | Medium | Decide on floor-contact points where bias ≈ 0; document the assumption. |
| Occlusion (player blocks ball at the key moment) | Medium | Track interpolation across short gaps; abstain on long gaps. |
| Learned detector needs labels we don't have | Certain (for B2) | Start with label-free classical B1; bootstrap B2 labels from B1 + human correction only if needed. |
| Whole build underdelivers | Possible | **The human-in-the-loop fallback already shipped** (every scored rally is a 1-click confirm/flip with cascade re-score). Ball tracking is upside on top of a working manual loop, not a prerequisite. |

**Secondary issue to revisit (from prior diagnosis, currently masked):** 23/51 videos sat below chance with a global sign — more than the Team1→top convention alone predicts. Likely causes: occasional corner-calibration slips, and/or **teams switching ends mid-game while corners are calibrated once.** Ball-tracking geometry is tied to which *team* is which only via the same corner convention, so before trusting any winner system, audit whether teams change ends mid-video and whether a per-game side bit (or re-calibration at side changes) is needed.

---

## Part 6 — Phased implementation outline (for later; no code now)

1. **Phase A — Tracker spike (classical, label-free).** Build Stage A+B on ~5 labeled games; overlay tracks on video; measure per-frame track coverage near vs. far. **Gate:** is the near-court track clean enough to reason on? If no → reconsider B2 or camera changes before going further.
2. **Phase B — Geometry + rules + abstain.** Add Stages C–F. Hand-build trajectory unit tests for each fault type. Wire the same `(winning_team, confidence)` output contract.
3. **Phase C — Cross-video validation.** Run the video-wise K-fold yardstick over all 52 training-ready games. Report accuracy-on-covered + coverage, sliced by near/far. **Gate:** beat the 58.6% prior decisively on covered rallies at usable coverage.
4. **Phase D — Integrate as Stage 2 alt path.** Feed confident predictions as the review pre-fill; abstained rallies keep today's amber-flag review. Measure the real metric: **% of review clicks eliminated.**
5. **Phase E (optional) — Learned detector (B2).** Only if Phase A coverage is the bottleneck. Bootstrap labels from B1 + human correction.

---

## Part 7 — Cheap wins worth noting (orthogonal to the build)

- **Fix the stale docstring** in `ml/predict_winner.py` (says "0 = server wins, 1 = receiver wins"). The value is actually a **court-side team index** (0 = canonical-top = Team 1), as used in `auto_edit.py:389`. Misleading for the next implementer.
- **Camera guidance for future games:** raising/centering the camera (or a second angle) would shrink the 5:1 near/far perspective ratio and is the single highest-leverage *data-side* change for far-court trackability. Worth a note in the recording checklist even if we never touch the old footage.
- **Don't delete `best_winner.pt` blindly**, but recognize it is a constant classifier — it should not be trusted as a tiebreaker. Its only current role is the non-authoritative pre-fill, which human review overrides anyway.

---

## Appendix — Evidence index

- Checkpoint metadata: `ml/checkpoints/best_winner.pt` → epoch 3, val 0.5457, confusion `[[0,0],[154,185]]`, temperature 11.94.
- Prior diagnosis probes (preserved): `/tmp/pb_diag/run.log` (capacity/overfit-50), `/tmp/pb_diag/sign.log` (K-fold cross-video yardstick), `/tmp/pb_diag/hifi_ram.log` (high-fidelity warp still base-rate), `/tmp/pb_diag/within_video_probe.py`, `/tmp/pb_diag/fidelity_probe.py`, `/tmp/pb_diag/aspect_probe.py`.
- This session's ball-feasibility probes: `/tmp/pb_diag/ball_probe.py`, `/tmp/pb_diag/motion_probe.py`; images under `/tmp/pb_diag/ball/`.
- Corpus snapshot (2026-06-14): 79 `.training.json` under `~/Videos/pickleball/`, all schema 1.1; 59 manual + 20 `generated_by` absent, 0 `auto_edit`; 58 with `court_corners`; **52 training-ready files, 1,847 labeled rallies.**
- Source video spec: 1920×1080 @ 60 fps H.264. Measured perspective (game `20260611_213043`): near baseline ~1,752 px / far ~353 px (4.96:1); ball ≈21 px near, ≈4 px far.
- Key code touchpoints: `ml/auto_edit.py` (orchestrator, Stage 2 call + all-rallies review flag), `ml/predict_winner.py` (output contract), `ml/video_features.py` (`compute_homography`, `warp_clip_to_canonical`, ffmpeg extraction), `ml/config.py` (`WinnerModelConfig`), `src/ui/widgets/court_calibrator.py` (corner click order).
</content>
</invoke>
