# Audio Rally-Boundary Model — Human-Correction Training Loop (Plan)

> **Status:** Plan / not yet implemented. No code has been changed.
> **Scope:** Operationalize a human-in-the-loop correction cycle for the Stage-1
> audio rally-boundary detector, with a rigorous before/after measurement protocol
> and small enabling code changes.
> **Rev 3:** Revised after two rounds of independent GPT-5.5 review. Rev 2 fixed test
> leakage and the train/val split confound (three-way split + `--val-dir`). Rev 3
> adds the round-2 must-dos: a `--model-path` evaluator flag, a **pinned tuning
> protocol** (no tuning on the improved model then judging the baseline with it), the
> **failure-mode metrics** that Step 6 promises but the base evaluator lacks, and
> **training-variance controls** (seeds; optional multi-seed). See §8 for the log.

---

## 1. The Problem

The Stage-1 audio model (`RallyDetector`, `ml/model.py`, ~211K params) detects rally
**start/end times** from match audio. Two characteristic errors:

1. **False positives** — dead time *between* points detected as a rally.
2. **Under-segmentation / merges** — a rally's end is missed, detection runs into the
   next point, two rallies reported as one.

Proposed fix: auto-process 8 new games, manually **refine** the cuts in the GUI (fix
start/end, delete spurious, insert missed), re-export corrected JSON, retrain.

**Worth it?** Yes, with realistic expectations: correcting near-misses is faster than
marking from scratch; it grows the corpus with the model's own failure cases; the
durable value is a **repeatable, measurable process**. Caveats: 8 games ≈ 10% of the
79 existing manual games; audio windows within a game are highly correlated, so the
effective new-sample count is closer to "8 games / courts / audio conditions" than to
the raw window count — **expect modest, possibly noisy gains**. Automation bias and a
low-power 6–8 game test set are handled below.

---

## 2. Key Finding: the loop is already ~95% built

Existing pieces (verified): audio model + `python -m ml train --data-dir`; label
builder (`ml/dataset.py:176` `build_labels_from_rallies`, per-sample 1/0 from
`raw.start_seconds`/`raw.end_seconds`); auto-edit writes `<stem>_auto.training.json`
tagged `generated_by="auto_edit"` (`ml/auto_edit.py:496,514`), skip-filtered out of
**both** training and evaluation; review mode edits start/end + insert + delete +
winner (`src/ui/review_mode.py`, `src/core/rally_manager.py`); manual re-export
defaults `generated_by="manual"` and uses the date/players basename (does **not**
overwrite the `_auto` file); measurement via `ml/tools/diff_reexport.py` and
`ml/tools/evaluate_boundaries.py`. The work is a runbook + measurement protocol +
small code changes (§6).

---

## 3. Methodology pitfalls designed out

Three ways a naive loop yields misleading numbers — all handled below:

1. **Test leakage from tuning** — tuning post-processing on the set you report on
   biases F1 (worse with 6–8 games). → tune on `val_tune`, report once on
   `test_final` (§5 Steps 5–6).
2. **Train/val split confound** — `ml/train.py` does
   `train_test_split(test_size=0.2, random_state=42)` over the file population, so
   adding 8 games reshuffles which **old** games are val and can change the saved
   checkpoint. → fix the val set with `--val-dir` (§6b).
3. **Unfair tuning comparison** — selecting a post-processing config on the *improved*
   model and then judging the *baseline* with it tilts the result. → pin one tuning
   estimand (§5 Step 5).

Residual confounds to control, not eliminate: **training randomness** (init,
dataloader order, CUDA nondeterminism) still makes one-run-vs-one-run noisy at this
scale → fix/log seeds, optionally multi-seed (§5 Steps 1/4, §6d). And `test_final`
degrades into a dev set if reused every cycle → reserve it for one ship decision and
rotate (§5 Step 0).

---

## 4. Approach

