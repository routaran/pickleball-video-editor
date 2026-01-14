# Detailed Design Document
## Pickleball Video Editor Tool

**Version:** 1.0
**Date:** 2026-01-14

---

## Table of Contents

1. [Use Cases](#1-use-cases)
2. [Sequence Diagrams](#2-sequence-diagrams)
3. [Class Diagrams](#3-class-diagrams)
4. [State Diagrams](#4-state-diagrams)
5. [Data Flow](#5-data-flow)

---

## 1. Use Cases

### 1.1 Use Case Diagram Overview

```
                              ┌─────────────────────────────────────────┐
                              │       Pickleball Video Editor           │
                              └─────────────────────────────────────────┘
                                                │
        ┌───────────────────────────────────────┼───────────────────────────────────────┐
        │                                       │                                       │
        ▼                                       ▼                                       ▼
┌───────────────────┐               ┌───────────────────┐               ┌───────────────────┐
│   Session Mgmt    │               │   Rally Marking   │               │   Output Gen      │
├───────────────────┤               ├───────────────────┤               ├───────────────────┤
│ UC-01: New Session│               │ UC-05: Start Rally│               │ UC-11: Review     │
│ UC-02: Resume     │               │ UC-06: End Rally  │               │ UC-12: Gen Project│
│ UC-03: Save       │               │ UC-07: Undo       │               │ UC-13: Export     │
│ UC-04: Quit       │               │ UC-08: Edit Score │               └───────────────────┘
└───────────────────┘               │ UC-09: Side-Out   │
                                    │ UC-10: Comment    │
                                    └───────────────────┘
```

---

### 1.2 Detailed Use Cases

#### UC-01: Start New Editing Session

| Field | Description |
|-------|-------------|
| **ID** | UC-01 |
| **Name** | Start New Editing Session |
| **Actor** | User |
| **Preconditions** | Application launched, video file exists |
| **Postconditions** | Main editing window displayed, video loaded |

**Main Flow:**
1. User launches application
2. System displays Setup Dialog
3. User clicks "Browse" and selects video file
4. User selects game type (Singles/Doubles)
5. User selects victory rules (Game to 11/9/Timed)
6. User enters player/team names
7. User clicks "Start Editing"
8. System validates inputs
9. System loads video in MPV
10. System initializes score state (0-0 or 0-0-2)
11. System displays main editing window

**Alternative Flows:**
- **3a.** File not found → Display error, return to step 3
- **8a.** Validation fails → Highlight invalid fields, remain on dialog

**Exception Flows:**
- **9a.** Video load fails → Display error message, return to Setup Dialog

---

#### UC-02: Resume Existing Session

| Field | Description |
|-------|-------------|
| **ID** | UC-02 |
| **Name** | Resume Existing Session |
| **Actor** | User |
| **Preconditions** | Saved session exists for selected video |
| **Postconditions** | Session restored, video seeked to last position |

**Main Flow:**
1. User selects video file in Setup Dialog
2. System detects existing session for this video
3. System displays Resume Session dialog
4. Dialog shows: rally count, current score, last position
5. User clicks "Resume Session"
6. System loads session state from JSON
7. System loads video and seeks to last position
8. System restores score state and rally list
9. System displays main editing window

**Alternative Flows:**
- **5a.** User clicks "Start Fresh" → Delete session, proceed as UC-01

---

#### UC-03: Save Session

| Field | Description |
|-------|-------------|
| **ID** | UC-03 |
| **Name** | Save Session |
| **Actor** | User |
| **Preconditions** | Editing session active |
| **Postconditions** | Session state persisted to disk |

**Main Flow:**
1. User clicks "Save Session" button
2. System collects current state:
   - Video path and hash
   - All rally data
   - Current score and server state
   - Current video position
3. System writes JSON to session directory
4. System displays confirmation (brief OSD message)

**Trigger Events:**
- Manual: User clicks "Save Session"
- Auto: Before application exit (if unsaved changes)

---

#### UC-04: Quit Application

| Field | Description |
|-------|-------------|
| **ID** | UC-04 |
| **Name** | Quit Application |
| **Actor** | User |
| **Preconditions** | Application running |
| **Postconditions** | Application closed |

**Main Flow:**
1. User clicks window close button or "Save & Quit"
2. System checks for unsaved changes
3. If no unsaved changes → Close application
4. If unsaved changes → Display Unsaved Changes dialog
5. User selects action:
   - "Save & Quit" → Save session, then close
   - "Don't Save" → Close without saving
   - "Cancel" → Return to editing

---

#### UC-05: Mark Rally Start

| Field | Description |
|-------|-------------|
| **ID** | UC-05 |
| **Name** | Mark Rally Start |
| **Actor** | User |
| **Preconditions** | Editing mode active, no rally in progress |
| **Postconditions** | Rally start timestamp recorded, status = IN RALLY |

**Main Flow:**
1. User watches video, sees server ready to serve
2. User clicks "Rally Start" button
3. System captures current video timestamp
4. System applies -0.5s padding to start time
5. System records rally start frame
6. System updates status to "IN RALLY"
7. System highlights Server Wins/Receiver Wins buttons
8. System dims Rally Start button
9. System displays OSD: "Rally started..."

**Alternative Flows:**
- **2a.** Rally already in progress → Display warning, no action

---

#### UC-06: Mark Rally End

| Field | Description |
|-------|-------------|
| **ID** | UC-06 |
| **Name** | Mark Rally End |
| **Actor** | User |
| **Preconditions** | Rally in progress |
| **Postconditions** | Rally recorded, score updated, status = WAITING |

**Main Flow (Server Wins):**
1. User watches rally conclude, server wins point
2. User clicks "Server Wins" button
3. System captures current video timestamp
4. System applies +1.0s padding to end time
5. System records rally end frame
6. System calls ScoreState.server_wins()
7. System creates Rally object with score
8. System checks for game over condition
9. System updates status to "WAITING"
10. System displays OSD with result and new score

**Main Flow (Receiver Wins):**
1. User watches rally conclude, receiver wins point
2. User clicks "Receiver Wins" button
3. Steps 3-10 same as above, but calls ScoreState.receiver_wins()

**Alternative Flows:**
- **2a.** No rally in progress → Display warning, no action
- **8a.** Game over detected → Display Game Over dialog (UC-14)

---

#### UC-07: Undo Last Action

| Field | Description |
|-------|-------------|
| **ID** | UC-07 |
| **Name** | Undo Last Action |
| **Actor** | User |
| **Preconditions** | At least one action to undo |
| **Postconditions** | Last action reversed, video seeked appropriately |

**Main Flow:**
1. User clicks "Undo" button
2. System identifies last action type
3. **If last action was Rally End:**
   - Remove last rally from list
   - Revert score state
   - Seek video to rally end position
   - Set status to IN RALLY
4. **If last action was Rally Start:**
   - Clear current rally start
   - Seek video to rally start position
   - Set status to WAITING
5. System updates UI to reflect reverted state

---

#### UC-08: Edit Score Manually

| Field | Description |
|-------|-------------|
| **ID** | UC-08 |
| **Name** | Edit Score Manually |
| **Actor** | User |
| **Preconditions** | Editing mode active |
| **Postconditions** | Score updated, intervention logged |

**Main Flow:**
1. User clicks "Edit Score" button
2. System displays Edit Score dialog
3. Dialog shows current score
4. User enters new score in text field
5. User optionally enters comment
6. User clicks "Apply"
7. System validates score format
8. System updates score state
9. System logs intervention with timestamp and comment
10. System closes dialog, updates UI

**Alternative Flows:**
- **7a.** Invalid format → Display error, remain on dialog

---

#### UC-09: Force Side-Out

| Field | Description |
|-------|-------------|
| **ID** | UC-09 |
| **Name** | Force Side-Out |
| **Actor** | User |
| **Preconditions** | Editing mode active |
| **Postconditions** | Serving team changed, intervention logged |

**Main Flow:**
1. User clicks "Force Side-Out" button
2. System displays Force Side-Out dialog
3. Dialog shows current server and what it will change to
4. User optionally enters new score
5. User optionally enters comment
6. User clicks "Apply"
7. System updates serving team/server number
8. If new score provided, update score state
9. System logs intervention
10. System closes dialog, updates UI

---

#### UC-10: Add Comment

| Field | Description |
|-------|-------------|
| **ID** | UC-10 |
| **Name** | Add Comment |
| **Actor** | User |
| **Preconditions** | Editing mode active |
| **Postconditions** | Comment recorded with timestamp |

**Main Flow:**
1. User clicks "Add Comment" button
2. System displays Add Comment dialog
3. Dialog shows current timestamp
4. User enters comment text
5. User adjusts duration (default 5 seconds)
6. User clicks "Add"
7. System records comment with timestamp and duration
8. System closes dialog

---

#### UC-11: Final Review

| Field | Description |
|-------|-------------|
| **ID** | UC-11 |
| **Name** | Final Review |
| **Actor** | User |
| **Preconditions** | At least one rally marked |
| **Postconditions** | User has verified/adjusted all rallies |

**Main Flow:**
1. User clicks "Final Review" button
2. System switches to Review Mode UI
3. System displays first rally
4. System seeks video to rally start
5. User verifies timing and score
6. User clicks "Next" to advance to next rally
7. Repeat steps 5-6 for all rallies
8. User clicks "Exit Review" to return to editing mode

**Optional Adjustments During Review:**
- Adjust start/end timing with +/- 0.1s buttons
- Edit score (with cascade option)
- Click any rally in list to jump to it

---

#### UC-12: Generate Kdenlive Project

| Field | Description |
|-------|-------------|
| **ID** | UC-12 |
| **Name** | Generate Kdenlive Project |
| **Actor** | User |
| **Preconditions** | In Final Review mode, rallies verified |
| **Postconditions** | .kdenlive and .srt files created |

**Main Flow:**
1. User clicks "Generate Kdenlive" button (in Review mode)
2. System compiles rally data into segments format
3. System calls Kdenlive generator with:
   - Video path
   - Segments (in/out frames, scores)
   - Profile settings (1080p60)
4. Generator creates .kdenlive XML file
5. Generator creates .srt subtitle file
6. System saves files to ~/Videos/pickleball/
7. System displays success message with file paths

---

#### UC-13: Export Debug Data

| Field | Description |
|-------|-------------|
| **ID** | UC-13 |
| **Name** | Export Debug Data |
| **Actor** | System (automatic) |
| **Preconditions** | Kdenlive project generated |
| **Postconditions** | Debug JSON file created |

**Main Flow:**
1. Triggered automatically after UC-12
2. System compiles complete session data
3. System includes: rallies, interventions, comments, game info
4. System writes JSON to ~/Videos/debug/
5. File available for troubleshooting

---

#### UC-14: Handle Game Over

| Field | Description |
|-------|-------------|
| **ID** | UC-14 |
| **Name** | Handle Game Over |
| **Actor** | System/User |
| **Preconditions** | Score reaches winning condition |
| **Postconditions** | Game ended or user continues editing |

**Main Flow:**
1. System detects game over condition after rally end
2. System displays Game Over dialog
3. Dialog shows winner and final score
4. User clicks "Finish Game"
5. System marks game as complete
6. System automatically enters Final Review mode

**Alternative Flows:**
- **4a.** User clicks "Continue Editing" → Close dialog, continue marking rallies

---

#### UC-15: Handle Timed Game Expiry

| Field | Description |
|-------|-------------|
| **ID** | UC-15 |
| **Name** | Handle Timed Game Expiry |
| **Actor** | User |
| **Preconditions** | Game type is "Timed" |
| **Postconditions** | Game ended based on current score |

**Main Flow:**
1. User determines time has expired (external clock)
2. User clicks "Time Expired" button
3. System displays Game Over dialog
4. Winner is team with higher score (no win-by-2 required)
5. Dialog shows winner and score
6. User clicks "Finish Game"
7. Continue as UC-14 step 5

---

## 2. Sequence Diagrams

### 2.1 Start New Session

```
┌──────┐          ┌─────────────┐          ┌─────────────┐          ┌──────────┐
│ User │          │ SetupDialog │          │ MainWindow  │          │ MPVPlayer│
└──┬───┘          └──────┬──────┘          └──────┬──────┘          └────┬─────┘
   │                     │                        │                      │
   │  Launch App         │                        │                      │
   │────────────────────>│                        │                      │
   │                     │                        │                      │
   │  Select Video       │                        │                      │
   │────────────────────>│                        │                      │
   │                     │                        │                      │
   │  Enter Game Config  │                        │                      │
   │────────────────────>│                        │                      │
   │                     │                        │                      │
   │  Click Start        │                        │                      │
   │────────────────────>│                        │                      │
   │                     │                        │                      │
   │                     │  validate()            │                      │
   │                     │────────┐               │                      │
   │                     │        │               │                      │
   │                     │<───────┘               │                      │
   │                     │                        │                      │
   │                     │  create(config)        │                      │
   │                     │───────────────────────>│                      │
   │                     │                        │                      │
   │                     │                        │  load(video_path)    │
   │                     │                        │─────────────────────>│
   │                     │                        │                      │
   │                     │                        │  video_loaded        │
   │                     │                        │<─────────────────────│
   │                     │                        │                      │
   │                     │  close()               │                      │
   │                     │────────┐               │                      │
   │                     │        │               │                      │
   │                     │<───────┘               │                      │
   │                     │                        │                      │
   │  Main Window Shown  │                        │                      │
   │<─────────────────────────────────────────────│                      │
   │                     │                        │                      │
```

---

### 2.2 Mark Rally (Complete Flow)

```
┌──────┐       ┌────────────┐       ┌────────────┐       ┌──────────┐       ┌──────────┐
│ User │       │ MainWindow │       │RallyManager│       │ScoreState│       │MPVPlayer │
└──┬───┘       └─────┬──────┘       └─────┬──────┘       └────┬─────┘       └────┬─────┘
   │                 │                    │                   │                  │
   │ Click Rally Start                    │                   │                  │
   │────────────────>│                    │                   │                  │
   │                 │                    │                   │                  │
   │                 │ get_position()     │                   │                  │
   │                 │───────────────────────────────────────────────────────────>
   │                 │                    │                   │                  │
   │                 │ position           │                   │                  │
   │                 │<───────────────────────────────────────────────────────────
   │                 │                    │                   │                  │
   │                 │ start_rally(frame) │                   │                  │
   │                 │───────────────────>│                   │                  │
   │                 │                    │                   │                  │
   │                 │ ok                 │                   │                  │
   │                 │<───────────────────│                   │                  │
   │                 │                    │                   │                  │
   │                 │ show_osd("Rally started...")           │                  │
   │                 │───────────────────────────────────────────────────────────>
   │                 │                    │                   │                  │
   │                 │ update_ui(IN_RALLY)│                   │                  │
   │                 │────────┐           │                   │                  │
   │                 │        │           │                   │                  │
   │                 │<───────┘           │                   │                  │
   │                 │                    │                   │                  │
   │ [Rally plays... │                    │                   │                  │
   │  User watches]  │                    │                   │                  │
   │                 │                    │                   │                  │
   │ Click Server Wins                    │                   │                  │
   │────────────────>│                    │                   │                  │
   │                 │                    │                   │                  │
   │                 │ get_position()     │                   │                  │
   │                 │───────────────────────────────────────────────────────────>
   │                 │                    │                   │                  │
   │                 │ position           │                   │                  │
   │                 │<───────────────────────────────────────────────────────────
   │                 │                    │                   │                  │
   │                 │ get_score_string() │                   │                  │
   │                 │───────────────────────────────────────>│                  │
   │                 │                    │                   │                  │
   │                 │ "7-5-2"            │                   │                  │
   │                 │<───────────────────────────────────────│                  │
   │                 │                    │                   │                  │
   │                 │ end_rally(frame, score, "server")      │                  │
   │                 │───────────────────>│                   │                  │
   │                 │                    │                   │                  │
   │                 │ Rally object       │                   │                  │
   │                 │<───────────────────│                   │                  │
   │                 │                    │                   │                  │
   │                 │ server_wins()      │                   │                  │
   │                 │───────────────────────────────────────>│                  │
   │                 │                    │                   │                  │
   │                 │ new_score, is_game_over                │                  │
   │                 │<───────────────────────────────────────│                  │
   │                 │                    │                   │                  │
   │                 │ show_osd("Server wins - 8-5-1")        │                  │
   │                 │───────────────────────────────────────────────────────────>
   │                 │                    │                   │                  │
   │                 │ update_ui(WAITING) │                   │                  │
   │                 │────────┐           │                   │                  │
   │                 │        │           │                   │                  │
   │                 │<───────┘           │                   │                  │
   │                 │                    │                   │                  │
```

---

### 2.3 Undo Action

```
┌──────┐       ┌────────────┐       ┌────────────┐       ┌──────────┐       ┌──────────┐
│ User │       │ MainWindow │       │RallyManager│       │ScoreState│       │MPVPlayer │
└──┬───┘       └─────┬──────┘       └─────┬──────┘       └────┬─────┘       └────┬─────┘
   │                 │                    │                   │                  │
   │ Click Undo      │                    │                   │                  │
   │────────────────>│                    │                   │                  │
   │                 │                    │                   │                  │
   │                 │ get_last_action()  │                   │                  │
   │                 │───────────────────>│                   │                  │
   │                 │                    │                   │                  │
   │                 │ ActionType.RALLY_END, Rally            │                  │
   │                 │<───────────────────│                   │                  │
   │                 │                    │                   │                  │
   │                 │ undo_last()        │                   │                  │
   │                 │───────────────────>│                   │                  │
   │                 │                    │                   │                  │
   │                 │                    │ revert_rally()    │                  │
   │                 │                    │──────────────────>│                  │
   │                 │                    │                   │                  │
   │                 │                    │ previous_state    │                  │
   │                 │                    │<──────────────────│                  │
   │                 │                    │                   │                  │
   │                 │ undone, seek_position                  │                  │
   │                 │<───────────────────│                   │                  │
   │                 │                    │                   │                  │
   │                 │ seek(position)     │                   │                  │
   │                 │───────────────────────────────────────────────────────────>
   │                 │                    │                   │                  │
   │                 │ update_ui()        │                   │                  │
   │                 │────────┐           │                   │                  │
   │                 │        │           │                   │                  │
   │                 │<───────┘           │                   │                  │
   │                 │                    │                   │                  │
```

---

### 2.4 Generate Kdenlive Project

```
┌──────┐       ┌────────────┐       ┌────────────┐       ┌─────────────────┐       ┌──────────┐
│ User │       │ ReviewMode │       │RallyManager│       │KdenliveGenerator│       │FileSystem│
└──┬───┘       └─────┬──────┘       └─────┬──────┘       └────────┬────────┘       └────┬─────┘
   │                 │                    │                       │                     │
   │ Click Generate  │                    │                       │                     │
   │────────────────>│                    │                       │                     │
   │                 │                    │                       │                     │
   │                 │ get_all_rallies()  │                       │                     │
   │                 │───────────────────>│                       │                     │
   │                 │                    │                       │                     │
   │                 │ List[Rally]        │                       │                     │
   │                 │<───────────────────│                       │                     │
   │                 │                    │                       │                     │
   │                 │ convert_to_segments(rallies)               │                     │
   │                 │────────┐           │                       │                     │
   │                 │        │           │                       │                     │
   │                 │<───────┘           │                       │                     │
   │                 │                    │                       │                     │
   │                 │ generate(video_path, segments, profile)    │                     │
   │                 │───────────────────────────────────────────>│                     │
   │                 │                    │                       │                     │
   │                 │                    │                       │ probe_video()       │
   │                 │                    │                       │────────┐            │
   │                 │                    │                       │        │            │
   │                 │                    │                       │<───────┘            │
   │                 │                    │                       │                     │
   │                 │                    │                       │ generate_srt()      │
   │                 │                    │                       │────────┐            │
   │                 │                    │                       │        │            │
   │                 │                    │                       │<───────┘            │
   │                 │                    │                       │                     │
   │                 │                    │                       │ write(srt_path)     │
   │                 │                    │                       │────────────────────>│
   │                 │                    │                       │                     │
   │                 │                    │                       │ generate_xml()      │
   │                 │                    │                       │────────┐            │
   │                 │                    │                       │        │            │
   │                 │                    │                       │<───────┘            │
   │                 │                    │                       │                     │
   │                 │                    │                       │ write(kdenlive_path)│
   │                 │                    │                       │────────────────────>│
   │                 │                    │                       │                     │
   │                 │ success, paths     │                       │                     │
   │                 │<───────────────────────────────────────────│                     │
   │                 │                    │                       │                     │
   │ Success Dialog  │                    │                       │                     │
   │<────────────────│                    │                       │                     │
   │                 │                    │                       │                     │
```

---

### 2.5 Session Resume Flow

```
┌──────┐       ┌─────────────┐       ┌───────────────┐       ┌────────────┐       ┌──────────┐
│ User │       │ SetupDialog │       │SessionManager │       │ MainWindow │       │MPVPlayer │
└──┬───┘       └──────┬──────┘       └───────┬───────┘       └─────┬──────┘       └────┬─────┘
   │                  │                      │                     │                   │
   │ Select Video     │                      │                     │                   │
   │─────────────────>│                      │                     │                   │
   │                  │                      │                     │                   │
   │                  │ find_session(path)   │                     │                   │
   │                  │─────────────────────>│                     │                   │
   │                  │                      │                     │                   │
   │                  │ SessionState         │                     │                   │
   │                  │<─────────────────────│                     │                   │
   │                  │                      │                     │                   │
   │                  │ show_resume_dialog() │                     │                   │
   │                  │────────┐             │                     │                   │
   │                  │        │             │                     │                   │
   │                  │<───────┘             │                     │                   │
   │                  │                      │                     │                   │
   │ Resume Dialog    │                      │                     │                   │
   │<─────────────────│                      │                     │                   │
   │                  │                      │                     │                   │
   │ Click Resume     │                      │                     │                   │
   │─────────────────>│                      │                     │                   │
   │                  │                      │                     │                   │
   │                  │ load(session_path)   │                     │                   │
   │                  │─────────────────────>│                     │                   │
   │                  │                      │                     │                   │
   │                  │ SessionState         │                     │                   │
   │                  │<─────────────────────│                     │                   │
   │                  │                      │                     │                   │
   │                  │ create(state)        │                     │                   │
   │                  │────────────────────────────────────────────>                   │
   │                  │                      │                     │                   │
   │                  │                      │                     │ load(video)       │
   │                  │                      │                     │──────────────────>│
   │                  │                      │                     │                   │
   │                  │                      │                     │ seek(last_pos)    │
   │                  │                      │                     │──────────────────>│
   │                  │                      │                     │                   │
   │                  │                      │                     │ restore_state()   │
   │                  │                      │                     │────────┐          │
   │                  │                      │                     │        │          │
   │                  │                      │                     │<───────┘          │
   │                  │                      │                     │                   │
   │ Main Window      │                      │                     │                   │
   │<──────────────────────────────────────────────────────────────│                   │
   │                  │                      │                     │                   │
```

---

## 3. Class Diagrams

### 3.1 Core Classes Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    APPLICATION LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐                │
│  │   MainWindow    │       │   SetupDialog   │       │   ReviewMode    │                │
│  ├─────────────────┤       ├─────────────────┤       ├─────────────────┤                │
│  │ video_widget    │       │ video_path      │       │ current_rally   │                │
│  │ rally_manager   │       │ game_type       │       │ rally_list      │                │
│  │ score_state     │       │ victory_rules   │       │ cascade_enabled │                │
│  │ session_manager │       │ player_names    │       ├─────────────────┤                │
│  ├─────────────────┤       ├─────────────────┤       │ navigate_rally()│                │
│  │ on_rally_start()│       │ validate()      │       │ adjust_timing() │                │
│  │ on_rally_end()  │       │ get_config()    │       │ edit_score()    │                │
│  │ on_undo()       │       └─────────────────┘       │ generate()      │                │
│  │ update_ui()     │                                 └─────────────────┘                │
│  └─────────────────┘                                                                    │
│           │                                                                             │
│           │ uses                                                                        │
│           ▼                                                                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                      CORE LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐                │
│  │  RallyManager   │       │   ScoreState    │       │ SessionManager  │                │
│  ├─────────────────┤       ├─────────────────┤       ├─────────────────┤                │
│  │ rallies: List   │       │ game_type       │       │ session_dir     │                │
│  │ current_start   │       │ victory_rules   │       ├─────────────────┤                │
│  │ action_stack    │       │ score: List     │       │ save()          │                │
│  ├─────────────────┤       │ serving_team    │       │ load()          │                │
│  │ start_rally()   │       │ server_number   │       │ find_existing() │                │
│  │ end_rally()     │       ├─────────────────┤       │ delete()        │                │
│  │ undo()          │       │ server_wins()   │       └─────────────────┘                │
│  │ get_rallies()   │       │ receiver_wins() │                                          │
│  └─────────────────┘       │ is_game_over()  │                                          │
│           │                │ get_score_str() │                                          │
│           │                │ get_server_info()                                          │
│           │                └─────────────────┘                                          │
│           │                         │                                                   │
│           ▼                         ▼                                                   │
│  ┌─────────────────────────────────────────────┐                                        │
│  │                    Rally                    │                                        │
│  ├─────────────────────────────────────────────┤                                        │
│  │ start_frame: int                            │                                        │
│  │ end_frame: int                              │                                        │
│  │ score_at_start: str                         │                                        │
│  │ winner: str                                 │                                        │
│  │ comment: Optional[str]                      │                                        │
│  └─────────────────────────────────────────────┘                                        │
│                                                                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                     VIDEO LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────┐       ┌─────────────────┐                                          │
│  │  VideoWidget    │       │   VideoProbe    │                                          │
│  ├─────────────────┤       ├─────────────────┤                                          │
│  │ player: MPV     │       │ path: str       │                                          │
│  ├─────────────────┤       ├─────────────────┤                                          │
│  │ load()          │       │ probe()         │                                          │
│  │ play/pause()    │       │ get_fps()       │                                          │
│  │ seek()          │       │ get_duration()  │                                          │
│  │ frame_step()    │       │ get_resolution()│                                          │
│  │ get_position()  │       └─────────────────┘                                          │
│  │ show_osd()      │                                                                    │
│  └─────────────────┘                                                                    │
│                                                                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                     OUTPUT LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐                │
│  │KdenliveGenerator│       │SubtitleGenerator│       │  DebugExporter  │                │
│  ├─────────────────┤       ├─────────────────┤       ├─────────────────┤                │
│  │ video_path      │       │ segments        │       │ session_data    │                │
│  │ segments        │       │ fps             │       ├─────────────────┤                │
│  │ profile         │       ├─────────────────┤       │ export()        │                │
│  ├─────────────────┤       │ generate_srt()  │       └─────────────────┘                │
│  │ generate()      │       └─────────────────┘                                          │
│  │ write_xml()     │                                                                    │
│  └─────────────────┘                                                                    │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 ScoreState Class Detail

```
┌───────────────────────────────────────────────────────────────┐
│                         ScoreState                            │
├───────────────────────────────────────────────────────────────┤
│ - game_type: str              # "singles" | "doubles"         │
│ - victory_rules: str          # "11" | "9" | "timed"          │
│ - score: List[int]            # [t1, t2] or [t1, t2, server#] │
│ - serving_team: int           # 0 or 1                        │
│ - server_number: Optional[int] # 1 or 2 (doubles only)        │
│ - history: List[ScoreSnapshot] # For undo support             │
├───────────────────────────────────────────────────────────────┤
│ + __init__(game_type, victory_rules)                          │
│ + server_wins() -> Tuple[str, bool]                           │
│ + receiver_wins() -> Tuple[str, bool]                         │
│ + is_game_over() -> Tuple[bool, Optional[int]]                │
│ + get_score_string() -> str                                   │
│ + get_server_info() -> ServerInfo                             │
│ + set_score(score: List[int]) -> None                         │
│ + force_side_out() -> None                                    │
│ + save_snapshot() -> None                                     │
│ + restore_snapshot() -> bool                                  │
│ + to_dict() -> dict                                           │
│ + from_dict(data: dict) -> ScoreState                         │
├───────────────────────────────────────────────────────────────┤
│ - _handle_singles_server_wins() -> None                       │
│ - _handle_singles_receiver_wins() -> None                     │
│ - _handle_doubles_server_wins() -> None                       │
│ - _handle_doubles_receiver_wins() -> None                     │
│ - _check_win_condition() -> Tuple[bool, Optional[int]]        │
└───────────────────────────────────────────────────────────────┘
                              │
                              │ contains
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                       ScoreSnapshot                           │
├───────────────────────────────────────────────────────────────┤
│ + score: List[int]                                            │
│ + serving_team: int                                           │
│ + server_number: Optional[int]                                │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                        ServerInfo                             │
├───────────────────────────────────────────────────────────────┤
│ + team: int                   # 0 or 1                        │
│ + player_index: int           # 0 or 1 (which player on team) │
│ + server_number: Optional[int] # 1 or 2 (doubles)             │
│ + court_side: str             # "right" | "left" (singles)    │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.3 RallyManager Class Detail

```
┌───────────────────────────────────────────────────────────────┐
│                       RallyManager                            │
├───────────────────────────────────────────────────────────────┤
│ - rallies: List[Rally]                                        │
│ - current_rally_start: Optional[int]  # Frame number          │
│ - action_stack: List[Action]          # For undo              │
│ - fps: float                          # Video frame rate      │
│ - start_padding: float = 0.5          # Seconds               │
│ - end_padding: float = 1.0            # Seconds               │
├───────────────────────────────────────────────────────────────┤
│ + __init__(fps: float)                                        │
│ + start_rally(frame: int) -> bool                             │
│ + end_rally(frame: int, score: str, winner: str) -> Rally     │
│ + is_rally_in_progress() -> bool                              │
│ + get_rally_count() -> int                                    │
│ + get_rallies() -> List[Rally]                                │
│ + get_rally(index: int) -> Rally                              │
│ + update_rally_timing(index: int, start: int, end: int)       │
│ + update_rally_score(index: int, score: str)                  │
│ + undo() -> Optional[Tuple[ActionType, Any]]                  │
│ + can_undo() -> bool                                          │
│ + to_segments() -> List[dict]                                 │
│ + to_dict() -> dict                                           │
│ + from_dict(data: dict, fps: float) -> RallyManager           │
├───────────────────────────────────────────────────────────────┤
│ - _apply_start_padding(frame: int) -> int                     │
│ - _apply_end_padding(frame: int) -> int                       │
│ - _push_action(action_type: ActionType, data: Any)            │
└───────────────────────────────────────────────────────────────┘
                              │
                              │ contains
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                          Rally                                │
├───────────────────────────────────────────────────────────────┤
│ + start_frame: int                                            │
│ + end_frame: int                                              │
│ + score_at_start: str                                         │
│ + winner: str                # "server" | "receiver"          │
│ + comment: Optional[str]                                      │
├───────────────────────────────────────────────────────────────┤
│ + duration_frames() -> int                                    │
│ + duration_seconds(fps: float) -> float                       │
│ + to_dict() -> dict                                           │
│ + from_dict(data: dict) -> Rally                              │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                         Action                                │
├───────────────────────────────────────────────────────────────┤
│ + action_type: ActionType                                     │
│ + data: Any                                                   │
│ + timestamp: datetime                                         │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                       ActionType                              │
├───────────────────────────────────────────────────────────────┤
│ RALLY_START                                                   │
│ RALLY_END                                                     │
│ SCORE_EDIT                                                    │
│ SIDE_OUT                                                      │
│ COMMENT_ADD                                                   │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.4 SessionManager Class Detail

```
┌───────────────────────────────────────────────────────────────┐
│                      SessionManager                           │
├───────────────────────────────────────────────────────────────┤
│ - session_dir: Path                                           │
│ - current_session_path: Optional[Path]                        │
├───────────────────────────────────────────────────────────────┤
│ + __init__(session_dir: Optional[Path] = None)                │
│ + save(state: SessionState) -> Path                           │
│ + load(path: Path) -> SessionState                            │
│ + find_existing(video_path: str) -> Optional[Path]            │
│ + delete(path: Path) -> bool                                  │
│ + list_sessions() -> List[SessionInfo]                        │
├───────────────────────────────────────────────────────────────┤
│ - _get_video_hash(path: str) -> str                           │
│ - _session_filename(video_path: str) -> str                   │
└───────────────────────────────────────────────────────────────┘
                              │
                              │ manages
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                       SessionState                            │
├───────────────────────────────────────────────────────────────┤
│ + version: str = "1.0"                                        │
│ + video_path: str                                             │
│ + video_hash: str                                             │
│ + game_type: str                                              │
│ + victory_rules: str                                          │
│ + player_names: dict                                          │
│ + rallies: List[Rally]                                        │
│ + current_score: List[int]                                    │
│ + serving_team: int                                           │
│ + server_number: Optional[int]                                │
│ + last_position: float                                        │
│ + interventions: List[Intervention]                           │
│ + comments: List[Comment]                                     │
│ + created_at: str                                             │
│ + modified_at: str                                            │
├───────────────────────────────────────────────────────────────┤
│ + to_dict() -> dict                                           │
│ + from_dict(data: dict) -> SessionState                       │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.5 UI Widget Classes

```
┌───────────────────────────────────────────────────────────────┐
│                       VideoWidget                             │
│                    (extends QWidget)                          │
├───────────────────────────────────────────────────────────────┤
│ - player: mpv.MPV                                             │
│ - fps: float                                                  │
├───────────────────────────────────────────────────────────────┤
│ # Signals                                                     │
│ + position_changed: pyqtSignal(float)                         │
│ + duration_changed: pyqtSignal(float)                         │
│ + eof_reached: pyqtSignal()                                   │
├───────────────────────────────────────────────────────────────┤
│ + load(path: str) -> None                                     │
│ + play() -> None                                              │
│ + pause() -> None                                             │
│ + toggle_pause() -> None                                      │
│ + seek(seconds: float) -> None                                │
│ + seek_frame(frame: int) -> None                              │
│ + frame_step() -> None                                        │
│ + frame_back_step() -> None                                   │
│ + set_speed(speed: float) -> None                             │
│ + get_position() -> float                                     │
│ + get_position_frame() -> int                                 │
│ + get_duration() -> float                                     │
│ + show_osd(message: str, duration: float) -> None             │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                      RallyButton                              │
│                   (extends QPushButton)                       │
├───────────────────────────────────────────────────────────────┤
│ - base_color: QColor                                          │
│ - bright_color: QColor                                        │
│ - dimmed_color: QColor                                        │
│ - is_highlighted: bool                                        │
├───────────────────────────────────────────────────────────────┤
│ + set_highlighted(highlighted: bool) -> None                  │
│ + set_dimmed(dimmed: bool) -> None                            │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                       StateBar                                │
│                    (extends QFrame)                           │
├───────────────────────────────────────────────────────────────┤
│ - score_label: QLabel                                         │
│ - server_label: QLabel                                        │
│ - rally_label: QLabel                                         │
│ - status_label: QLabel                                        │
├───────────────────────────────────────────────────────────────┤
│ + set_score(score: str) -> None                               │
│ + set_server(server_info: str) -> None                        │
│ + set_rally_count(count: int) -> None                         │
│ + set_status(status: str) -> None  # "WAITING" | "IN RALLY"   │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. State Diagrams

### 4.1 Application State Machine

```
                                    ┌─────────────┐
                                    │             │
                                    │   STARTUP   │
                                    │             │
                                    └──────┬──────┘
                                           │
                                           │ launch
                                           ▼
                                    ┌─────────────┐
                              ┌────▶│             │
                              │     │    SETUP    │
                              │     │             │
                              │     └──────┬──────┘
                              │            │
                              │            │ start_editing
                              │            ▼
                              │     ┌─────────────┐
                              │     │             │◀──────────────────────┐
              start_fresh     │     │   EDITING   │                       │
                              │     │             │                       │
                              │     └──────┬──────┘                       │
                              │            │                              │
                              │            ├─────────────┐                │
                              │            │             │                │
                              │            │             ▼                │
                              │            │      ┌─────────────┐         │
                              │            │      │             │         │
                              │            │      │   REVIEW    │─────────┘
                              │            │      │             │  exit_review
                              │            │      └──────┬──────┘
                              │            │             │
                              │            │             │ generate
                              │            │             ▼
                              │            │      ┌─────────────┐
                              │            │      │             │
                              │            │      │  EXPORTING  │
                              │            │      │             │
                              │            │      └──────┬──────┘
                              │            │             │
                              │            ▼             │
                              │     ┌─────────────┐      │
                              │     │             │      │
                              └─────│  GAME_OVER  │◀─────┘
                                    │             │
                                    └──────┬──────┘
                                           │
                                           │ quit
                                           ▼
                                    ┌─────────────┐
                                    │             │
                                    │    EXIT     │
                                    │             │
                                    └─────────────┘
```

---

### 4.2 Rally State Machine

```
                         ┌──────────────────────────────────────┐
                         │                                      │
                         │                                      ▼
                  ┌──────┴──────┐                        ┌─────────────┐
                  │             │    rally_start         │             │
    ──────────────│   WAITING   │───────────────────────▶│  IN_RALLY   │
                  │             │                        │             │
                  └──────┬──────┘                        └──────┬──────┘
                         ▲                                      │
                         │                                      │
                         │      server_wins / receiver_wins     │
                         │                                      │
                         └──────────────────────────────────────┘


    State Details:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ WAITING                                                             │
    ├─────────────────────────────────────────────────────────────────────┤
    │ • Rally Start button: HIGHLIGHTED                                   │
    │ • Server Wins button: DIMMED                                        │
    │ • Receiver Wins button: DIMMED                                      │
    │ • Status label: "WAITING"                                           │
    │ • Allowed actions: Rally Start, Edit Score, Side-Out, Comment, Undo │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │ IN_RALLY                                                            │
    ├─────────────────────────────────────────────────────────────────────┤
    │ • Rally Start button: DIMMED                                        │
    │ • Server Wins button: HIGHLIGHTED                                   │
    │ • Receiver Wins button: HIGHLIGHTED                                 │
    │ • Status label: "IN RALLY"                                          │
    │ • Allowed actions: Server Wins, Receiver Wins, Undo                 │
    └─────────────────────────────────────────────────────────────────────┘
```

---

### 4.3 Score State Transitions (Doubles)

```
    Server 1 Loses                    Server 2 Loses
    ┌───────────┐                     ┌───────────┐
    │           │                     │           │
    ▼           │                     ▼           │
┌───────┐       │                 ┌───────┐       │
│Server │───────┘                 │Server │───────┘
│   1   │                         │   2   │
│ Team A│                         │ Team A│
└───┬───┘                         └───┬───┘
    │                                 │
    │ Server 1 Wins                   │ Server 2 Wins
    │ (Team A scores)                 │ (Team A scores)
    ▼                                 ▼
┌───────┐                         ┌───────┐
│Server │                         │Server │
│   1   │                         │   2   │
│ Team A│                         │ Team A│
└───────┘                         └───────┘
                                      │
                                      │ Server 2 Loses
                                      │ (Side-out)
                                      ▼
                                 ┌───────┐
                                 │Server │
                                 │   1   │
                                 │ Team B│
                                 └───────┘


    Example Progression:
    ┌────────┬────────────┬──────────────┬─────────────────────────┐
    │ Rally  │   Event    │    Score     │         Server          │
    ├────────┼────────────┼──────────────┼─────────────────────────┤
    │   -    │ Game Start │    0-0-2     │ Team 1, Server 2        │
    │   1    │ Server Win │    1-0-1     │ Team 1, Server 1        │
    │   2    │ Server Win │    2-0-1     │ Team 1, Server 1        │
    │   3    │ Recv Win   │    2-0-2     │ Team 1, Server 2        │
    │   4    │ Recv Win   │    2-0-1     │ Team 2, Server 1 (S.O.) │
    │   5    │ Server Win │    2-1-1     │ Team 2, Server 1        │
    │  ...   │    ...     │     ...      │          ...            │
    └────────┴────────────┴──────────────┴─────────────────────────┘
```

---

## 5. Data Flow

### 5.1 Rally Marking Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              RALLY MARKING DATA FLOW                                 │
└──────────────────────────────────────────────────────────────────────────────────────┘

    User Action                Memory State                    Persistence
    ───────────────────────────────────────────────────────────────────────────────────

    Click "Rally Start"
           │
           ▼
    ┌─────────────┐
    │ MPV Player  │──── get_position() ────▶ timestamp (float)
    └─────────────┘                                │
                                                   │ convert to frame
                                                   ▼
                                          ┌───────────────┐
                                          │ RallyManager  │
                                          │ current_start │ = frame - padding
                                          └───────────────┘


    Click "Server Wins"
           │
           ▼
    ┌─────────────┐
    │ MPV Player  │──── get_position() ────▶ timestamp (float)
    └─────────────┘                                │
                                                   │ convert to frame
                                                   ▼
                         ┌─────────────┐   ┌───────────────┐
                         │ ScoreState  │◀──│ RallyManager  │
                         │             │   │ end_rally()   │
                         │ score_str   │   └───────────────┘
                         └──────┬──────┘           │
                                │                  │ create Rally object
                                │                  ▼
                                │          ┌───────────────┐
                                │          │    Rally      │
                                │          │ start_frame   │
                                │          │ end_frame     │
                                │          │ score         │
                                │          │ winner        │
                                │          └───────────────┘
                                │                  │
                                │                  │ append to list
                                ▼                  ▼
                         ┌─────────────┐   ┌───────────────┐
                         │ ScoreState  │   │ RallyManager  │
                         │ server_wins()   │ rallies[]     │
                         │ new score   │   └───────────────┘
                         └─────────────┘


    Click "Save Session"
           │
           ▼
    ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
    │ ScoreState    │────▶│ SessionState  │────▶│   JSON File   │
    │ RallyManager  │     │   (combined)  │     │ ~/.local/...  │
    │ Video Position│     │               │     │               │
    └───────────────┘     └───────────────┘     └───────────────┘
```

---

### 5.2 Output Generation Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           OUTPUT GENERATION DATA FLOW                                │
└──────────────────────────────────────────────────────────────────────────────────────┘

    ┌───────────────┐
    │ RallyManager  │
    │ rallies[]     │
    └───────┬───────┘
            │
            │ to_segments()
            ▼
    ┌───────────────────────────────────────────┐
    │ segments = [                              │
    │   {"in": 1534, "out": 2610, "score": "0-0-2"},
    │   {"in": 3200, "out": 4100, "score": "1-0-1"},
    │   ...                                     │
    │ ]                                         │
    └───────────────────┬───────────────────────┘
                        │
                        ▼
    ┌───────────────────────────────────────────┐
    │           KdenliveGenerator               │
    │                                           │
    │  ┌─────────────────────────────────────┐  │
    │  │         probe_video()               │  │
    │  │  • fps, duration, resolution        │  │
    │  └─────────────────────────────────────┘  │
    │                    │                      │
    │                    ▼                      │
    │  ┌─────────────────────────────────────┐  │
    │  │       generate_srt()                │  │
    │  │  • Convert frames to timeline time  │  │
    │  │  • Create subtitle entries          │  │
    │  └─────────────────────────────────────┘  │
    │                    │                      │
    │                    ▼                      │
    │  ┌─────────────────────────────────────┐  │
    │  │       generate_xml()                │  │
    │  │  • Build MLT structure              │  │
    │  │  • Add playlist entries             │  │
    │  │  • Add subtitle filter              │  │
    │  └─────────────────────────────────────┘  │
    │                                           │
    └───────────────────┬───────────────────────┘
                        │
                        ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ~/Videos/pickleball/                                          │
    │   ├── match_2026-01-14.kdenlive    ◀─── MLT XML project         │
    │   └── match_2026-01-14.srt         ◀─── Subtitles               │
    │                                                                 │
    │   ~/Videos/debug/                                               │
    │   └── match_2026-01-14.json        ◀─── Debug data              │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

---

### 5.3 Session Persistence Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                          SESSION PERSISTENCE DATA FLOW                               │
└──────────────────────────────────────────────────────────────────────────────────────┘


    SAVE FLOW:
    ──────────────────────────────────────────────────────────────────────────────────

    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    ┌──────────────┐
    │ MainWindow  │   │ ScoreState  │   │RallyManager │    │ VideoWidget  │
    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘    └──────┬───────┘
           │                 │                 │                  │
           │ save_session()  │                 │                  │
           │─────────────────┼─────────────────┼──────────────────┤
           │                 │                 │                  │
           │ ◀── to_dict() ──│                 │                  │
           │                 │                 │                  │
           │ ◀───────────────────── to_dict() ─│                  │
           │                 │                 │                  │
           │ ◀───────────────────────────────────── get_position()
           │                 │                 │                  │
           ▼
    ┌─────────────────┐
    │ SessionManager  │
    │    save()       │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │  ~/.local/share/pickleball-editor/sessions/{hash}.json      │
    └─────────────────────────────────────────────────────────────┘


    LOAD FLOW:
    ──────────────────────────────────────────────────────────────────────────────────

    ┌─────────────────────────────────────────────────────────────┐
    │  ~/.local/share/pickleball-editor/sessions/{hash}.json      │
    └─────────────────────────────────────────────────────────────┘
             │
             │ read
             ▼
    ┌─────────────────┐
    │ SessionManager  │
    │    load()       │
    └────────┬────────┘
             │
             │ SessionState
             ▼
    ┌─────────────┐
    │ MainWindow  │
    │ restore()   │
    └──────┬──────┘
           │
           ├──────────────▶ ScoreState.from_dict()
           │
           ├──────────────▶ RallyManager.from_dict()
           │
           └──────────────▶ VideoWidget.seek(last_position)
```

---

## Appendix A: Error Handling Matrix

| Scenario | Detection | User Feedback | Recovery |
|----------|-----------|---------------|----------|
| Video file not found | File.exists() | Error dialog | Return to Setup |
| Video load fails | MPV error event | Error dialog | Return to Setup |
| Invalid score format | Regex validation | Inline error | Keep dialog open |
| Rally End without Start | State check | Warning popup | No action |
| Rally Start while in rally | State check | Warning popup | No action |
| Session save fails | IO exception | Error dialog | Retry option |
| Session load fails | JSON parse error | Error dialog | Start fresh |
| Kdenlive gen fails | Exception | Error dialog | Stay in Review |

---

## Appendix B: Performance Considerations

| Operation | Target | Strategy |
|-----------|--------|----------|
| Video seek | < 100ms | MPV hardware acceleration |
| Frame step | < 50ms | MPV frame-step command |
| UI update | < 16ms | Minimal redraws, Qt signals |
| Session save | < 500ms | JSON serialization |
| Kdenlive gen | < 2s | String building, single write |
| OSD display | Immediate | MPV show-text command |

---

*Document Version: 1.0*
*Created: 2026-01-14*
