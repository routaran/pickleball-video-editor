# Review Mode - User Guide

## Overview

Review Mode is the final step before generating your Kdenlive project. It allows you to verify and fine-tune rally timings, correct any score errors, and preview your marked rallies.

## Entering Review Mode

**From Editing Mode:**
1. Mark all rallies in your match
2. Click the **Final Review** button in the toolbar
3. Rally controls and toolbar will hide
4. Review Mode interface will appear

**Note:** You need at least one marked rally to enter review mode.

## Review Mode Interface

### Layout

```
┌─────────────────────────────────────────────┐
│  FINAL REVIEW MODE    Rally X of Y   [Exit] │  ← Header
├─────────────────────────────────────────────┤
│                                             │
│              Video Player                   │  ← Always visible
│                                             │
├─────────────────────────────────────────────┤
│  ◄ | ▌▌ | ► | ►► | ►►    1.0x    00:00 / 05:00│  ← Playback controls
├─────────────────────────────────────────────┤
│  TIMING                                     │  ← Timing controls
│    START: 01:23.4  [-0.1s] [+0.1s]         │
│    END:   01:28.6  [-0.1s] [+0.1s]         │
│    DURATION: 00:05.2                        │
├─────────────────────────────────────────────┤
│  SCORE                                      │  ← Score editor
│    CURRENT: 3-2-1  →  NEW SCORE: [____]    │
│    □ Cascade to later rallies               │
├─────────────────────────────────────────────┤
│  RALLY LIST (click to navigate)             │  ← Rally cards
│  ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐     │
│  │R 1 ││R 2 ││R 3 ││R 4 ││R 5 ││R 6 │     │
│  │0-0-2││1-0-1││1-1-2││2-1-1││2-2-2││3-2-1││
│  └────┘└────┘└────┘└────┘└────┘└────┘     │
├─────────────────────────────────────────────┤
│  [◄ Previous]  [▶ Play Rally]  [Next ▶]   │  ← Navigation
├─────────────────────────────────────────────┤
│  ✓ Ready to generate output                 │
│       [GENERATE KDENLIVE PROJECT]           │  ← Generate
└─────────────────────────────────────────────┘
```

## Features

### 1. Rally Navigation

**Methods:**
- **Rally Cards:** Click any rally card to jump to that rally
- **Previous/Next Buttons:** Step through rallies sequentially
- **Automatic Seeking:** Video seeks to rally start and pauses

**Visual Feedback:**
- Selected rally card is highlighted with green border
- Video shows rally start frame
- OSD displays "Rally X: score"

### 2. Timing Adjustment

**Purpose:** Fine-tune rally start and end times

**Controls:**
- **START -0.1s / +0.1s:** Adjust rally start time
- **END -0.1s / +0.1s:** Adjust rally end time
- **DURATION:** Automatically calculated (read-only)

**How to Use:**
1. Navigate to the rally you want to adjust
2. Watch the rally to identify the exact start/end
3. Click +/- buttons to shift timing
4. Each click adjusts by 0.1 seconds (6 frames at 60fps)
5. Duration updates automatically

**Tips:**
- Start should capture the serve preparation (added -0.5s padding)
- End should include ball settling (added +1.0s padding)
- Use Play Rally to verify timing feels right

### 3. Score Editing

**Purpose:** Correct score errors or inconsistencies

**Without Cascade:**
1. Type new score in "NEW SCORE" field
2. Press Enter or click elsewhere
3. Only this rally's score is updated

**With Cascade:**
1. Type new score in "NEW SCORE" field
2. Check "Cascade to later rallies"
3. Press Enter
4. All subsequent rallies recalculate based on winners

**Example:**

Initial state:
```
Rally 1: 0-0-2 → server wins → Rally 2: 1-0-2
Rally 2: 1-0-2 → receiver wins → Rally 3: 1-0-1
Rally 3: 1-0-1 → server wins → Rally 4: 2-0-2
```

If you change Rally 2 score to "2-1-1" with cascade:
```
Rally 1: 0-0-2 → server wins → Rally 2: 1-0-2 (unchanged)
Rally 2: 2-1-1 → receiver wins → Rally 3: 2-1-2 (recalculated)
Rally 3: 2-1-2 → server wins → Rally 4: 3-1-1 (recalculated)
```

**Score Format:**
- Singles: `X-Y` (e.g., "5-3")
- Doubles: `X-Y-Z` (e.g., "7-4-1")

### 4. Play Rally

**Purpose:** Preview a rally from start to end

**How to Use:**
1. Navigate to the rally
2. Click **▶ Play Rally** button
3. Video plays from rally start
4. Automatically pauses at rally end

**Notes:**
- Playback uses normal speed (can change with playback controls)
- Auto-pause is approximate (±50ms)
- Starting a new play cancels previous play

### 5. Generate Kdenlive Project

**Purpose:** Export marked rallies to Kdenlive for editing

**How to Use:**
1. Review all rallies and make adjustments
2. Click **GENERATE KDENLIVE PROJECT**
3. Choose save location
4. Kdenlive .kdenlive file is created

