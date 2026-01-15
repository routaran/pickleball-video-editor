# Review Mode Integration - Implementation Summary

## Overview

This document describes the integration of `ReviewModeWidget` with `MainWindow` to enable final review and adjustment of rally timings before generating Kdenlive output.

## Architecture

### Mode Switching

The MainWindow supports two mutually exclusive modes:

1. **Editing Mode** (default)
   - Rally controls panel visible
   - Toolbar panel visible
   - User marks rallies in real-time

2. **Review Mode**
   - Rally controls panel hidden
   - Toolbar panel hidden
   - ReviewModeWidget visible
   - User adjusts timings, scores, and navigates rallies

### State Variables

```python
# In MainWindow.__init__()
self._review_widget: ReviewModeWidget | None = None  # Lazy-created
self._in_review_mode = False  # Current mode flag
self._rally_playback_timer: QTimer | None = None  # For play rally feature
```

### Panel References

Rally controls and toolbar are stored as instance variables to enable show/hide:

```python
self.rally_controls_panel = self._create_rally_controls()
self.toolbar_panel = self._create_toolbar()
```

## Key Methods

### enter_review_mode()

**Triggered by:** Final Review button click

**Actions:**
1. Hide rally controls panel
2. Hide toolbar panel
3. Create ReviewModeWidget if not exists (lazy initialization)
4. Insert review widget into main layout at index 2 (after playback controls)
5. Connect all review widget signals
6. Populate review widget with rallies from `rally_manager`
7. Pass actual video fps for accurate time display
8. Show review widget
9. Set `_in_review_mode = True`
10. Show toast notification

**Signal Connections:**
- `rally_changed` → `_on_review_rally_changed`
- `timing_adjusted` → `_on_review_timing_adjusted`
- `score_changed` → `_on_review_score_changed`
- `play_rally_requested` → `_on_review_play_rally`
- `exit_requested` → `exit_review_mode`
- `generate_requested` → `_on_review_generate`

### exit_review_mode()

**Triggered by:** Exit Review button in ReviewModeWidget

**Actions:**
1. Hide review widget (keeps it in layout for next entry)
2. Show rally controls panel
3. Show toolbar panel
4. Set `_in_review_mode = False`
5. Show toast notification

**Note:** Review widget is not destroyed, allowing fast re-entry to review mode.

## Signal Handlers

### _on_review_rally_changed(index: int)

**Purpose:** Navigate to a different rally in review mode

**Implementation:**
1. Validate index range
2. Get rally from rally_manager
3. Convert start_frame to seconds using video_fps
4. Seek video to rally start (absolute seek)
5. Pause video
6. Show OSD with rally info

**Video Interaction:**
```python
start_seconds = rally.start_frame / self.video_fps
self.video_widget.seek(start_seconds, absolute=True)
self.video_widget.pause()
```

### _on_review_timing_adjusted(index: int, which: str, delta: float)

**Purpose:** Adjust rally start or end time

**Parameters:**
- `index`: Rally index (0-based)
- `which`: "start" or "end"
- `delta`: Time change in seconds (positive = later, negative = earlier)

**Implementation:**
1. Validate index range
2. Call `rally_manager.update_rally_timing()` with appropriate deltas
3. Mark session as dirty
4. Show OSD feedback

**RallyManager Integration:**
```python
if which == "start":
    rally = self.rally_manager.update_rally_timing(
        index=index,
        start_delta=delta,
        end_delta=0.0
    )
elif which == "end":
    rally = self.rally_manager.update_rally_timing(
        index=index,
        start_delta=0.0,
        end_delta=delta
    )
```

**Frame Conversion:** RallyManager handles conversion from time delta to frame delta internally using its fps setting.

### _on_review_score_changed(index: int, new_score: str, cascade: bool)

**Purpose:** Update rally score with optional cascade to later rallies

**Parameters:**
- `index`: Rally index (0-based)
- `new_score`: New score string (e.g., "5-3-1")
- `cascade`: If True, recalculate all subsequent rally scores

**Implementation:**

**Without Cascade:**
1. Update single rally's `score_at_start`
2. Show success toast

**With Cascade:**
1. Parse `new_score` and set as starting point in `score_state`
2. Iterate through rallies from `index` to end
3. For each rally:
   - Update `score_at_start` with current score state
   - Apply winner to score state (server_wins or receiver_wins)
4. Refresh review widget with updated rallies
5. Show success toast with count of affected rallies

**Error Handling:**
- Invalid score format: Show error toast, do not update
- Empty new_score: Silently ignore

**Score State Machine Integration:**
```python
self.score_state.set_score(new_score)
for i in range(index, self.rally_manager.get_rally_count()):
    rally = self.rally_manager.get_rally(i)
    if i > index:
        rally.score_at_start = self.score_state.get_score_string()

    if rally.winner == "server":
        self.score_state.server_wins()
    elif rally.winner == "receiver":
        self.score_state.receiver_wins()
```

