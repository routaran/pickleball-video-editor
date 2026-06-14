# Design decisions

The design in this plan was shaped by a few key questions. Each decision here locked in a
downstream choice; revisiting them later means revisiting large chunks of the plan.

## Camera setup: semi-fixed, mobile between courts

**Decision**: we do not assume the camera is in a fixed position across all videos. It is
in the "same general location" (same height, same relative orientation to the court) but
is moved court-to-court, so each video has a slightly different angle.

**Implication**: a classifier trained on raw pixel-space clips would over-fit to whatever
court angles happened to appear in the training set. **We chose to use homography-based
canonical-view warping** to absorb the per-video variation. Cost: one-time 4-corner click
per video (~5 seconds). Benefit: the model sees a fixed, camera-invariant court every
time.

**Alternative considered**: auto-detect court via ML. Rejected because it adds a whole
separate ML task with its own training data needs, and the user's click takes ~5 seconds.
Not worth the complexity.

**Alternative considered**: heuristic (assume team 1 is on the far side at video start).
Rejected because silent failure is possible when the convention is broken, and those
failures are very hard to debug.

## Training data: 14 games today, 30+ target

**Decision**: design the model assuming ~14 games at the start and ~30 at target.

**Implication**: we can't afford a data-hungry architecture. **We chose pretrained
ResNet-18 + 1D temporal conv** for the winner classifier. Heavy augmentation (horizontal
flip + label swap doubles the effective dataset). No from-scratch training of large
models.

**Implication 2**: winner labels must come from data we already have. **We chose to
derive `winning_team` from existing `winner` + `serving_team` fields** rather than ask
the user to relabel. Zero new labeling work.

## Autonomy: auto + optional review (not fully headless)

**Decision**: the pipeline produces a draft; the user can open it in the existing review
mode, fix flagged rallies, then export.

**Implication**: the bar for model accuracy is lower — errors caught in review don't
reach the final output. **We chose to expose winner-classifier confidence per rally and
visually flag low-confidence ones** in review mode.

**Implication 2**: corrections re-exported from the review mode become new training data.
**We chose to tag auto-generated `.training.json` with `generated_by: "auto_edit"`** so
they don't pollute training unless curated through review.

**Alternative considered**: fully headless CLI-only export. Rejected because with 14
games of training data, any model will make some mistakes, and those mistakes would ship
to the final output silently. A 10-second review pass is a small price.

## Game type: doubles first

**Decision**: design and validate with doubles games first.

**Implication**: the 0-0-2 case, server rotation, and `first_server_player_index`
tracking all need to work day one. **The existing `ScoreState` engine already handles
all of these**, so this adds zero new code — it just means we pick doubles games as the
first training/evaluation set.

**Implication 2**: the visual task is harder (4 players instead of 2, more action on
screen). Mitigated by the canonical-view warp (players are in fixed regions of the
canvas) and by heavy augmentation.

**Singles support comes for free** since `ScoreState` already supports it and the winner
task is strictly easier with fewer players. No special-case code needed.

## Compute: local NVIDIA GPU

**Decision**: we have a CUDA-capable GPU on the development machine.

**Implication**: we can use a pretrained ResNet-18 backbone and train end-to-end without
worrying about CPU inference performance. **We chose to target GPU both for training and
inference.** If the user later wants CPU-only inference (e.g., for distribution), we'd
swap in a MobileNet-class backbone — the `ml/winner_model.py` abstraction makes this a
~10-line change.

## Court-side identification: one-time manual click per video

**Decision**: the user clicks 4 court corners once per video, in a labelled sequence
that also encodes the team-to-side mapping:
1. Team 1 baseline-left
2. Team 1 baseline-right
3. Team 2 baseline-right
4. Team 2 baseline-left

**Why the click order matters**: corner geometry alone tells you the perspective
transform, but not which side is Team 1. We don't want a separate "which side is Team 1"
input — one click sequence is enough if the UI labels each click explicitly. After
homography warp, Team 1 is always the top half of the canonical 256×128 canvas.

**Implication**: we need a small UI widget (`CourtCalibratorWidget`) in the setup dialog
with explicit per-click labelling, plus a retrofit tool to add corners to the 14
already-labeled videos.

**Implication 2**: `GameConfig`, `SessionState`, and the training-JSON schema all grow a
`court_corners` field. The JSON schema bumps to `"1.1"`.

## First server: keep Team-1 convention, don't add configurability

**Decision**: Team 1 always serves first. Do not add a first-server selector.

**Why**: `ScoreState` today hard-codes `serving_team = 0` (`src/core/score_state.py:70`)
and the manual editor has shipped with this convention throughout its life. No user has
reported needing it configurable. Adding configurability would require changes to
`GameConfig`, `SetupDialog`, `SessionState`, `ScoreState`, and the training JSON
schema — significant blast radius for a feature that hasn't been needed. If a user ever
truly needs this (e.g., to record a video where Team 2 actually starts), add it then.

**Implication**: the auto-mode inputs are **video + the existing `GameConfig` (player
names, game type, victory rules) + corners**. No "who serves first" selector.

## Winner-flip action in review mode: add it

**Decision**: review mode gets a new `winner_flipped` signal and a button per rally
card. `RallyManager` gets `update_rally_winner(index, new_winner, cascade=True)`.

**Why**: without it, the human-in-the-loop feedback loop is broken. If the winner
classifier misclassifies a rally, the user can currently only fix it by re-marking the
rally from scratch (the review UI exposes only timing and score-string edits). Exported
`.training.json` would keep the wrong winner, and the next training run would learn
from it.

**Bonus**: this also plugs a gap in the existing manual workflow — a user who pressed
the wrong key during live marking currently has no way to fix it in review either. The
new primitive benefits both modes.

## v1 simplicity: skip temperature scaling, skip random erasing

**Decision**: v1 of the winner model uses raw softmax confidence with a 0.7 threshold
and only two augmentations (horizontal flip + label swap, color jitter, temporal
jitter). Temperature scaling and random erasing are explicitly deferred.

**Why**: neither is load-bearing for a working first release. Temperature scaling is a
calibration nicety — add it only if the flag rate at threshold 0.7 is clearly wrong in
practice. Random erasing is low-signal augmentation for this task. Start simple, add
complexity only with evidence it helps.

## What we're NOT building

- **Explicit ball tracking**. Unnecessary for the winner task; the CNN can learn where
  action ended from pixel motion alone.
- **Pose estimation / player tracking**. Unnecessary for the winner task and would add
  significant complexity for minimal benefit.
- **Auto player-identity recognition**. We don't need to know which player is which; we
  only need to know which team won. Player names are subtitle labels, typed by the user.
- **A bigger scoring engine**. `ScoreState` already handles every rule we care about.
- **A new review UI**. The existing review mode is already the right place for
  human-in-the-loop correction; we just add a visual flag for low-confidence rallies.
- **Multi-modal rally boundary model** (Phase 5 in the plan). Only built if Phase 4
  reveals that boundary errors, not winner errors, are the dominant failure mode.
