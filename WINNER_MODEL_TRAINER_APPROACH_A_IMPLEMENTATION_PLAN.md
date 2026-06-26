# Winner Model Trainer Approach A Implementation Plan

## Status

Revised after two Opus review rounds. The plan now treats the seven review findings as required design constraints, not optional polish:

1. terminal-event-side annotation is required for any far-side conclusion,
2. side mapping must be per-rally/per-segment or restricted to verified constant-side videos,
3. train/val/test splits must be pinned by manifest,
4. checkpoint config auto-loading requires schema/versioning and legacy handling,
5. 5s clips must clamp to rally start with explicit padding/masking and versioning,
6. batch-size/gradient-accumulation comparisons must account for ResNet BatchNorm and optimizer confounds,
7. end-window leakage must be audited before interpreting model gains.

## Purpose

Update the pickleball rally-winner trainer so we can safely test whether the current visual winner-classification approach improves when it receives:

1. higher-resolution source/canonical clips,
2. longer end-of-rally context,
3. higher frame sampling rate,
4. valid side-stratified evaluation of the actual far-side visibility problem.

This plan intentionally focuses only on **Approach A**: improving and evaluating the current winner-classifier training/evaluation pipeline. It does **not** add ball tracking, OpenCV motion features, player tracking, OCR, or a new video architecture. Those approaches remain deferred until Approach A has been measured correctly.

## Background

The current auto-edit pipeline is structured as:

1. audio model detects rally boundaries,
2. `WinnerClassifier` predicts the absolute winning team for each rally,
3. deterministic `ScoreState` simulates scoring from the winner sequence,
4. the review UI allows human correction and re-export.

Current winner-model defaults are defined in `ml/config.py::WinnerModelConfig`:

```text
fps_out = 8
clip_duration_s = 2.5
canonical_width = 256
canonical_height = 128
clip_extract_max_dim = 640
checkpoint_path = ml/checkpoints/best_winner.pt
```

The reported issue is that winner prediction is unreliable when the rally-ending action or ball is on the far side of the court. Because the far-side pickleball is small and hard even for a human to see at 60fps, we should not assume explicit ball tracking is the right first fix. Instead, this plan makes the current trainer configurable, safe, and measurable so we can test whether more source information, more temporal context, and higher frame rate are sufficient.

## Critical measurement correction

A previous version of this plan proposed measuring near/far performance by checking whether:

```text
winning_team == camera_near_team
```

That is **not a valid primary metric** for the user's complaint. It groups by the side that won, not by where the rally-ending action occurred. If the far-side player makes an error, the near-side team wins, so the metric can be inverted relative to the actual visibility problem.

Therefore:

- Winner-side near/far metrics may be reported only as secondary, explicitly non-decisive diagnostics.
- The primary far-side metric requires terminal-event-side annotation, e.g. where the final action/error/winner-defining event occurred.
- No Approach A conclusion may claim to fix far-side visibility unless evaluated against terminal-event-side labels.

## Key distinction: extraction resolution vs canonical resolution

There are two separate resolution knobs:

- `clip_extract_max_dim`: maximum long-side dimension of frames extracted from the source video before homography warp.
- `canonical_width` / `canonical_height`: model input size after court homography warp.

For far-side problems, `clip_extract_max_dim` may be the more important first lever because the homography cannot recover details discarded during source extraction. Increasing canonical resolution alone may only upscale already-lost information. The ablation matrix therefore isolates extraction resolution before increasing canonical model input size.

## Goals

- Allow training multiple winner-model configurations without editing source code.
- Prevent experiment checkpoints from overwriting the production/default checkpoint.
- Ensure training, evaluation, prediction, and auto-edit use checkpoint-compatible clip geometry and timing configuration.
- Add terminal-event-side evaluation so far-side visibility is measured directly.
- Add pinned train/validation/test split manifests so experiments are comparable over time.
- Add resource diagnostics so larger clip experiments are practical and debuggable.
- Produce a repeatable ablation runbook that can determine whether Approach A materially improves far-side winner prediction.

## Non-goals

Deferred until after Approach A evaluation:

- explicit ball tracking,
- OpenCV optical-flow or motion-heatmap features,
- player/person detection or tracking,
- pose estimation,
- scoreboard OCR,
- transformer/SlowFast/VideoMAE-style architecture changes,
- permanent schema migration for event-side labels unless the sidecar workflow proves valuable enough to promote.

## Relevant existing files

Likely implementation targets:

```text
ml/config.py
ml/train_winner.py
ml/cli.py
ml/predict_winner.py
ml/winner_dataset.py
ml/winner_model.py
ml/tools/evaluate_winner.py
ml/evaluation/game_metrics.py
ml/evaluation/confidence.py
ml/examples.py
```

Likely new files:

```text
ml/evaluation/side_metrics.py
ml/evaluation/split_manifest.py
ml/tools/verify_side_annotations.py
ml/tools/export_event_annotation_clips.py
```

Likely documentation updates:

```text
docs/TRAINING_GUIDE.md
docs/auto-editor-plan/README.md or related current ML docs
```

Likely tests:

```text
tests/test_evaluate_winner.py
tests/test_train_winner.py or new focused trainer config tests
tests/test_side_metrics.py
tests/test_split_manifest.py
tests/test_winner_checkpoint_config.py
tests/test_winner_clip_windowing.py
```

