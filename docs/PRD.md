# Product Requirements Document
## Pickleball Video Editor Tool

**Version:** 1.0
**Date:** 2026-01-14
**Status:** Draft - Pending Approval

---

## 1. Executive Summary

A desktop GUI application for Manjaro Linux that streamlines the editing of pickleball match videos. The tool embeds MPV for video playback, captures rally timestamps via mouse-driven controls, automatically calculates scores following pickleball rules, and generates a Kdenlive project file with cuts and score subtitles pre-applied.

---

## 2. User Profile

| Attribute | Value |
|-----------|-------|
| Primary User | Single user (developer/owner) |
| Technical Level | Advanced - Linux sysadmin (Debian, Arch, RedHat), Full-stack LAMP developer |
| Platform | Manjaro Linux |
| Release Scope | Personal use only, no public release planned |

---

## 3. Input Specifications

### 3.1 Video Format

| Property | Value |
|----------|-------|
| Container | MP4 |
| Video Codec | H.264 (High profile) |
| Resolution | 1920x1080 |
| Frame Rate | 60 fps |
| Audio Codec | AAC LC, 48kHz stereo |
| Typical Duration | ~9-15 minutes per game |
| Camera Setup | Single camera, fixed position |

---

## 4. Game Mode Support

### 4.1 Match Types