### _on_review_play_rally(index: int)

**Purpose:** Play video from rally start to end, auto-pausing at end

**Implementation:**
1. Validate index range
2. Get rally from rally_manager
3. Convert start_frame and end_frame to seconds
4. Calculate duration in milliseconds
5. Seek to rally start
6. Start playback
7. Create QTimer to pause at end (single-shot)
8. Show OSD feedback

**Timer Management:**
```python
# Stop and clean up any existing timer
if self._rally_playback_timer is not None:
    self._rally_playback_timer.stop()
    self._rally_playback_timer.deleteLater()

# Create new timer
self._rally_playback_timer = QTimer(self)
self._rally_playback_timer.setSingleShot(True)
self._rally_playback_timer.timeout.connect(lambda: self.video_widget.pause())
self._rally_playback_timer.start(duration_ms)
```

**Precision:** Timer is approximate (±50ms). For frame-accurate playback, could use MPV property observers, but current approach is sufficient for review purposes.

### _on_review_generate()

**Purpose:** Generate Kdenlive project file

**Current Status:** Placeholder stub

**Planned Implementation:**
1. Call KdenliveGenerator with rally segments
2. Show file save dialog
3. Write .kdenlive XML file
4. Show success dialog with file path
5. Optionally launch Kdenlive with the project

**Placeholder:**
```python
ToastManager.show_info(
    self,
    "Kdenlive generation not yet implemented",
    duration_ms=3000
)
```

## ReviewModeWidget Updates

### FPS Support

Added `_fps` attribute to ReviewModeWidget for accurate time display:

```python
def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self._fps = 60.0  # Default, updated by set_rallies()
```

Updated `set_rallies()` signature:
```python
def set_rallies(self, rallies: list[Rally], fps: float = 60.0) -> None:
    self._rallies = rallies
    self._fps = fps
    # ...
```

Updated `set_current_rally()` to use actual fps:
```python
start_seconds = rally.start_frame / self._fps
end_seconds = rally.end_frame / self._fps
self._timing_widget.set_times(start_seconds, end_seconds)
```

## Layout Structure

When review mode is active, the layout looks like:

```
QMainWindow
└── QWidget (central widget)
    └── QVBoxLayout (main_layout)
        ├── [0] video_area (QWidget) - ALWAYS VISIBLE
        ├── [1] playback_controls (PlaybackControls) - ALWAYS VISIBLE
        ├── [2] review_widget (ReviewModeWidget) - VISIBLE IN REVIEW MODE
        ├── [3] rally_controls_panel (QFrame) - HIDDEN IN REVIEW MODE
        └── [4] toolbar_panel (QFrame) - HIDDEN IN REVIEW MODE
```

**Note:** Review widget is inserted at index 2 (between playback controls and rally controls) to maintain logical flow.

## Data Flow

### Entering Review Mode

```
User clicks "Final Review"
    ↓
_on_final_review()
    ↓
enter_review_mode()
    ↓
Hide rally_controls_panel, toolbar_panel
    ↓
Create ReviewModeWidget (if needed)
    ↓
Connect signals
    ↓
rally_manager.get_rallies()
    ↓
review_widget.set_rallies(rallies, fps=video_fps)
    ↓
Show review_widget
    ↓
Set _in_review_mode = True
```

### Adjusting Timing

```
User clicks +/-0.1s button
    ↓
TimingControlWidget.timing_adjusted signal
    ↓
ReviewModeWidget._on_timing_adjusted
    ↓
ReviewModeWidget.timing_adjusted signal
    ↓
MainWindow._on_review_timing_adjusted
    ↓
rally_manager.update_rally_timing()
    ↓
Rally frames updated in-place
    ↓
Set _dirty = True
    ↓
Show OSD feedback
```

### Cascading Score Changes

```
User edits score, enables cascade, presses Enter
    ↓
ScoreEditWidget.score_changed signal
    ↓
ReviewModeWidget._on_score_changed
    ↓
ReviewModeWidget.score_changed signal
    ↓
MainWindow._on_review_score_changed
    ↓
rally_manager.update_rally_score(index, new_score, cascade=False)
    ↓
score_state.set_score(new_score)
    ↓
FOR each rally from index to end:
    rally.score_at_start = score_state.get_score_string()
    score_state.apply_winner(rally.winner)
    ↓
review_widget.set_rallies(updated_rallies, fps)
    ↓
review_widget.set_current_rally(index)
    ↓
Set _dirty = True
    ↓
Show success toast
```

## Edge Cases Handled

### 1. No Rallies to Review
- Entering review mode with 0 rallies shows warning toast
- Review mode is not entered

### 2. Invalid Rally Index
- All signal handlers validate index before accessing rally_manager
- Out-of-range indices are silently ignored

### 3. Empty Score Input
- Empty new_score string is ignored (no update)
- Prevents clearing scores accidentally