---

# Implementation phases

## Phase 0 — Measurement and data-validity prerequisites

### Objective

Before running expensive ablations, make sure the experiment can measure the actual failure mode: rally-ending action on the far side of the court.

Engineering scaffolding may be implemented before this phase is complete, but no experimental conclusion about far-side visibility is valid until this phase is satisfied.

## Phase 0A — Terminal-event-side annotation set

### Required annotation

Create a small but intentionally selected validation annotation set that identifies where the rally-ending event occurred.

Recommended sidecar schema:

```json
{
  "schema_version": "1.0",
  "description": "Terminal event side annotations for winner-model far-side evaluation",
  "annotations": [
    {
      "video_path": "/absolute/path/to/video.mp4",
      "source_json_path": "/absolute/path/to/game.training.json",
      "rally_index": 17,
      "raw_start_seconds": 123.45,
      "raw_end_seconds": 130.20,
      "terminal_event_side": "far",
      "terminal_event_team": 1,
      "event_type": "losing_error",
      "confidence": "high",
      "notes": "far team hit ball into net"
    }
  ]
}
```

Fields:

- `video_path`: absolute path to source video.
- `source_json_path`: training JSON used to identify the rally.
- `rally_index`: rally index from JSON.
- `raw_start_seconds` / `raw_end_seconds`: copied for stability and review.
- `terminal_event_side`: `"near" | "far" | "unknown"`.
- `terminal_event_team`: `0 | 1 | null` if the event can be tied to a team.
- `event_type`: optional but useful, e.g. `"losing_error"`, `"winning_shot"`, `"out_call"`, `"net"`, `"miss"`, `"unknown"`.
- `confidence`: `"high" | "medium" | "low"`.
- `notes`: optional human-readable context.

### Annotation discipline

- Annotators should not see model predictions while labeling terminal-event side.
- Include hard examples: far-side action, near-side action, short rallies, long rallies, ambiguous calls, varied courts/lighting.
- Track `unknown` explicitly rather than forcing low-confidence labels.
- If possible, have a second person review a subset to estimate ambiguity.

### Minimum sample-size guidance

The exact number depends on available data, but the decision metric should not rely on tiny strata. Before using the set for go/no-go decisions, report:

```text
N total annotated rallies
N near terminal events
N far terminal events
N unknown terminal events
N per video/game
```

If either near or far has too few examples to detect a meaningful difference, collect more annotations before drawing conclusions.

### Acceptance criteria

- Evaluation can compute accuracy grouped by terminal-event side.
- Far-side metrics are based on terminal-event labels, not winning side.
- The plan confirms whether a far-side deficit exists before running the full ablation matrix.

## Phase 0B — Per-rally/per-segment side mapping

### Problem

A single per-video `camera_near_team` can be wrong if:

- a video spans multiple games,
- players switch sides,
- the source video is a segment of a larger match,
- court orientation/camera position changes,
- the exported JSON combines rallies from multiple side configurations.

### Requirement

Use per-rally or per-segment mapping whenever side changes are possible.

Recommended side mapping schema:

```json
{
  "schema_version": "1.0",
  "segments": [
    {
      "video_path": "/absolute/path/to/video.mp4",
      "start_seconds": 0.0,
      "end_seconds": 742.0,
      "camera_near_team": 0,
      "verified_by": "human",
      "notes": "single game, no side switch"
    }
  ],
  "rallies": [
    {
      "video_path": "/absolute/path/to/video.mp4",
      "rally_index": 17,
      "camera_near_team": 1,
      "verified_by": "human"
    }
  ]
}
```

Rules:

- Per-rally mapping overrides segment mapping.
- Segment mapping applies only when `raw_start_seconds`/`raw_end_seconds` are inside the segment.
- Per-video constant mapping is allowed only as shorthand for a single verified segment covering the evaluated game.
- Missing mapping must produce explicit `unmapped` counts, not silent assumptions.

### Verification tool

Add a small visual verification workflow, e.g. `ml.tools.verify_side_annotations`, that renders or exports representative frames with the chosen near team annotation so a human can confirm the mapping.

### Acceptance criteria

- Side mapping source is independent of winner labels.
- Per-video constants are not used when side changes are possible.
- Evaluation reports mapped/unmapped sample counts.

## Phase 0C — End-window leakage audit

### Problem

The model sees the final clip window before `raw_end_seconds`. If `raw_end_seconds` includes post-point celebration, score overlays, camera cuts, or other non-play cues, the model may learn winner cues unrelated to on-court visibility. That would make Approach A look successful while failing to solve the real far-side visual problem.

### Required audit

Before interpreting ablation results:

1. Export sample clips from current default settings and proposed 5s settings.
2. Visually inspect a representative set.
3. Record whether the final window contains:
   - on-court terminal action,
   - post-point celebration,
   - score overlay changes,
   - camera movement/cuts,
   - ball retrieval/dead time,
   - previous-rally frames.

### Acceptance criteria

- The plan documents what `raw_end_seconds` means in current training data.
- If significant leakage is found, adjust the clip anchor/windowing before ablations.
- If leakage cannot be eliminated, results must be interpreted as “winner cue recognition,” not necessarily “far-side visibility improvement.”

