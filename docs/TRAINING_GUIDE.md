# Training the Winner Classifier

## What you're training

`WinnerClassifier` is a ResNet-18 backbone with the final FC replaced by `nn.Identity` (producing a 512-d frame embedding), followed by a lightweight temporal module (`Conv1d(512→128, k=3) → ReLU → AdaptiveAvgPool1d(1)`) and a linear classification head (`128 → 2`). Total parameters: ~11.2 M. Input is a batch of short clips `(B, T, 3, H, W)`; output is raw logits `(B, 2)` — team 0 wins vs. team 1 wins.

Each training sample is the final 2.5 seconds of a rally, sampled at 8 fps (20 frames), with each frame perspective-warped to a canonical 256×128 top-down court view using a homography computed from the four user-clicked court corners. The label is `winning_team ∈ {0, 1}`.

The output checkpoint is saved to `ml/checkpoints/best_winner.pt`. At inference time it is loaded by `ml/predict_winner.py::predict_winners`, which is called inside the auto-edit pipeline.

---

## WARNING: current ~/Videos/pickleball/ state is NOT training-ready

As of 2026-04-24, the corpus has 20 games / 816 rallies. **None** of the 20 training JSONs have `court_corners` yet, and 6 files are still on schema 1.0 with no `winning_team` labels (248 unlabeled rallies). You must complete Steps 1 and 2 below before running training.

---

## Prerequisites

**Install ML dependencies** — the venv is populated from `ml/requirements.txt` by the configure script:

```sh
$ ./configure --enable-ml
```

This installs: `torch`, `torchaudio`, `torchvision`, `numpy`, `scikit-learn`, `decord`, `opencv-python-headless`.

**Training data directory** — by convention `~/Videos/pickleball/`. Each game is one `<name>.training.json` co-located with its `<name>.mp4` (or other video extension). All 20 current files are there.

**Python 3.13** per the project standard. A GPU is recommended but training falls back to CPU automatically if CUDA is unavailable.

---

## Data preconditions (READ FIRST)

The classifier requires schema 1.1 training JSONs with all three of the following:

1. **`video.court_corners`** — a 4-element list of `[x, y]` pixel coordinates clicked in this exact order: Team1-baseline-left → Team1-baseline-right → Team2-baseline-right → Team2-baseline-left.
2. **`winning_team`** per rally — integer `0` (team1) or `1` (team2) on every non-post-game rally; `null` on post-game rallies.
3. **`generated_by` must not be `"auto_edit"`** — absent or `"manual"` both pass. Auto-generated JSONs are excluded until human-reviewed and re-exported.

A file missing any of these is silently dropped from the dataset. A file can pass the file-level gate (criteria 1 and 3) then have every individual rally filtered out at the rally gate (criterion 2) — see Known Caveats.

---

## Step 1: Add court_corners to existing JSONs (interactive, one-time per game)

For each training JSON missing `court_corners`, you click four court-corner points in a Qt dialog. The tool extracts a frame at ~5% into each video and presents it for calibration.

```sh
$ python -m ml.tools.calibrate_existing --root ~/Videos/pickleball/
```

`--root` defaults to `~/Videos/pickleball/` so the flag is optional here.

For each uncalibrated file, the tool:
1. Reads the video path from the JSON.
2. Uses `ffprobe` to get duration, then `ffmpeg` to extract a frame at `duration * 0.05`.
3. Opens a Qt dialog with a `CourtCalibratorWidget` displaying the frame.
4. Prompts you to click four corners in order: Team1-baseline-left → Team1-baseline-right → Team2-baseline-right → Team2-baseline-left.
5. Writes the corners into `video.court_corners` and bumps `schema_version` to `"1.1"` if it was `"1.0"`.

Files already containing `court_corners` are skipped automatically. Closing the dialog without confirming counts as a skip, not an error; rerun the tool to try again.

Expected output (one line per file, then a summary):

```
SKIP: some_game.training.json (already has corners)
DONE: another_game.training.json
...
17 files updated, 3 skipped.
```

Estimate ~5–15 seconds of interaction per video. With 20 uncalibrated files, plan for roughly 10–15 minutes total.

---

## Step 2: Backfill winning_team for older JSONs (automated, one-time)

Six files are on schema 1.0 with no `winning_team` labels, and any schema 1.1 file that predates the field also needs this. The tool re-derives `winning_team` from each rally's existing `score_at_start` and `winner` fields using the re-sync-per-rally algorithm: `ScoreState.set_score(rally["score_at_start"])` before reading `serving_team`. This correctly absorbs any mid-game Edit Score or Force Side-Out interventions whose history was not persisted.