### 4. Invalid Score Format
- Try/except catches ValueError from score_state.set_score()
- Shows error toast, does not update rallies

### 5. Multiple Play Rally Calls
- Existing timer is stopped and deleted before creating new one
- Prevents multiple timers running simultaneously

### 6. Mode Switching with Unsaved Changes
- `_dirty` flag is set for all modifications (timing, score)
- Existing closeEvent() handler checks dirty flag
- User is prompted to save before closing

## Testing Recommendations

### Manual Testing Checklist

1. **Mode Switching**
   - [ ] Enter review mode with rallies
   - [ ] Enter review mode with 0 rallies (should warn)
   - [ ] Exit review mode
   - [ ] Re-enter review mode (should preserve state)
   - [ ] Verify panels hide/show correctly

2. **Rally Navigation**
   - [ ] Click rally cards
   - [ ] Use Previous/Next buttons
   - [ ] Verify video seeks to rally start
   - [ ] Verify video pauses on navigation

3. **Timing Adjustment**
   - [ ] Adjust start time earlier (-0.1s)
   - [ ] Adjust start time later (+0.1s)
   - [ ] Adjust end time earlier (-0.1s)
   - [ ] Adjust end time later (+0.1s)
   - [ ] Verify OSD feedback
   - [ ] Verify duration updates

4. **Score Editing**
   - [ ] Change score without cascade
   - [ ] Change score with cascade
   - [ ] Verify subsequent rallies update
   - [ ] Try invalid score format
   - [ ] Try empty score

5. **Play Rally**
   - [ ] Play short rally (< 5s)
   - [ ] Play long rally (> 10s)
   - [ ] Verify auto-pause at end
   - [ ] Start new play before first finishes

6. **Persistence**
   - [ ] Make timing adjustments
   - [ ] Exit review mode
   - [ ] Save session
   - [ ] Close and reload
   - [ ] Verify adjustments are preserved

### Unit Test Coverage

**Recommended tests:**
- `test_enter_review_mode()`: Verify state transitions
- `test_exit_review_mode()`: Verify state restoration
- `test_rally_navigation()`: Mock video_widget.seek calls
- `test_timing_adjustment()`: Verify rally_manager updates
- `test_score_cascade()`: Verify score state machine replay
- `test_play_rally_timer()`: Verify QTimer setup/cleanup

## Future Enhancements

### 1. Keyboard Shortcuts
Add keyboard navigation in review mode:
- Left/Right arrows: Previous/Next rally
- Space: Play/Pause current rally
- J/L: Adjust timing by -0.1s/+0.1s

### 2. Visual Timeline
Add a visual timeline showing all rallies with:
- Miniature preview thumbnails
- Rally duration bars
- Score labels

### 3. Undo/Redo in Review Mode
Extend undo stack to include:
- Timing adjustments
- Score edits
- Allow reverting changes made in review mode

### 4. Batch Operations
Add ability to:
- Adjust all rally timings by a fixed delta
- Renumber rallies after deletion
- Merge adjacent rallies

### 5. Export Options
Add multiple export formats:
- Kdenlive project (primary)
- ASS subtitle file
- CSV rally list
- JSON segments for other tools

## Files Modified

### src/ui/main_window.py
- Added `ReviewModeWidget` import
- Added `QTimer` import
- Added instance variables: `_review_widget`, `_in_review_mode`, `_rally_playback_timer`
- Changed `rally_controls` → `self.rally_controls_panel`
- Changed `toolbar` → `self.toolbar_panel`
- Modified `_on_final_review()` to call `enter_review_mode()`
- Added `enter_review_mode()` method
- Added `exit_review_mode()` method
- Added `_on_review_rally_changed()` handler
- Added `_on_review_timing_adjusted()` handler
- Added `_on_review_score_changed()` handler
- Added `_on_review_play_rally()` handler
- Added `_on_review_generate()` placeholder

### src/ui/review_mode.py
- Added `_fps` instance variable
- Updated `set_rallies()` to accept `fps` parameter
- Updated `set_current_rally()` to use `self._fps` instead of hardcoded 30.0

### test_review_integration.py (new)
- Created test script with instructions
- Provides manual testing workflow

## Summary

The review mode integration provides a seamless way to:

1. **Navigate** between rallies with visual feedback
2. **Adjust** rally timings with frame-accurate precision
3. **Edit** scores with automatic cascade recalculation
4. **Preview** individual rallies with auto-pause
5. **Prepare** for Kdenlive generation (placeholder)

The implementation follows LBYL principles, uses modern Python 3.13 syntax, and integrates cleanly with existing MainWindow state management.

**Status:** ✅ Complete (pending Kdenlive generator implementation)

**Next Steps:**
1. Run `test_review_integration.py` for manual testing
2. Implement `_on_review_generate()` with KdenliveGenerator
3. Add keyboard shortcuts for improved UX
4. Write unit tests for signal handlers
