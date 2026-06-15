# Review request for GPT-5.5 (high reasoning) — validate endgame + deliverable

You are GPT-5.5, finishing our collaboration on the pickleball **rally-winner** detector. I ran your
two recommended cheap tests (end-switch audit + a dynamics/audio probe). I have a conclusion and a
proposed deliverable. Validate or correct before I write it up and ship. Be blunt; don't pad.

## Output instructions
- Markdown. **No tools.** Structure: (1) do you agree with the conclusion, (2) is the proposed
  deliverable right / how to refine it, (3) is a fuller audio build worth it or does duration suffice,
  (4) anything to fix before I write it up. End with a 3-4 sentence "Bottom line".

## Test 1 — End-switch / label-side consistency audit (your #1 cheap test)
Rendered early-rally vs late-rally frames for multiple videos/dates and checked whether teams swap
physical court ends within a game (which would break the once-per-video corner calibration and poison
all modalities). Result across the videos checked: **NO end-switching** — the same players (by
clothing) stay on the same court halves from rally #1 to the last rally. These are casual single-game-
to-11 doubles; ends are not switched mid-game. **Hypothesis 2 (within-video side flip) is ruled out.**
So the 3-method convergence stands: the transferable court-side rally-winner signal is genuinely not
recoverable from this footage.

## Test 2 — Rally-dynamics probe (the court-side-INDEPENDENT angle)
Key realization: mono audio + rally dynamics have ZERO court-side info, so they cannot predict
`winning_team` (court-side) — but they CAN predict the `winner` field (server vs receiver wins), which
the auto-edit pipeline maps to winning_team via the deterministically-tracked serving team. I probed
rally DURATION (already in the data) vs `winner` (server/receiver), date-grouped:

```
receiver-win rate by rally duration:
  <3s   n=19   receiver-win=1.00
  3-4s  n=61   receiver-win=0.82
  4-5s  n=97   receiver-win=0.40   <- dips (server's 3rd-shot lands, receiver error?)
  5-6s  n=183  receiver-win=0.60
  6-8s  n=481  receiver-win=0.53
  8s+   ~1000  receiver-win~0.51   (= prior, NO signal)
overall receiver-win prior = 0.542

abstaining rule "very short rally -> receiver wins":
  T<3.0s: coverage 1.0%  precision 1.00
  T<3.5s: coverage 2.3%  precision 0.905
  T<4.0s: coverage 4.3%  precision 0.863
per-date: short-rally receiver-win is 0.65-0.88 in 8/9 dates (one date n=5 is noise).
```
So: a SMALL, robust, high-precision signal exists for very short rallies (serve faults / aces / quick
errors -> receiver wins). ~90% of rallies (>=5s) show no duration signal. Visual/behavioral approaches
add nothing transferable on top (all ~prior).

## My conclusion
1. **Fully automatic rally-winner detection from this single-camera footage is not feasible.** Three
   independent visual/behavioral methods converge to <=+4% over the per-video prior even with oracle
   sign; end-switching is ruled out; the cue isn't there.
2. **A small high-precision dynamics signal is deployable**: very short rallies -> receiver wins.

## Proposed deliverable (the honest "model")
A **calibrated abstaining winner-suggestion model** integrated with the existing human-in-the-loop:
- Predicts `winner` (server/receiver) from rally dynamics (duration now; optionally audio impact-count
  / terminal-silence later). Emits a suggestion ONLY when high-precision (e.g. very short rally ->
  receiver), maps to winning_team via the pipeline's serving_team, and ABSTAINS otherwise.
- Everything abstained goes to the existing 1-click confirm/flip review, ordered by confidence.
- ScoreState already validates/cascades; flag impossible score sequences.
- Documented honestly as an assistive review tool with a high-precision auto-suggest on a small subset,
  NOT an autonomous winner classifier. No court-side visual model ships (it doesn't work).

## Questions
1. Do you agree with the conclusion and that I should STOP here (no more visual/behavioral modeling)?
2. Is the abstaining-dynamics deliverable the right thing to ship? Any refinement (e.g., also auto-
   suggest the symmetric high-precision pockets if any; how to set the precision/coverage operating
   point; calibration with only ~80 short rallies)?
3. Is a fuller AUDIO build (paddle-impact onset detection -> hit count -> who-hit-last; terminal
   silence) worth it, or does the duration probe already tell me dynamics won't crack the long rallies?
   Give a clear yes/no with reasoning.
4. Anything I should add/verify before writing the final report (e.g., leakage in the duration signal,
   how short-rally coverage interacts with the audio boundary model's own short-rally reliability)?