Do not attempt to fix this by replaying `server_wins()` / `receiver_wins()` from scratch — that approach diverges after the first intervention.

```sh
$ python -m ml.tools.backfill_winner_labels --root ~/Videos/pickleball/
```

`--root` defaults to `~/Videos/pickleball/` so the flag is optional here.

Post-game rallies receive `winning_team = null` (correct — they are excluded from training at the rally filter). Files where every non-post-game rally already carries `winning_team` are skipped.

Expected output:

```
Found 20 .training.json file(s) under /home/<user>/Videos/pickleball

SKIP: already_labeled_game.training.json (already has winning_team labels)
DONE: 2026-04-20_G1_BenRavi_vs_CoreyRahman.training.json
...
6 files updated, 14 skipped.
```

If a file has a malformed `score_at_start`, the tool logs a WARN and skips the entire file rather than writing partial labels.

---

## Verifying readiness

After Steps 1 and 2, every file should show `corners=4`, `labeled=N/N` (where the denominator may be less than total rallies due to post-game exclusions), and `gen` absent or `manual`.

```sh
$ for f in ~/Videos/pickleball/*.training.json; do
    python -c "
import json, sys
d = json.load(open('$f'))
v = d.get('video', {})
n_corners = len(v.get('court_corners') or [])
n_rallies = len(d.get('rallies', []))
n_labeled = sum(1 for r in d.get('rallies', []) if r.get('winning_team') in (0, 1))
gen = d.get('generated_by', 'absent')
print(f'{sys.argv[1]}: schema={d.get(\"schema_version\")} corners={n_corners} labeled={n_labeled}/{n_rallies} gen={gen}')
" "$f"
done
```

A ready corpus looks like:

```
2026-04-08_G2_RaviHussein_vs_ChrisAnish.training.json: schema=1.1 corners=4 labeled=50/50 gen=absent
2026-04-08_G3_YunusHussein_vs_RaviAnthony.training.json: schema=1.1 corners=4 labeled=34/34 gen=absent
...
```

Current state for reference (before running prep steps):
- 20 total files, 20 need `court_corners` (Step 1)
- 6 files on schema 1.0 needing `winning_team` backfill (Step 2)
- After both steps: ~792 trainable rallies (816 total minus ~24 post-game)

---

## Running training

With preconditions met:

```sh
$ python -m ml train-winner --root ~/Videos/pickleball/
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--root` | (required) | Directory searched recursively for `*.training.json` |
| `--epochs` | `50` | Maximum training epochs |
| `--batch-size` | `8` | Minibatch size |
| `--device` | `cuda` | Compute device: `cuda`, `cuda:1`, or `cpu` |

There is no `--lr`, `--resume`, `--checkpoint`, or `--patience` flag. Those hyperparameters are hardcoded in `ml/train_winner.py`: backbone LR `1e-4`, temporal+head LR `1e-3`, Adam optimizer, CrossEntropy with class weights, early-stop patience 5 epochs on val accuracy. Edit `train_winner.py` directly to change them.

### What happens during a run

**Dataset load:** every JSON is filtered for schema >= 1.1, `video.court_corners` present, and `generated_by != "auto_edit"`. Filtered files log at DEBUG; the usable rally count logs at INFO. If zero training or zero validation samples survive, training exits with a clear error message before touching any checkpoint.

**Split:** video-wise 80/20, sorted deterministically by path. The last 20% of videos (by sort order) go to validation. Rally-wise splitting is never done — rallies within a single video share lighting, angle, and court, so a rally-wise split would leak information.

**Per epoch:**
1. Train pass with augmentation: 50% horizontal flip (label swapped to match), color jitter ±0.2 brightness/contrast/saturation, temporal jitter ±0.2 s.
2. Validation pass with no augmentation.
3. Log val accuracy, per-class precision/recall.
4. Save checkpoint to `ml/checkpoints/best_winner.pt` if val accuracy improved.

**Early stopping:** if val accuracy does not improve for 5 consecutive epochs, training terminates early.

**Checkpoint directory** is created automatically if it does not exist.

### Console output during training

