# Handoff: Pivot to Rich Visual Signal Analysis for Scoring

> **TEMP doc — not committed.** Context for the next agent picking up the pickleball
> auto-editor. The mandate: **abandon the cheap shortcuts and build a rich visual
> signal pipeline** for scoring / per-shot understanding. Delete this when absorbed.

---

## 1. TL;DR

- **Rally detection is solved and shipped** (audio + visual fusion, leave-one-session-out
  interval F1 ≈ 0.75). A human-in-the-loop correction→retrain loop for it is also shipped.
- **Scoring works today only via manual winner labeling** (review mode → one click/rally →
  the app's rule engine awards the point). That's fine as a fallback.
- **Every cheap path to *automatic* scoring has been empirically killed** (evidence below).
  The remaining path is a **rich visual signal**: native-resolution temporal ball tracking
  (TrackNet-style) and/or a holistic VLM and/or fine player pose — trained on labels the
  user is willing to make.
- The user has **decided to defer** the big visual build to "the analytics phase" but wants
  the next agent to start **scoping/developing the rich-visual-signal approach**.

---

## 2. What works right now (don't rebuild)

- **Rally detector** = frozen audio CNN (mel-spectrogram → per-window rally prob) + a tiny
  logistic **combiner** over `[audio prob + 14 court-plane visual features]` → intervals
  (hysteresis edge extension). Code: `ml/motion/joint_fusion.py`, `joint_dataset.py`,
  `visual_features.py`; eval `ml/tools/evaluate_joint.py`; model
  `ml/checkpoints/joint_combiner.json`.
- **Player perception** = YOLOv8n + ByteTrack @ **10 fps**, frames decoded at **≤1280px**,
  reduced to **on-court player foot-points** projected to a normalized `[0,1]²` court plane
  (homography). Cached per video at `ml/cache/motion/<stem>.npz` (foot points + track ids).
- **Human-in-the-loop loops** (the product pattern — reuse it):
  - Rally cuts: correct in review → Generate writes `manual` training.json → retrain combiner
    (`ml/tools/retrain_rally_combiner.py`, with leave-one-session-out A/B + Apply/Keep, runs
    out-of-process; GUI: Tools → "Retrain rally detector from corrections").
- **Scoring rules engine** already exists: given "which team won," it cascades the score
  correctly. So the ML target for scoring is just **winning_team** (and, for richer use,
  last-hitter + end_reason).

---

## 3. Shortcuts we KILLED (with evidence — do not re-attempt)

1. **Cheap winner prediction from player-position + audio → DEAD.**
   `ml/tools/winner_probe.py` (re-runnable harness). 1847 rallies / 9 sessions, LOSO. Every
   learned model (LogReg, GBM) over whole / final-5s / final-2s / post-3s windows lands at
   **0.48–0.52 accuracy / ~0.50 AUC = the 0.521 class prior**, worst-fold at or below prior.
   Geometry (kitchen-nearer) and audio-parity heuristics also at chance. The winner is decided
   by a **terminal ball event** (in/out/net) that coarse player-position + audio features
   cannot encode **at any resolution**.
2. **Classical CV ball tracking (motion / color / trajectory heuristics) → DEAD.**
   Native-res probe on `resets1.mp4` (scratch scripts were in `/tmp/ball_*.py`; findings here):
   - The ball IS visible (~**12 px**), recoverable in principle — not a 4px worst case.
   - **Color is a trap**: the most salient red blob is a *stationary wall sign*; the real ball
     is low-contrast yellow-white.
   - Motion-on-unique-frames surfaces the ball but buried in 3–160 limb/paddle/shadow blobs;
     a velocity-gated trajectory linker just chains the clutter into player-localized scribbles.
   - Conclusion: needs a **learned multi-frame model**, not classical heuristics.
3. **Speed-based motion features for rally detection → anti-signal** (earlier finding).
   Occupancy/formation carries the fusion gain; player *speed* is mildly anti-correlated
   (pickleball is slow net play; walking happens *between* points).

---

## 4. Key empirical facts to carry forward

- **The "60 fps" files are effectively ~30 fps**: every-other-frame is an exact duplicate
  (transcode artifact). **Decode analysis at reduced fps (~25–30)** for real inter-frame
  motion; keep the 60 fps source untouched for slow-mo replays (independent `ffmpeg -r`).
  Also: dedup before any motion processing. (Our current 10fps extraction wastes half its
  frames on duplicates.)
- **Current visual data is an extreme abstraction**: 1280px / 10fps / player-foot-points only.
  No ball, no pose, no pixels. A rich-visual pipeline MUST decode at **native resolution** and
  capture ball/pose/pixels — the abstraction, not the compression, is why winner prediction
  failed.
- **`serving_team` / `score_snapshot_at_start` is `None` in ALL training.json** → serve context
  isn't persisted (it's derivable from the score cascade). Populating it is a cheap win that
  helps the scoring state machine and any serve-aware model.
