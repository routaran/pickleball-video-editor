# PlaybackControls Widget

**File**: `/home/rkalluri/Documents/source/pickleball_editing/src/ui/widgets/playback_controls.py`

## Overview

The `PlaybackControls` widget provides a complete video playback control interface with transport buttons, speed toggles, and time display. It follows the "Court Green" design system and uses monospace fonts for timecodes to prevent layout shifts.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  |◀   ◀◀   [     ▶     ]   ▶▶   ▶|      0.5x  1x  2x    03:45/09:15    │
│ -5s   -1s    play        +1s  +5s          speed           timecode     │
└──────────────────────────────────────────────────────────────────────────┘
```

## Components

### Transport Controls (Left)
- **|◀ Skip Back 5s**: Jump backward 5 seconds
- **◀◀ Skip Back 1s**: Jump backward 1 second
- **▶/❚❚ Play/Pause**: Toggle playback (larger, central button)
- **▶▶ Skip Forward 1s**: Jump forward 1 second
- **▶| Skip Forward 5s**: Jump forward 5 seconds

### Speed Toggles (Center)
- **0.5x**: Half speed playback
- **1x**: Normal speed (default)
- **2x**: Double speed playback

Speed buttons use `QButtonGroup` with exclusive selection (radio-button behavior). The selected button has a filled accent background.

### Time Display (Right)
- **Format**: `MM:SS / MM:SS` (current / total)
- **Font**: JetBrains Mono 16px (tabular figures)
- **Appearance**: Inset style with tertiary background

## API

### Constructor

```python
PlaybackControls(parent: QWidget | None = None)
```

### Public Methods

#### `set_playing(playing: bool) -> None`
Update play/pause button icon based on playback state.

```python
controls.set_playing(True)   # Shows pause icon (❚❚)
controls.set_playing(False)  # Shows play icon (▶)
```

#### `set_time(current_seconds: float, total_seconds: float) -> None`
Update time display with current position and total duration.

```python
controls.set_time(125.0, 555.0)  # Displays "02:05 / 09:15"
```

#### `set_speed(speed: float) -> None`
Update speed toggle selection programmatically (does not emit signal).

```python
controls.set_speed(0.5)  # Selects 0.5x button
controls.set_speed(1.0)  # Selects 1x button
controls.set_speed(2.0)  # Selects 2x button
```

#### `get_speed() -> float`
Get current playback speed selection.

```python
current_speed = controls.get_speed()  # Returns 0.5, 1.0, or 2.0
```

### Signals

All signals are defined as `pyqtSignal()` and should be connected to video player actions:

#### Navigation Signals
```python
skip_back_5s = pyqtSignal()      # |◀ button clicked
skip_back_1s = pyqtSignal()      # ◀◀ button clicked
play_pause = pyqtSignal()        # ▶/❚❚ button clicked
skip_forward_1s = pyqtSignal()   # ▶▶ button clicked
skip_forward_5s = pyqtSignal()   # ▶| button clicked
```

#### Speed Signal
```python
speed_changed = pyqtSignal(float)  # Emits 0.5, 1.0, or 2.0
```

## Usage Example

```python
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt
from src.ui.widgets import PlaybackControls
from src.video.player import VideoWidget

class VideoEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create widgets
        self.player = VideoWidget()
        self.controls = PlaybackControls()

        # Connect navigation signals
        self.controls.play_pause.connect(self.player.toggle_pause)
        self.controls.skip_back_5s.connect(lambda: self.player.seek(-5.0, absolute=False))
        self.controls.skip_back_1s.connect(lambda: self.player.seek(-1.0, absolute=False))
        self.controls.skip_forward_1s.connect(lambda: self.player.seek(1.0, absolute=False))
        self.controls.skip_forward_5s.connect(lambda: self.player.seek(5.0, absolute=False))

        # Connect speed control
        self.controls.speed_changed.connect(self.player.set_speed)

        # Update UI from player state
        self.player.position_changed.connect(self._update_time)
        self.player.playing_changed.connect(self.controls.set_playing)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.player)
        layout.addWidget(self.controls)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _update_time(self, position: float) -> None:
        """Update time display when player position changes."""
        duration = self.player.get_property('duration') or 0.0
        self.controls.set_time(position, duration)