---

## Phase 1 — Make winner trainer configuration explicit

### Objective

Allow experiments to change clip duration, frame rate, canonical size, extraction size, checkpoint output path, seed, and optimization settings without editing source code or changing default behavior.

### Changes

Update `ml/train_winner.py` so `train_winner(...)` accepts a `WinnerModelConfig` instance and additional training-control parameters.

Add CLI arguments to `python -m ml.train_winner` and `python -m ml train-winner`:

```text
--canonical-width INT
--canonical-height INT
--clip-duration-s FLOAT
--fps-out INT
--clip-extract-max-dim INT
--checkpoint-out PATH
--num-workers INT
--amp
--seed INT
--grad-accum-steps INT
--val-manifest PATH
--test-manifest PATH
--train-manifest PATH
```

Current defaults must remain unchanged:

```text
canonical_width = 256
canonical_height = 128
clip_duration_s = 2.5
fps_out = 8
clip_extract_max_dim = 640
checkpoint_out = ml/checkpoints/best_winner.pt
```

### Checkpoint output behavior

Add `--checkpoint-out PATH` rather than `--run-name` for the first implementation. This is explicit and avoids ambiguous precedence.

If `--checkpoint-out` is omitted, preserve current behavior:

```text
PathConfig().checkpoints_dir / "best_winner.pt"
```

If `--checkpoint-out` is provided:

- expand `~`,
- resolve relative paths from current working directory,
- create parent directory if needed,
- save best checkpoint there,
- print the exact output path.

### Seed behavior

Add `--seed INT` for repeatability and variance measurement. It should seed:

- Python `random`,
- NumPy,
- PyTorch CPU,
- PyTorch CUDA when available.

Do not claim perfect determinism. CUDA/cuDNN may remain nondeterministic depending on operations and settings. Multiple seeds are required for final comparisons.

### Gradient accumulation behavior

Add `--grad-accum-steps INT` to allow larger effective batches when memory-limited.

Important caveat: torchvision ResNet-18 uses BatchNorm. Gradient accumulation does not reproduce true large-batch BatchNorm statistics because each micro-batch computes its own BatchNorm stats. Therefore:

- use gradient accumulation primarily to stabilize optimizer step size when large physical batches do not fit,
- do not claim it exactly matches true larger-batch training,
- for final comparisons, either match physical batch size where possible or rerun baselines under the same physical/effective batch conditions,
- hold LR, weight decay, scheduler, AMP state, and augmentation policy constant across compared runs.

### Tests

Add focused tests for:

- CLI argument parsing/building passes values into `WinnerModelConfig`.
- `--checkpoint-out` is accepted and used by `train_winner(...)`.
- Defaults remain unchanged when no new arguments are provided.
- Checkpoint metadata includes modified config fields.
- Seed parameter is accepted and plumbed to training setup.
- Gradient accumulation updates optimizer at the expected cadence in a small mocked loop.

Avoid expensive training in unit tests. Mock dataset/model save paths where possible.

### Acceptance criteria

- Existing command still works:

```bash
python -m ml train-winner --root ~/Videos/pickleball --epochs 50 --batch-size 8 --device cuda
```

- New command works without code edits:

```bash
python -m ml train-winner \
  --root ~/Videos/pickleball \
  --epochs 50 \
  --batch-size 2 \
  --grad-accum-steps 4 \
  --seed 0 \
  --device cuda \
  --canonical-width 512 \
  --canonical-height 256 \
  --clip-duration-s 5.0 \
  --fps-out 15 \
  --clip-extract-max-dim 1080 \
  --checkpoint-out ml/checkpoints/winner_512x256_5s_15fps_extract1080.pt \
  --amp
```

- Experiment checkpoints do not overwrite `ml/checkpoints/best_winner.pt` unless explicitly requested.

---

## Phase 2 — Checkpoint config schema, legacy handling, and inference safety

### Objective

Prevent silent mismatch between how clips are generated during training and how they are generated during evaluation, prediction, or auto-edit.

### Known issue

`winner_dataset._fetch_clip_tensor(...)` uses:

```python
config.effective_clip_duration_s
```

`ml/predict_winner.py::predict_winners(...)` currently computes clip start from:

```python
config.clip_duration_s
```

This should be changed to use checkpoint-compatible effective duration and full geometry.

### Required checkpoint schema

Add a checkpoint metadata schema version for winner model checkpoints:

```python
{
    "checkpoint_schema_version": "2.0",
    "model_state_dict": ...,
    "config": {
        "checkpoint_path": "...",
        "confidence_threshold": 0.75,
        "fps_out": 15,
        "clip_duration_s": 5.0,
        "canonical_width": 512,
        "canonical_height": 256,
        "device": "cuda",
        "clip_duration_override_s": None,
        "clip_extract_max_dim": 1080,
        "effective_clip_duration_s": 5.0,
        "clip_window_policy": "clamp_to_rally_start_v1",
        "padding_policy": "repeat_first_frame_v1"
    },
    "training": {
        "seed": 0,
        "batch_size": 2,
        "grad_accum_steps": 4,
        "amp": true,
        "train_manifest": "...",
        "val_manifest": "...",
        "selection_metric": "balanced_val_accuracy"
    }
}
```

### Legacy checkpoint handling

