# Current state of the project

Everything below already exists in the repo as of writing. This document captures what's
there so the plan builds on it correctly.

## The editor (manual flow, fully working)

`src/main.py` launches a Qt app:
- `SetupDialog` collects video path, game type, victory rule, player names.
- `MainWindow` loads the video via `python-mpv` and presents rally-marking controls.
- User hotkeys:
  - **C** → rally start
  - **S** → server wins (ends rally, increments serving team)
  - **R** → receiver wins (ends rally, triggers side-out logic)
  - **U** → undo
- Interventions: Edit Score, Force Side-Out, Add Comment, Time Expired.
- Review mode lets the user adjust timing, scores, and comments before exporting.
- Export produces `.kdenlive` + `.ass` + `.training.json`.

Key files:
- `src/ui/main_window.py` — main controller (~2500 lines).
- `src/ui/setup_dialog.py` — new-session flow, game config.
- `src/ui/review_mode.py` — pre-export review UI.
- `src/ui/dialogs/edit_score.py`, `force_side_out.py`, etc.
- `src/video/player.py` — MPV widget wrapper.

**Review-mode gap addressed by this plan (now landed)**: `ReviewModeWidget`
exposes `winner_flipped(int)` alongside `timing_adjusted` and `score_changed`
(`src/ui/review_mode.py`), and `RallyManager.update_rally_winner(index,
new_winner)` mutates the rally's winner without touching the score cascade.
A Flip Winner button in the review control panel emits the signal; the cascade
replay in `_on_review_score_changed` reads the updated winner so corrections
propagate to downstream rallies.

**GameConfig status**: `GameConfig` now carries auto-edit setup state including
court corners and the auto-mode flag. It still has no first-server field; Team 1
remains the preserved first-server convention.

## Scoring engine (fully working, reused as-is)

`src/core/score_state.py` — `ScoreState` class:
- Constructor signature: `ScoreState(game_type, victory_rules, player_names)` —
  `player_names` is required, not optional (`src/core/score_state.py:41-46`). Any
  pseudocode in this plan must pass it.
- **Team 0 (Team 1 in the UI) serves first, hard-coded** at `serving_team = 0`
  (`src/core/score_state.py:70`). There is no first-server parameter. The plan adopts
  this as a convention rather than adding configurability.
- Handles singles and doubles.
- Handles 0-0-2 edge case (first server in doubles has only one fault).
- Handles server rotation: Server 1 fault → Server 2 serves; Server 2 fault → side-out.
- Handles side-switching via `first_server_player_index` based on score parity.
- Win detection: `is_game_over()` returns `(bool, winning_team|None)` for standard games
  (win-by-2 required); always returns `False` for timed games.
- Score string formatting: `"X-Y"` for singles, `"X-Y-Z"` for doubles.
- `set_score(score_string)` re-syncs internal state from a score string — used by the
  backfill tool to absorb missing intervention history.
- Serialization: `save_snapshot()` / restore via snapshots for undo.

`src/core/rally_manager.py` — `RallyManager` class:
- Tracks rallies in progress.
- Applies start/end padding (-0.5s / +1.0s) for editorial cuts; stores both raw and
  padded timestamps.
- `to_segments()` emits the list of `{in, out, score, is_post_game}` dicts that the
  Kdenlive generator consumes.
- Undo stack with action history.

`src/core/models.py` — dataclasses:
- `Rally` — padded + raw timestamps, winner, score_at_start, comment.
- `ScoreSnapshot` — frozen dataclass: `score`, `serving_team`, `server_number`,
  `first_server_player_index`.
- `SessionState` — full game: players, rallies, score history, interventions.
- **Gap**: sessions are currently persisted with `interventions=[]` and `comments=[]`
  hard-coded (`src/ui/main_window.py:1707-1708`, with TODOs). This means intervention
  history is not recoverable after save/load. This plan handles it by re-syncing
  `ScoreState` from each rally's recorded `score_at_start` during backfill rather than
  trying to replay interventions we no longer have. Rally-level score data itself is
  faithful because it's captured at rally time by the live ScoreState.

## Output generators (fully working, reused as-is)

`src/output/kdenlive_generator.py`:
- Takes segments + fps + resolution + player names.
- Emits MLT-XML `.kdenlive` project file referencing an ASS subtitle track.
- Internally calls `SubtitleGenerator` to build the ASS file with per-rally score
  overlays.