```
Device: cuda
=== Loading datasets ===
Train samples: 633 (team0=318, team1=315)
Val   samples: 159
Class weights: team0=0.996, team1=1.004
Model parameters: 11,181,642

=== Training ===
Epoch | Train Loss |  Val Acc |     P0     R0 |     P1     R1
---------------------------------------------------------------
    1 |     0.6891 |  57.2%   |  0.601  0.523 |  0.548  0.623
    2 |     0.6214 |  63.5%   |  0.651  0.612 |  0.621  0.659
       New best saved  (val_acc=63.5%)
       Confusion matrix: [[49, 31], [27, 52]]
...
Early stopping after 18 epochs (patience=5)

Best checkpoint saved to: ml/checkpoints/best_winner.pt
Best val accuracy: 74.2%
```

### Expected runtime

On the current ~20-game / ~792-rally corpus: a few minutes per epoch on a recent GPU. On CPU, plan for 30+ minutes per epoch — use `--device cuda` if at all possible.

The production quality target is 30+ games / ~1200+ rallies. The current corpus is functional but borderline; accuracy will improve as more games are added.

---

## Verifying the trained model

Load the checkpoint directly to confirm it is readable:

```python
from pathlib import Path
from ml.winner_model import load_winner_classifier

model = load_winner_classifier(Path("ml/checkpoints/best_winner.pt"), device="cpu")
print("loaded:", sum(p.numel() for p in model.parameters()), "params")
```

Expected output: `loaded: 11181642 params`

Then run an end-to-end smoke test using an existing labeled game:

```sh
$ python -m ml auto-edit \
    --from-training ~/Videos/pickleball/2026-04-08_G2\ RaviHussein_vs_ChrisAnish.training.json \
    --out /tmp/auto-edit-test \
    --checkpoint ml/checkpoints/best_winner.pt
```

Expected console output:

```
Auto-edit complete.
Rallies detected: 50
Low-confidence rallies: 7 (indices: [3, 11, 22, ...])
Final score: 11-8
Output: /tmp/auto-edit-test/2026-04-08_G2 RaviHussein_vs_ChrisAnish.kdenlive
```

Compare the auto-generated `.training.json` in `/tmp/auto-edit-test/` against the source file. Winner predictions and confidence values should agree with the human-labeled file on the majority of rallies; low-confidence rallies (below the default 0.75 threshold) are expected to account for the disagreements.

---

## Known caveats (flagged by code review, 2026-04-24)

**1. Checkpoint config metadata — RESOLVED (commit d9ba004).**
Checkpoints now embed a `WinnerModelConfig` snapshot under a `"config"` key alongside `model_state_dict`, `epoch`, `val_accuracy`, per-class precision/recall, and the confusion matrix. `load_winner_classifier()` compares the stored config against the active one and warns on mismatch, so tuning `clip_duration_s` / `fps_out` / `canonical_width` / `canonical_height` and loading an older checkpoint no longer silently mismatches preprocessing. (Checkpoints written before this change lack the `"config"` key and load without the check.)

**2. Silent rally attrition.**
The file-level usability filter gates on `court_corners` and `generated_by`, not on `winning_team`. A file that passes the file gate can still have every rally dropped at the rally gate (e.g., all `winning_team` values are `null`). This shows up only as an aggregate "Skipped N rally records" log at INFO — easy to miss on a small corpus. Run the verification one-liner from "Verifying readiness" before training.

**3. No `--resume` flag.**
Training cannot resume from a checkpoint. An interrupted run means starting over. Run on a stable machine or accept the restart cost.

---

## Re-training as you collect more data

1. The manual editor exports `generated_by` absent (treated as manual) automatically — no action needed.
2. For games auto-edited and then human-reviewed, re-export from the review UI. This sets `generated_by` to `"manual"`, making them eligible for training.
3. Run `python -m ml.tools.calibrate_existing` to add corners to any new games.
4. Run `python -m ml.tools.backfill_winner_labels` if any new files are on schema 1.0.
5. Re-run training:

```sh
$ python -m ml train-winner --root ~/Videos/pickleball/
```

The previous `ml/checkpoints/best_winner.pt` is overwritten without versioning. If you want to keep the previous checkpoint, copy it manually before retraining.

---

<!-- DRAFT: wiki-source-update 2026-05-31; prompted by 7eef4c9 -->
## Auxiliary tools

Three CLIs support the data → train → evaluate workflow (all `python -m ml.tools.<name>`):

- `audit_training_corpus` — read-only corpus health check: file/rally eligibility, skip tallies, class balance, per-video counts. Run before training.
- `collect_features` — batch feature extraction over the rally corpus, cached idempotently under the features subdir.
- `evaluate_winner` — runs rule-based baselines and (optionally) a trained checkpoint on a video-wise split, reporting accuracy and calibration.