Existing checkpoints may lack full config metadata or schema version. Do not silently treat them as current schema.

Safe behavior:

1. If checkpoint has full schema/config, auto-load that config.
2. If checkpoint lacks schema/config but is known to be an old default checkpoint, load with old default geometry and emit a loud warning.
3. If checkpoint lacks schema/config and the caller requested non-default geometry, refuse unless an explicit debug override is passed.
4. Before changing production defaults, backfill important legacy checkpoints with their known actual config or preserve a legacy-default fallback table.

### Prediction and auto-edit config loading

In `ml/predict_winner.py`:

- load checkpoint once,
- derive `WinnerModelConfig` from checkpoint metadata when caller passes `config=None`,
- if caller passes explicit `config`, compare it to checkpoint metadata,
- refuse geometry conflicts by default,
- allow explicit override only for debugging/testing.

In `ml/auto_edit.py`:

- if `winner_config` is None, allow `predict_winners(...)` to derive config from checkpoint metadata,
- do not construct default geometry for an experiment checkpoint,
- surface clear errors in the UI/CLI when checkpoint metadata is missing or conflicting.

### Evaluation config loading

`ml/tools/evaluate_winner.py` already loads checkpoint config for model evaluation. Extend it to:

- report the config used in JSON output,
- report the config in human-readable output,
- include schema version and clip-window policy,
- fail clearly on invalid metadata.

### Effective duration fix

Use:

```python
config.effective_clip_duration_s
```

where prediction currently uses `config.clip_duration_s`.

### Tests

Add/adjust tests for:

- `predict_winners(...)` derives full config from checkpoint metadata.
- `predict_winners(...)` uses `effective_clip_duration_s`.
- explicit runtime config conflict raises a clear error.
- legacy checkpoint without metadata uses old default config with warning.
- auto-edit does not silently run experiment checkpoint with default geometry.
- evaluation uses checkpoint config, not default config.

### Acceptance criteria

- A checkpoint trained with `5.0s`, `15fps`, `512x256`, `extract=1080` evaluates and predicts with those same values.
- Existing default checkpoints still load through a deliberate legacy path.
- No silent geometry mismatch occurs between training and inference.

---

## Phase 3 — Pinned train/validation/test manifests

### Objective

Make experiments comparable over time and avoid validation/test drift when videos are added or removed.

### Problem

The current code uses deterministic video-wise split by sorting video paths and reserving the last `n_val`. This avoids rally-level leakage, but it is positional. Adding/removing videos changes which videos are in validation, making runs incomparable.

### Manifest format

Use explicit manifests grouped at the safest available unit: match/event/game, not individual rally.

Recommended schema:

```json
{
  "schema_version": "1.0",
  "split_name": "winner_approach_a_2026_06",
  "unit": "match",
  "entries": [
    {
      "id": "match_001",
      "video_path": "/absolute/path/to/video.mp4",
      "training_json_path": "/absolute/path/to/game.training.json",
      "notes": "held out for test"
    }
  ]
}
```

Create separate files:

```text
winner_train_manifest.json
winner_val_manifest.json
winner_test_manifest.json
```

### Rules

- No video/match/game may appear in more than one split.
- Test manifest is locked and used only for final reporting.
- Validation manifest is used for checkpoint selection and ablation finalist selection.
- Training manifest is used for fitting.
- If `video_path` is not a full independent match/game, add a higher-level `match_id` and split by that.

### Implementation

Add manifest support to `train_winner` and `evaluate_winner`:

- `--train-manifest PATH`
- `--val-manifest PATH`
- `--test-manifest PATH`

Training behavior:

- if manifests are supplied, use them instead of positional split,
- select best checkpoint using validation manifest,
- never train on validation or test manifest entries.

Evaluation behavior:

- can evaluate on a specified manifest,
- test evaluation should be explicit.

### Tests

Add tests for:

- manifest parsing,
- duplicate detection across splits,
- missing video/JSON handling,
- stable membership regardless of unrelated files under root,
- no accidental fallback to positional split when manifest is requested.

### Acceptance criteria

- Adding a new video to the root does not change val/test membership when manifests are used.
- Final test set is touched by only one selected finalist plus baseline comparison.
- Split provenance appears in checkpoint metadata and evaluation output.

---

## Phase 4 — Clip windowing: clamp, padding/masking, cache keys, and leakage controls

### Objective

Safely support 5s clips without including previous-rally frames or introducing padding-based label leakage.

### Current problem

Current prediction uses the last `clip_duration_s` before `end_s`:

```python
clip_start = max(0.0, end_s - clip_duration_s)
```

For short rallies and 5s clips, this can include frames from the previous point.

Training currently stores only rally end time in `_RallyRecord`, so clamp-to-rally-start requires storing `raw_start` as well.

### Required record changes

Extend `_RallyRecord` to include:

```python
raw_start_seconds: float
raw_end_seconds: float
```

Update all constructors:

- JSON scanning path,
- `from_rally_examples`,
- `_from_rally_examples_no_split`,
- tests/mocks.

### Clip window policy

Introduce a named clip-window policy and store it in checkpoint metadata:

```text
clip_window_policy = "clamp_to_rally_start_v1"
```

Policy:

