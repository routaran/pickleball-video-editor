# Model Training & Benchmark Report — 2026-06-16

**Run by:** automated training session (Claude Code)
**Data:** `/home/rkalluri/Videos/pickleball/` (79 `*.training.json` label files, 3,130 annotated rallies, ~219 GB of `.mp4`)
**Hardware:** NVIDIA RTX 3500 Ada Laptop GPU (12 GB), CUDA, torch 2.11.0+cu130, Python 3.14.5
**All run artifacts/logs:** `/home/rkalluri/pickleball_training_run_20260616/`

---

## TL;DR

| Model | Trained? | Benchmark result | Verdict |
|---|---|---|---|
| **Audio rally-boundary** | ✅ Yes | F1 **0.508**, P 0.438 / R 0.605 (IoU 0.5, full corpus) | Works, but over-segments (+38%); metrics optimistic (see caveats) |
| **Rally-winner classifier** | ⚠️ Trained, but degenerate | Val acc **0.544 = majority-class baseline**, balanced acc **0.500** | **Effectively non-functional** — learned nothing (predicts one team for everything) |

**Two code/data blockers had to be worked around to train the winner model at all** (a real code bug + one corrupt annotation — both detailed below and **need fixing**). **No source code was modified**, per instruction. **5 UI tests are failing** (stale expectations — listed at the end).

---

## 1. Audio Rally-Boundary Model

### Training
- Command: `python -m ml.cli train --data-dir <data> --epochs 30 --batch-size 64 --seed 42`
- Auto-CUDA. Internal seeded 80/20 split: **63 train / 16 val** videos → 165,395 train windows, 66,729 val windows. Positive-class weight 2.73. Model: 355,521 params.
- **Early-stopped at epoch 14** (patience 5). **Best val loss 0.6127** (epoch 9). Window-level val accuracy peaked ~86%; at the best-loss epoch: acc 83.7%, precision 0.567, recall 0.652.
- Wall time ≈ 20 min. Checkpoint: `ml/checkpoints/best_model.pt` (overwritten; prior version backed up — see §6).

### Benchmark (`ml.tools.evaluate_boundaries`, full corpus, IoU 0.5)
| Metric | Value |
|---|---|
| Precision | 0.438 |
| Recall | 0.605 |
| **F1** | **0.508** |
| Predicted vs ground-truth rallies | 4,294 vs 3,106 (**over-segments by ~38%**) |
| Boundary MAE | 1.58 s (start 1.36 s / end 1.79 s) |
| Merges / over-segmentations | 248 / 197 |
| False-positive active time | 6,832 s |

### Interpretation
The audio model detects rally boundaries with moderate quality but **over-predicts heavily** (1,188 more rallies than exist), which drives precision down to 0.44. It is usable as a first-pass detector but would benefit from threshold tuning (the `--threshold`, `--min-rally`, `--merge-gap` flags on `evaluate_boundaries`/inference exist for exactly this) — tuned against a *proper* held-out split, not the full corpus.

### ⚠️ Benchmark-validity caveats (numbers are optimistic)
1. **No held-out test set exists on disk.** The eval ran over all 79 videos, including the 63 the model trained on → reported F1 is optimistic vs true generalization. The honest held-out signal is the *training* val curve (best val loss 0.6127), but that is window-level, not rally-level.
2. **Train/val leakage from shared source videos.** The split is per-annotation-file, and several annotation files point to the *same* recording. Example: `20260504_210035_compressed` appears in **both** the train and val lists. Same audio on both sides of the split inflates the val metric.

---

## 2. Rally-Winner Classifier

### What it took to train it (two blockers)
The winner model **could not be trained on the first two attempts**:

1. **CODE BUG — AMP GradScaler (needs a fix).**
   `ml/train_winner.py:690` calls `torch.amp.GradScaler(device_type="cuda")`, but `GradScaler.__init__` does not accept `device_type` (only `autocast` does). With `--amp` this raises `TypeError: GradScaler.__init__() got an unexpected keyword argument 'device_type'` immediately. The test suite never exercised the CUDA+AMP path, so it went undetected.
   **Workaround used (no code change):** dropped `--amp` and trained in FP32 with `--batch-size 4 --grad-accum-steps 2` (effective batch 8). The no-AMP path (`scaler=None`) is clean.
   **Recommended fix:** `torch.amp.GradScaler("cuda")` (or `GradScaler(device="cuda")`).

