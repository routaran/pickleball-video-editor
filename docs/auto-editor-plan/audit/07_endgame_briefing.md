# Review request for GPT-5.5 (high reasoning) — 3-method convergence; decide endgame

You are GPT-5.5, continuing our collaboration on the pickleball **rally-winner** detector. We pivoted
from ball tracking to behavior. I ran the behavior audit. The result, combined with the earlier ones,
now forms a striking convergence. I need a decisive call on the endgame, not encouragement.

## Output instructions
- Markdown. **No tools.** Structure: (1) your read of the convergence, (2) THE decision: keep trying
  or conclude auto-winner-from-video is infeasible, (3) the cheap high-value tests (if any) to run
  BEFORE concluding, ranked, (4) what to actually deliver to the user given the goal "a model that
  determines who won the point", (5) anything I'm missing. End with a 3-4 sentence "Bottom line".

## The convergence (this is the key data)
Three INDEPENDENT approaches, all evaluated with date-grouped CV on the same labeled corpus
(1,847 rally winner labels / 51 videos / 9 dates; ~all doubles; single fixed camera per game;
1080p60; balanced classes). "Oracle per-video sign" = upper bound if we knew which physical side each
team is on per video.

| approach | leave-date-out acc | leave-video-out | oracle per-video sign | per-video prior | lift over prior |
|---|---|---|---|---|---|
| ball-appearance CNN (warped clip, prior session) | 0.51 | — | 0.598 | 0.586 | +1.2% |
| classical ball-geometry (this session) | 0.558 | 0.533 | 0.721 | 0.685 | +3.6% |
| post-rally player behavior (this session) | 0.370 | 0.430 | 0.690 | 0.675 | +1.5% |

- All three reach **at most ~+1-4% over the per-video majority prior**, even WITH oracle per-video sign.
- Behavior's raw 0.370 is BELOW chance: global-flip = 0.630, oracle-per-date-sign = 0.630,
  oracle-per-video-sign = 0.690. Permutation p=1.000; nuisance-only = 0.495 (clean). So behavior carries
  a strong signal that ANTI-generalizes — it flips sign across videos/dates.
- Interpretation: what's predictable is "which team is stronger this game" (the per-video class balance,
  prior ~0.68), NOT who won a SPECIFIC rally. The cross-court transferable rally-level signal is ~absent.

## Two hypotheses for the universal failure
1. **No transferable signal exists.** Single camera, casual doubles, tiny ball, subtle terminal events;
   the rally winner just isn't reliably recoverable from this footage. (Most parsimonious given 3-method
   convergence.)
2. **A label↔court-side inconsistency is destroying the signal.** The whole pipeline assumes
   "Team1 = canonical court top" via a once-per-video corner calibration. If teams **switch ends
   mid-game** (some pickleball formats switch at a midpoint score), the court-side↔team mapping breaks
   WITHIN a video, so neither geometry nor behavior nor appearance could ever transfer — and even
   oracle-per-video-sign can't fix a WITHIN-video flip. This single bug would explain ALL three failures
   AND be fixable (detect/track which side each team is on, or record a side bit). The original
   diagnosis flagged "23/51 videos below chance with a global sign — more than a clean convention
   predicts," consistent with within-video end-switching.

## Relevant facts
- I have: 1,847 labels, homography per video, a working person detector, the audio rally-boundary model
  (works well, not winner-aware), and ScoreState (deterministic rules). NO ball GT, NO per-rally side GT.
- The within-video ball-CNN probe earlier got 63.3% (vs 50% within-video prior) — i.e. SOME within-video
  signal existed for appearance when the court was seen in training. Behavior shows ~none beyond prior.
- Human-in-the-loop winner review already ships (1-click confirm/flip + score cascade); abstain is fine.
- Audio winner cues are completely UNTESTED (last-hit side, net-cord sound, silence/reset pattern).

## My current read
The 3-method convergence is strong evidence for hypothesis (1) — but hypothesis (2) is cheap to test and
would be a "found the bug" moment if true, so I should not declare infeasible until I check label↔side
consistency. After that, the only untested signal source is audio.

## Specific questions
1. Do you agree the convergence makes a fully-automatic rally-winner model unlikely, and that the
   responsible move is (a) one cheap label-consistency / end-switching check + (b) a quick audio audit,
   THEN conclude — rather than more behavior/ball engineering?
2. How would you cheaply test hypothesis (2) WITHOUT per-rally side ground truth? My ideas: (i) within-
   video CV — if within-video accuracy is also ~chance, the label is likely broken or signal absent; if
   within-video is high but cross-video chance, it's a transfer wall not a label bug; (ii) detect serve/
   score-driven side changes from the rally sequence; (iii) check whether a strong court-side feature's
   correlation with the label flips at a consistent rally index within games. Which is most decisive?
3. Given the goal "deliver a model that determines who won the point," if auto-winner is infeasible,
   what is the honest, valuable deliverable? (e.g., ship the human-in-the-loop as the product, plus a
   confidence-ranked review order; or a per-game "stronger side" prior that pre-fills + human confirms;
   or abstain-everything.) What would you actually hand the user?
4. Is there any approach we have NOT tried that has a real chance here (audio; multi-frame learned tiny-
   ball detector with the small-GT bootstrap; using the final score + per-game structure as a prior),
   ranked by expected value?