| Mode | Score Format | Server Tracking |
|------|--------------|-----------------|
| Singles | `X-Y` (server score first) | Side-out on any lost rally |
| Doubles | `X-Y-Z` (serving-receiving-server#) | Server 1 → Server 2 → Side-out |

### 4.2 Victory Conditions

| Rule | Description |
|------|-------------|
| Game to 11 | First to 11 points, win by 2 |
| Game to 9 | First to 9 points, win by 2 |
| Timed | Play until Target point and win by 2 or time expires, if time expires then highest score wins (no win-by-2 requirement) |

### 4.3 Scoring Rules

**Singles:**
- Server serves from right court when their score is even
- Server serves from left court when their score is odd
- Side-out occurs on any lost rally by server

**Doubles:**
- Standard server rotation: Server 1 → Server 2 → Side-out
- Game always starts at `0-0-2` (first server starts as Server 2)
- Only serving team can score

### 4.4 Starting Scores

| Mode | Starting Score |
|------|----------------|
| Singles | `0-0` |
| Doubles | `0-0-2` |

---

## 5. Functional Requirements

### 5.1 Application Startup Flow

1. Launch application
2. Browse/select source video file
3. Select game type (Singles/Doubles dropdown)
4. Select victory rules (Game to 11 / Game to 9 / Timed dropdown)
5. Enter player/team names
   - Singles: Player A name, Player B name
   - Doubles: Team 1 (Player 1, Player 2), Team 2 (Player 1, Player 2)
6. Define which team/player serves first
7. Click "Start Editing" to begin

### 5.2 Rally Marking

| Action | Trigger | Timing |
|--------|---------|--------|
| Rally Start | Click "Rally Start" button | When server is in position ready to serve |
| Rally End - Server Wins | Click "Server Wins" button | A few moments after point is decided |
| Rally End - Receiver Wins | Click "Receiver Wins" button | A few moments after point is decided |

### 5.3 Cut Padding

| Boundary | Padding |
|----------|---------|
| Before rally start | 0.5 seconds |
| After rally end | 1.0 second |

### 5.4 Score Correction & Manual Intervention

| Feature | Description |
|---------|-------------|
| Manual Score Edit | User can override score with optional comment explaining why |
| Manual Side-Out | User can force side-out with optional comment explaining why |
| Add Comment | User can add timestamped comment with custom duration (default 5 seconds) |

All manual interventions with comments appear as subtitles in the output video.

### 5.5 Undo Functionality

- Undo last action
- Rewind video to appropriate position
- Allow user to retry the marking

### 5.6 Game End Handling

When score reaches winning condition:
1. Display prompt: "Game Over - [Team/Player X] wins. Save and exit?"
2. Option to continue (in case of miscount)
3. For timed games: "Time Expired" button triggers game end with current score determining winner

### 5.7 Error Prevention

The application must prevent and warn for illogical sequences:
- Pressing "Rally End" without a "Rally Start"
- Pressing "Rally Start" twice in a row

### 5.8 Session Management

| Feature | Description |
|---------|-------------|
| Pause/Resume | Pause MPV and resume during same session |
| Save State | Save current session state to disk for resume after reboot |
| Resume Session | Restore session, seek to last position, show rally summary |
| Unsaved Warning | Warn user when closing with unsaved work |

### 5.9 Final Review Mode

1. Click "Final Review" button
2. System starts at beginning of video
3. Navigate through rallies using Forward/Back buttons
4. At each rally start/stop:
   - Video plays at that position
   - Subtitle displays for verification
   - User can verify score matches player callout
5. Adjustment capabilities:
   - Slide start/stop time of rally
   - Change score in subtitle
   - Score cascade: changing a score adjusts all subsequent scores accordingly

---

## 6. User Interface Requirements

### 6.1 Window Layout

Single application window containing:
- **Top area:** Embedded MPV video player
- **Bottom area:** Control panel with buttons and inputs

### 6.2 Setup Controls

| Control | Type | Description |
|---------|------|-------------|
| Source Video | Browse button + file path display | Select input video file |
| Game Type | Dropdown | Singles / Doubles |
| Victory Rules | Dropdown | Game to 11 / Game to 9 / Timed |
| Player/Team Names | Text inputs | Names for subtitle display |
| First Server | Selection | Define who serves first |
| Start Editing | Button | Begin rally marking session |

### 6.3 Editing Controls

| Control | Type | Description |
|---------|------|-------------|
| Rally Start | Button | Mark rally start timestamp |
| Server Wins | Button | Mark rally end, server won |
| Receiver Wins | Button | Mark rally end, receiver won |
| Undo | Button | Undo last action |
| Time Expired | Button | End timed game (only visible for timed games) |
| Save & Quit | Button | Save session and exit |

### 6.4 Playback Controls (GUI)

| Control | Type | Description |
|---------|------|-------------|
| Play/Pause | Button | Toggle video playback |
| Speed | Dropdown/Buttons | 0.5x, 1x, 2x playback speed |
| Frame Step | Buttons | Frame-by-frame forward/back for precise marking |

Note: MPV arrow keys (5-second skip) remain functional. No keyboard shortcuts for application functions (mouse-only to avoid MPV hotkey conflicts).

### 6.5 Visual Feedback

| Feedback | Location | Content |
|----------|----------|---------|
| Rally Status | MPV OSD | "Rally started..." / "Rally ended - Server wins" |
| Current Score | MPV OSD | Current score in appropriate format |
| State Display | Terminal output | Logging of actions and state |
| Pre-Rally Info | GUI/OSD | Current server, score - user can verify before marking |

---

## 7. Output Requirements

### 7.1 Primary Output

| Property | Value |
|----------|-------|
| Format | Kdenlive project file (.kdenlive) |
| Location | `~/Videos/pickleball/` (default, user-configurable) |
| Filename | `{original_video_name}.kdenlive` |

### 7.2 Debug Output

| Property | Value |
|----------|-------|
| Format | JSON |
| Location | `~/Videos/debug/` |
| Filename | `{original_video_name}.json` |
| Contents | All timestamps, events, score states, comments, manual interventions |

### 7.3 Kdenlive Project Settings

| Property | Value |
|----------|-------|
| Resolution | 1920x1080 |
| Frame Rate | 60 fps |

### 7.4 Subtitle Specifications

| Property | Value |
|----------|-------|
| Position | Bottom-center |
| Font | Default, white |
| Background | Black, alpha 0.4 |
| Duration | Persists through entire rally |
| Initial Display | Player/team names shown for 5 seconds at game start |
| Score Format | Singles: `X-Y` / Doubles: `X-Y-Z` (compact) |
| Comments | Displayed as subtitles with user-specified duration |

---

## 8. Non-Functional Requirements

### 8.1 Platform

- Manjaro Linux (primary target)
- Should be compatible with Arch-based systems

### 8.2 Performance

- Video playback at 60fps without frame drops
- Responsive UI during video playback
- Timestamp precision sufficient for frame-accurate cuts

### 8.3 Reliability

- Session state saved reliably for resume after reboot
- No data loss on unexpected termination (auto-recovery consideration)

---

## 9. Out of Scope

The following are explicitly NOT included in this version:

- Automated rally detection (audio/motion analysis)
- Multi-game match handling
- Multiple camera angles
- Direct video rendering
- Public release/distribution
- Cross-platform support (Windows/Mac)
- Keyboard shortcuts for application functions
- Support for video editors other than Kdenlive
- Match statistics/analytics

---

## 10. Assumptions

1. MPV player is installed and functional on the target system
2. Kdenlive is installed for viewing/editing output files
3. User has sufficient disk space for video files and projects
4. Single-game recordings only (no multi-game matches)
5. All input videos match the specified format (1080p/60fps/H.264)

---

## 11. Open Items

| # | Item | Status |
|---|------|--------|
| 1 | Kdenlive XML schema analysis | Pending - need sample file |
| 2 | MPV embedding approach (IPC vs library) | To be determined in tech stack discussion |
| 3 | GUI framework selection | To be determined in tech stack discussion |

---

## 12. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | | | |
| Developer | | | |

---

*Document generated from PRD Interview conducted 2026-01-14*