2. **DATA BUG — one corrupt rally annotation (needs a fix).**
   After dropping `--amp`, training crashed in the validation phase with:
   `RuntimeError: ffmpeg returned insufficient frame data for .../20260601_223013_compressed.mp4 [352.05-340.85s]: got 0 bytes`.
   Root cause: in **`2026-06-01_G6_SamsherJoel_vs_RaviRandy.training.json`, rally `index 16`** has `start > end` (raw 352.05 → 340.6; padded 351.55 → 341.6) — an impossible, negative-duration window. The `clamp_to_rally_start_v1` clip policy / `extract_clip` do not validate window ordering, so they ask ffmpeg for a backwards window and crash. This killed both winner training *and* winner eval.
   A read-only scan of all 79 files / 3,130 rallies found **exactly this one bad rally** (no other start≥end cases; no rallies beyond video duration).
   **Workaround used (no code change, originals untouched):** built a curated training root at `…/curated_root/` containing symlinks to all 79 originals, except `…_G6_…json` which is a corrected copy with rally 16 dropped (37 → 36 rallies). Trained/evaluated from there.
   **Recommended fix:** correct rally 16 in that file (likely a transposed start/end), **and** add a guard in `extract_clip`/`winner_dataset` to skip or clearly error on `start >= end` so one bad label can't abort a whole run.

### Training (curated root)
- Command: `python -m ml.cli train-winner --root <curated> --epochs 50 --batch-size 4 --grad-accum-steps 2 --device cuda --seed 42 --num-workers 4` (no `--amp`).
- 11,373,506 params; clip tensor `(20, 3, 128, 256)`. Eligible rallies: 1,846 → 1,508 train / 338 val (positional video-wise split).
- **Early-stopped after 6 epochs.** Train loss stuck at ≈ 0.693 (= ln 2, i.e. random for binary). Val accuracy oscillated between 45.6% (predict all-team0) and 54.4% (predict all-team1). **Best val accuracy 54.4%.**
- Wall time ≈ 3.5 min (warm clip cache). Checkpoint: `ml/checkpoints/best_winner.pt` (overwritten; prior backed up — see §6).

### Benchmark (`ml.tools.evaluate_winner`, curated root, val_fraction 0.2, calibration)
| Predictor | Val accuracy |
|---|---|
| **Trained winner_classifier** | **0.544** |
| majority_class | 0.544 |
| always_team_1 | 0.544 |
| always_team_0 | 0.456 |
| score_lead heuristic | 0.515 |
| score_trail heuristic | 0.479 |

- **Confusion matrix `[[0, 154], [0, 184]]`** → the model predicts **team_1 for all 338 validation rallies**. Balanced accuracy **0.500** (pure chance). Calibration ECE 0.0429 (meaningless for a constant predictor).
- Game-sequence metrics: exact-sequence match 0.0%, mean per-rally winner accuracy 0.557.
- Eval skip counts: 239 rallies skipped (`winning_team = None`), 21 (`no_court_corners`), 24 (post-game).
- A benign `WinnerModelConfig mismatch` warning appeared on load (`clip_duration_override_s: saved=None vs current=2.5`); weights still load correctly.

### Interpretation
**The winner model is non-functional.** It collapsed to predicting a single class and is statistically indistinguishable from "always guess the majority team." More epochs will not help — the loss never moved off random. This is consistent with the previously documented **fidelity wall**: at the current clip resolution/representation the model cannot extract a winner signal from the video. Meaningful progress needs a different input signal (higher-resolution clips, ball/player tracking), not more training. Note also that **239 rallies have no labeled winner** and 21 lack court corners, shrinking usable data.

---

## 3. Data-Quality Findings (action items for you)

1. **Corrupt rally** — `2026-06-01_G6_SamsherJoel_vs_RaviRandy.training.json`, rally `index 16`: `start > end`. Fix or remove it.
2. **One recording shared by 7 game annotations** — `20260504_210035_compressed.mp4` is referenced by all of `2026-05-04_G1…G7.training.json`. The audio benchmark scored **0.0 F1 on all 7** (only 19 predictions for the whole file vs 40–55 expected each). Either the path is wrong/truncated or seven games were mistakenly pointed at one file. This also causes the train/val leakage in §1.
3. **No held-out test split / pinned manifests.** For honest grading, create video-wise pinned manifests (the `ml.evaluation.split_manifest` module supports leakage checks) that de-duplicate shared source videos.
4. **239 rallies with `winning_team = None`** — fill these in to grow the winner training set.