```

**Note**: For global keyboard shortcuts (Space, Left/Right arrows), implement them in the main window's `keyPressEvent()` method. See the **Keyboard Shortcuts** section below for details.

## Design System

The widget follows the "Court Green" design system from `docs/UI_SPEC.md`:

### Colors
- **Background**: `BG_SECONDARY` (#252A33) - Elevated surface
- **Buttons**: `BG_TERTIARY` (#2D3340) - Card surface
- **Border**: `BG_BORDER` (#3D4450) - Subtle edges
- **Text**: `TEXT_PRIMARY` (#F5F5F5) - Off white
- **Accent**: `TEXT_ACCENT` (#3DDC84) - Pickle green for active states

### Typography
- **Time Display**: JetBrains Mono 16px (tabular figures)
- **Button Text**: System default 14-16px

### Spacing
- **Container padding**: 16px vertical, 8px horizontal
- **Button spacing**: 8px between buttons
- **Section spacing**: 24px between control groups

### Border Radius
- All buttons and containers: 6px (`RADIUS_MD`)

## Testing

### Unit Tests
Run automated tests to verify functionality:

```bash
python test_playback_controls_unit.py
```

Tests cover:
- Time formatting (`_format_time()`)
- API methods (`set_playing`, `set_time`, `set_speed`, `get_speed`)
- Signal emissions (all navigation and speed signals)
- Exclusive button selection (speed toggles)

### Interactive Test
Launch interactive test window:

```bash
python test_playback_controls.py
```

Features:
- Simulated playback with position updates
- All transport controls functional
- Speed control affects simulated playback rate
- Console logging of events

## Helper Functions

### `_format_time(seconds: float) -> str`
Formats seconds as `MM:SS` string.

```python
_format_time(0.0)      # "00:00"
_format_time(65.5)     # "01:05"
_format_time(3725.8)   # "62:05"
```

## Implementation Notes

1. **Monospace Time Display**: Uses `Fonts.timestamp()` with tabular figures to prevent layout shifts when numbers change (e.g., "7:59" → "8:00").

2. **Exclusive Speed Selection**: Uses `QButtonGroup` with `setExclusive(True)` to ensure only one speed button is selected at a time.

3. **Signal Blocking**: The `set_speed()` method blocks signals during programmatic updates to prevent recursive emission.

4. **Unicode Icons**: Uses Unicode characters (|◀, ◀◀, ▶, ❚❚, ▶▶, ▶|) for transport controls to avoid font dependencies.

5. **Tooltips**: All buttons have descriptive tooltips for better UX.

6. **No Auto-Focus**: Buttons in `PlaybackControls` do not have special focus handling. In `MainWindow`, they are set to `Qt.FocusPolicy.NoFocus` to prevent interfering with global keyboard shortcuts. This is a parent-level concern, not handled by the widget itself.

## Keyboard Shortcuts

Global keyboard shortcuts are implemented in `MainWindow` (not in the `PlaybackControls` widget itself):

### Video Playback
- **Space**: Pause/unpause video
- **Left Arrow**: Seek backward 5 seconds
- **Right Arrow**: Seek forward 5 seconds

### Rally Marking
- **C**: Rally Start (when enabled)
- **S**: Server Wins (when enabled)
- **R**: Receiver Wins (when enabled)
- **U**: Undo (when enabled, also pauses video)

### Implementation Details

1. **Global Scope**: Shortcuts are handled in `MainWindow.keyPressEvent()` to work regardless of which widget has focus
2. **No Focus Stealing**: All buttons use `Qt.FocusPolicy.NoFocus` so they don't steal keyboard focus
3. **MPV Input Disabled**: MPV's built-in keyboard bindings are disabled via `input-default-bindings=no`
4. **Conditional Actions**: Rally shortcuts (C/S/R/U) only trigger if the corresponding button is enabled
5. **Review Mode**: Shortcuts are disabled when in Review Mode (allows text editing in review widgets)
6. **No Auto-Pause**: Rally marking actions (C/S/R) do not auto-pause video (only Undo pauses)

## Future Enhancements

Potential improvements for future phases:

1. **Volume Control**: Add volume slider/buttons
2. **Frame-Accurate Seek**: Add frame-by-frame navigation buttons (e.g., , and . keys)
3. **Custom Speed**: Allow user to input arbitrary speed values
4. **Loop Mode**: Add toggle for loop playback
5. **Playback Rate Display**: Show actual playback rate including audio pitch correction status

## Related Files

- **Widget Implementation**: `src/ui/widgets/playback_controls.py`
- **Keyboard Shortcuts**: `src/ui/main_window.py` (see `keyPressEvent()` method)
- **Unit Tests**: `test_playback_controls_unit.py`
- **Interactive Test**: `test_playback_controls.py`
- **Video Player**: `src/video/player.py` (VideoWidget with MPV)
- **Design Spec**: `docs/UI_SPEC.md` (Section 2: Design System)
- **Fonts**: `src/ui/styles/fonts.py`
- **Colors**: `src/ui/styles/colors.py`