---

## Human-in-the-loop combiner retraining

The rally detector uses a two-stage pipeline:

1. **Frozen audio CNN** (`ml/checkpoints/best_model.pt`) — proposes a per-window
   rally probability from mel spectrograms.  This is never retrained here.
2. **Logistic combiner** (`ml/checkpoints/joint_combiner.json`) — a small
   standardiser + class-balanced logistic regression over `[p_audio + 14 visual
   features]` that lifts held-out interval F1 from ~0.60 to ~0.75.  This is what
   the CLI below refits.

### Retraining workflow

```
Auto Process video                    (ml auto-edit, or GUI Auto-Process button)
  ↓
Review & fix rally cuts in the GUI    (add/remove/adjust segments)
  ↓
Generate → {video}.training.json      (GUI "Generate" action; marked generated_by absent / "manual")
  ↓
python -m ml.tools.retrain_rally_combiner --dir ~/Videos/pickleball
  ↓
Review before→after held-out F1 in the printed JSON line
  ↓
python -m ml.tools.retrain_rally_combiner --apply   ← only if F1 improved
```

### CLI reference

```sh
# Generate mode — computes LOSO A/B validation, writes candidate (does NOT touch live combiner)
python -m ml.tools.retrain_rally_combiner [--dir DIR ...] [--combiner PATH]

# Apply mode — swap candidate into the live combiner after reviewing the JSON
python -m ml.tools.retrain_rally_combiner --apply [--combiner PATH]

# Multiple search directories
python -m ml.tools.retrain_rally_combiner --dir ~/Videos/pickleball --dir /mnt/nas/more
```

| Flag | Default | Description |
|---|---|---|
| `--dir DIR` | `~/Videos/pickleball` | Directory to search for `*.training.json` (repeatable) |
| `--combiner PATH` | `ml/checkpoints/joint_combiner.json` | Path to the live combiner |
| `--apply` | off | Swap the candidate into place |

### Output (generate mode)

Progress is written to **stderr**; exactly **one JSON line** is written to **stdout**:

```json
{
  "status": "ok",
  "eligible": 42,
  "skipped": [{"path": "...", "reason": "missing motion .npz"}, ...],
  "before_loso_f1": 0.742,
  "after_loso_f1": 0.761,
  "delta": 0.019,
  "candidate": "/abs/path/joint_combiner.candidate.json",
  "manifest": "/abs/path/joint_combiner.candidate.manifest.json"
}
```

`before_loso_f1` and `delta` are `null` when there is no prior manifest or when
no training files are newer than the last manifest (single-number mode).

The candidate manifest (`joint_combiner.candidate.manifest.json`) records
`created_at`, `source_audio_model`, `training_file_count`, the `skipped` list,
and the LOSO validation numbers so the decision is auditable.

### Skipped videos

A video is **combiner-eligible** only if:
- The `*.training.json` is not `generated_by: "auto_edit"` (files from an
  unreviewed auto-edit pass are excluded silently).
- The video file exists on disk.
- `video.court_corners` has exactly 4 corners.
- A cached motion `.npz` exists under `ml/cache/motion/`.

Ineligible files (except `auto_edit`) appear in the `skipped` list with one of
these reasons: `"video missing"`, `"missing/!=4 corners"`, `"missing motion .npz"`.
They are never silently dropped.

To add missing motion caches run:

```sh
python -m ml.tools.extract_motion_features --dir ~/Videos/pickleball
```

### What gets retrained

Only the logistic combiner is updated.  The audio CNN (`best_model.pt`) is
**not** touched.  The combiner learns to weight `p_audio` against 14 on-court
visual features; since it is tiny (~16 parameters) a full refit takes seconds
even on CPU.

---

## See also

- `docs/auto-editor-plan/training-data.md` — schema migration, augmentation policy, class-balance rationale.
- `docs/auto-editor-plan/implementation.md` — Phase 2 (Dataset / Model / Training) source spec.
- `ml/train_winner.py` — training loop, hyperparameters, checkpoint format.
- `ml/winner_dataset.py` — dataset construction, split logic, augmentation implementation.
- `ml/winner_model.py` — `WinnerClassifier` architecture and `load_winner_classifier`.
- `ml/tools/calibrate_existing.py` — court-corner calibration tool.
- `ml/tools/backfill_winner_labels.py` — `winning_team` backfill tool.
- `ml/tools/retrain_rally_combiner.py` — combiner retraining CLI (human-in-the-loop).