`src/output/subtitle_generator.py`:
- ASS / SRT generation with rally scores as subtitles.
- Centisecond timing, intro line with player names, final score line.

`src/output/training_data_generator.py`:
- Walks a completed `SessionState` and emits `.training.json`.
- Current schema version: `"1.1"` (`TrainingDataGenerator.SCHEMA_VERSION`).
  Per-rally fields: `index`, `score_at_start`, `winner`, `winning_team`,
  `is_post_game`, `comment`, `padded.*`, `raw.*`.
- `winning_team` (0 or 1, or `None` for post-game/highlights) is derived by
  re-syncing `ScoreState` from each rally's recorded `score_at_start`.

`src/output/ffmpeg_exporter.py`:
- Direct MP4 export with hardware encoding. Not touched by this plan.

## Audio ML (working, reused for Stage 1)

`ml/` directory:
- `config.py` — `AudioConfig`, `TrainConfig`, `InferenceConfig`, `PathConfig`.
- `dataset.py` — audio extraction via ffmpeg (22050 Hz mono WAV), mel spectrogram
  computation (128 bins, 2048 FFT, 512 hop), sliding-window PyTorch `Dataset`, caching.
- `model.py` — `RallyDetector`, a small CNN (3 conv blocks, ~4.6K params) for binary
  classification per 2-second window.
- `train.py` — full training loop: video-wise 80/20 split, `BCEWithLogitsLoss` with
  positive-class weighting, Adam, early stopping, saves `best_model.pt`.
- `predict.py` — sliding-window inference at 0.25s hop, median smoothing, thresholding,
  segment merging, minimum-length filtering. Outputs JSON `{start_seconds, end_seconds,
  duration_seconds}` per rally.
- `cli.py` — unified CLI entry point. `python -m ml train|predict`.

Additional ML pieces now present:
- `video_features.py` — native-frame extraction, homography computation, and
  canonical court warping for winner clips.
- `winner_dataset.py`, `winner_model.py`, `predict_winner.py`, `train_winner.py`
  — winner-classifier data loading, model, inference, and training.
- `auto_edit.py` and `cli.py` — end-to-end auto-edit orchestration and unified
  CLI entry points.
- `motion/` — offline YOLOv8n + ByteTrack motion-feature extraction (runs in a
  separate `.venv-motion`; writes `ml/cache/motion/*.npz`) plus a court-polygon-
  dilation fusion path (`predict_fused`) that augments the Stage-1 audio rally
  boundaries. `auto_edit.py` Stage 1 uses fusion when a motion cache exists, else
  falls back to tuned audio-only.

## Training data volume

- 14 games labeled today as `.training.json` files. User targets 30+.
- Per-game: ~40 rallies average → ~560 rally examples today, ~1200 at target.
- Schema `"1.1"` is current. Older `"1.0"` files lack `winning_team` and need
  migration; `court_corners` is also absent from legacy files.

## Build & run

- `./configure --enable-ml` sets up the `.venv` with ML dependencies.
- `make run` launches the editor.
- `make test` runs pytest.
- `make lint` runs ruff + mypy.
- Application entry: `src/main.py`.

## Config / settings

- User config lives at `~/.config/pickleball-editor/config.json`.
- Keyboard shortcuts are configurable (`src/core/app_config.py`).
- Recent sessions stored at `~/.local/share/pickleball-editor/sessions/`.

<!-- DRAFT: wiki-source-update 2026-05-31; prompted by 6ac5b59, f700643, f71d626, b7d8305, 9087838, d9ba004, e09da78 -->
## Data & evaluation tooling (landed since)

A second-generation data/eval layer now sits around the winner classifier:

- `ml/examples.py` — `RallyExample` / `RallyExampleIndex` + deterministic `example_key()` over the labeled corpus (6ac5b59).
- `ml/features/` — pluggable feature extraction: `FeatureExtractor` protocol, version-aware on-disk cache, registry/service, a rally-metadata extractor, and a torch-free audio-end stub (f700643).
- `ml/evaluation/` — rule-based baselines, calibration/ECE diagnostics, and deterministic video-wise splits (f71d626).
- `ml/review_priority.py` — triages low-confidence predictions for human review (b7d8305).
- `WinnerDataset.from_rally_examples()` — build datasets from pre-parsed examples (9087838); checkpoints now embed config + warn on mismatch, and training prints per-video validation accuracy (d9ba004).
- `ml/config.py` adds `FeatureCollectionConfig` and a `clip_duration_override_s` ablation knob (e09da78).