```text
clip_end = raw_end_seconds
clip_start = max(raw_start_seconds, raw_end_seconds - effective_clip_duration_s)
```

This prevents previous-rally frames from entering the clip.

### Padding/masking policy

If the clamped clip is shorter than the requested frame count, define behavior explicitly and store it in checkpoint metadata.

Possible v1 policy:

```text
padding_policy = "repeat_first_frame_v1"
```

or:

```text
padding_policy = "left_pad_black_with_mask_v1"
```

Recommendation:

- Keep model architecture unchanged for the first implementation.
- Use a deterministic padding policy that does not encode obvious class-specific information if possible.
- Report padding/truncation rates by class and terminal-event side.
- If padding rate differs substantially by winner class or terminal-event side, do not use padded clips as decisive evidence without further mitigation.

Important: adding a mask would require model changes if the mask is consumed by the network. Since architecture changes are out of scope, mask can initially be logged for diagnostics but not fed to the model.

### Old-checkpoint comparison warning

Clamped and unclamped windows are different data distributions. Treat them as separate model variants.

Do not directly compare an old unclamped checkpoint to a new clamped checkpoint without clearly labeling the window-policy difference.

### Cache keys

Cache keys must separate clip variants that differ by:

- video path,
- raw start,
- raw end,
- effective duration,
- fps,
- extraction size,
- clip-window policy,
- padding policy,
- canonical size if any warped cache exists,
- config schema/version.

The raw frame cache currently stores pre-warp extracted frames and includes time range, fps, and extraction size. Once clamp behavior changes the time range, stale cache reuse should be avoided naturally, but add regression tests. If any higher-level clip/feature cache exists, include full policy/config in the key.

### Diagnostics

Log per run:

```text
requested_frames
actual_extracted_frames_before_padding
padding_frames
padding_fraction
number of clamped rallies
padding by winner class
padding by terminal_event_side, when annotations exist
```

### Tests

Add tests for:

- clips do not start before `raw_start_seconds`,
- short clips are padded according to policy,
- padding policy is stable,
- cache keys differ for clamped vs unclamped variants,
- checkpoint metadata records window/padding policy,
- prediction and training use the same policy.

### Acceptance criteria

- 5s clips do not include previous-rally frames.
- Padding/truncation rates are visible and checked for confounding.
- Clip-window policy is versioned and checkpointed.

---

## Phase 5 — Side/event metrics

### Objective

Measure the reported failure mode correctly while still providing useful secondary diagnostics.

### New helper module

Create `ml/evaluation/side_metrics.py` with small, torch-free functions:

```python
@dataclass(frozen=True)
class SideMetricBucket:
    name: str
    n_total: int
    n_correct: int
    accuracy: float | None
    base_rate: float | None = None
    balanced_accuracy: float | None = None


def compute_team_metrics(labels: list[int], preds: list[int]) -> dict[str, Any]:
    ...


def compute_terminal_event_side_metrics(
    labels: list[int],
    preds: list[int],
    annotations: list[TerminalEventAnnotation],
) -> dict[str, Any]:
    ...


def compute_winner_side_diagnostics(
    labels: list[int],
    preds: list[int],
    camera_near_by_rally: dict[RallyKey, int],
) -> dict[str, Any]:
    ...
```

### Metrics to report always

Regardless of annotations:

- Team 0 winner accuracy,
- Team 1 winner accuracy,
- confusion matrix by true winning team,
- balanced accuracy,
- per-video/per-match accuracy.

### Primary metrics when terminal-event annotations exist

Report:

- near terminal-event accuracy,
- far terminal-event accuracy,
- unknown terminal-event count,
- near/far sample counts,
- balanced accuracy by terminal-event side,
- confusion matrix by terminal-event side,
- per-video/per-match terminal-event side breakdown.

### Secondary non-decisive metrics

If side mapping exists, optionally report winner-side diagnostics:

- winning team was camera-near,
- winning team was camera-far,
- mapped/unmapped count.

These must be clearly labeled:

```text
Winner-side diagnostics only. Not a terminal-event-side metric and not valid for far-side visibility decisions.
```

### Evaluation CLI

Add:

```text
--terminal-event-annotations PATH
--side-map PATH
```

Example:

```bash
python -m ml.tools.evaluate_winner \
  --dir ~/Videos/pickleball \
  --checkpoint ml/checkpoints/winner_512x256_5s_15fps_extract1080.pt \
  --test-manifest winner_test_manifest.json \
  --terminal-event-annotations terminal_events.json \
  --side-map side_map.json \
  --calibration \
  --device cuda
```

### Tests

Add tests for:

- team metrics with balanced and imbalanced labels,
- terminal-event-side metrics with near/far/unknown,
- partial annotation coverage,
- winner-side diagnostics labeled non-decisive,
- malformed annotation files rejected with clear error,
- JSON output includes metrics,
- human-readable output does not conflate winner-side and terminal-event-side.

### Acceptance criteria

- Evaluation never falsely labels winner-side metrics as terminal-event/far-side metrics.
- Far-side decision metrics require terminal-event annotations.
- Sample counts and base rates are visible.

---

## Phase 6 — Resource diagnostics and AMP support

### Objective

Make larger clips practical to train and debug.

The user-requested clip shape changes frame count from roughly:

```text
2.5s * 8fps = 20 frames
```

