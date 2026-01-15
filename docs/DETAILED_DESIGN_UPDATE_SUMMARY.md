# DETAILED_DESIGN.md Update Summary

**Date:** 2026-01-14

## Overview

Updated the Detailed Design Document to reflect recent architectural changes and implementation decisions for the Main Window, Video Player, and Rally Manager components.

---

## Changes Made

### 1. Rally Timing Padding (Section 1.0 - NEW)

**Added comprehensive documentation of timing constants:**

- **START_PADDING:** Changed from -0.5s to **-1.0s**
  - Rally cut now begins **1 second before** the marked start point
  - Captures server preparation, stance, and serve motion

- **END_PADDING:** Remains at **+1.0s**
  - Rally cut ends **1 second after** the marked end point
  - Captures follow-through and immediate reaction

**Included:**
- Visual timeline example showing padding application
- Rationale for padding values
- Implementation location reference

**Updated References:**
- UC-05: Mark Rally Start (step 4)
- UC-06: Mark Rally End (step 4)
- Section 3.3: RallyManager class diagram

---

### 2. Main Window Architecture (Section 3.5 - NEW)

**Added comprehensive class diagram and documentation for:**

#### MainWindow
- Lifecycle methods: `__init__()`, `showEvent()`, `keyPressEvent()`, `closeEvent()`
- Rally management methods
- UI update methods
- **Key Pattern:** Deferred video loading in `showEvent()`

#### _VideoContainer
- Purpose: Proper resize handling for embedded MPV
- `resizeEvent()` implementation
- Aspect ratio maintenance

**Architecture Notes Added:**
1. **Deferred Video Loading**
   - Why: Ensures valid WinId before MPV embedding
   - How: Load triggered in `MainWindow.showEvent()`
   - Prevents race condition with X11/XCB handles

2. **Global Keyboard Shortcuts**
   - `MainWindow.keyPressEvent()` handles Space, Left, Right
   - All rally buttons have `Qt.FocusPolicy.NoFocus`
   - Prevents buttons from stealing keyboard input

3. **Video Container Pattern**
   - Wraps VideoWidget for proper resize handling
   - Isolates video widget from layout changes
   - Maintains proper embedding on window resize

4. **MPV Keyboard Handling**
   - MPV keyboard bindings disabled
   - All input handled by Qt event system
   - Ensures predictable keyboard behavior

---

### 3. Video Player Architecture (Section 3.6 - ENHANCED)

**Expanded VideoWidget documentation:**

#### New Attributes
- `player: mpv.MPV | None` - Initially None until shown
- `video_path: str | None` - Deferred video path
- `_player_ready: bool` - Initialization state flag

#### New Lifecycle Methods
- `showEvent()` - Creates MPV player when widget is shown
- `_initialize_player()` - MPV instance creation with embedding config
- `_on_property_change()` - MPV property observer callback

#### Implementation Notes Added
1. **Deferred MPV Initialization**
   - Player is None until `showEvent()`
   - Ensures valid WinId before embedding
   - Prevents "invalid WinId" errors

2. **X11/XCB Forced Mode**
   - `vo='gpu'` and `gpu-context='x11'`
   - Ensures X11 embedding on Wayland
   - Provides reliable embedding behavior

3. **MPV Keyboard Bindings Disabled**
   - `input-default-bindings=no`
   - `input-vo-keyboard=no`
   - Qt handles all keyboard events

4. **Property Observers**
   - `observe_property()` for time-pos, duration
   - Callbacks emit Qt signals
   - Enables UI updates from MPV state changes

---

### 4. Architecture Patterns (Section 6 - NEW)

**Added comprehensive section documenting architectural patterns:**

#### 6.1 Widget Lifecycle Pattern
- **Problem:** Invalid WinId at widget creation
- **Solution:** Deferred initialization in `showEvent()`
- Code examples for VideoWidget and MainWindow

#### 6.2 Keyboard Input Handling Pattern
- **Problem:** Buttons stealing focus and keyboard input
- **Solution:** Global `keyPressEvent()` + `NoFocus` policy
- MPV keyboard bindings disabled
- Code examples showing implementation

#### 6.3 Video Container Resize Pattern
- **Problem:** Embedded MPV doesn't resize properly
- **Solution:** Container widget with `resizeEvent()`
- Code examples for `_VideoContainer` and `VideoWidget`

#### 6.4 MPV Embedding Configuration
- X11/XCB forced mode configuration
- Property observers setup
- Why X11 mode is required (Wayland compatibility)

#### 6.5 Summary Table
- Quick reference of all patterns
- Problem/solution pairs
- Implementation details

---

## Document Structure Changes

### New Sections
1. **Section 1.0** - Timing Constants and Padding
2. **Section 3.5** - Main Window Architecture (was 3.5 UI Widget Classes)
3. **Section 3.6** - UI Widget Classes (renumbered from 3.5)
4. **Section 6** - Architecture Patterns and Implementation Details

### Updated Sections
- **UC-05** - Rally start padding updated to -1.0s
- **UC-06** - Rally end padding clarified as +1.0s
- **Section 3.3** - RallyManager padding constants updated

---

## Key Architectural Decisions Documented

| Decision | Rationale | Impact |
|----------|-----------|--------|
| START_PADDING = -1.0s | Capture full serve motion | Better rally context in cuts |
| Deferred MPV init | Valid WinId requirement | Reliable video embedding |
| Global keyPressEvent | Consistent playback control | Better UX |
| NoFocus button policy | Prevent focus stealing | Keyboard shortcuts always work |
| X11/XCB forced mode | Wayland compatibility | Works on all desktop environments |
| Disabled MPV bindings | Qt owns all input | Predictable behavior |
| _VideoContainer | Proper resize handling | Smooth window resize |

---

## Files Modified

- `/home/rkalluri/Documents/source/pickleball_editing/docs/DETAILED_DESIGN.md`

## Lines Changed

- Added: ~200 lines
- Modified: ~10 lines
- Total sections added: 5

---

## Next Steps

1. Update any implementation code that references old padding values
2. Ensure all documentation cross-references are correct
3. Consider adding diagrams for the lifecycle patterns (future enhancement)
4. Update TESTING.md to include tests for deferred initialization
