# Pickleball Video Editor Tool - Inception Document

## Executive Summary

This project aims to build a command-line tool that streamlines the editing of pickleball match videos. The tool integrates with MPV for playback and timestamp capture, then generates a Kdenlive project file with cuts and score subtitles pre-applied—eliminating hours of manual editing work.

---

## Problem Statement

### Current Workflow Pain Points

Manual editing of pickleball match videos in Kdenlive is tedious and time-consuming:

| Task | Pain Point |
|------|------------|
| Cutting dead time | Must identify each rally boundary manually |
| Score subtitles | Created individually, scores typed by hand |
| Subtitle duration | Must be manually extended to fill each rally |
| Score tracking | Mental calculation while editing |

Rally lengths vary significantly, meaning every subtitle requires individual adjustment. A typical match may have 50+ rallies, each requiring multiple manual operations.

### Impact

What should be a straightforward editing task becomes a multi-hour chore, discouraging timely publishing of match recordings.

---

## Proposed Solution

### Overview

A Python-based tool that:
1. Launches MPV with the raw footage
2. Captures keypress events with timestamps during playback
3. Calculates scores automatically based on rally outcomes
4. Generates a Kdenlive project XML with cuts and subtitles pre-applied

### User Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Load video     │────▶│  Mark rallies   │────▶│  Generate XML   │
│  in MPV         │     │  (keypresses)   │     │  project file   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  Open in        │
                                               │  Kdenlive       │
                                               └─────────────────┘
```

### Key Interactions

| Key | Action |
|-----|--------|
| `[TBD]` | Mark rally start (server ready to serve) |
| `S` | Mark rally end - serving team won |
| `R` | Mark rally end - receiving team won |
| `←/→` | 5-second skip (standard MPV navigation) |

### Automatic Calculations

- **Segments to keep**: rally start → rally end
- **Segments to cut**: everything between rallies
- **Running score**: based on win sequence and pickleball rules
- **Subtitle timing**: score appears at rally start, persists through rally

---

## Technical Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                    pickleball-editor                     │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ MPV         │  │ Score       │  │ Kdenlive XML    │  │
│  │ Controller  │  │ State       │  │ Generator       │  │
│  │             │  │ Machine     │  │                 │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│         │                │                  │           │
│         ▼                ▼                  ▼           │
│  ┌─────────────────────────────────────────────────────┐│
│  │              Event/Timestamp Store                  ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| Platform | Manjaro Linux |
| Language | Python 3 |
| Video playback | MPV (via IPC or console output) |
| Output format | Kdenlive project XML (.kdenlive) |
| Fallback output | SRT subtitle file |

### MPV Integration

MPV provides:
- Console output with current timestamp
- IPC socket for programmatic control
- Built-in navigation (arrow keys for 5-second skips)

---

## Pickleball Scoring Rules

### Standard Rules (to confirm with user)

- Games played to **11 points**, win by **2**
- Only the serving team can score
- Score format: `[serving team]-[receiving team]-[server number]`
- Example: `7-5-2` = serving team has 7, receiving has 5, second server

### Server Rotation

```
Server 1 loses rally → Server 2 serves
Server 2 loses rally → Side-out (other team serves)
```

### Game Start Exception

First server of each game starts as **Server 2** (0-0-2), meaning first side-out happens after one fault instead of two.

---

## Scope

### In Scope (MVP)

- [ ] MPV integration for video playback
- [ ] Keypress capture with timestamp association
- [ ] Rally start/end marking
- [ ] Automatic score calculation
- [ ] Kdenlive XML generation with cuts
- [ ] Subtitle track generation with scores
- [ ] Single-game support

### Out of Scope (MVP)

- Automated rally detection (audio/motion analysis)
- Multi-game match handling
- GUI interface
- Direct video rendering
- Team name customization in subtitles

### Future Considerations

- **Automated cut detection**: Audio analysis (paddle impacts) + motion detection
- **Multi-game support**: "New game" reset functionality
- **Subtitle customization**: Team names, decorative formatting

---

## Dependencies & Prerequisites

### Required

- Sample Kdenlive project file with:
  - Video clips with cuts applied
  - Subtitle track with timed entries
- Confirmation of scoring rule variations (if any)

### Development Environment

- Python 3.x
- MPV player installed
- Kdenlive (for testing output)

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Kdenlive XML schema - need sample file to reverse-engineer | Pending |
| 2 | Any scoring rule variations from standard? | Pending |
| 3 | Multi-game handling needed for MVP? | Pending |
| 4 | Subtitle format preference: `0-0-2` vs `Score: 0-0-2`? | Pending |

---

## Implementation Phases

### Phase 1: Foundation
- Analyze Kdenlive XML structure from sample file
- Design internal data model for events/timestamps
- Implement score state machine

### Phase 2: MPV Integration
- Implement MPV launch and control
- Capture keypresses with timestamps
- Provide visual feedback during marking

### Phase 3: Output Generation
- Implement Kdenlive XML generation
- Generate subtitle track with timing
- Apply cuts to video track

### Phase 4: Polish
- Error handling and edge cases
- User documentation
- Testing with real footage

---

## Success Criteria

1. User can mark rallies in real-time during video playback
2. Scores are calculated correctly following pickleball rules
3. Generated Kdenlive project opens without errors
4. Cuts are applied at correct timestamps
5. Subtitles appear at rally start with correct scores
6. Total editing time reduced by >75%

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Kdenlive XML format undocumented | High | Reverse-engineer from sample files |
| MPV timestamp precision issues | Medium | Use IPC socket for reliable timestamps |
| Complex scoring edge cases | Medium | Implement comprehensive test suite |

---

## Appendix: Deferred Feature - Automated Detection

For future exploration after MVP:

**Audio Analysis**
- Detect paddle/ball impacts during active play
- Identify quiet periods between rallies

**Motion Detection**
- High motion = active rally
- Low motion = setup time
- Camera is fixed, simplifying analysis

**Hybrid Approach**
- Require both signals to reduce false positives
- Generate suggested cut points for user review
- Not fully automated—human confirmation required

---

*Document Version: 1.0*
*Created: 2026-01-14*