to:

```text
5.0s * 15fps = 75 frames
```

At the same time, increasing canonical size from `256x128` to `512x256` increases pixels per frame by 4x. This can create major GPU memory and training-time increases.

### Training log additions

At training start, print:

```text
WinnerModelConfig:
  canonical_width
  canonical_height
  clip_duration_s
  effective_clip_duration_s
  fps_out
  frames_per_clip T
  clip_extract_max_dim
  confidence_threshold
  clip_window_policy
  padding_policy

Training runtime:
  batch_size
  grad_accum_steps
  effective_batch_size
  num_workers
  seed
  device
  AMP enabled/disabled
  checkpoint_out
  train_manifest
  val_manifest

Estimated input tensor:
  shape per sample: (T, 3, H, W)
  MB per sample float32
  MB per micro-batch float32
```

When CUDA is available, after each epoch or at least after training, print:

```text
CUDA max memory allocated
CUDA max memory reserved
```

### AMP implementation

When `--amp` is enabled and the resolved device is CUDA:

- use the non-deprecated `torch.amp` API available in the installed PyTorch version,
- use gradient scaling,
- preserve non-AMP behavior when `--amp` is false or device is CPU,
- do not compare AMP runs to non-AMP runs as if AMP were not a training-variable change.

### Batch-size guidance

Document recommended starting points:

```text
256x128, 75 frames: batch 4-8 if memory allows
512x256, 75 frames: batch 1-2
768x384, 75 frames: batch 1
```

Because ResNet-18 contains BatchNorm, batch-size changes are not purely a memory setting. When comparing configurations:

- keep physical batch size constant where feasible,
- or rerun baseline at the same physical batch size as the larger config,
- use gradient accumulation for optimizer-step stability, but do not treat it as equivalent to true large-batch BatchNorm behavior.

### Tests

Add tests that do not require CUDA for:

- diagnostic shape/size computation,
- AMP flag ignored or warned on CPU,
- gradient accumulation update cadence,
- training metadata records AMP/batch/seed settings.

CUDA behavior can be manually verified on the development machine.

### Acceptance criteria

- Larger experiments print enough information to diagnose memory use.
- AMP can be enabled explicitly.
- CPU/default training path remains unaffected.
- Batch-size differences are accounted for in experiment interpretation.

---

## Phase 7 — Controlled ablation experiments

### Objective

Determine which input changes improve true far-side terminal-event performance while minimizing training/inference cost.

Do not change production defaults before this phase produces evidence.

### Required before running full ablation

- Phase 0 terminal-event annotation set exists.
- Pinned train/val/test manifests exist.
- Checkpoint schema/config auto-loading is safe.
- Clip-window policy is versioned and consistent.
- End-window leakage audit is complete.
- Baseline variance is estimated with multiple seeds.

### Experiment naming

Use descriptive checkpoint names:

```text
ml/checkpoints/approach_a_A_baseline_256x128_2p5s_8fps_extract640_seed0.pt
ml/checkpoints/approach_a_B_extract1080_256x128_2p5s_8fps_seed0.pt
ml/checkpoints/approach_a_C_duration5_256x128_5s_8fps_extract1080_seed0.pt
ml/checkpoints/approach_a_D_fps15_256x128_2p5s_15fps_extract1080_seed0.pt
ml/checkpoints/approach_a_E_temporal_256x128_5s_15fps_extract1080_seed0.pt
ml/checkpoints/approach_a_F_canon512_512x256_5s_15fps_extract1080_seed0.pt
ml/checkpoints/approach_a_G_canon768_768x384_5s_15fps_extractNative_seed0.pt
```

### Experiment A — Baseline

```text
canonical: 256x128
duration: 2.5s
fps: 8
extract max: 640
clip policy: current or explicitly versioned baseline policy
```

Purpose: establish reproducible baseline and variance.

Run at least three seeds if compute permits:

```text
seed 0
seed 1
seed 2
```

### Experiment B — Source extraction resolution only

```text
canonical: 256x128
duration: 2.5s
fps: 8
extract max: 1080 or native
```

Purpose: test whether far-side information is being discarded before homography warp.

### Experiment C — Duration only

```text
canonical: 256x128
duration: 5.0s
fps: 8
extract max: best from B
```

Purpose: isolate longer context.

### Experiment D — FPS only

```text
canonical: 256x128
duration: 2.5s
fps: 15
extract max: best from B
```

Purpose: isolate temporal density.

### Experiment E — User-requested temporal combination

```text
canonical: 256x128
duration: 5.0s
fps: 15
extract max: best from B
```

Purpose: test the requested 5s/15fps configuration before spatial model-size increases.

### Experiment F — Moderate canonical resolution bump

```text
canonical: 512x256
duration: 5.0s
fps: 15
extract max: 1080 or native
```

Purpose: test whether larger model input helps after source resolution and temporal settings are improved.

### Experiment G — Larger canonical resolution only if F helps

```text
canonical: 768x384
duration: 5.0s
fps: 15
extract max: native
```

Purpose: test upper-end spatial resolution only if moderate resolution shows evidence of benefit and memory is manageable.

### Batch-size control

For each ablation:

- record physical batch size,
- record gradient accumulation,
- record effective batch size,
- record AMP state,
- if physical batch size differs from baseline, rerun baseline under comparable physical/effective settings or treat the result as confounded.

