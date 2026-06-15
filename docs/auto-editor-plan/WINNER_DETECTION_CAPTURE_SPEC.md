# Capture Spec — making a rally-winner model feasible on FUTURE footage

**Date:** 2026-06-14. **Why this exists:** six independent approaches all failed to determine the
rally winner from the *current* single-camera footage (see `WINNER_DETECTION_FINDINGS.md`). The
blocker is not the model — it's that the deciding information isn't *captured*. This spec lists the
recording changes that would put the signal into the footage, ordered by leverage-per-effort. Each is
something to set up once at the venue; none requires new software up front.

## #1 (highest leverage, lowest cost): capture the spoken score
In pickleball the server **calls the score before every serve**. If that call is audible, the score is
read directly (ASR or a small spoken-digit classifier) and differencing consecutive calls gives every
rally winner — **no visual winner model needed at all.** Today only ~4% of pre-serve windows contain
*any* detectable speech: the camera's built-in mic is too far to capture conversational score calls.

Fix (cheap):
- Put a mic near the court — a **clip-on/lavalier or a small recorder on the net post / fence** at
  court level, or a phone running a voice recorder on the bench. Even one mic per court helps.
- Ask players to **call the score clearly** (most already do; just louder/toward the mic).
- Sync: a clap or the first serve's pock aligns the mic track to the video.

Verify it worked: run ASR on 20 pre-serve windows from a test recording; success = the called score is
recognizable in ≥70–80% of them. (Tooling already prototyped: `ml/winner_tracking/audio_winner.py`
+ torchaudio Wav2Vec2; swap in a stronger ASR like Whisper if needed.)

**If this one change works, the winner problem is essentially solved** — the score is the answer, and
it's being spoken aloud already.

## #2: fix the camera geometry so the ball is trackable
Today: single camera behind one baseline → **5:1 near/far perspective, far-side ball ≈ 4 px**. A 4 px
fast ball under player clutter is not reliably trackable, which is why ball-geometry failed.

Fix (one of):
- **Raise and centre the camera** (mount it high, ~side-on at the net line or elevated behind a
  baseline but higher) to flatten the perspective so the far ball is ≥ ~10–12 px. Higher is better.
- **Add a second camera** (opposite end or side) so at least one view sees each terminal event large.
- Keep ≥1080p; **4K** would roughly double the far-ball pixels and is worth it if available.
- Keep the camera **fixed** for the whole session and **re-click the 4 court corners** whenever it
  moves (the homography is calibrated once per position).

Verify it worked: on a test clip, measure the ball's pixel diameter at the *far* baseline; target ≥10 px.

## #3: small per-court ball-position labels (only if pursuing the visual path)
If you go the ball-tracking route (#2), a one-time **30–50 rally ball-position annotation set**
(mark the ball in ~10 terminal frames each, across camera setups) is needed to measure detector recall
and to train/validate a tracker. A human watching the video can mark the ball trivially; an agent
cannot from stills. This is the gate that tells you whether tracking will work before building it.

## What does NOT need to change
- The **audio rally-boundary (cut) model** is good — keep it as-is.
- The **ScoreState** engine and the **human-in-the-loop review** are correct and stay.
- The current **short-rally auto-suggest** (`winner_dynamics.py`) keeps working regardless.

## Recommended order
1. **Add a court-side mic and test score-call ASR** (cheap, and if it works it solves the whole thing).
2. Only if #1 is impractical, **improve camera geometry** (#2) and then do the ball-GT gate (#3).

The realistic path to "a model that determines who won the point" runs through **#1** — the information
already exists as the players' spoken score; it just needs to be recorded.
