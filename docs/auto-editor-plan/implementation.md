# Implementation Plan

Step-by-step instructions for building the automated pipeline. Each phase is
self-contained and leaves the existing manual-editing flow working.

## Phase 0 — Infrastructure

**Goal**: add video frame extraction, homography utilities, and a 4-corner court
calibrator widget. Retrofit the 14 already-labeled videos with corner data.

### 0.1 Add dependencies

Two files need updating — not just `ml/requirements.txt`. The `configure` script has an
inline `ML_DEPS` array (`configure:268-274`) that is what actually gets installed by
`./configure --enable-ml`. If only `ml/requirements.txt` is updated, `./configure` will
drift and users will get broken setups.

Edit both:

**`ml/requirements.txt`**:
```
decord>=0.6.0
opencv-python-headless>=4.8.0
torchvision>=0.15.0
```

**`configure` (ML_DEPS array around line 268)**:
```bash
ML_DEPS=(
    "torch>=2.0.0"
    "torchaudio>=2.0.0"
    "torchvision>=0.15.0"
    "numpy>=1.24.0"
    "scikit-learn>=1.3.0"
    "decord>=0.6.0"
    "opencv-python-headless>=4.8.0"
)
```

Rationale for each new dep:
- `decord`: fast seekable video frame extraction with GPU support.
- `opencv-python-headless`: only for `cv2.getPerspectiveTransform` and `cv2.warpPerspective`;
  `-headless` keeps it dependency-free of Qt.
- `torchvision`: pretrained ResNet-18 backbone for the winner classifier.

### 0.2 Create `ml/video_features.py`

Public API:
```python
def extract_clip(video_path: Path, start_s: float, end_s: float, fps_out: int, size: tuple[int, int]) -> np.ndarray:
    """Extract a clip as (T, H, W, 3) uint8 array. Cached under ml/cache/clips/."""

def compute_homography(corners_pixel: list[tuple[int, int]], canonical_size: tuple[int, int]) -> np.ndarray:
    """Given 4 corners in pixel coords (TL, TR, BR, BL) return a 3x3 perspective transform
    matrix mapping the source court to a canonical rectangular top-down view."""

def warp_clip_to_canonical(frames: np.ndarray, homography: np.ndarray, canonical_size: tuple[int, int]) -> np.ndarray:
    """Apply homography per frame. Returns (T, H_canon, W_canon, 3) uint8."""

def hash_clip_key(video_path: Path, start_s: float, end_s: float, fps_out: int, size: tuple[int, int]) -> str:
    """Stable cache key."""
```

Implementation notes:
- Extract frames via the system `ffmpeg` CLI (subprocess), resampling each clip to exactly
  N frames. Decoding runs out-of-process so it cannot clash with the GUI's in-process mpv.
- Cache: `ml/cache/clips/{hash}.npy`. Evict nothing automatically; this is a dev-time cache.
- Canonical court size suggestion: 256×128 (court is 44×20 ft → 2.2 aspect ratio, rounded).

### 0.3 Create `src/ui/widgets/court_calibrator.py`

New `QWidget` subclass. Responsibilities:
- Accept a frame image (QPixmap) and display it at fit-to-widget scale.
- Track mouse clicks in a labelled sequence. The UI must explicitly prompt for each
  click so the team-side mapping is unambiguous:
  1. "Click **Team 1's** baseline-left corner"
  2. "Click **Team 1's** baseline-right corner"
  3. "Click **Team 2's** baseline-right corner"
  4. "Click **Team 2's** baseline-left corner"
  The click order — not the court geometry alone — is what encodes the team-to-side
  mapping for the rest of the pipeline.
- Draw markers + polygon as clicks come in, with the current prompt visible.
- Emit `cornersCaptured(list[tuple[int, int]])` when the user confirms 4 clicks.
- Provide a "Reset" button to start over.
- Provide a "Confirm" button that only activates when all 4 are clicked.

Unit-test it with an offscreen QPixmap and synthesized click events.

### 0.4 Integrate calibrator into setup

In `src/ui/setup_dialog.py`, after the video is selected and before "Start editing",
add a step that:
- Reads frame at ~5% into the video with `ffmpeg` (one-off, reuse existing ffmpeg usage).
- Shows the `CourtCalibratorWidget` in a dialog.
- Stores `corners: list[tuple[int, int]]` on the `GameConfig`.

Add `court_corners` to `GameConfig` in `src/ui/setup_dialog.py:73`.

### 0.5 Persist corners in SessionState and training JSON

