# Intervention Dialogs Implementation Summary

**Date:** 2026-01-14
**Phase:** 4.1 - Main Window UI Components

## Overview

This document summarizes the implementation of the three intervention dialogs for the Pickleball Video Editor. These dialogs allow users to manually correct or annotate the automatically tracked game state during video editing.

## Files Created

### 1. Edit Score Dialog
**File:** `/home/rkalluri/Documents/source/pickleball_editing/src/ui/dialogs/edit_score.py`

**Purpose:** Manually correct rally scores when automatic tracking fails.

**Key Features:**
- Current score displayed as read-only
- New score input with format validation
- Singles format: X-Y (two numbers)
- Doubles format: X-Y-Z (three numbers)
- Optional comment field for documentation
- Apply button disabled until valid score entered
- Inline error messages for invalid formats

**Result Object:**
```python
@dataclass
class EditScoreResult:
    new_score: str
    comment: str | None
```

**Usage Example:**
```python
dialog = EditScoreDialog(
    current_score="7-5-2",
    is_doubles=True,
    parent=main_window
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        rally_manager.update_score(result.new_score, result.comment)
```

---

### 2. Force Side-Out Dialog
**File:** `/home/rkalluri/Documents/source/pickleball_editing/src/ui/dialogs/force_sideout.py`

**Purpose:** Manually force a side-out when serving state tracking fails.

**Key Features:**
- Displays current server information
- Shows preview of server after side-out
- Optional score correction field
- Optional comment field
- Score validation (if provided)
- Visual highlighting of next server state

**Result Object:**
```python
@dataclass
class ForceSideOutResult:
    new_score: str | None  # None means keep current
    comment: str | None
```

**Usage Example:**
```python
dialog = ForceSideOutDialog(
    current_server_info="Team 1 - Server 2",
    next_server_info="Team 2 - Server 1",
    current_score="7-5-2",
    is_doubles=True,
    parent=main_window
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        rally_manager.force_sideout(result.new_score, result.comment)
```

---

### 3. Add Comment Dialog
**File:** `/home/rkalluri/Documents/source/pickleball_editing/src/ui/dialogs/add_comment.py`

**Purpose:** Add commentary markers at specific video timestamps.

**Key Features:**
- Timestamp displayed in MM:SS.ss format (read-only)
- Required comment text field
- Duration spinner (1-60 seconds, default: 5)
- Add button disabled until comment entered
- Useful for marking exceptional plays or referee calls

**Result Object:**
```python
@dataclass
class AddCommentResult:
    timestamp: float
    comment: str
    duration: float
```

**Usage Example:**
```python
current_time = player.get_position()

dialog = AddCommentDialog(
    timestamp=current_time,
    parent=main_window
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        comment_manager.add_comment(
            result.timestamp,
            result.comment,
            result.duration
        )
```

---

### 4. Package Exports
**File:** `/home/rkalluri/Documents/source/pickleball_editing/src/ui/dialogs/__init__.py`

Updated to export all intervention dialogs and their result classes:

```python
from src.ui.dialogs.edit_score import EditScoreDialog, EditScoreResult
from src.ui.dialogs.force_sideout import ForceSideOutDialog, ForceSideOutResult
from src.ui.dialogs.add_comment import AddCommentDialog, AddCommentResult
```

---

## Design System Compliance

All dialogs follow the "Court Green" design system as specified in `docs/UI_SPEC.md`:

### Colors
- Background: `#252A33` (BG_SECONDARY)
- Borders: `#3D4450` (BG_BORDER)
- Text: `#F5F5F5` (TEXT_PRIMARY)
- Secondary text: `#9E9E9E` (TEXT_SECONDARY)
- Primary action: `#3DDC84` (PRIMARY_ACTION)
- Error text: `#EF5350` (Coral Red)

### Typography
- Dialog titles: IBM Plex Sans, 18px, SemiBold
- Body text: IBM Plex Sans, 14px, Regular
- Timestamps/scores: JetBrains Mono, 16px, Medium (tabular figures)
- Secondary text: 12px

### Spacing
- Dialog padding: 24px
- Section spacing: 24px (SPACE_LG)
- Element spacing: 16px (SPACE_MD)
- Border radius: 12px (RADIUS_XL)

### Button Styling
- **Cancel button:** Secondary style (border only)
- **Primary button:** Accent style (green background, glow on hover)
- **Disabled state:** Opacity 0.4, gray border, cursor: not-allowed

### Validation Feedback
- Inline error messages below invalid fields
- Red text with warning icon (⚠)
- Primary button disabled until validation passes
- Real-time validation on text change

---

## Testing

### 1. Smoke Test
**File:** `/home/rkalluri/Documents/source/pickleball_editing/test_dialogs.py`

Basic instantiation test that verifies:
- All dialogs can be imported
- All dialogs can be instantiated with typical parameters
- Result dataclasses are properly structured

**Run:**
```bash
python test_dialogs.py
```

**Result:** ✓ All tests passed

---

### 2. Visual Test
**File:** `/home/rkalluri/Documents/source/pickleball_editing/test_dialogs_visual.py`

