# Spec — Court-Polygon Dilation & Identity Tracking

_Status: **COMPLETE & VALIDATED ON HELD-OUT TEST (2026-06-21).** Change 0 + Change 2
implemented; the v2 re-extraction was run (15/15 corner videos, 0 failures); Change 1
(dilation) was swept and 0.12 is optimal; the fusion re-sweep ran with sustain. Results
below. Remaining: the auto_edit wiring (user-gated — see "Integration" at the end)._
_Author context: follow-on to the displacement-gate fix (commit `089b08e`)._

## Results — held-out test (2026-06-21)

Pipeline now stacks two independent wins (held-out test split, IoU 0.5):

| stage | F1 | precision | recall | over_segs |
|---|---|---|---|---|
| original audio (untuned) | 55.6% | 45.0% | 72.6% | 68 |
| + tuned audio post-proc (`smooth_kernel 9`, `merge_gap 1.5`) | 60.0% | 50.6% | 73.7% | 42 |
| **+ motion fusion (veto+sustain @0.12)** | **62.5%** | **53.5%** | **75.1%** | **30** |

Net: **F1 +6.9, precision +8.5, recall +2.5, over-segmentation more than halved**, on
videos the model never saw. The audio half helps every video; the fusion half helps the
9 corner-labeled test videos (7/9 improve), audio-only fallback on the 2 without corners.

**Locked fusion config = bare `FusionConfig()` defaults** (veto `<1.5` det, hysteresis 3,
displacement gate OFF) **+ sustain ON** (`>=3.5` det, sym `>=0.5`), at **dilation 0.12**.

- **Sustain is now net-positive** (val F1 68.5→69.1 adding sustain): ByteTrack-cleaned
  counts reach 4, which the old anonymous-detection counts (capped at 3) never did, so
  sustain can finally fire and bridge over-split rallies.
- **Change 1 verdict: keep dilation at 0.12 — do NOT increase.** The sweep showed 0.22 is
  *worse* (val F1 69.1→68.1): recovering more bodies pulls in spurious detections that
  cause bad sustains. The asymmetric-dilation idea below is therefore unnecessary; the
  overlay gate was not needed because the smaller dilation won on the metrics outright.
- **Caveat:** fused `fp_active_seconds` rose on test (855→958) — sustain occasionally
  over-extends an interval, adding a little recoverable dead-time to a clip. Net F1/recall
  still clearly up; for cuts this is a trim-in-app annoyance, not lost footage.

Sweep artifacts (gitignored cache): `ml/cache/fusion_resweep_val_*.md`,
`ml/cache/audio_postproc_*_2026-06-21.md`.

> **Implemented (Change 0 + Change 2).** `detector.detect_video()` now returns raw
> foot-points (extracted-frame pixels) + per-detection ByteTrack `track_id` via
> `track(persist=True, tracker="bytetrack.yaml")`, processed as a sequential stream
> with a per-video tracker reset for deterministic ids; the court filter/projection
> moved to the cheap path (`ml/motion/court_apply.py`). The `.npz` cache is v2
> (`schema_version=2`): flat `foot_x/foot_y/frame_offsets/track_id` + `scaled_corners`,
> `extract_size`, `t`, `fps_out`, `video_path`; legacy caches (no `schema_version`)
> are rejected with a re-extract message. `displacement` is now **per-track** mean
> frame-to-frame court-plane motion. **Required next step:** re-run the GPU
> extraction in `.venv-motion` to replace the 15-video v1 cache:
> `.venv-motion/bin/python -m ml.tools.extract_motion_features --dir ~/Videos/pickleball --overwrite`

Two upgrades to the motion-perception layer, plus the one **enabling refactor**
that makes the first cheaply tunable. Together they (a) make the on-court count
honest enough to validate **sustain**, and (b) give every detection a persistent
**track id**, which restores a meaningful motion signal *and* is the substrate
for the player-level classification roadmap (player ID, hit attribution).

Standing constraints (unchanged): the heavy YOLO pass runs in `.venv-motion`
only; the cheap feature/fusion path runs in the GUI `.venv` (cv2/ultralytics-
free); fully offline; never `git add` the two root `*_PLAN.md` files.

---

## Why now

