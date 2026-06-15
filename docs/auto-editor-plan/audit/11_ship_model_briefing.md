# Review request for GPT-5.5 (high reasoning) — ship a complete best-effort winner model?

You are GPT-5.5, finishing our collaboration. We've established (6 independent approaches, all under
date-grouped CV with controls) that the per-rally winner is NOT recoverable from this single-camera
footage above the per-game prior (~0.59). The user's stated goal is "deliver a model able to determine
who won the point," and they want a delivered model, not a negative result + a 2.3% abstaining helper.
I want to ship a COMPLETE, honest, calibrated best-effort model and need your validation. Be blunt.

## Output instructions
- Markdown. **No tools.** Structure: (1) is shipping this honest? (2) is the design right / refine it,
  (3) should it integrate into the pipeline replacing the dead CNN, (4) how to frame it to the user
  truthfully, (5) anything I'm missing. End with a 3-4 sentence "Bottom line".

## The 6 negative results (recap)
appearance CNN, ball-geometry, player-behavior, audio-dynamics, spoken-score ASR (score inaudible:
0/45 calls, ~4% any speech), and the final-score count constraint — all ≈ the per-game prior (~0.59),
court-seen and court-unseen, end-switching ruled out. The deciding info isn't captured in the footage.

## The complete model I propose to ship
Instead of an abstaining 2.3% helper, a **complete winner model that predicts EVERY rally with
calibrated confidence**, combining the only things that carry signal:
- **Final-score-derived per-game majority**: in side-out scoring, receiver-wins (side-outs) per game =
  N_rallies - total_points, so the known final score (ONE number the user enters) gives the per-game
  class balance. Predict that majority class as the base.
- **Short-rally override**: rally < 3.5 s -> receiver won (validated ~90%, Wilson [0.78,0.96]).
- **Calibrated confidence** per rally; the pipeline auto-fills high-confidence and routes low-confidence
  to the existing 1-click review, ordered by confidence.

Measured on 72 games / 2,676 rallies:
```
overall per-rally accuracy = 0.592   (all-server baseline 0.441; per-game prior ~0.59)
calibration (confidence -> empirical accuracy):
  conf [0.50,0.60): acc 0.556  n=1666   (the weak majority calls — most rallies)
  conf [0.60,0.70): acc 0.626  n=861
  conf [0.70,0.85): acc 0.723  n=94
  conf [0.85,1.00]: acc 0.927  n=55     (short rallies)
high-confidence (conf>=0.65) subset: 14.8% coverage @ 0.711 accuracy
```
So: complete (100% coverage), monotonically calibrated, ~0.59 overall, with a genuinely useful
high-confidence tier. Maps `winner`(server/receiver) -> `winning_team` via the tracked serving team.
Without the final score (deployment without it), it degrades to short-rally-only + a low-confidence
default (everything else -> review).

## Specific questions
1. Is shipping a ~0.59-overall model honest and worth it, given it's barely above the per-game prior
   but well-calibrated and complete (100% coverage with confidence)? Or is a complete-but-weak model
   worse than honestly saying "use human review + the short-rally suggest"? Which serves the user more?
2. Is the design sound (final-score majority + short-rally + calibration)? The count constraint alone
   gave 0.526 (worse than majority 0.589), so I dropped count-ranking in favor of majority-class. Right
   call? Any better way to use the final score?
3. Should this REPLACE the dead winner CNN in `auto_edit` (the CNN is a constant classifier), with the
   final score as an optional new `AutoEditSetup` field and review ordered by confidence? Or keep the
   pipeline untouched and ship the model as a standalone the user invokes?
4. How do I frame this to the user truthfully — as "a winner model" (it does determine every winner,
   best-effort, calibrated) without overstating its ~0.59 accuracy?
5. Anything I'm missing that would make the complete model meaningfully better than 0.59 (e.g., a better
   use of the final-score + serve structure + short-rally anchors via constrained sequence inference)?