### Test-set rule

Use validation set to pick one finalist configuration. Only the baseline and selected finalist should be evaluated on the locked test manifest.

Do not iterate on test results.

---

## Phase 8 — Experiment reporting and decision criteria

### Metrics to record for every run

```text
overall validation accuracy
balanced validation accuracy
Team 0 accuracy
Team 1 accuracy
terminal-event near accuracy, if annotations exist
terminal-event far accuracy, if annotations exist
terminal-event sample counts
unknown terminal-event count
per-video/per-match accuracy
game-level exact sequence percentage
mean first divergence rally
low-confidence flag rate at threshold 0.75
ECE/calibration
padding/truncation rate
padding by class and terminal-event side
training time per epoch
total training time
peak GPU memory
cache size
checkpoint path
full WinnerModelConfig
checkpoint schema version
clip-window policy
padding policy
seed
batch/grad accumulation/AMP settings
train/val/test manifest IDs
```

### Minimum reporting table

Create a table like:

```text
Run | Canon | Extract | Dur | FPS | Overall | BalAcc | EventFar | EventNear | ExactSeq | LowConf | Pad% | GPU Mem | Time/Epoch
A   | 256x128 | 640  | 2.5 | 8  | ... | ... | ... | ... | ... | ... | ... | ... | ...
B   | 256x128 | 1080 | 2.5 | 8  | ... | ... | ... | ... | ... | ... | ... | ... | ...
```

### Checkpoint selection metric

Pre-register the validation selection metric before running the ablation. Recommended:

```text
balanced validation accuracy, with game-level exact sequence as a secondary operational metric
```

Do not select based only on a tiny far-side subset unless the annotated set is large enough and the selection rule is pre-registered.

### Final decision rule

Prefer the smallest and cheapest configuration that improves:

1. terminal-event far-side accuracy,
2. balanced validation/test accuracy,
3. game-level exact score sequence rate,
4. mean first divergence,
5. low-confidence review burden,
6. calibration enough that confidence remains useful.

Do not select a configuration based only on overall validation accuracy if terminal-event far-side accuracy is unchanged or worse.

### Statistical reporting

Before changing production defaults:

- report baseline variance across seeds,
- report finalist-vs-baseline deltas across seeds where feasible,
- report confidence intervals or bootstrap intervals at the video/match level,
- report per-stratum sample counts,
- account for multiple comparisons by allowing only one selected finalist to touch the locked test set.

### Failure criteria

Approach A is insufficient if:

- terminal-event far-side accuracy does not improve beyond baseline variance,
- source extraction increase does not improve terminal-event far-side accuracy,
- 5s/15fps does not improve far-side or game-level metrics,
- canonical resolution increases are too expensive or do not help,
- gains appear to come from padding, celebration, overlay, or other leakage cues.

If this occurs, move to deferred approaches in this order:

1. OpenCV motion/optical-flow features,
2. player/person tracking,
3. stronger video action model,
4. ball tracking only if evidence suggests it is feasible and necessary.

---

## Phase 9 — Documentation and runbook

### Files to update

```text
docs/TRAINING_GUIDE.md
docs/auto-editor-plan/README.md or related current ML docs
```

### Document

- new trainer CLI flags,
- checkpoint-output behavior,
- checkpoint schema and legacy behavior,
- split manifest format,
- terminal-event annotation format,
- side-map format and limitations,
- extraction resolution vs canonical model resolution,
- clip-window and padding policies,
- recommended experiment matrix,
- batch-size/BatchNorm/gradient-accumulation caveats,
- AMP guidance,
- how to evaluate a checkpoint,
- how to compare run metrics,
- warning that winner-side near/far is not terminal-event-side.

### Example commands

Baseline training:

```bash
python -m ml train-winner \
  --root ~/Videos/pickleball \
  --train-manifest winner_train_manifest.json \
  --val-manifest winner_val_manifest.json \
  --epochs 50 \
  --batch-size 8 \
  --seed 0 \
  --device cuda \
  --checkpoint-out ml/checkpoints/approach_a_A_baseline_256x128_2p5s_8fps_extract640_seed0.pt
```

Evaluation on validation manifest:

```bash
python -m ml.tools.evaluate_winner \
  --dir ~/Videos/pickleball \
  --checkpoint ml/checkpoints/approach_a_A_baseline_256x128_2p5s_8fps_extract640_seed0.pt \
  --val-manifest winner_val_manifest.json \
  --terminal-event-annotations terminal_events_val.json \
  --calibration \
  --device cuda
```

Final locked test evaluation for selected finalist:

```bash
python -m ml.tools.evaluate_winner \
  --dir ~/Videos/pickleball \
  --checkpoint ml/checkpoints/approach_a_SELECTED_FINALIST.pt \
  --test-manifest winner_test_manifest.json \
  --terminal-event-annotations terminal_events_test.json \
  --calibration \
  --device cuda
```

User-requested temporal combo:

```bash
python -m ml train-winner \
  --root ~/Videos/pickleball \
  --train-manifest winner_train_manifest.json \
  --val-manifest winner_val_manifest.json \
  --epochs 50 \
  --batch-size 4 \
  --grad-accum-steps 2 \
  --seed 0 \
  --device cuda \
  --canonical-width 256 \
  --canonical-height 128 \
  --clip-duration-s 5.0 \
  --fps-out 15 \
  --clip-extract-max-dim 1080 \
  --checkpoint-out ml/checkpoints/approach_a_E_temporal_256x128_5s_15fps_extract1080_seed0.pt \
  --amp
```

Moderate canonical bump:

```bash
python -m ml train-winner \
  --root ~/Videos/pickleball \
  --train-manifest winner_train_manifest.json \
  --val-manifest winner_val_manifest.json \
  --epochs 50 \
  --batch-size 2 \
  --grad-accum-steps 4 \
  --seed 0 \
  --device cuda \
  --canonical-width 512 \
  --canonical-height 256 \
  --clip-duration-s 5.0 \
  --fps-out 15 \
  --clip-extract-max-dim 1080 \
  --checkpoint-out ml/checkpoints/approach_a_F_canon512_512x256_5s_15fps_extract1080_seed0.pt \
  --amp
```

---

## Recommended implementation order

1. Checkpoint config schema/versioning and safe auto-load/fallback rules.
2. Trainer CLI/config/checkpoint output plumbing, including seed and batch controls.
3. Pinned train/val/test manifest support.
4. Terminal-event annotation and side/event metrics tooling.
5. Clip-window clamp, padding policy, cache-key updates, and leakage diagnostics.
6. Resource diagnostics and AMP.
7. Documentation/runbook.
8. Baseline variance measurement.
9. Controlled ablations.
10. Locked test evaluation of baseline and one selected finalist.
11. Production default change only if evidence justifies it.

## Verification commands

After implementation, run narrow tests first:

```bash
pytest tests/test_evaluate_winner.py
pytest tests/test_side_metrics.py
pytest tests/test_split_manifest.py
pytest tests/test_winner_model.py
pytest tests/test_winner_dataset.py
pytest tests/test_video_features.py
```

Run broader checks if the touched areas are stable:

```bash
make test
make lint
```

Manual smoke test for config propagation:

```bash
python -m ml train-winner \
  --root ~/Videos/pickleball \
  --train-manifest winner_train_manifest.json \
  --val-manifest winner_val_manifest.json \
  --epochs 1 \
  --batch-size 1 \
  --seed 0 \
  --device cuda \
  --canonical-width 256 \
  --canonical-height 128 \
  --clip-duration-s 5.0 \
  --fps-out 15 \
  --clip-extract-max-dim 1080 \
  --checkpoint-out ml/checkpoints/smoke_winner_5s_15fps.pt
```

Manual smoke test for evaluation:

```bash
python -m ml.tools.evaluate_winner \
  --dir ~/Videos/pickleball \
  --checkpoint ml/checkpoints/smoke_winner_5s_15fps.pt \
  --val-manifest winner_val_manifest.json \
  --terminal-event-annotations terminal_events_val.json \
  --calibration \
  --device cuda
```

## Risks and mitigations

### Risk: terminal-event side cannot be annotated reliably

Mitigation: include `unknown`, estimate annotation ambiguity, and do not claim far-side improvement if the target metric is unavailable.

### Risk: near/far side changes during a video

Mitigation: use per-rally/per-segment side mapping. Per-video mapping is allowed only for verified constant-side videos.

### Risk: larger clips cause CUDA OOM

Mitigation: add AMP, lower physical batch size, log memory diagnostics, and start with extraction-only and temporal-only ablations before larger canonical sizes.

### Risk: batch-size changes confound results

Mitigation: record physical/effective batch size, use batch-size-matched baselines where possible, use gradient accumulation with the BatchNorm caveat, and hold LR/weight decay/scheduler/AMP constant.

### Risk: canonical resolution increase only upscales lost source information

Mitigation: isolate `clip_extract_max_dim` first. Treat extraction resolution as the first far-side lever.

### Risk: end-window leakage drives apparent gains

Mitigation: audit clips, document `raw_end_seconds` meaning, clamp to rally start, and report padding/truncation/leakage indicators.

### Risk: old checkpoints behave differently after config changes

Mitigation: add checkpoint schema version, legacy fallback/backfill, refuse geometry conflicts, and do not change defaults until legacy behavior is safe.

### Risk: cache bloat or stale cache reuse

Mitigation: log cache size per experiment, include clip-window/padding/config in relevant cache keys, add regression tests, and avoid destructive automated cleanup.

## Definition of done

This implementation is complete when:

- winner trainer config is fully CLI-controllable,
- experiment checkpoints can be written without overwriting the default checkpoint,
- checkpoint schema/config metadata is complete and safely loaded for prediction/evaluation/auto-edit,
- legacy checkpoints are handled deliberately,
- train/val/test splits are pinned by manifest,
- terminal-event-side annotation can drive the far-side decision metric,
- winner-side near/far diagnostics are clearly non-decisive,
- clip windows are clamped/versioned with explicit padding policy,
- cache keys/tests protect against stale geometry/window reuse,
- resource diagnostics and AMP support are available,
- docs explain how to run and compare Approach A experiments,
- tests cover config propagation, split manifests, side/event metrics, checkpoint compatibility, and clip windowing,
- no production defaults are changed without experimental evidence from the locked protocol.