- **Mechanical scoring insight**: `last_hitter` + `end_reason` → winner is nearly deterministic
  (the faulting team loses; a clean winner's team wins). Labeling those two may unlock
  auto-scoring more directly than a winner classifier.
- **Eval discipline**: always leave-one-session-out (group = `YYYYMMDD` video-stem prefix via
  `ml/motion/joint_dataset.py:group_id_for`); never random split. ~9 sessions today.

---

## 5. The rich-visual-signal directions (what to develop)

Three non-exclusive paths; they compose. Prove cheap before expensive (our standing discipline).

- **(A) Holistic VLM** — fine-tune a small VLM (e.g. SmolVLM2) on rally clips → `{winning_team,
  end_reason, shot_type}`. Bypasses explicit ball tracking; trains on existing winner labels +
  future per-shot labels. Heavier compute; resolution caps razor-close line calls. *Likely the
  fastest path to automatic scoring.* Treat as experiment + label-assist first, not
  system-of-record.
- **(B) Ball tracking (TrackNet-family)** — native-res, multi-frame heatmap model + physics
  trajectory fit + visibility output. Highest ceiling (precise shot events, shot type), but a
  real sub-project needing thousands of labeled ball center-points and careful session splits.
- **(C) Fine player pose / kinematics** — the **untested middle path**. Native-res + higher-fps
  per-player pose (body keypoints): lunge, stretch, off-balance, who goes still. Might carry
  winner signal the coarse features missed, without the ball.

**Recommended first move (cheapest escalation):** re-extract a few sessions at **native res +
~25–30 fps + fine per-player kinematics/pose**, re-run `winner_probe.py` unchanged. This tests
"richer motion, still no ball" and tells us whether pose-level behavior carries winner signal
**before** committing to full ball tracking or a VLM. If that's also at chance, go to (A) VLM or
(B) ball tracking.

---

## 6. Labeling plan (the user WILL do this, over weeks — build the UI for it)

ROI order (from adversarial review — label in this order):
1. **winner** (have it; keep expanding)
2. **serve / team context** (populate `score_snapshot_at_start`; mostly derivable)
3. **coarse `end_reason`** (`winner / out / net / error / unknown`)
4. **last-hitter / last-touch team** (higher ROI than ball tracking; cheap from video+audio)
5. **player IDs 0–3** (for per-shot attribution)
6. **ball centers — LAST, selectively**

- Ball labels = **single `(x, y)` center click + visible/occluded flag**, NOT bounding boxes
  (TrackNet trains on center→heatmap; a box on a 12px ball is fiddly and no more informative).
- Label at **reduced fps**, and **correct model proposals** (human-in-the-loop) rather than
  from scratch — reuse the retrain-loop pattern.
- Schema is **already forward-compatible**: `ml/LABEL_SCHEMA_EXTENSION_SPEC.md` defines optional
  `shots[]` (`{t_seconds, player_id, shot_type}`), `players` block, `end_reason`, `serving_side`.
  All loaders (`ml/dataset.py`, `ml/motion/joint_dataset.py`, `ml/examples.py`) ignore unknown
  keys. The review UI (`src/ui/review_mode.py`) already does delete/insert/adjust-rally; extend
  it for per-shot + ball labeling.
- **Stable player identity** is the load-bearing sub-problem for per-shot attribution: anchor
  identity to **court quadrant via homography** (near/far × left/right), not appearance/track-id.
  Only reach for SAM2 if quadrant-role assignment proves insufficient.

---

## 7. Reference pipeline (basketball, similar footage) — borrow ideas, don't copy

A YouTube pipeline: RF-DETR (players+numbers) → SAM2 (tracking) → SigLIP+UMAP+K-means (team
clustering by jersey) → fine-tuned **SmolVLM2** (classify result) → court mapping → shot-event
detection. Notably it classifies the *result with the VLM*, not by precise ball tracking.
- **Transferable lesson**: use learned semantic classifiers where exact physical reconstruction
  is unnecessary (→ supports path A).
- **We're better positioned** than basketball: trivial team assignment (net side, not jersey
  clustering), and an **audio shot-anchor** (paddle pock) they lack.
