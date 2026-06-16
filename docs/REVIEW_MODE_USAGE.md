# Review Mode - User Guide

## Overview

Review Mode is the final step before exporting your match. It lets you verify and
fine-tune rally timings, correct scores, declare the winner of any rally, add or
remove rallies, and then either generate a Kdenlive project or export a finished
MP4 directly.

## Entering Review Mode

**From Editing Mode:**
1. Mark all rallies in your match
2. Click the **Final Review** button in the toolbar
3. Rally controls, toolbar, and the clip timeline hide
4. The Review Mode interface appears

**Note:** You need at least one marked rally to enter review mode. If you click
Final Review with no rallies, a warning toast appears and nothing happens.

The layout adapts to your window: on normal/portrait windows the video and
controls stack vertically with the rally list and export panel below; on very
wide (ultrawide) windows the video and rally list sit on the left with the
controls and export panel in a column on the right. The arrangement is chosen
once, when review mode opens, and stays fixed for the session.

## Review Mode Interface

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  FINAL REVIEW MODE   Rally X of Y      [Main Menu] [Exit]   │  ← Header
├────────────────────────────────────────────────────────────┤
│                                                            │
│                      Video Player                          │  ← Always visible
│                                                            │
├────────────────────────────────────────────────────────────┤
│  [ PLAY RALLY ]                                            │
│                                                            │
│  WINNER                                                    │  ← Declare winner
│    Serving: Alice & Bob                                    │
│    [ Alice & Bob Won ]   [ Carol & Dave Won ]            │
│                                                            │
│  [ Delete Rally ]   [ Insert Rally After ]               │  ← Add / remove
│                                                            │
│  TIMING                                Step: [0.1 s ▾]    │  ← Timing controls
│    START [ 01:23.4 ]   [-0.1 s] [+0.1 s]                 │
│    END   [ 01:28.6 ]   [-0.1 s] [+0.1 s]                 │
│    DURATION [ 00:05.2 ]               [ Reset ]          │
│                                                            │
│  GAME STATE                                               │  ← Score anchor
│    Set score and serving team at start of rally          │
│    Serving team:  [Alice & Bob] [Carol & Dave]          │
│    Score: [ 3-2-1 ]                                       │
│    [ Apply to Rally ]                                     │
├────────────────────────────────────────────────────────────┤
│  RALLY LIST (click to navigate)         [Prev] [Next]    │  ← Rally cards + nav
│  ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐                  │
│  │ 1  ││ 2  ││ 3  ││ 4  ││ 5  ││ 6  │                  │
│  │0-0-2││1-0-1││1-1-2││2-1-1││2-2-2││3-2-1│            │
│  └────┘└────┘└────┘└────┘└────┘└────┘                  │
├────────────────────────────────────────────────────────────┤
│  ✓ Ready to generate output                              │
│  □ Mark Game Completed                                    │
│  Export Options                                           │
│    ┌── Kdenlive Project ──┐  ┌── MP4 Video ──┐         │
│    │ Export to: [______]  │  │ Ready-to-share │         │
│    │ [Browse]             │  │ [ EXPORT MP4 ] │         │
│    │ [ GENERATE PROJECT ] │  └────────────────┘         │
│    └──────────────────────┘                              │
└────────────────────────────────────────────────────────────┘
```

## Features

### 1. Rally Navigation

**Methods:**
- **Rally Cards:** Click any rally card to jump to that rally
- **Previous / Next Buttons:** Step through rallies sequentially

**What happens when you select a rally:**
- The video seeks to the rally start and **plays the rally through**, then
  auto-pauses at the rally end
- The selected card is highlighted with a colored (accent) border
- The OSD shows "Playing Rally X"

Post-game clips are labeled "PG" on their card, and the header counter shows
"(post-game)".

### 2. Play Rally

**Purpose:** Re-watch the current rally from start to end at any time

**How to Use:**
1. Navigate to the rally
2. Click **PLAY RALLY**
3. Video seeks to the rally start and plays
4. Playback auto-pauses at the rally end

**Notes:**
- Auto-pause is approximate (a few frames of tolerance)
- Starting a new play (or navigating to another rally) cancels the previous play

### 3. Timing Adjustment

**Purpose:** Fine-tune rally start and end times.

**Controls:**
- **Step selector:** Choose how much each nudge moves the time — `0.1 s`,
  `0.25 s`, `0.5 s`, or `1.0 s`. The nudge button labels update to match.
- **START / END nudge buttons:** Shift the start or end by the current step in
  either direction (e.g. `-0.25 s` / `+0.25 s`).
- **Direct entry fields:** Type an exact time into the **START**, **END**, or
  **DURATION** field instead of nudging. Both `MM:SS.s` (e.g. `01:23.4`) and raw
  seconds (e.g. `83.4`) are accepted. Press Enter or click elsewhere to commit.
- **DURATION field:** Editing the duration moves the **END** so that
  `end = start + duration`. The start stays put.
- **Reset button:** Restores the original start/end for this rally. It is enabled
  only after you have made a change.

**How to Use:**
1. Navigate to the rally you want to adjust
2. Watch the rally (Play Rally) to identify the exact start/end
3. Either pick a step and click the +/- buttons, or type an exact value into the
   Start, End, or Duration field
4. The other fields update automatically; an offset caption (e.g.
   "+0.30s from original") appears under any field you've changed

**Notes:**
- Start can't go below 0; end is never allowed before start
- After a typed entry is applied, the field refreshes to the model's
  frame-snapped value, so the displayed time may differ slightly from what you typed
- The OSD confirms each nudge (e.g. "Start adjusted 0.2s later")

**Tips:**
- Start should capture the serve preparation (padding is added automatically)
- End should include the ball settling after the point
- Use a large step (1.0 s) to get close quickly, then switch to 0.1 s to fine-tune

### 4. Declaring the Winner

**Purpose:** Set who actually won a rally — for example when auto-detection
picked the wrong side.

**Controls:**
- A "Serving: <team>" line shows which side was serving at the start of the rally
- Two buttons declare the winner directly, labeled with the real team/player
  names: **"<Serving team> Won"** and **"<Returning team> Won"**

**How to Use:**
1. Navigate to the rally with the wrong winner
2. Click the button for the team that actually won
3. The rally's winner is set and **all later rally scores recalculate
   automatically** from this point forward
4. A toast confirms the change and how many downstream rallies were affected

**Low-Confidence Highlighting:**
- Rallies whose winner is uncertain (auto-derived from the model) are flagged for
  attention: when you navigate to a flagged rally, the two winner buttons are
  drawn with an **amber** border instead of the normal blue
- When a cascade re-derives downstream winners from model predictions, those
  rallies are added to the attention set so you can review them
- Declaring a winner is a no-op if the rally already has that winner

### 5. Score Editing (Game State Anchor)

**Purpose:** Correct the score at a given rally. There is no per-rally "new
score" field or cascade checkbox anymore — instead you set a **game-state anchor**
(serving team + score) at a rally, and the system **always** recalculates every
later rally from that anchor.

**Controls (the GAME STATE panel):**
- **Serving team:** Two toggle buttons (labeled with the real team names). Pick
  which side was serving at the start of this rally.
- **Score:** A validated text field. The format depends on the game mode:
  - Doubles: `X-Y-Z` (e.g. `7-4-1`)
  - Singles: `X-Y` (e.g. `5-3`)
  - The **Apply to Rally** button stays disabled until the score is valid, and an
    inline error message appears for invalid (non-empty) input.
- **Apply to Rally:** Commits the anchor.

**How to Use:**
1. Navigate to the rally where the score is wrong
2. Choose the serving team
3. Type the correct score
4. Click **Apply to Rally**
5. This rally and every rally after it recalculate from the new anchor, using
   each rally's recorded winner. A toast confirms how many rallies were cascaded.

**Example:**

Initial state:
```
Rally 1: 0-0-2 → server wins → Rally 2: 1-0-2
Rally 2: 1-0-2 → receiver wins → Rally 3: 1-0-1
Rally 3: 1-0-1 → server wins → Rally 4: 2-0-2
```

If you anchor Rally 2 to serving team = Team 2, score `2-1-1`, everything from
Rally 2 onward is recomputed from that point using each rally's winner.

### 6. Delete / Insert Rally

**Purpose:** Remove a stray rally, or add a missing one, directly in review.

**How to Use:**
- **Delete Rally:** Navigate to the rally and click **Delete Rally**. Confirm the
  prompt. The rally is removed and all later scores recalculate automatically.
- **Insert Rally After:** Navigate to the rally you want to insert after and click
  **Insert Rally After**. A new placeholder rally is created in the gap that
  follows (roughly a 4-second clip), all later scores recalculate, and the new
  rally is selected so you can adjust its timing, winner, and score.

A toast confirms each action and how many downstream rallies were affected.

### 7. Marking the Game Completed

**Purpose:** Tell the exporter the match is finished so a final-score title can be
added at the end of the output.

- Tick **Mark Game Completed** to reveal the final score / winner line.
- If the current score already implies the game is over, this is auto-ticked when
  you enter review mode and a toast tells you the detected final score (untick it
  if that's wrong).
- When unchecked, the export skips the final-score subtitle.

### 8. Export: Generate Project or Export MP4

There are two export paths, shown as side-by-side cards.

**Kdenlive Project**
- **Export to:** A path field (prefilled with a sensible default next to your
  video). Use **Browse** to choose a different location.
- Click **GENERATE PROJECT** to write a `.kdenlive` project (with score overlay
  subtitles) you can open and refine in Kdenlive. If the path field is empty, a
  save dialog appears.

**MP4 Video**
- Click **EXPORT MP4** to render a finished, ready-to-share MP4 directly via
  FFmpeg (with hardware encoding when available). A save dialog asks where to
  write it, and a progress dialog tracks the encode.

Both export buttons are disabled until at least one rally exists. If the game is
marked completed, a final-score title is appended to the exported output.

## Keyboard Shortcuts

There are no review-specific keyboard shortcuts yet — navigation and editing in
review mode are mouse-driven (rally cards, Prev/Next, and the control buttons).

## Common Workflows

### Quick Review (No Changes)

1. Enter review mode
2. Use Previous/Next (or click cards) to step through each rally — each one plays
   automatically
3. Verify timings and scores look correct
4. Generate a Kdenlive project or export an MP4
5. Done!

### Fix One Rally Timing

1. Enter review mode
2. Click the rally card that needs adjustment
3. Watch it play to identify the issue
4. Pick a step and nudge Start/End, or type an exact Start/End/Duration
5. Click Play Rally to verify
6. Continue or export

### Correct a Wrong Winner

1. Enter review mode
2. Navigate to the rally with the wrong outcome (amber winner buttons flag
   uncertain ones)
3. Click the button for the team that actually won
4. Confirm the downstream scores now look right (they recalculate automatically)

### Correct the Score from a Point Forward

1. Enter review mode
2. Navigate to the rally where the score first went wrong
3. In the GAME STATE panel, set the serving team and type the correct score
4. Click **Apply to Rally**
5. Verify all subsequent rallies now have correct scores
6. Export

### Add or Remove a Rally

1. Enter review mode
2. Navigate to the offending rally (to delete) or the rally to insert after
3. Click **Delete Rally** (and confirm) or **Insert Rally After**
4. Adjust the new/renumbered rallies as needed — scores re-cascade automatically

## Tips and Best Practices

### Timing Adjustments
- **Starts too early:** nudge START later (+step), or type a later start
- **Cuts off the serve:** nudge START earlier (-step)
- **Ends abruptly:** nudge END later (+step), or increase DURATION
- **Runs into the next point:** nudge END earlier (-step), or decrease DURATION
- Use the step selector: big steps to get close, 0.1 s to fine-tune

### Score Verification
- Always check the score at the *start* of each rally, not after the point
- Rally 1 in doubles should be `0-0-2`
- Fix the *earliest* wrong rally with a game-state anchor — everything after it
  recalculates for free
- Verify the final score matches your memory of the game

### Efficient Navigation
- Use rally cards for random access, Prev/Next for sequential review
- Pay special attention to rallies whose winner buttons show amber — those are the
  ones the system is unsure about

### Before Exporting
- [ ] First rally score is correct (`0-0` or `0-0-2`)
- [ ] Final rally score matches the game outcome
- [ ] No rallies are cut off or too long
- [ ] Spot-check 2-3 rallies by playing them
- [ ] Set **Mark Game Completed** if you want a final-score title
- [ ] Save your session if you made changes

## Exiting Review Mode

**Return to Editing:**
1. Click **Exit Review** in the header
2. Rally controls, toolbar, and the clip timeline reappear
3. The playhead parks at the end of the last rally so you can keep capturing
4. Re-enter review mode whenever you're ready

**Return to Main Menu:**
- Click **Main Menu** in the header to leave the match entirely

**Important:** Changes made in review mode are preserved. You can save the session
to keep timing/score/winner adjustments, exit and re-enter review without losing
them, and continue marking more rallies afterward.

## Troubleshooting

### Issue: Final Review button does nothing / warns
**Cause:** No rallies marked yet
**Solution:** Mark at least one rally (Rally Start → declare a winner)

### Issue: Rally cards are empty
**Cause:** Rallies don't have scores
**Solution:** This shouldn't happen in normal use. Re-check the rally marking flow.

### Issue: Video doesn't seek when clicking a rally card
**Cause:** Video file may be unloaded or corrupted
**Solution:** Exit review and confirm the video loads correctly in editing mode

### Issue: A typed Start/End time "snaps" to a slightly different value
**Cause:** Times are snapped to the nearest video frame after you commit them
**Solution:** This is expected — the displayed value reflects the real frame position

### Issue: My score won't apply / Apply button is disabled
**Cause:** The score field doesn't match the expected format
**Solution:** Use `X-Y-Z` for doubles or `X-Y` for singles; the inline error
explains the format

### Issue: Cascade changed scores I didn't expect
**Cause:** A downstream rally has the wrong winner
**Solution:** Navigate to that rally and declare the correct winner; scores
re-cascade automatically

### Issue: Play Rally doesn't pause exactly at the end
**Cause:** Auto-pause has a few frames of tolerance
**Solution:** This is expected; nudge the END time if the clip is consistently long

## Data Safety

### Automatic Dirty Tracking
- Timing nudges and typed entries mark the session as dirty
- Winner changes, score anchors, deletes, and inserts mark the session as dirty
- Toggling Mark Game Completed marks the session as dirty
- Closing the window prompts you to save if there are unsaved changes

### Session Persistence
- Changes are held in memory until you save
- Use **Save Session** before closing
- Reload the session to resume where you left off

### Undo Limitations
- There is no in-place undo within review mode yet
- Most edits (winner, score anchor, delete, insert) are easy to reverse manually —
  re-declare a winner, re-apply a score anchor, or re-insert a rally
- Save your session frequently to avoid losing work

## Highlights Mode

When the match is a highlights reel, the **WINNER** and **GAME STATE** panels and
the game-completion controls are hidden — there are no scores to track. Timing
adjustment, delete/insert, navigation, and export all work the same way.

## What's Next?

After generating a Kdenlive project:

1. **Open in Kdenlive** — File → Open Project → select the generated `.kdenlive`
2. **Customize** — adjust transitions, fine-tune score overlays, add titles,
   effects, or music
3. **Export** the final video

If you used **Export MP4**, the rendered file is ready to share as-is.

## Getting Help

**Issue tracker:** File bugs and feature requests in the project repository

**Related Documentation:**
- `REVIEW_MODE_INTEGRATION.md`: Technical integration details
- `OUTPUT_GENERATION_USAGE.md`: Kdenlive/output generation details
- `UI_SPEC.md`: Visual design specifications
- `DETAILED_DESIGN.md`: Use cases and flows