- The sweep showed the count-only veto gains are **modest** (+0.8 F1 on val). The
  larger lever is **sustain**, which currently almost never fires because active
  rallies read **3 on-court, not 4** — the 4th player (serving/deep/wide) falls
  outside the dilated court polygon. Sustain needs `n >= 3.5`; it can't trigger
  on a count that's capped at 3. **Dilation makes the count honest → unlocks
  sustain.**
- We just deleted the displacement gate because anonymous-centroid displacement
  is noise. **Tracking** gives per-player displacement (smooth, real), which can
  bring a *meaningful* motion gate back — and feeds Tier-A classification.

---

## Change 0 (ENABLING REFACTOR): cache raw foot-points, not just aggregates

Today `detector.detect_video()` applies the court filter **inside** the detector
and the `.npz` caches only post-filter aggregates (`n_detections`, `displacement`,
…). So the dilation value (currently `0.12`) is **baked into the cache** — tuning
it would mean re-running the GPU pass for every value, exactly the bottleneck we
avoided for fusion.

**Refactor so the GPU pass caches the raw, pre-filter geometry**, and the court
filter + projection + feature-compute move into the cheap (`.venv`) path:

- `detector.detect_video()` returns, per sampled frame: raw person foot-points in
  **extracted-frame pixel space**, the raw box count `n_raw`, and (after Change 2)
  per-detection `track_id`. It no longer applies `filter_on_court`/`to_court_plane`.
- `.npz` schema (new keys; ragged stored flat + offsets):
  - `foot_x`, `foot_y` — `(N_total,)` float32, all detections concatenated
  - `frame_offsets` — `(F+1,)` int, slice boundaries per frame
  - `track_id` — `(N_total,)` int (−1 until Change 2)
  - `scaled_corners` — `(4,2)` float32 (extracted-frame pixel space)
  - `extract_size`, `t`, `fps_out`, `video_path` (provenance)
- New cheap-path step (in `features.py` or a thin `court_apply.py`): rebuild
  `CourtModel(scaled_corners, dilation=X)`, filter raw foot-points, project to the
  court plane, then the existing `compute_frame_features`. **Now `X` is a
  cheap-path knob** — dilation tunes with no GPU, just like fusion did.

Cost: one richer GPU re-extraction (combine with Change 2 below so it's a single
pass). Touch: `detector.py`, `features.py` (+ `extract_motion_features.py` writer,
`predict_fused.py`/`sweep_fusion.py` loaders). Bump the npz cache-key/version.

---

## Change 1: Court-polygon dilation (cheap once Change 0 lands)

**Goal:** recover the real 4th player without admitting adjacent-court players or
spectators.

- Knob: `CourtModel(dilation=...)` (`court_filter.py:51`). Current `0.12` expands
  the convex-hull quad uniformly about its centroid.
- **Preferred: asymmetric dilation.** At this facility the neighbouring court sits
  off the **sidelines**, while open apron sits behind the **baselines** (where
  servers/deep receivers stand). So expand **more along the baseline-perpendicular
  axis** (toward/behind each baseline) and **less along the sidelines**. Use the
  homography to expand in court-axis space rather than uniformly in pixel space,
  so the extra margin goes where players legitimately stand and *not* toward the
  next court. Uniform-bump (`0.12 → ~0.22`) is the quick first cut; switch to
  axis-aware if it pulls in neighbours.
- **Validation gate (mandatory):** re-run `ml.tools.validate_detector` overlays on
  ≥3 videos, including one with an **active neighbouring court**. Accept only if
  active rallies read **4 on-court** AND adjacent-court players stay rejected
  (red dots). This is eyeball-verified, same as the original Step-1 check.
- Then **re-sweep with sustain enabled** (`sweep_fusion.py`, drop `--no-sustain`)
  on val. Keep sustain only if it nets positive; lock the result the same way.

Risk: over-dilation re-introduces neighbour-court bleed (the exact failure the
court filter exists to prevent) → the overlay gate is non-negotiable. Low effort.

---

## Change 2: Identity tracking

**Goal:** persistent `track_id` per on-court player across frames.

