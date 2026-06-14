# Training data

## Schema migration: 1.0 → 1.1 (landed)

The schema bump described below has been applied. `TrainingDataGenerator.SCHEMA_VERSION`
is `"1.1"` and new exports emit `winning_team`; `court_corners` is captured on
`SessionState`. The "1.0" form is documented here for legacy compatibility.

### Legacy schema (`"1.0"`)

```json
{
  "schema_version": "1.0",
  "video": {
    "path": "...",
    "fps": 60.0,
    "duration_seconds": ...,
    "width": 1920,
    "height": 1080
  },
  "game": {
    "type": "doubles",
    "victory_rules": "11",
    "team1_players": [...],
    "team2_players": [...],
    "completion": { ... }
  },
  "rallies": [
    {
      "index": 0,
      "score_at_start": "0-0-2",
      "winner": "server",
      "is_post_game": false,
      "comment": null,
      "padded": { "start_frame": ..., "end_frame": ..., "start_seconds": ..., "end_seconds": ... },
      "raw":    { "start_frame": ..., "end_frame": ..., "start_seconds": ..., "end_seconds": ... }
    }
  ],
  "rally_count": 42
}
```

### Current schema (`"1.1"`)

Three additions:
1. `video.court_corners: [[x, y], [x, y], [x, y], [x, y]]` — user-clicked pixel
   coordinates in the order Team-1-baseline-left → Team-1-baseline-right →
   Team-2-baseline-right → Team-2-baseline-left. The click order carries the
   team-to-side mapping; the calibrator UI prompts each click explicitly. Required
   for the winner classifier.
2. Per rally: `winning_team: 0 | 1` — derived from `winner` + live `serving_team`.
3. Top-level: `generated_by: "manual" | "auto_edit"` — distinguishes human-edited vs
   auto-generated exports. Auto-generated files should be filtered out of training
   unless explicitly allowlisted, to prevent bootstrapping model errors.

Backward-compatible reads: code that loads a training file should tolerate missing
`court_corners` and `winning_team` on `"1.0"` files.

## Label derivation for existing games (no new annotation)

### Why a naive replay is wrong

A first-pass approach would be: init `ScoreState`, chain `server_wins()` /
`receiver_wins()` per rally, read `serving_team` at each step to derive `winning_team`.

This fails for any game where the user used Edit Score or Force Side-Out mid-game.
Session state persists `interventions=[]` and `comments=[]` hard-coded
(`src/ui/main_window.py:1707-1708`, with TODOs), so we have no record of what
interventions happened. A naive replay will diverge from the real game state after the
first intervention and produce wrong `winning_team` values from that point on.

### What actually works: re-sync per rally

Each rally's `score_at_start` was captured at rally time by the live `ScoreState`,
including the effect of any interventions just applied. So `score_at_start` is faithful
even when intervention history is lost. Re-sync `ScoreState` from it per rally:

```python
# ScoreState requires player_names (src/core/score_state.py:41-46).
score = ScoreState(
    game_type=game["type"],
    victory_rules=game["victory_rules"],
    player_names={"team1": game["team1_players"], "team2": game["team2_players"]},
)
# Team 1 serves first by convention, matching the manual editor.

for rally in rallies:
    # Re-sync from the recorded score — absorbs any lost intervention effects.
    score.set_score(rally["score_at_start"])
    serving = score.serving_team

    if rally["winner"] == "server":
        winning_team = serving
        score.server_wins()
    else:
        winning_team = 1 - serving
        score.receiver_wins()
    rally["winning_team"] = winning_team
```

This works because:
- `score_at_start` is recorded per rally at capture time, so it reflects the truth
  including interventions.
- `ScoreState.set_score()` already exists to parse a score string back into internal
  state, including `serving_team` and (for doubles) `server_number` and
  `first_server_player_index`.
- We never need to reconstruct the intervention *history*; we just need the *effect* at
  each rally's start, which is what `score_at_start` gives us.

If a rally's `score_at_start` fails to parse (malformed data), log and skip the
containing game — don't ship silently-wrong labels.

## Dataset construction (for winner classifier training)

For each rally in each `.training.json` (schema `1.1` with corners):
- Clip window: `raw.end_seconds - 2.5s` to `raw.end_seconds`.
- Frame rate: 8 fps → 20 frames per clip.
- Per-frame homography warp to canonical 256×128.
- Label: `winning_team ∈ {0, 1}`.

Dataset size estimates:
- 14 games × ~40 rallies = ~560 examples.
- With horizontal-flip + label-swap augmentation: ~1120 effective examples.
- At 30-game target: ~1200 base, ~2400 augmented.

## Train/val split

**Video-wise split (not rally-wise)**: all rallies from any single video go entirely into
train OR val. Rally-wise splitting would leak information because rallies within a single
video share lighting, court, angle — a model could memorize those as shortcuts.

Target: 80/20 video split. At 14 games that's 11 train / 3 val — tight but workable.
Prefer stratified-by-winner-distribution so each split has roughly balanced wins.

## Class balance

Pickleball games are roughly balanced winner-wise on average, but any individual game can
be lopsided (11-3, 11-4). Across 14 games, expect approximate 50/50 team-0 vs team-1 wins
overall. If the split is skewed, use class-weighted `CrossEntropyLoss`:

```python
class_weights = torch.tensor([
    total_samples / (2 * n_team0_wins),
    total_samples / (2 * n_team1_wins),
])
loss = nn.CrossEntropyLoss(weight=class_weights)
```

## Augmentation strategy

Applied only to training split. v1 keeps this minimal:

- **Horizontal flip + label swap**. Flips canonical frame horizontally and toggles
  `winning_team`. Essentially free data doubling since the canonical court is
  left/right symmetric.
- **Color jitter**: brightness ±0.2, contrast ±0.2, saturation ±0.2. Simulates lighting
  variation.
- **Temporal jitter**: shift clip start by ±0.2 s uniformly random. Regularizes the
  model against fixating on exact frame positions.

Explicitly deferred for v1: random erasing and mixup. Add only if validation accuracy
stalls and augmentation is the suspected cause — evidence-driven, not preemptive.

## Flagging auto-generated training data

Every `.training.json` emitted by `auto_edit` carries `generated_by: "auto_edit"`. The
training loader defaults to **excluding** these files. Only files with `generated_by:
"manual"` (i.e., human-edited, possibly post-auto-correction via review mode) are used
for training.

This prevents the model from learning its own errors. A file becomes "manual" once the
user has opened it in review mode, made corrections (or simply confirmed), and
re-exported.
