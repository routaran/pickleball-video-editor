# Technical Architecture

## Data flow

```
┌─────────────────────────────────────────────────────────┐
│ Inputs                                                  │
│   • video file (mp4)                                    │
│   • game setup: doubles, victory rules, player names    │
│     (Team 1 serves first by convention — same as the    │
│      existing manual app; ScoreState hard-codes this)   │
│   • 4 court corners (user-clicked once, in the order    │
│     Team-1-baseline-left → Team-1-baseline-right →      │
│     Team-2-baseline-right → Team-2-baseline-left)       │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 1: Audio rally boundary detection (existing)      │
│   ffmpeg → 22050 Hz mono WAV                            │
│   → mel spectrogram (128 bins × T frames)               │
│   → CNN binary classifier (per 2s window, hop 0.25s)    │
│   → smooth + threshold + merge + filter                 │
│   Output: list[(start_s, end_s)]                        │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 2: Per-rally winner classification (new)          │
│   For each rally:                                       │
│     ffmpeg CLI → last 2.5s at 8 fps (20 frames)         │
│     → per-frame homography warp (256×128 canonical)     │
│     → ResNet-18 backbone → 1D temporal conv → softmax   │
│   Output: list[(winning_team ∈ {0,1}, confidence)]      │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 3: Deterministic score simulation (existing code) │
│   Init ScoreState(game_type, victory_rules, player_names)│
│   For each rally, in order:                             │
│     snapshot = ScoreState.save_snapshot()               │
│     score_at_start = ScoreState.get_score_string()      │
│     RallyManager.start_rally(start, snapshot)           │
│     if winning_team == serving_team: server_wins()      │
│     else: receiver_wins()                               │
│     RallyManager.end_rally(end, winner, score, snap)    │
│     if is_game_over(): break                            │
│   Output: list[Rally] with full score history           │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 4: Output (mostly reused)                         │
│   KdenliveGenerator → .kdenlive + .ass (unchanged)      │
│   TrainingDataGenerator → .training.json (schema 1.1:   │
│     adds winning_team, court_corners, generated_by)     │
└───────────────────────┬─────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 5: Optional human review (existing review UI)     │
│   Load predicted rallies into review mode               │
│   Amber-flag rallies with confidence < threshold        │
│   User adjusts, then exports                            │
└─────────────────────────────────────────────────────────┘
```

## Why homography calibration

The camera moves between courts. A classifier that trains on pixel-space clips would see
a different court position in every game, effectively learning a mix of "court shape" and
"camera pose". With only 14 games of training data, that's not enough signal.

By asking the user to click the 4 court corners once per video (takes ~5 seconds), we
compute a perspective transform that maps the actual court pixels onto a fixed canonical
256×128 rectangle. Every clip fed to the classifier looks like a top-down view of the
exact same court. The model only has to learn ball/player motion patterns in canonical
space — a much smaller problem, well-served by our dataset size.

This also means "which side is Team 1?" is trivial, but only because the click order
itself carries the mapping. The user is instructed to click corners in this sequence:

1. Team 1 baseline-left (from the camera's point of view)
2. Team 1 baseline-right
3. Team 2 baseline-right
4. Team 2 baseline-left

After homography warp, Team 1 is always the top half of the canonical 256×128 canvas and
Team 2 is the bottom half. The calibrator UI must label the clicks explicitly ("click
Team 1's baseline-left corner") so the user can't guess wrong — the mapping is not
inferable from geometry alone.

## Why the winner classifier is the right abstraction

The naive alternative is to predict score directly from the full video — one huge
sequence model over the whole game. That's a terrible idea: the model would need to learn
pickleball scoring rules from data, which requires far more examples than we have.

Instead, we decompose:
- Learn "who won this rally" from a 2.5-second clip → a **simple binary visual task**.
- Compose rallies into a final score via the **existing, correct, already-tested scoring
  engine** (`ScoreState`).

The ML only handles the visual pattern recognition; the deterministic code handles the
rules. This decomposition is the single most important design choice in this plan.

## Why "winner of the rally" is learnable from visual signal alone

At the end of every rally, something definitive happens in the video: the ball lands out,
the ball hits the net, the ball bounces twice on one side, a player clearly misses. All
of these cues are in the visual signal. Sonar-like ball tracking isn't required — a CNN
looking at canonical-view motion patterns in the final 2.5s can learn "where did the
action end" without ever tracking the ball explicitly.

Augmentation by horizontal flip + label swap is particularly powerful: a clip of Team 0
losing is identical to Team 1 losing when mirrored. We get a 2× dataset for free.

## Model architecture

```
Clip: (B, T=20, 3, 128, 256)      # B=batch, T=frames, 3=RGB
        │
        ▼
torchvision.resnet18 backbone (pretrained ImageNet)
fc replaced with Identity
        │
        ▼ per-frame features: (B, T, 512)
        │
Permute → (B, 512, T)
        │
        ▼
Conv1d(512 → 128, kernel=3) + ReLU
AdaptiveAvgPool1d(1)
        │
        ▼ (B, 128)
        │
Linear(128 → 2)
        │
        ▼ logits: (B, 2)
```

- ~11.2M params, dominated by ResNet-18.
- Inference cost per rally: one ResNet forward on 20 frames ≈ 10-50ms on GPU.
- Trainable in ~10 minutes on the 14-game dataset on a single GPU.

## Integration points

The pipeline terminates at `rally_manager.to_segments()` with the exact same data
structure the existing manual editor produces. `KdenliveGenerator` and
`SubtitleGenerator` are reused unchanged. `TrainingDataGenerator` gets a small schema
bump (1.0 → 1.1). Review mode gets two additions: low-confidence flagging and a
winner-flip primitive.

Source-code changes outside of `ml/`:
- `GameConfig` and `SessionState`: add `court_corners`.
- `TrainingDataGenerator`: schema 1.1 fields (`winning_team`, `court_corners`,
  `generated_by`).
- `SetupDialog`: manual/auto toggle and corner-calibrator launch.
- `MainWindow`: auto-mode entry path, `_on_review_winner_flipped` slot.
- `ReviewModeWidget`: `winner_flipped` signal, per-rally flip button, amber low-
  confidence flag.
- `RallyManager`: new `update_rally_winner(index, new_winner, cascade=True)` method.

The scoring engine (`ScoreState`) and the core rally tracking logic stay untouched.
`KdenliveGenerator` and `SubtitleGenerator` stay untouched.

## Confidence and human oversight

Two places where confidence matters:

1. **Winner classifier softmax**. v1 uses raw softmax probability and a simple 0.7
   threshold to flag rallies for review. If flag rates turn out miscalibrated in
   practice (too many or too few), add temperature scaling then — don't preemptively.
2. **Audio CNN rally boundaries**. These already have per-window probabilities; for now,
   we don't expose boundary confidence to the user, but if Phase 5 becomes necessary, we
   could.

The review UI needs a "flip winner" action (new in Phase 4) so that when the model
misclassifies, the user can fix it in one click rather than re-marking the rally. This
is the critical correction primitive that makes the human-in-the-loop loop actually
close.

The design assumes the user will glance at flagged rallies and fix any that look wrong.
That's a lightweight interaction — much faster than editing from scratch.