Interactive test application with buttons to launch each dialog. Useful for:
- Visual inspection of layout and styling
- Manual testing of validation logic
- Verifying result objects are correctly constructed
- Testing dialog flow and user experience

**Run:**
```bash
python test_dialogs_visual.py
```

**Features:**
- Test launcher window with buttons for each dialog
- Result display showing parsed result objects
- Shows both accepted and cancelled states

---

## Code Quality

### Python 3.13 Modern Syntax
- Type hints using modern syntax (no `typing` module imports)
- `str | None` instead of `Optional[str]`
- `list[str]` instead of `List[str]`

### LBYL Pattern (Look Before You Leap)
- All validation checks happen before actions
- No exceptions used for control flow
- Defensive programming throughout

### Documentation
- Comprehensive module docstrings
- Detailed class and method docstrings
- Usage examples in class docstrings
- Inline comments for non-obvious logic

### Separation of Concerns
- UI setup in `_setup_ui()`
- Styling in `_apply_styles()`
- Signal connections in `_connect_signals()`
- Validation logic in dedicated methods

---

## Integration Points

These dialogs are designed to integrate with the main window via button clicks:

### Intervention Toolbar Buttons (Main Window)

```python
# Edit Score button
edit_score_btn.clicked.connect(self._on_edit_score)

def _on_edit_score(self):
    dialog = EditScoreDialog(
        current_score=self.rally_manager.get_current_score(),
        is_doubles=self.game_config.is_doubles,
        parent=self
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        result = dialog.get_result()
        if result:
            self.rally_manager.edit_score(result.new_score, result.comment)
            self._update_ui()
```

### Similar patterns for:
- Force Side-Out button → `ForceSideOutDialog`
- Add Comment button → `AddCommentDialog`

---

## Validation Rules

### Edit Score Dialog
- **Singles:** Must match pattern `X-Y` (two integers separated by dash)
- **Doubles:** Must match pattern `X-Y-Z` (three integers separated by dashes)
- **Apply button:** Disabled until valid score entered
- **Error display:** Inline message below input field

### Force Side-Out Dialog
- **Score field:** Optional (blank = keep current)
- **If provided:** Same validation as Edit Score
- **Apply button:** Always enabled (even with blank score)

### Add Comment Dialog
- **Comment field:** Required (must be non-empty)
- **Duration:** 1-60 seconds (spinner enforces range)
- **Add button:** Disabled until comment entered

---

## File Structure

```
src/ui/dialogs/
├── __init__.py              # Package exports (updated)
├── edit_score.py            # Edit Score Dialog (NEW)
├── force_sideout.py         # Force Side-Out Dialog (NEW)
├── add_comment.py           # Add Comment Dialog (NEW)
├── game_over.py             # Existing system dialog
├── resume_session.py        # Existing system dialog
└── unsaved_warning.py       # Existing system dialog
```

---

## Next Steps

These dialogs are ready for integration into the main window UI. The next phase involves:

1. **Main Window Integration:**
   - Add intervention toolbar buttons
   - Connect dialog launches to button clicks
   - Implement handlers for dialog results

2. **RallyManager Integration:**
   - Add methods to handle score corrections
   - Add methods to handle forced side-outs
   - Add comment tracking to rally data

3. **Session Persistence:**
   - Serialize comments with rallies
   - Include intervention metadata in session JSON

4. **Export Integration:**
   - Generate subtitle overlays for comments
   - Include intervention history in debug export

---

## Design Decisions

### 1. Dataclass Results
Used dataclasses for result objects instead of dictionaries for:
- Type safety
- IDE autocomplete
- Self-documenting code
- Easier refactoring

### 2. Optional Comment Fields
Comments are optional in Edit Score and Force Side-Out because:
- Not every correction needs documentation
- Reduces friction for quick fixes
- Still available for audit trail when needed

### 3. Read-Only Timestamp Display
Add Comment dialog shows timestamp as read-only because:
- Timestamp is captured from current video position
- Prevents accidental modification
- Users can seek to different position if needed

### 4. Arrow Visual (→)
Used in Edit Score and Force Side-Out to show transformation:
- Clear before/after visual
- Matches mental model of correction flow
- Consistent with Final Review mode design

### 5. Inline Validation
Real-time validation as user types because:
- Immediate feedback reduces errors
- Clear what format is expected
- Prevents submission of invalid data

---

## Known Limitations

1. **Score validation is format-only:** Does not check if score is logically valid (e.g., 99-0-3)
2. **No undo for dialog actions:** Once applied, changes must be undone through main Undo button
3. **Single comment per timestamp:** Cannot add multiple comments at same position
4. **Fixed duration increments:** Duration spinner uses 1-second increments (no 0.5s option)

These limitations are acceptable for MVP and can be addressed in future iterations if needed.

---

## References

- **UI Specification:** `docs/UI_SPEC.md` (Section 6: Modal Dialogs)
- **Design System:** `docs/UI_SPEC.md` (Section 2: Design System)
- **Color Palette:** `src/ui/styles/colors.py`
- **Typography:** `src/ui/styles/fonts.py`
- **Python Standards:** `.claude/skills/python313/`

---

**Implementation Status:** ✓ Complete
**Tests:** ✓ Passing
**Code Review:** Ready