- Add `court_corners: list[tuple[int, int]] | None` to `SessionState` in `src/core/models.py`.
- Bump training JSON schema from `"1.0"` to `"1.1"`. Add
  `video.court_corners: [[x,y], [x,y], [x,y], [x,y]]` in
  `src/output/training_data_generator.py:generate()`. Keep reading `1.0` files as
  "corners missing → prompt user".

### 0.6 Retrofit the 14 existing labeled videos

New CLI `ml/tools/calibrate_existing.py`:
- Recursively find all `.training.json` files under a root dir.
- For each file where `video.court_corners` is missing, open the video, show first frame
  using the same `CourtCalibratorWidget` (or a plain OpenCV window if we want it headless),
  capture corners, write back to the file, bump schema to `1.1`.
- One-time cost: ~5 seconds × 14 = ~70 seconds of clicking.

### 0.7 Verification

- Unit tests `tests/test_video_features.py`:
  - `compute_homography` with corners at `[(0,0), (W,0), (W,H), (0,H)]` yields identity
    (up to scale).
  - `extract_clip(v, 10.0, 11.0, 24, (320,240))` returns shape `(24, 240, 320, 3)`.
  - Cache hit on second call returns same array without re-extraction (check mtime).
- Unit test `tests/test_court_calibrator.py` with QTest synthesizing clicks.
- Manual: run `calibrate_existing` on your 14 videos, confirm each JSON now has corners.

---

## Phase 1 — Winner-label backfill (no new annotation work)

**Goal**: add a `winning_team: 0|1` field to every rally in every `.training.json`
derived from existing `winner` + `serving_team` data.

### 1.1 Update `TrainingDataGenerator`

In `src/output/training_data_generator.py:generate()`, for each rally emit:
```python
rally_dict["winning_team"] = (
    snapshot.serving_team if rally.winner == "server"
    else 1 - snapshot.serving_team
)
```

Bump schema to `"1.1"`.

### 1.2 Create `ml/tools/backfill_winner_labels.py`

**Critical detail**: current saved session state persists `interventions=[]` and
`comments=[]` with TODOs (`src/ui/main_window.py:1707-1708`). Historical games that used
Edit Score or Force Side-Out mid-game have NO intervention history preserved. A naive
replay (init `ScoreState`, chain `server_wins`/`receiver_wins`) will diverge from the
real game state whenever an intervention happened, producing wrong `winning_team`
values from that rally onwards.

**Fix**: re-sync `ScoreState` from the recorded `score_at_start` per rally. The
`score_at_start` is captured at rally time by the live ScoreState (including any
intervention effects just applied), so it is faithful even when intervention history is
lost. `ScoreState.set_score()` already exists for this purpose.

Algorithm:
```python
score_state = ScoreState(game_type, victory_rules, player_names)
for rally in rallies:
    # Re-sync from recorded score — this absorbs any lost intervention effects.
    score_state.set_score(rally["score_at_start"])
    serving = score_state.serving_team

    # Derive winning_team from winner + current serving_team.
    if rally["winner"] == "server":
        winning_team = serving
        score_state.server_wins()
    else:
        winning_team = 1 - serving
        score_state.receiver_wins()
    rally["winning_team"] = winning_team
```

- Find all `.training.json`, including those with `schema_version == "1.0"`.
- Apply the algorithm above. Write back with `schema_version = "1.1"` and a
  `winning_team` per rally.