Four-set layout: **train_old/** (fitting), **val_tune/** (checkpoint selection +
post-processing tuning; frozen), **test_final/** (one-time reporting only),
**new_corrected/** (the 8 corrected games → added to training). Decisions: retrain
**from scratch** each cycle; **tune post-processing** but only on `val_tune`.

---

## 5. Implementation Plan

### Step 0 — Data layout + hygiene (one-time)

`--data-dir` scans **recursively**, so val/test must be **sibling** dirs of the train
pool. Under `~/Videos/pickleball/`: `train_old/` (point `--data-dir` here),
`val_tune/` (~6–8 games), `test_final/` (~6–8 games), `auto/` (`*_auto` outputs). New
corrected games → `train_old/`.

Pick `val_tune` and `test_final` **once** and freeze. Make both **failure-mode
representative** (long dead times, short rallies, close back-to-back rallies, varied
courts/audio), not "average" games. Source videos for both must stay accessible.

**Hygiene / leakage checks (stronger than path equality — different paths can point to
the same video):** dedup by **(duration, file hash, normalized stem)**, not just
`video.path`; ensure no game appears in more than one split; no duplicate manual JSON
per source video; no `*_auto.training.json` inside train/val/test dirs; verify the
dataset cache key includes **label content** so corrected boundaries invalidate.

**`test_final` policy:** reserve it for **one** ship decision per fresh test set. For
an ongoing loop, do NOT re-judge against the same `test_final` every cycle (it becomes
a dev set) — let `val_tune` carry per-cycle iteration and rotate in new untouched test
games periodically.

### Step 1 — Baseline (from scratch, fixed val, seeded)

```bash
python -m ml train --data-dir ~/Videos/pickleball/train_old/ \
  --val-dir ~/Videos/pickleball/val_tune/ --seed 0 --epochs 30   # --val-dir, --seed: §6
cp ml/checkpoints/best_model.pt ml/checkpoints/baseline_model.pt
```

Log the seed, the train/val file manifest, and the saved checkpoint's epoch + val
metrics. Do **not** touch `test_final` yet (Step 6). Do **not** use the existing
`best_model.pt` as the baseline unless you are certain it never saw a `val_tune`/
`test_final` game.

> **Lower test-power risk (recommended):** run 3–5 seeds for baseline (and improved in
> Step 4) and report paired test deltas across seeds, since a single run differs by
> init/order noise that's nontrivial with this little data.

### Step 2 — Auto-process + correct the 8 new games

GUI Auto-process path (Setup → *Auto-process* → calibrate corners → Start) → review
mode. **Full-game review discipline** (segments are a starting point, not a checklist):

- **Delete** spurious rallies (FPs).
- **Insert** missed rallies; catch misses by **reconciling the rally/point count
  against the known final score** — a count mismatch flags a missed or spurious rally
  that isn't visually obvious.
- **Fix start/end** to the **true raw onset/offset** on every off rally.
- **Define and write down one boundary convention** (e.g. *start = first audible serve
  contact*, *end = last audible ball contact / out-call*) — it sets the MAE target;
  inconsistent conventions make MAE meaningless across games. Keep a short written QA
  checklist so reviews are consistent.

Winner confirmation is **not used** by Stage-1 boundary training (only needed if you
also want the corrected game's video deliverable). Optional: a second reviewer labels
1–2 games from scratch to estimate under-correction.

Preserve each `<stem>_auto.training.json` into `~/Videos/pickleball/auto/` **before**
re-exporting; save the corrected `manual` JSON into `train_old/`.

### Step 3 — Quantify the corrections

```bash
python -m ml.tools.diff_reexport --auto-dir ~/Videos/pickleball/auto/ \
  --reviewed-dir ~/Videos/pickleball/train_old/ --json corrections.json
```

Per-game + aggregate: FPs deleted, rallies inserted (missed), boundary deltas, ranked
hard examples.

### Step 3.5 — Diagnose merges: model vs post-processing (BEFORE retraining)

Retraining only fixes *model-caused* merges. For each merged GT pair from Step 3,
make the diagnosis **reproducible**:

- **Checkpoint:** `baseline_model.pt`.
- **Config:** the inference config that generated the auto labels (or the current
  default if unknown) — state which.
- Dump, per case: **raw** probabilities and **median-smoothed** probabilities
  (`smooth_kernel`), the binary runs, the GT intervals, and the min probability in the
  inter-rally gap. Check whether a sub-threshold valley exists **after smoothing**
  (smoothing can erase a short valley), whether its gap ≤ `merge_gap_seconds` (1.0),
  and the **counterfactual**: would a lower `merge_gap` / higher `threshold` split it —
  and would `min_rally_seconds` (1.5) then discard either resulting segment?

Classify each merge as **post-processing** (valley exists, fused by `merge_gap`/
smoothing → fix is tuning) or **model** (prob stays high through dead time → needs
data/labels). If most merges are post-processing-caused, **tuning (Step 5) is the real
lever and retraining is secondary** — an important finding in itself. (Raw per-window
probs come from `ml.predict.predict_raw`, which exists at `ml/predict.py:57`; a
~30-line throwaway script dumps the traces — not production code.)

### Step 4 — Retrain improved (from scratch, same fixed val, same seed(s))

```bash
python -m ml train --data-dir ~/Videos/pickleball/train_old/ \
  --val-dir ~/Videos/pickleball/val_tune/ --seed 0 --epochs 30
```

`train_old/` now includes the 8 corrected games; `val_tune/` and the seed(s) are
identical to Step 1 → baseline and improved differ **only** by the new training data.

### Step 5 — Tune post-processing on `val_tune` ONLY, with a pinned protocol

§6a/§6c give the evaluator override flags and metrics. **Choose one estimand and
follow it — do not tune on the improved model then judge the baseline with that
config.**

- **Primary (full-system, fair):** tune each model's post-processing on `val_tune`
  *independently* (sweep `merge_gap` × `threshold` × `smooth_kernel`; pick each
  model's best by `val_tune` F1). Report each model on `test_final` with **its own**
  val-selected config. Answers "best baseline system vs best improved system."
- **Secondary (data-only attribution):** also report both models at **one shared,
  frozen** config chosen *before* adding the 8 games. The gap between the two readings
  attributes how much came from **new data** vs **better post-processing** — and ties
  directly to the Step 3.5 finding.

```bash
for mg in 0.5 0.75 1.0; do for th in 0.5 0.6; do for sk in 3 5 7; do
  python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball/val_tune/ \
    --model-path ml/checkpoints/<MODEL>.pt \
    --merge-gap $mg --threshold $th --smooth-kernel $sk --json > tune_${mg}_${th}_${sk}.json
done; done; done
```

Include `smooth_kernel` (≈1.25 s @ kernel 5, hop 0.25 — interacts with `merge_gap`).
`threshold=0.5` may be wrong: `pos_weight=neg/pos` favors recall, so the precision/
recall trade lives in `threshold`.

### Step 6 — Final report, ONCE, on `test_final`

Evaluate baseline and improved on the frozen test set, using `--model-path` so no file
swapping is needed:

```bash
python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball/test_final/ \
  --model-path ml/checkpoints/baseline_model.pt --merge-gap <B> --threshold <B> --smooth-kernel <B> --json > eval_baseline.json
python -m ml.tools.evaluate_boundaries --dir ~/Videos/pickleball/test_final/ \
  --model-path ml/checkpoints/best_model.pt     --merge-gap <I> --threshold <I> --smooth-kernel <I> --json > eval_improved.json
```

Report a **paired per-game table** (low power → never a lone aggregate):

```
game     base_f1 imp_f1  Δf1  fp_Δ missed_Δ merge_Δ startMAE_Δ endMAE_Δ
g_001    0.82    0.87  +.05  -3     0       -1     -0.10s    -0.05s
...
```

Metrics, by source:
- **Free from current output:** F1 at **IoU 0.3/0.5/0.7** (run 3×, vary `--iou`);
  **missed** = `n_ground_truth − n_matched`; **unmatched-pred** = `n_predicted −
  n_matched`; matched-only start/end MAE.
- **Need the §6c metrics addition:** **merge count** (one prediction overlaps >1 GT),
  **over-seg count** (one GT covered by >1 prediction), **FP active-seconds** during
  true dead time.
- ⚠️ **Matched-only MAE has survivorship bias** — it can improve as bad cases become
  unmatched and drop out. Always read it with missed/merge counts.
- If multi-seed (Step 1 note), report deltas per seed (and a bootstrap CI if feasible).

If improved doesn't beat baseline on `test_final`, **do not ship** — re-examine label
quality (Step 2) and the Step 3.5 diagnosis.

---

## 6. Code changes

### 6a. `ml/tools/evaluate_boundaries.py` — overrides + `--model-path` (required)
- Add `--threshold`, `--merge-gap`, `--min-rally`, `--smooth-kernel` (default `None`)
  **and `--model-path`**.
- **Validate:** `0 ≤ threshold ≤ 1`; `merge_gap ≥ 0`; `min_rally ≥ 0`;
  `smooth_kernel ≥ 1` and **odd** (median filter requires odd kernel).
- Build an `InferenceConfig` from overrides; thread it **and `model_path`** through
  `run_boundary_evaluation` → `_evaluate_file` → `_predict_intervals`, changing
  `predict_video(video_path)` → `predict_video(video_path, model_path=..., inference_config=cfg)`
  (`predict_video` already accepts both). ~30 lines.

### 6b. `ml/train.py` — optional `--val-dir` (required for a clean comparison)
When supplied, train on **all** of `--data-dir` and validate on the games in
`--val-dir`, skipping the internal `train_test_split` (`ml/train.py:151-179`). ~15–25
lines. *(Minimal-code fallback: keep the random split and treat the result as the
end-to-end loop effect, not the isolated 8-game value — weaker, not recommended now
that we're measuring carefully.)*

### 6c. Failure-mode metrics (required for Step 6's promised analysis)
The base evaluator reports single-IoU P/R/F1 + matched MAE only. Add **merge count**,
**over-seg count**, and **FP active-seconds** — either extend
`ml/evaluation/event_metrics.py::interval_detection_metrics` (preferred; reused by the
existing per-video/aggregate path) or a small dedicated `report_boundaries.py` that
consumes pred+GT intervals. ~40–60 lines. (Missed/unmatched/multi-IoU need no code —
see Step 6.)

### 6d. `ml/train.py` — seed control (recommended)
Accept `--seed`; set Python/NumPy/PyTorch seeds and log them with the train/val
manifest and the saved checkpoint's epoch + val metrics. ~10 lines. Enables the
multi-seed option and makes runs reproducible.

### Files
- **Modify:** `ml/tools/evaluate_boundaries.py` (6a); `ml/train.py` (6b, 6d);
  `ml/evaluation/event_metrics.py` *or* new `ml/tools/report_boundaries.py` (6c).
- **Unchanged but central:** `ml/predict.py`, `ml/dataset.py`, `ml/config.py`,
  `ml/auto_edit.py`, `diff_reexport.py`, `review_mode.py`, `rally_manager.py`,
  `training_data_generator.py`.
- **Data:** create `~/Videos/pickleball/{train_old,val_tune,test_final,auto}/`.

---

## 7. Verification

1. **6a:** `evaluate_boundaries --dir val_tune/ --model-path ml/checkpoints/baseline_model.pt
   --merge-gap 0.75 --threshold 0.6 --smooth-kernel 7` differs from the default run;
   bad inputs (`--smooth-kernel 4`, `--threshold 1.5`) are rejected; `--model-path`
   demonstrably evaluates the named checkpoint (not always `best_model.pt`).
2. **6b/6d:** with `--val-dir val_tune/ --seed 0`, training logs the val set == the
   `val_tune/` games (not a random subset) and the seed, identically across both runs.
3. **6c:** merge/over-seg/FP-seconds appear in per-video + aggregate output; sanity-
   check on a hand-built pred/GT pair.
4. **Loop integrity:** `auto/` has 8 `*_auto` files, `train_old/` has 8 corrected
   `manual` files, `diff_reexport` pairs all 8 with non-zero corrections.
5. **No leakage:** train logs `SKIP generated_by=auto_edit` = 0 in `train_old/`; the
   hash/duration dedup finds no game across splits.
6. **Result (one-time, `test_final`):** improved beats baseline on the paired table at
   the pinned operating point, read together with MAE and (if multi-seed) per-seed.

---

## 8. Review-response log (GPT-5.5, two rounds)

**Round 1 (folded into Rev 2):** test leakage → three-way split; split confound →
`--val-dir`; merge model-vs-post-proc → Step 3.5; low power → paired reporting +
lowered expectations; metrics hide failures → multi-IoU + FP-seconds + merge/over-seg
+ matched-MAE caveat; automation bias → full-game review, count reconciliation,
written boundary convention; winner work demoted to optional; input validation / odd
kernel; representativeness; threshold/smoothing notes.

**Round 2 verdict — "conditional go"; the two original HIGH issues confirmed resolved
(given `--val-dir` is implemented and the random-split fallback is not used). New
must-dos, all folded into Rev 3:**
- **`--model-path` on the evaluator** (else baseline vs improved needs brittle file
  swaps) → §6a.
- **Pin the tuning protocol** (don't tune on improved then judge baseline with it) →
  Step 5 primary/secondary estimands.
- **Implement the promised failure-mode metrics** (the base evaluator lacks merge/
  over-seg/FP-seconds) → §6c; clarified which metrics are free.
- **Training-variance control** (seeds; optional multi-seed) → Steps 1/4, §6d.
- **Step 3.5 reproducibility** (checkpoint, config, raw-vs-smoothed, counterfactual,
  `min_rally` effect) → Step 3.5; confirmed `predict_raw` exists.
- **`test_final` reuse leaks over cycles** → Step 0 reuse/rotation policy.
- **Stronger-than-path leakage checks** (hash/duration/stem) → Step 0 hygiene.

**Noted, not adopted as blocking:** interval-F1 checkpoint selection (more code; fixed
`val_tune` + frozen `test_final` mitigates); full manifest system with file hashes
(the `--val-dir` + hash-dedup checks achieve the needed determinism more cheaply);
bootstrap CIs (offered as optional under multi-seed).
