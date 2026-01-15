# Final Review Mode Implementation

**File:** `src/ui/review_mode.py`
**Status:** Complete
**Date:** 2026-01-14

## Overview

The Final Review Mode UI provides a comprehensive interface for users to verify and adjust rally timings before generating Kdenlive output. This replaces the Rally Controls and Toolbar sections when activated from the Main Window's "Final Review" button.

## Components

### 1. RallyHeaderWidget

**Purpose:** Display current rally progress and exit control
**Features:**
- Large "FINAL REVIEW MODE" title in accent color
- Rally counter showing "Rally X of Y" (1-based display)
- Exit Review button on the right
- Green accent border styling

**Signals:**
- `exit_requested()`: User clicked Exit Review button

**Methods:**
- `set_rally(current: int, total: int)`: Update displayed rally count

### 2. TimingControlWidget

**Purpose:** Adjust rally start/end times with precision
**Features:**
- Start time display with -0.1s and +0.1s buttons
- End time display with -0.1s and +0.1s buttons
- Duration display (read-only, calculated)
- Monospace font for all time displays (MM:SS.s format)

**Signals:**
- `timing_adjusted(field: str, delta: float)`: Timing adjusted
  - `field`: "start" or "end"
  - `delta`: Change in seconds (0.1 or -0.1)

**Methods:**
- `set_times(start_seconds: float, end_seconds: float)`: Set displayed times

**Implementation Details:**
- Uses `_format_time()` helper for consistent MM:SS.s formatting
- Prevents negative start times
- Ensures end time >= start time
- Auto-calculates and displays duration

### 3. ScoreEditWidget

**Purpose:** Edit rally score with optional cascading
**Features:**
- Current score display (read-only, in gray box)
- Visual arrow (→) indicator
- New score input field
- "Cascade to later rallies" checkbox

**Signals:**
- `score_changed(new_score: str, cascade: bool)`: Score input changed

**Methods:**
- `set_current_score(score: str)`: Set displayed current score
- `get_new_score() -> str`: Get entered new score
- `get_cascade() -> bool`: Get cascade checkbox state

**Styling:**
- Current score in muted gray to indicate read-only
- New score input with focus highlight
- Custom checkbox styling matching theme

### 4. RallyCardWidget

**Purpose:** Individual rally card for the rally list
**Features:**
- Rally number (large, centered)
- Score at start (small, monospace)
- Selection state with green border + glow
- Hover effect
- Click to select

**Signals:**
- `clicked()`: Card was clicked

**Methods:**
- `set_selected(selected: bool)`: Set selection state

**Styling:**
- Normal: Gray background, subtle border
- Hover: Darker background, green border
- Selected: Green border (2px), glow effect

**Dimensions:**
- Fixed size: 100px × 60px

### 5. RallyListWidget

**Purpose:** Horizontal scrollable grid of rally cards
**Features:**
- Grid layout (6 cards per row)
- Horizontal scroll for overflow
- Current rally highlighted
- Click any card to navigate
- Section title: "RALLY LIST (click to navigate)"

**Signals:**
- `rally_selected(rally_index: int)`: Rally card clicked (0-based index)

**Methods:**
- `set_rallies(rallies: list[Rally])`: Populate with rally data
- `set_current_rally(index: int)`: Update selection state

**Implementation:**
- Uses QScrollArea with custom scrollbar styling
- QGridLayout with 6-column grid
- Auto-scrolls to keep selected rally visible

### 6. ReviewModeWidget (Main Container)

**Purpose:** Compose all review components into single interface
**Layout:**
```
┌─────────────────────────────────────┐
│ RallyHeaderWidget                   │ (Exit button)
├─────────────────────────────────────┤
│ TimingControlWidget                 │ (Start/End adjustments)
├─────────────────────────────────────┤
│ ScoreEditWidget                     │ (Score editing)
├─────────────────────────────────────┤
│ RallyListWidget                     │ (Rally cards grid)
├─────────────────────────────────────┤
│ Navigation Controls                 │ (Prev/Play/Next)
├─────────────────────────────────────┤
│ Generate Section                    │ (Big green button)
└─────────────────────────────────────┘
```

