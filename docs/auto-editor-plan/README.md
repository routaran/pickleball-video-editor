# Automated Pickleball Video Editor

## Problem statement

The existing Pickleball Video Editor is a manual tool. For every game I record, I have to:

- Watch the full video in the editor
- Press a key to mark the start of every rally
- Press a key at the end of every rally to record who won (server or receiver)
- Handle corrections manually via the Edit Score and Force Side-Out dialogs
- Finally export to `.kdenlive` + `.ass` subtitles

For a typical doubles game this is ~40 rallies of click-work per game, plus watching the
full video in near-real-time. It is repetitive, time-consuming, and error-prone.

What I actually want is:

> Give me a system where I drop in a raw video, tell it who the players are, click the
> four court corners once, and it hands me back a complete `.kdenlive` project with
> `.ass` subtitles showing correctly tracked scores for every rally — with zero
> per-rally click-work. A quick review pass to fix any rally the model wasn't confident
> about is fine; no per-rally marking from scratch.

The audio-only rally detector that lives in `ml/` today solves a fraction of this (it
detects rally boundaries from audio). It does **not** know who won each rally and it is
not wired into the output pipeline. This plan closes that gap.

**First server convention**: Team 1 serves first. This matches the existing manual
editor, where `ScoreState` hard-codes `serving_team = 0`. Making first-server
configurable would touch `GameConfig`, `SetupDialog`, `SessionState`, `ScoreState`, and
the training JSON schema for no real-world benefit — the manual app has never needed
this knob. If that changes later, we add it then.

## Solution summary

A two-stage ML pipeline plus deterministic score simulation:

1. **Stage 1: Rally boundary detection** — reuse the existing audio CNN (`ml/predict.py`)
   to produce a list of `(start, end)` intervals.
2. **Stage 2: Point-winner classification** — new video-based classifier that looks at
   the last ~2.5 seconds of each rally and predicts which team won. Because the camera
   moves between courts, the user clicks the 4 court corners once per video; we use that
   homography to warp every rally clip into a canonical top-down court view before
   feeding the model. The model sees a camera-invariant representation.
3. **Stage 3: Deterministic score simulation** — walk through the predicted rallies in
   order, feeding "server wins" or "receiver wins" into the existing `ScoreState` engine
   based on whether the predicted winning team equals the currently-serving team. The
   existing code already handles every pickleball rule (doubles 0-0-2, side-outs, server
   rotation, win-by-2).
4. **Stage 4: Output generation** — the simulated rallies plug straight into the existing
   `KdenliveGenerator` and `SubtitleGenerator`. `TrainingDataGenerator` has been bumped
   to schema `"1.1"` (carries `winning_team`); `court_corners` lives on `SessionState`
   and is written into the training JSON.
5. **Stage 5: Optional review pass** — auto-generated rallies load into the existing
   review mode. Rallies whose winner-confidence was low are visually flagged. The user
   scans, optionally flips wrong winners (new primitive — see `implementation.md`),
   adjusts timing if needed, and exports. Corrections feed the next training run — the
   system gets better as it is used.

**Key insight that makes this tractable**: winner labels can be recovered from training
data I've already collected — no new labeling work. Each `.training.json` rally has
`winner: "server"|"receiver"` and a recorded `score_at_start`. The backfill tool
re-syncs `ScoreState` from `score_at_start` per rally (which faithfully captures the
post-intervention serving team at rally time) and derives `winning_team: 0|1` from
`winner` + the re-synced `serving_team`. See `training-data.md` for the algorithm and
why a naive replay without re-sync would fail on games that had mid-game interventions.
I currently have 14 labeled games (~560 rally examples), targeting 30+ (~1200
examples).

## Reading order

New to this effort? Read in this order:

1. **This file** (README.md) — you are here.
2. **`current-state.md`** — what the codebase does today. Skip if you already know it.
3. **`decisions.md`** — the key design decisions and why they were made the way they
   were. Short; read it.
4. **`architecture.md`** — the full technical design with data flow diagrams and model
   details.
5. **`training-data.md`** — training data schema, label derivation, dataset strategy.
6. **`implementation.md`** — the step-by-step build plan. Open this when it's time to
   actually start coding.

## Project status

- Documentation: this directory.
- Implementation: rally-trainer pipeline landed (training, dataset, models,
  prediction in `ml/`); court corner calibration tools landed in `ml/tools/`;
  Flip Winner review action and auto-process mode integrated. See
  `implementation.md` for the original phase breakdown and `review-fixes.md`
  for post-review adjustments.