**What's Included:**
- All marked rallies as clips
- Score overlays for each rally
- Transitions between rallies
- Project settings matching your video

**Note:** Currently a placeholder - full implementation coming soon.

## Keyboard Shortcuts

**Navigation:**
- (Future) Left/Right arrows: Previous/Next rally
- (Future) Space: Play/Pause current rally

**Editing:**
- (Future) J/L: Adjust timing -0.1s / +0.1s

## Common Workflows

### Quick Review (No Changes)

1. Enter review mode
2. Use Previous/Next to step through each rally
3. Verify timings look correct
4. Generate Kdenlive project
5. Done!

### Fix One Rally Timing

1. Enter review mode
2. Click the rally card that needs adjustment
3. Use Play Rally to identify the issue
4. Adjust start/end timing with +/- buttons
5. Play Rally again to verify
6. Exit review mode or continue

### Correct Score Cascade

1. Enter review mode
2. Navigate to the rally where score went wrong
3. Type correct score in "NEW SCORE" field
4. Check "Cascade to later rallies"
5. Press Enter
6. Verify all subsequent rallies now have correct scores
7. Generate project

### Fine-Tune All Rallies

1. Enter review mode
2. For each rally:
   - Navigate to rally
   - Play rally to check timing
   - Adjust if needed
   - Verify score is correct
3. After reviewing all rallies, generate project

## Tips and Best Practices

### Timing Adjustments
- **Too Early:** Rally starts before serve or in middle of previous point
  - Solution: Click START +0.1s multiple times
- **Too Late:** Rally cuts off serve preparation
  - Solution: Click START -0.1s
- **Ends Abruptly:** Rally cuts off before ball settles
  - Solution: Click END +0.1s
- **Too Long:** Rally includes next point's setup
  - Solution: Click END -0.1s

### Score Verification
- Always check the score at rally start, not after the point
- Rally 1 in doubles should always be "0-0-2"
- Use cascade when fixing early mistakes
- Verify the final score matches your memory of the game

### Efficient Navigation
- Use rally cards for random access
- Use Previous/Next for sequential review
- Click card, verify, next card, verify, etc.

### Before Generating
- [ ] Check first rally score (0-0 or 0-0-2)
- [ ] Check final rally score matches game outcome
- [ ] Verify no rallies are cut off or too long
- [ ] Play 2-3 rallies randomly to spot-check
- [ ] Save session if you made changes

## Exiting Review Mode

**To Return to Editing:**
1. Click **Exit Review** button in header
2. Rally controls and toolbar reappear
3. You can mark more rallies or make corrections
4. Re-enter review mode when ready

**Important:** Changes made in review mode are preserved. You can:
- Save session to keep timing/score adjustments
- Exit and re-enter review mode without losing changes
- Continue editing more rallies after exiting

## Troubleshooting

### Issue: Review button is grayed out
**Cause:** No rallies marked yet
**Solution:** Mark at least one rally (Rally Start → Server/Receiver Wins)

### Issue: Rally cards are empty
**Cause:** Rallies don't have scores
**Solution:** This shouldn't happen in normal use. Check rally marking logic.

### Issue: Video doesn't seek when clicking rally card
**Cause:** Video file may be unloaded or corrupted
**Solution:** Exit review, check video loads correctly in editing mode

### Issue: Timing adjustments have no effect
**Cause:** FPS not set correctly
**Solution:** Verify video loaded successfully, check console for errors

### Issue: Cascade changes wrong rallies
**Cause:** Winner information is incorrect
**Solution:** Exit review mode, re-mark the rally with correct winner

### Issue: Play Rally doesn't pause
**Cause:** Timer may not have started
**Solution:** Try again, or manually pause when rally ends

## Data Safety

### Automatic Dirty Tracking
- All timing adjustments mark session as dirty
- All score changes mark session as dirty
- Closing window prompts to save if dirty

### Session Persistence
- Changes are stored in memory until saved
- Use "Save Session" before closing
- Reload session to resume where you left off

### Undo Limitations
- No undo in review mode (yet)
- To undo changes: Exit review, use main undo button
- Save session frequently to avoid losing work

## What's Next?

After generating your Kdenlive project:

1. **Open in Kdenlive**
   - File → Open Project
   - Navigate to generated .kdenlive file
   - Video clips are ready to edit

2. **Customize in Kdenlive**
   - Adjust transitions
   - Fine-tune score overlays
   - Add titles, effects, music
   - Export final video

3. **Share Your Highlight Reel**
   - Upload to YouTube
   - Share with players
   - Archive for coaching review

## Future Features (Planned)

- [ ] Keyboard shortcuts for faster navigation
- [ ] Visual timeline with rally thumbnails
- [ ] Undo/redo in review mode
- [ ] Batch timing adjustments
- [ ] Export to multiple formats (SRT, CSV, JSON)
- [ ] Rally duration statistics
- [ ] Score verification warnings

## Getting Help

**Issue tracker:** File bugs and feature requests in the project repository

**Documentation:**
- `REVIEW_MODE_INTEGRATION.md`: Technical implementation details
- `UI_SPEC.md`: Visual design specifications
- `DETAILED_DESIGN.md`: Use cases and flows