**Signals:**
- `rally_changed(int)`: Current rally index changed
- `timing_adjusted(int, str, float)`: Rally timing adjusted
  - rally_idx, field ("start"|"end"), delta
- `score_changed(int, str, bool)`: Rally score changed
  - rally_idx, new_score, cascade
- `exit_requested()`: Exit review mode
- `generate_requested()`: Generate Kdenlive project
- `play_rally_requested(int)`: Play specified rally
- `navigate_previous()`: Navigate to previous rally
- `navigate_next()`: Navigate to next rally

**Methods:**
- `set_rallies(rallies: list[Rally])`: Populate all rallies
- `set_current_rally(index: int)`: Update current rally display
- `get_current_rally_index() -> int`: Get current index
- `navigate_to_previous()`: Navigate to previous
- `navigate_to_next()`: Navigate to next

**Navigation Controls:**
- "◀ Previous" - Previous rally
- "▶ Play Rally" - Play current rally
- "Next ▶" - Next rally

**Generate Section:**
- Shows validation summary ("✓ Ready to generate output")
- Large "GENERATE KDENLIVE PROJECT" button
- Green accent styling with glow on hover
- Prominent placement at bottom

## Design Adherence

### Color Scheme
- **Backgrounds:** BG_PRIMARY (#1A1D23), BG_SECONDARY (#252A33), BG_TERTIARY (#2D3340)
- **Borders:** BORDER_COLOR (#3D4450)
- **Accent:** PRIMARY_ACTION (#3DDC84) for highlights
- **Text:** TEXT_PRIMARY (#F5F5F5), TEXT_SECONDARY (#9E9E9E), TEXT_ACCENT (#3DDC84)
- **Glow:** GLOW_GREEN for selected states

### Typography
- **Display Font:** JetBrains Mono (via `Fonts.display()`) for times and scores
- **Body Font:** IBM Plex Sans (via `Fonts.body()`) for labels and buttons
- **Weights:** Bold (700) for scores, Semibold (600) for buttons, Regular (400) for labels
- **Tabular Figures:** Enabled for all numeric displays to prevent layout shift

### Spacing
- **Containers:** SPACE_LG (24px), SPACE_XL (32px)
- **Between elements:** SPACE_MD (16px)
- **Tight gaps:** SPACE_SM (8px)

### Border Radius
- **Buttons:** RADIUS_MD (6px)
- **Panels:** RADIUS_LG (8px)

### Button States
- **Normal:** Tertiary background, border, hover effect
- **Primary (Generate):** Green fill, glow on hover
- **Disabled:** Not implemented yet (add opacity: 0.4 as needed)

## Integration Points

### With MainWindow
When "Final Review" button is clicked in MainWindow:
1. Hide Rally Controls panel
2. Hide Toolbar
3. Show ReviewModeWidget in their place
4. Connect all signals to appropriate handlers

**Expected MainWindow connections:**
```python
self.review_widget.rally_changed.connect(self._on_review_rally_changed)
self.review_widget.timing_adjusted.connect(self._on_review_timing_adjusted)
self.review_widget.score_changed.connect(self._on_review_score_changed)
self.review_widget.exit_requested.connect(self._exit_review_mode)
self.review_widget.generate_requested.connect(self._generate_kdenlive)
self.review_widget.play_rally_requested.connect(self._play_rally)
```

### With VideoWidget (MPV)
- `_on_review_rally_changed(index)`: Seek to rally start frame
- `_play_rally(index)`: Play from rally start to end, then pause

### With RallyManager
- `timing_adjusted`: Update rally start_frame or end_frame
- `score_changed`: Update rally score_at_start (and cascade if checked)

### Frame/Time Conversion
Currently hardcoded to 30fps in `set_current_rally()`:
```python
fps = 30.0  # TODO: Get from video metadata
```

**TODO:** Pass actual FPS from video probe data.

## Helper Functions

### `_format_time(seconds: float) -> str`
Converts seconds to MM:SS.s format.

**Examples:**
- `_format_time(0.0)` → "00:00.0"
- `_format_time(125.7)` → "02:05.7"
- `_format_time(3665.2)` → "61:05.2"

**Implementation:**
```python
minutes = int(seconds // 60)
remaining_seconds = seconds % 60
return f"{minutes:02d}:{remaining_seconds:04.1f}"
```

## Styling Summary

All components use consistent styling:
- Dark backgrounds with subtle borders
- Green accent for active/selected states
- Monospace for all numeric values
- Hover effects on interactive elements
- Custom scrollbar styling

## Testing Recommendations

1. **Unit Tests:**
   - `_format_time()` with edge cases (0, fractional, large values)
   - RallyCardWidget selection state changes
   - TimingControlWidget time bounds (negative, end < start)

2. **Integration Tests:**
   - Load 20+ rallies, verify grid layout
   - Navigate through all rallies
   - Adjust timings and verify signals
   - Edit scores with/without cascade

3. **Visual Tests:**
   - Verify all fonts render correctly
   - Check selected rally glow effect
   - Test horizontal scroll with many rallies
   - Verify hover states on all buttons

4. **Edge Cases:**
   - Empty rally list
   - Single rally
   - Very long rally list (100+)
   - Rally with invalid score format

## Known Limitations

1. **FPS Hardcoded:** Currently assumes 30fps for frame/second conversion
2. **No Validation:** Score input doesn't validate format yet
3. **No Error Display:** Invalid inputs don't show error messages
4. **No Duration Limits:** Timing adjustments don't check video boundaries

## Future Enhancements

1. **Keyboard Navigation:**
   - Arrow keys to navigate rallies
   - Enter to play rally
   - Esc to exit review

2. **Validation Feedback:**
   - Real-time score format validation
   - Visual indicators for invalid times
   - Summary of validation errors

3. **Batch Operations:**
   - Select multiple rallies
   - Bulk timing adjustment
   - Bulk score correction

4. **Export Preview:**
   - Show total output duration
   - Display segment count
   - Preview subtitle text

## File Dependencies

```python
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.core.models import Rally
from src.ui.styles import (
    # Colors
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_BORDER,
    BORDER_COLOR, PRIMARY_ACTION, TEXT_ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, GLOW_GREEN,
    # Spacing & Radius
    SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL,
    RADIUS_MD, RADIUS_LG,
    # Fonts
    Fonts,
)
```

## Code Style Compliance

✅ **Modern Python 3.13 syntax:**
- `list[Rally]` instead of `List[Rally]`
- `str | None` instead of `Optional[str]`
- No `from typing import` imports

✅ **LBYL (Look Before You Leap):**
- Bounds checking before array access
- State validation before operations
- No exception-based control flow

✅ **Type Hints:**
- All methods fully annotated
- Signal parameters documented
- Return types specified

✅ **Docstrings:**
- Module-level docstring
- Class docstrings with purpose
- Method docstrings with Args/Returns
- Signal documentation

✅ **PyQt6 Best Practices:**
- Signals defined at class level
- Slots use @pyqtSlot decorator (where appropriate)
- QSS styling in stylesheets
- Object names set for CSS targeting (where needed)

## Summary

The Final Review Mode implementation is complete and ready for integration with MainWindow. All components follow the design specification, use the Court Green theme consistently, and emit appropriate signals for parent widget handling.

**Next Steps:**
1. Integrate with MainWindow (show/hide on "Final Review" button)
2. Connect signals to RallyManager for data updates
3. Connect video player for rally playback
4. Add score format validation
5. Get actual FPS from video metadata
6. Test with real rally data

**Files Created:**
- `/home/rkalluri/Documents/source/pickleball_editing/src/ui/review_mode.py` (850+ lines)

**Exports:**
```python
__all__ = [
    "RallyHeaderWidget",
    "TimingControlWidget",
    "ScoreEditWidget",
    "RallyCardWidget",
    "RallyListWidget",
    "ReviewModeWidget",
]
```