- Swap `self._model.predict(...)` → `self._model.track(..., persist=True)` in
  `detector.MotionDetector.person_boxes` / the `detect_video` loop
  (`detector.py:230-316`). Use **ByteTrack** (ultralytics `tracker="bytetrack.yaml"`),
  not BoT-SORT+ReID — ByteTrack is appearance-free and **deterministic**, which the
  offline-reproducibility invariant requires.
- Tracking is **stateful across frames**, so the current 16-frame independent
  batching must become a **sequential** stream (`persist=True` carries track state
  frame-to-frame). Throughput drops; still offline, acceptable.
- `FrameDetections` gains a `track_ids` array aligned with `court_points`; the
  cache stores it (Change 0 schema).
- New per-track features (in the cheap path), replacing the deleted anonymous
  displacement:
  - `per_track_displacement` — mean over live tracks of each track's frame-to-frame
    court-plane movement. **Smooth and real** → candidate for a re-enabled veto
    motion gate (`enable_displacement_gate=True` with a sane threshold).
  - track-count stability / churn (diagnostic).

**Limits — be honest:**
- ID **switches** on net occlusions/crossings are normal. Track ids are stable
  enough for *aggregate motion* and *rough hit attribution*, NOT for perfect
  per-player identity within a long rally.
- Tracking gives **within-video** ids only. **Cross-video** identity (the same
  named player across matches) needs appearance re-ID — a separate effort, out of
  scope here.

Cost: detector change + one GPU re-extraction (do it together with Change 0).

---

## Sequencing — DONE through step 3

1. ✅ **Change 0 + Change 2** re-extraction — v2 tracked cache (15/15, 0 failures).
2. ✅ **Change 1 (dilation)** — swept; **0.12 optimal** (0.22 worse). No overlay gate
   needed (smaller dilation won outright).
3. ✅ **Re-validate fusion** — re-swept on val with sustain; locked config; ran test
   once. **Fusion beats audio-only on test (F1 60.0→62.5).** (Per-track displacement
   gate left OFF — its prior failure mode is resolved by tracking, but it was not
   needed to win; revisit only if precision needs more.)
4. ⏳ **Wire `predict_fused` into `ml/auto_edit.py:292`** — the remaining step (below).

## Integration (USER-GATED — not done autonomously)

The Stage-1 seam is `raw_rallies = predict_video(video_path)` (`ml/auto_edit.py:292`).
Fusion beat audio-only on test, so wiring it is worthwhile — but it is **not a transparent
drop-in**, for one architectural reason:

- **Fusion needs an offline motion-feature cache.** `predict_fused` reads `<stem>.npz`
  produced by `extract_motion_features` in **`.venv-motion`** (YOLO/ByteTrack). The GUI
  runs in `.venv` and **must not** import ultralytics/cv2 in-process (the mpv-segfault
  invariant). So the GUI cannot generate features on the fly — the workflow becomes:
  label corners → run the offline extraction tool → then `auto_edit` uses fused.

Recommended wiring (graceful degradation, safe + additive):
```
# ml/auto_edit.py Stage 1
feat = motion_feature_path_for(video_path)         # ml/cache/motion/<stem>.npz
if corners and feat.exists():
    raw_rallies = predict_fused_intervals(video_path, corners, feature_dir=...)  # uses FusionConfig() defaults
else:
    raw_rallies = predict_video(video_path)        # audio-only (already improved)
```
This keeps the GUI flow working with no YOLO in-process: fusion is used only when a cache
exists, else it falls back to the (already-better) tuned audio path. Match `predict_fused`'s
return shape to the `{"start_seconds","end_seconds"}` dicts `auto_edit` expects. Add a unit
test for both branches. Left for the user because it changes the production cut path and
can't be GUI-tested headlessly.

**Resolved:** the `enable_sustain=True` default is now the *validated* config (sustain is
net-positive on test), so the earlier "ship veto-only" concern no longer applies — bare
`FusionConfig()` == the locked, test-validated config.

## Applying to the 8 new `20260615_200237_compressed_*` files

They share one fixed-camera recording, and `_1_auto.training.json` already has
`court_corners` → **the same corners apply to all 8**. So they can get the full
fusion treatment: inject the shared corners, run `extract_motion_features` on them in
`.venv-motion`, then `predict_fused`. Rally cuts (Stage 1) need no per-game setup; full
score-sim kdenlive still needs each game's players (only `_1`'s is known).