- **Tooling stance**: keep YOLOv8n + ByteTrack + homography (none are the bottleneck); defer
  SAM2 / RF-DETR until a proven blocker; TrackNet is the right family for (B); VLM = experiment
  + label-assist, not system-of-record.

---

## 8. Hard constraints (must respect)

- **GUI process must NOT load heavy ML in-process** (full opencv-python / ultralytics / Qt have
  a segfault history with mpv). GUI venv = `opencv-python-headless`. Heavy ML runs in
  `.venv-motion` or as a **subprocess** (pattern: `ml/motion/extract_runner.py`; the retrain
  GUI action follows it). `predict_joint` inference is pure-numpy on purpose (no sklearn in GUI).
- **Single GPU** (RTX 3500, 12 GB). Offline batch is fine; favor LoRA / small models.
- **Leave-one-session-out** for every eval claim.
- **NEVER `git add`** the two root files `AUDIO_BOUNDARY_CORRECTION_LOOP_PLAN.md` and
  `WINNER_MODEL_TRAINER_APPROACH_A_IMPLEMENTATION_PLAN.md` (and don't commit this handoff).

---

## 9. Pointers

- **Re-runnable probe:** `ml/tools/winner_probe.py` (re-run after any new feature/label set).
- **Fusion infra to extend:** `ml/motion/{joint_fusion,joint_dataset,visual_features,
  court_apply,court_filter,detector,extract_runner}.py`; `ml/tools/{extract_motion_features,
  train_joint_combiner,evaluate_joint,retrain_rally_combiner}.py`.
- **Label schema:** `ml/LABEL_SCHEMA_EXTENSION_SPEC.md`. **Review UI:** `src/ui/review_mode.py`,
  `src/output/training_data_generator.py`.
- **Data:** ~56 corner-labeled videos at `~/Videos/pickleball/*.training.json` (+ winner labels);
  motion cache `ml/cache/motion/*.npz` (10fps). Known-bad: 7-file `20260504_210035_compressed`
  leak + 2 corrupt intervals (see `ml/splits/audio_clean_2026_06_17/excluded.json`).
- **Decision trail:** three GPT-5.5 adversarial reviews were run this session (fusion plan,
  retrain plan, and this scoring/vision workflow) — their consistent verdict drove the
  "prove cheap first, defer the heavy visual build" discipline reflected here.

---

## 10. Suggested first actions for the next agent

1. Read this doc + `ml/tools/winner_probe.py` + `ml/LABEL_SCHEMA_EXTENSION_SPEC.md`.
2. Decide with the user: **(C) pose/kinematics probe** first (cheapest, re-uses `winner_probe.py`),
   or jump to **(A) VLM** or **(B) ball tracking + labeling UI**.
3. If (C): add a native-res + ~25–30fps + per-player pose extraction path and re-run the probe.
4. Whatever path: keep the human-in-the-loop correction→retrain pattern, and LOSO eval.
