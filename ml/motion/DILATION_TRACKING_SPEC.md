# Spec — Court-Polygon Dilation & Identity Tracking

_Status: **Change 0 + Change 2 implemented** (code + cv2-free unit tests landed on
`motion-fusion`), pending the one-time GPU re-extraction that rewrites the cache to
the v2 schema. Change 1 (dilation tuning) + the fusion re-sweep remain open and are
now cheap offline knobs (`--dilation` on `evaluate_fused`/`sweep_fusion`)._
_Author context: follow-on to the displacement-gate fix (commit `089b08e`)._

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

## Sequencing

1. **Change 0 + Change 2 in one GPU re-extraction** — cache raw foot-points +
   `track_id` (one pass produces the tunable, tracked cache).
2. **Change 1 (dilation)** — tune offline against the new cache; pass the overlay
   gate.
3. **Re-validate fusion** — re-sweep on val with sustain enabled (honest counts)
   and optionally re-test the displacement gate with `per_track_displacement`.
   Lock the winning config; only then run **test once**.
4. **Wire `predict_fused` into `ml/auto_edit.py:289-299`** if it beats audio-only
   on test.

## Open decision (carry to integration)

`FusionConfig.enable_sustain` currently defaults **True**, but the *validated*
config was **veto-only** (`--no-sustain`). Sustain is effectively inert pre-
dilation (count capped at 3), so it's harmless today — but before wiring fusion
into `auto_edit`, either (a) default it **False** until the post-dilation re-sweep
proves it helps, or (b) keep it on only with a config validated on test. Don't
ship an unvalidated override into the cut path.