---

## 4. Code Bugs Found (need fixing — not fixed here, per "no code changes")

1. **`ml/train_winner.py:690`** — `torch.amp.GradScaler(device_type="cuda")` → `TypeError`. Breaks `--amp` entirely. Fix: `torch.amp.GradScaler("cuda")`.
2. **`ml/video_features.py` / `ml/winner_dataset.py`** — clip extraction has no `start < end` guard; a single malformed rally aborts the whole run with an opaque ffmpeg error. Add validation that skips or clearly reports such rallies.

---

## 5. UI Errors That Need Fixing

`QT_QPA_PLATFORM=offscreen pytest tests/test_config_dialog.py tests/test_playback_controls.py` → **5 failures, 59 passed**. All five are **stale test expectations** (the production UI moved ahead of the tests; these are test-fix tasks, not necessarily runtime bugs):

| # | Test | Expected | Actual | Likely cause |
|---|---|---|---|---|
| 1 | `test_config_dialog.py:78` `test_dialog_has_tabs` | 3 tabs | **4 tabs** | A 4th config tab was added |
| 2 | `test_playback_controls.py:250` `test_tooltips_show_custom_durations` | `"Skip back 0.5s"` | `"Skip back 0.5s (Left)"` | Keyboard hint added to tooltip |
| 3 | `test_playback_controls.py:266` `test_tooltips_integer_durations` | `"Skip back 1s"` | `"Skip back 1s (Left)"` | Keyboard hint added to tooltip |
| 4 | `test_playback_controls.py:277` `test_play_pause_tooltip_updates` | `"Play / Pause"` | `"Play / Pause (Space)"` | Keyboard hint added to tooltip |
| 5 | `test_playback_controls.py:346` `test_set_playing_updates_button_icon` | `"▶"` | `""` (empty) | Play/pause button switched from text glyph to an icon |

**Fix direction:** update these tests to assert the new tab count (4), the `" (Key)"` tooltip suffixes, and icon-based (rather than text-based) play/pause state.

---

## 6. Artifacts & Checkpoints

**Run directory:** `/home/rkalluri/pickleball_training_run_20260616/`
- `STATUS.txt` — stage timeline + exit codes
- `audio_train.log`, `audio_eval.json` (+ `.err`)
- `winner_train.amp_crash.log` (AMP bug), `winner_train.log` (ffmpeg/corrupt-rally crash), `winner_train_curated.log` (successful run)
- `winner_eval.json` (+ `.err`)
- `curated_root/` — 79 `.training.json` (78 symlinks + 1 corrected copy)
- `scan_bad_windows.py`, `build_curated.py`, `run_*.sh` — the helper scripts used
- `checkpoint_backups/best_model.prev.pt`, `best_winner.prev.pt` — **your prior (Jun 13) checkpoints, preserved**

**Live checkpoints (overwritten by this run, as requested):**
- `ml/checkpoints/best_model.pt` — NEW audio model (good; the one benchmarked above)
- `ml/checkpoints/best_winner.pt` — NEW winner model (**degenerate**; restore `checkpoint_backups/best_winner.prev.pt` if the prior one was better)

---

## 7. Recommendations (priority order)

1. **Fix the corrupt rally** (G6 #16) and the **7-way shared `20260504` video** — both directly corrupt benchmarks today.
2. **Fix the AMP `GradScaler` bug** (one line) to re-enable mixed precision (faster, larger batches).
3. **Add a `start < end` clip-window guard** so one bad label can't crash a whole training run.
4. **Build proper video-wise, de-duplicated held-out test manifests** for honest grading of both models.
5. **Winner model:** treat 54.4% (= majority class) as the floor it currently sits at. It needs a stronger input signal (higher-res clips / ball tracking) and more labeled winners (239 are currently `None`) — not more epochs.
6. **Audio model:** tune detection threshold / min-rally / merge-gap to curb the ~38% over-segmentation, evaluated on a held-out split.
7. **Update the 5 stale UI tests** (§5).