- Log (don't fail) if a rally's `score_at_start` can't be parsed; skip that game.

### 1.3 Verification

- Unit test with a hand-constructed game: 5 rallies with known winners → verify
  `winning_team` output matches expectation.
- Spot-check 5 rallies across 2 real games manually.

---

## Phase 2 — Winner classifier (the new ML component)

**Goal**: train a model that, given a short clip at the end of a rally warped to the
canonical court view, predicts which team won.

### 2.1 Dataset: `ml/winner_dataset.py`

PyTorch `Dataset`:
- Walks all `.training.json` with `schema_version >= "1.1"` and `court_corners` present.
- For each rally: clip is `raw.end_seconds - 2.5 s` to `raw.end_seconds`. Extract at
  8 fps → 20 frames, resize to 256×128 via `warp_clip_to_canonical`. Label = `winning_team`.
- Cached on disk per rally.
- Augmentation path (training only):
  - Horizontal flip + swap label (essentially doubles the dataset for free since the
    canonical court is symmetric).
  - Color jitter ±0.2 brightness/contrast.
  - Temporal jitter ±0.2 s on the clip start.
  - Intentionally no random erasing / mixup in v1 — keep augmentation minimal and
    legible. Add more only if validation accuracy stalls and augmentation is the
    suspected cause.

### 2.2 Model: `ml/winner_model.py`

```python
class WinnerClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        backbone = torchvision.models.resnet18(weights="DEFAULT")
        backbone.fc = nn.Identity()  # (B*T, 512)
        self.backbone = backbone
        self.temporal = nn.Sequential(
            nn.Conv1d(512, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Linear(128, 2)

    def forward(self, clip):  # clip: (B, T, 3, H, W)
        B, T, C, H, W = clip.shape
        x = self.backbone(clip.view(B * T, C, H, W))  # (B*T, 512)
        x = x.view(B, T, 512).permute(0, 2, 1)  # (B, 512, T)
        x = self.temporal(x).squeeze(-1)  # (B, 128)
        return self.head(x)  # (B, 2)
```

Rationale: ResNet-18 is pretrained on ImageNet, robust to small data; 1D conv over time
is simpler than 3D conv and trains faster. ~11M params.

### 2.3 Training: `ml/train_winner.py`

Mirror `ml/train.py`:
- Video-wise 80/20 split (no data leakage).
- `CrossEntropyLoss` with per-class weights to counter imbalance.
- Adam, lr=1e-4 for backbone, 1e-3 for head/temporal (parameter groups).
- Early stop on val accuracy, patience 5 epochs.
- Save to `ml/checkpoints/best_winner.pt` with metadata (epoch, val accuracy, val
  per-class precision/recall, confusion matrix).

Target: **val accuracy ≥ 80% at 14 games; ≥ 85% at 25+ games.**

### 2.4 Inference: `ml/predict_winner.py`

```python
def predict_winners(
    video_path: Path,
    corners: list[tuple[int, int]],
    rally_intervals: list[tuple[float, float]],
    checkpoint_path: Path,
) -> list[tuple[int, float]]:
    """Returns [(winning_team, confidence), ...] per rally."""
```

v1 uses raw softmax probability as confidence with a 0.7 flag threshold. If in practice
the flag rate turns out miscalibrated (way too many or way too few rallies flagged), add
temperature scaling as a follow-up. Don't build it preemptively.

### 2.5 Verification

- Unit test `tests/test_winner_model.py`: forward pass with dummy `(2, 20, 3, 256, 128)`
  tensor returns `(2, 2)`.
- Training run on the 14 games: report train/val curves, confusion matrix, accuracy.
- Hold out one game entirely, run inference, compare to ground truth.

---

## Phase 3 — Pipeline orchestrator

**Goal**: one CLI command that takes a video + setup + corners and emits `.kdenlive` +
`.ass` + `.training.json`.

### 3.1 Create `ml/auto_edit.py`

```python
@dataclass
class AutoEditResult:
    kdenlive_path: Path
    ass_path: Path
    training_json_path: Path
    predicted_rally_count: int
    low_confidence_rally_indices: list[int]
    simulated_final_score: tuple[int, int] | None
    session_state: SessionState
    n_detected: int = 0
    n_scored: int = 0
    n_post_game: int = 0

def auto_edit(
    video_path: Path,
    setup: AutoEditSetup,           # Qt-free player names, game type, victory rules
    corners: list[tuple[int, int]],
    output_dir: Path,
    checkpoint_path: Path,
    confidence_threshold: float | None = None,
    winner_config: WinnerModelConfig | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> AutoEditResult:
    # Step 1: audio rally detection (existing)
    intervals = ml.predict.predict_rallies(video_path)

    # Step 2: winner classification (new)
    winners = ml.predict_winner.predict_winners(video_path, corners, intervals, CHECKPOINT)

    # Step 3: score simulation via existing ScoreState + RallyManager
    # ScoreState requires player_names (see src/core/score_state.py:41-46).
    # Team 1 serves first by convention, same as the manual editor.
    score_state = ScoreState(
        game_type=setup.game_type,
        victory_rules=setup.victory_rule,
        player_names={"team1": setup.team1_players, "team2": setup.team2_players},
    )
    rally_manager = RallyManager(fps=video_fps)
    low_conf = []
    for i, ((start, end), (team, conf)) in enumerate(zip(intervals, winners)):
        if conf < confidence_threshold:
            low_conf.append(i)
        snapshot = score_state.save_snapshot()
        score_at_start = score_state.get_score_string()
        rally_manager.start_rally(start, snapshot)

        if team == score_state.serving_team:
            score_state.server_wins()
            winner_str = "server"
        else:
            score_state.receiver_wins()
            winner_str = "receiver"

        new_snapshot = score_state.save_snapshot()
        rally_manager.end_rally(end, winner_str, score_at_start, new_snapshot)

        if score_state.is_game_over()[0]:
            break  # trim remaining predictions

    # Step 4: output. KdenliveGenerator + SubtitleGenerator are reused as-is.
    # TrainingDataGenerator gets a small schema bump (1.0 → 1.1) to carry
    # winning_team, court_corners, and generated_by. No other output-layer changes.
    segments = rally_manager.to_segments()
    kdenlive_path, ass_path = KdenliveGenerator(
        segments=segments, fps=video_fps, resolution=resolution,
        team1_players=setup.team1_players, team2_players=setup.team2_players,
    ).generate(output_dir / f"{video_path.stem}.kdenlive")

    training_json_path = output_dir / f"{video_path.stem}.training.json"
    TrainingDataGenerator.write(
        training_json_path, video_path, fps=video_fps, rallies=rally_manager.get_rallies(),
        game_config=setup, court_corners=corners,
        generated_by="auto_edit",
    )

    return AutoEditResult(...)
```

### 3.2 Register CLI subcommand in `ml/cli.py`

```
python -m ml auto-edit --video game.mp4 --setup setup.json --corners corners.json --out dist/
```

`setup.json` and `corners.json` are the structured inputs; or accept an existing
`.training.json` from the same video (use its `game` block and corners).

### 3.3 Flag auto-generated training data

In `TrainingDataGenerator.write()`, accept `generated_by: str = "manual"` and write it
at the top level. When training the next round of models, filter out
`generated_by == "auto_edit"` unless explicitly allowlisted — otherwise we bootstrap our
own errors.

### 3.4 Verification

Integration test `tests/test_auto_edit.py`:
- Use a short fixture video (30 seconds with known synthetic audio events) if possible,
  or mock the audio and winner predictors to return fixed outputs.
- Assert: kdenlive XML parses, ASS file valid, expected rally count, expected final
  score (hand-computed from the mocked winners).
- Manual smoke: run on a held-out real game, open `.kdenlive` in Kdenlive, confirm load.

---

## Phase 4 — UI integration

**Goal**: add an "Auto-process" path to the setup dialog. On completion, drop the user
into the existing review mode with low-confidence rallies visually flagged.

### 4.1 Setup dialog toggle

In `src/ui/setup_dialog.py`, add a radio button or mode selector:
- "Manual editing" (existing flow)
- "Auto-process (experimental)" (new flow)

When auto-process is selected:
- Require court corners (trigger calibrator).
- Require the existing `GameConfig` fields: player names + game type + victory rule.
  (Team 1 serves first by convention — no first-server input.)
- "Start" button kicks off `auto_edit()` on a `QThread` with a progress dialog.

### 4.2 Progress dialog

New `src/ui/dialogs/auto_edit_progress.py`. Shows:
- Current phase ("Detecting rallies from audio...", "Classifying rally winners...",
  "Simulating score...", "Writing output...").
- Cancel button that signals cooperative cancellation.

Model the threading on the existing `ExportManager` pattern (`src/main.py` already uses
it for non-blocking FFmpeg exports).

### 4.3 Hand off to review mode

On completion of `auto_edit()`:
- Hydrate a `SessionState` from the `AutoEditResult` (rallies + score history).
- Launch `MainWindow` directly into review mode rather than the marking mode.
- Visually flag `low_confidence_rally_indices`: amber border on rally cards in the review
  mode list view.
- User scans, flips any wrong winners (new primitive — see 4.4), adjusts timing if
  needed, and exports as today via the Generate button.

### 4.4 Add "Flip winner" primitive to review mode (critical)

**Problem**: The current review UI only exposes timing and score-string edits
(`src/ui/review_mode.py:741-743` — `timing_adjusted`, `score_changed`). It has no way to
change `rally.winner`. Cascade replay in `MainWindow._on_review_score_changed`
(`src/ui/main_window.py:2042-2046`) uses the existing `rally.winner` unchanged.

That means a misclassified rally's winner stays wrong in the exported
`.training.json`, which then poisons the next training run. The feedback loop is broken
without this primitive.

**Fix**:
1. `src/ui/review_mode.py`: add a new signal `winner_flipped(int)` (rally index). Add a
   button or icon on each rally card labelled "Flip winner" (or similar) that emits it.
2. `src/ui/main_window.py`: add slot `_on_review_winner_flipped(index)`:
   ```python
   rally = self.rally_manager.get_rally(index)
   rally.winner = "receiver" if rally.winner == "server" else "server"
   # Then cascade: same logic as _on_review_score_changed's cascade branch,
   # replaying ScoreState from this rally's score_at_start forwards, using the
   # now-corrected rally.winner values to re-derive score_at_start for subsequent
   # rallies.
   ```
3. `src/core/rally_manager.py`: add `update_rally_winner(index, new_winner, cascade=True)`
   mirroring the shape of the existing `update_rally_score()`.
4. The "Flip winner" button should be especially visible on rally cards with the amber
   low-confidence flag — that's where it's most often needed.

**Why this matters beyond auto-mode**: even in purely manual editing, a user who pressed
the wrong key during live marking currently has no way to fix it in review without
re-marking from scratch. This is a genuine gap, and fixing it benefits both workflows.

### 4.5 Feedback loop

When the user re-exports after corrections, the `.training.json` produced reflects the
corrected winners (because `rally.winner` is now editable). Next time they train, these
new examples improve the model — the system gets better as it is used.

### 4.6 Verification

- Unit test for amber-flag rendering given a stub `AutoEditResult`.
- Unit test for `RallyManager.update_rally_winner` cascade: build a hand-constructed
  game, flip a rally's winner, assert downstream `score_at_start` values match a
  hand-computed expectation.
- Manual end-to-end: fresh video → auto-process radio → corner clicks → progress dialog
  → review mode opens pre-populated → low-confidence rally is amber → user flips its
  winner → downstream scores update → export → open in Kdenlive → confirm subtitles
  match.

---

## Phase 5 (optional, deferred)

Multi-modal rally boundary model. Only invest if, after Phases 0–4 ship, you see that
rally boundary errors (not winner errors) are the dominant source of review-mode
corrections.

Approach: extend `ml/dataset.py` to emit `(mel_spectrogram, optical_flow_magnitude)`
paired windows; add a second input branch to `RallyDetector`; retrain on existing audio
labels. Compare precision/recall to the audio-only baseline.

---

## Effort estimate

| Phase | Days |
|-------|------|
| 0. Infra + corner UI + retrofit 14 videos | 2–3 |
| 1. Schema 1.1 + winner-label backfill | 0.5 |
| 2. Winner dataset + model + training | 3–5 |
| 3. Pipeline orchestrator + CLI + integration test | 2–3 |
| 4. UI integration (auto mode + review-mode flagging) | 2–3 |
| **Total (Phases 0–4)** | **~10–14 working days** |

## Files at a glance

### Reused without modification
- `src/core/score_state.py`
- `src/core/rally_manager.py`
- `src/core/models.py` (additions only to `SessionState` and `GameConfig`)
- `src/output/kdenlive_generator.py`
- `src/output/subtitle_generator.py`
- `src/ui/review_mode.py`
- `ml/model.py`, `ml/train.py`, `ml/predict.py` (existing audio CNN)
- `ml/config.py` (extended with `WinnerModelConfig`)
- `ml/dataset.py`

### To modify
- `ml/requirements.txt`, `ml/cli.py`, `ml/__init__.py`
- `configure` (inline `ML_DEPS` array — must match `ml/requirements.txt`)
- `src/output/training_data_generator.py` (schema 1.1, `winning_team`, `court_corners`, `generated_by`)
- `src/ui/setup_dialog.py` (auto toggle, corner calibrator launch)
- `src/ui/main_window.py` (auto-mode entry path, `_on_review_winner_flipped` slot)
- `src/ui/review_mode.py` (add `winner_flipped` signal + button per rally card)
- `src/core/rally_manager.py` (`update_rally_winner` method with cascade)
- `src/core/models.py` (`SessionState.court_corners`, `GameConfig.auto_mode`, `GameConfig.court_corners`)
- `Makefile` (optional new `build-auto-editor` target)

### To create
- `ml/video_features.py`
- `ml/winner_dataset.py`
- `ml/winner_model.py`
- `ml/train_winner.py`
- `ml/predict_winner.py`
- `ml/auto_edit.py`
- `ml/tools/backfill_winner_labels.py`
- `ml/tools/calibrate_existing.py`
- `src/ui/widgets/court_calibrator.py`
- `src/ui/dialogs/auto_edit_progress.py`
- `tests/test_video_features.py`
- `tests/test_court_calibrator.py`
- `tests/test_winner_model.py`
- `tests/test_auto_edit.py`
