# System Dialogs Implementation

**Date:** 2026-01-14
**Status:** Complete
**Phase:** UI Layer - System Dialogs

---

## Overview

This document describes the implementation of three critical system dialogs for the Pickleball Video Editor, designed per UI_SPEC.md Section 6.

All dialogs follow the "Court Green" design system with:
- Dark theme background (#252A33)
- 12px border radius
- Consistent button styling (primary in accent green, secondary with borders)
- Modern Python 3.13 syntax
- Comprehensive type hints and docstrings

---

## Implemented Dialogs

### 1. GameOverDialog (`src/ui/dialogs/game_over.py`)

**Purpose:** Announces game completion and offers options to continue or finish.

**API:**
```python
from src.ui.dialogs import GameOverDialog, GameOverResult

dialog = GameOverDialog(
    winner_team=1,              # 1 or 2
    final_score="11-9-2",       # Score string
    rally_count=23,             # Total rallies marked
    is_timed=False,             # Timed game variant
    parent=main_window
)

result = dialog.get_result()    # Returns GameOverResult enum

if result == GameOverResult.FINISH_GAME:
    enter_review_mode()
elif result == GameOverResult.CONTINUE_EDITING:
    # User suspects miscount, continue editing
    pass
```

**Features:**
- Large winner announcement in accent-colored box
- Final score display with monospace font
- Rally count summary
- Timed game variant: "Time Expired - Game Over" title + "(Highest score wins)" subtitle
- Two buttons: Continue Editing (secondary) and Finish Game (primary)

**Visual Layout:**
```
┌─────────────────────────────────────┐
│   Game Over                         │
│                                     │
│   ╔═══════════════════════════╗     │
│   ║     TEAM 1 WINS!          ║     │
│   ╚═══════════════════════════╝     │
│                                     │
│   Final Score: 11-9                 │
│   23 rallies                        │
│                                     │
│   [Continue Editing]  [Finish Game] │
└─────────────────────────────────────┘
```

---

### 2. ResumeSessionDialog (`src/ui/dialogs/resume_session.py`)

**Purpose:** Offers to resume a previously saved editing session.

**API:**
```python
from src.ui.dialogs import (
    ResumeSessionDialog,
    ResumeSessionResult,
    SessionDetails
)

details = SessionDetails(
    video_name="match_2026-01-14.mp4",
    rally_count=15,
    current_score="8-6-1",
    last_position=323.45,       # Seconds
    game_type="Doubles",
    victory_rule="Game to 11"
)

dialog = ResumeSessionDialog(details, parent=main_window)
result = dialog.get_result()

if result == ResumeSessionResult.RESUME:
    load_saved_session()
elif result == ResumeSessionResult.START_FRESH:
    clear_session()
```

**Features:**
- Video filename display in styled box
- Session details in bulleted format:
  - Progress (rally count)
  - Current score
  - Last video position (formatted as MM:SS.ss)
  - Game type
  - Victory rules
- Two buttons: Start Fresh (secondary) and Resume Session (primary)

**Visual Layout:**
```
┌────────────────────────────────────────┐
│   Resume Session?                      │
│                                        │
│   Found saved session for:             │
│   ┌──────────────────────────────────┐ │
│   │ match_2026-01-14.mp4             │ │
│   └──────────────────────────────────┘ │
│                                        │
│   SESSION DETAILS                      │
│   • Progress:      15 rallies marked   │
│   • Current Score: 8-6-1               │
│   • Last Position: 05:23.45            │
│   • Game Type:     Doubles             │
│   • Victory Rules: Game to 11          │
│                                        │
│   [Start Fresh]      [Resume Session]  │
└────────────────────────────────────────┘
```

---

### 3. UnsavedWarningDialog (`src/ui/dialogs/unsaved_warning.py`)

**Purpose:** Prevents data loss when quitting with unsaved changes.

**API:**
```python
from src.ui.dialogs import UnsavedWarningDialog, UnsavedWarningResult

dialog = UnsavedWarningDialog(parent=main_window)
result = dialog.get_result()

if result == UnsavedWarningResult.SAVE_AND_QUIT:
    save_session()
    quit_application()
elif result == UnsavedWarningResult.DONT_SAVE:
    quit_application()
# UnsavedWarningResult.CANCEL: continue editing
```

**Features:**
- Simple, clear warning message
- Three action buttons:
  - Don't Save (secondary, left)
  - Cancel (secondary, center)
  - Save & Quit (primary, right)
- Enter key defaults to Save & Quit (safe action)
- Escape key mapped to Cancel

**Visual Layout:**
```
┌────────────────────────────────────────┐
│   Unsaved Changes                      │
│                                        │
│   You have unsaved changes that        │
│   will be lost.                        │
│                                        │
│   [Don't Save] [Cancel]  [Save & Quit] │
└────────────────────────────────────────┘
```

---

## Design System Compliance

### Colors (from `src.ui.styles.colors`)

All dialogs use the "Court Green" palette:
- Background: `BG_SECONDARY` (#252A33)
- Border: `BG_BORDER` (#3D4450)
- Primary text: `TEXT_PRIMARY` (#F5F5F5)
- Secondary text: `TEXT_SECONDARY` (#9E9E9E)
- Accent: `TEXT_ACCENT` / `PRIMARY_ACTION` (#3DDC84)

### Typography (from `src.ui.styles.fonts`)

- Dialog titles: `Fonts.dialog_title()` (18px, SemiBold)
- Body text: `Fonts.label()` (14px, Regular)
- Button text: `Fonts.button_other()` (14px, Medium)
- Monospace displays: `Fonts.display()` with tabular figures

### Spacing

- Dialog padding: `SPACE_LG` (24px)
- Section spacing: `SPACE_LG` (24px)
- Element spacing: `SPACE_MD` (16px)
- Large gaps: `SPACE_XL` (32px)

### Border Radius

- Dialog corners: `RADIUS_XL` (12px)
- Buttons: 6px
- Input boxes: 4px

---

## Button Styling Pattern

All dialogs use consistent button styling:

**Primary Button (e.g., "Finish Game", "Save & Quit"):**
```python
QPushButton#primary_button {
    background-color: #3DDC84;   /* PRIMARY_ACTION */
    border: 2px solid #3DDC84;
    border-radius: 6px;
    color: #252A33;              /* Dark text for contrast */
    padding: 8px 16px;
    font-weight: 600;
    min-width: 140px;
}

QPushButton#primary_button:hover {
    background-color: #4FE695;   /* Lighter shade */
}
```

**Secondary Button (e.g., "Cancel", "Start Fresh"):**
```python
QPushButton#secondary_button {
    background-color: #2D3340;   /* BG_TERTIARY */
    border: 2px solid #3D4450;   /* BG_BORDER */
    border-radius: 6px;
    color: #F5F5F5;              /* TEXT_PRIMARY */
    padding: 8px 16px;
    min-width: 110px;
}

QPushButton#secondary_button:hover {
    border-color: #F5F5F5;       /* Highlight border */
}
```

---

## Testing

### Manual Testing

Run the demo script to visually verify all dialogs:

```bash
python test_dialogs_demo.py
```

This launches a window with buttons to test each dialog variant:
1. Game Over (Standard)
2. Game Over (Timed)
3. Resume Session
4. Unsaved Changes Warning

### Import Verification

```bash
python -c "from src.ui.dialogs import GameOverDialog, ResumeSessionDialog, UnsavedWarningDialog"
```

### Usage in Application

All dialogs are modal and blocking:

```python
# Example: Check for unsaved changes on quit
def closeEvent(self, event):
    if self.has_unsaved_changes:
        dialog = UnsavedWarningDialog(parent=self)
        dialog.exec()  # Blocking call

        result = dialog.get_result()
        if result == UnsavedWarningResult.SAVE_AND_QUIT:
            self.save_session()
            event.accept()
        elif result == UnsavedWarningResult.DONT_SAVE:
            event.accept()
        else:  # CANCEL
            event.ignore()
    else:
        event.accept()
```

---

## Code Standards

All dialog implementations follow project coding standards:

### Python 3.13 Syntax
- Modern type annotations (`dict[str, int]` not `Dict[str, int]`)
- No legacy `from typing import Optional, List`
- Type hints on all functions and methods
- Enum for result types

### LBYL (Look Before You Leap)
- No exception-based control flow
- All checks performed before actions

### Pathlib Usage
- Not applicable (dialogs are UI-only, no file I/O)

### PyQt6 Patterns
- Proper signal/slot connections
- Object names for stylesheet targeting
- Layouts (no absolute positioning)
- Modal dialogs with `exec()`

### Documentation
- Module-level docstrings
- Class docstrings with examples
- Method docstrings with Args/Returns
- Inline comments for non-obvious logic

---

## File Structure

```
src/ui/dialogs/
├── __init__.py              # Package exports
├── game_over.py             # GameOverDialog + GameOverResult
├── resume_session.py        # ResumeSessionDialog + ResumeSessionResult + SessionDetails
└── unsaved_warning.py       # UnsavedWarningDialog + UnsavedWarningResult

test_dialogs_demo.py         # Visual testing demo
```

---

## Integration Points

### Main Window Integration

These dialogs will be integrated with the main window in the following scenarios:

1. **GameOverDialog:**
   - Triggered when `ScoreState` detects game victory
   - Triggered when user clicks "Time Expired" button (timed games)
   - Result determines whether to enter review mode or continue editing

2. **ResumeSessionDialog:**
   - Triggered in `SetupDialog` when session file exists for selected video
   - Shown before main window opens
   - Result determines whether to load session or start fresh

3. **UnsavedWarningDialog:**
   - Triggered in `MainWindow.closeEvent()` when `dirty` flag is set
   - Triggered when loading new video with unsaved changes
   - Result determines whether to save, discard, or cancel

### Session Manager Integration

```python
# Pseudocode for session detection
def load_video(video_path: Path) -> None:
    session = session_manager.find_session(video_path)

    if session is not None:
        details = SessionDetails(
            video_name=video_path.name,
            rally_count=len(session.rallies),
            current_score=session.current_score,
            last_position=session.last_position,
            game_type=session.game_type,
            victory_rule=session.victory_rule
        )

        dialog = ResumeSessionDialog(details, parent=self)
        dialog.exec()

        if dialog.get_result() == ResumeSessionResult.RESUME:
            self.restore_session(session)
        else:
            session_manager.clear_session(video_path)
```

---

## Future Enhancements

Potential improvements for future phases:

1. **Animation:**
   - Fade-in animation on dialog open (per UI_SPEC.md Section 7.4)
   - Scale-in animation for modal backdrop

2. **Accessibility:**
   - Tab navigation order optimization
   - Screen reader support with ARIA labels
   - Keyboard shortcuts (Alt+S for Save, etc.)

3. **Internationalization:**
   - Extract all strings to translation files
   - Support for multiple languages

4. **Customization:**
   - User preference for default action (some users prefer "Don't Save" as default)
   - Configurable warnings (e.g., "Don't show this again")

---

## Related Documentation

- **UI Specification:** `docs/UI_SPEC.md` Section 6 (Modal Dialogs)
- **Color System:** `src/ui/styles/colors.py`
- **Typography System:** `src/ui/styles/fonts.py`
- **Button Widgets:** `src/ui/widgets/rally_button.py` (reference implementation)

---

**Status:** All three system dialogs implemented and tested.
**Next Steps:** Implement intervention dialogs (Edit Score, Force Side-Out, Add Comment).
