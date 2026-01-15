# Testing VideoWidget (MPV Player)

## Phase 3.2 Implementation Status

**Status**: COMPLETE

All requirements from TODO.md have been implemented:
- VideoWidget class extending QWidget
- MPV embedding with proper Qt integration
- All playback control methods
- Frame-accurate seeking
- Position/duration signals
- OSD message display

## Prerequisites

### System Requirements

```bash
# Install MPV library (Arch/Manjaro)
sudo pacman -S mpv

# Install python-mpv package
pip install python-mpv
```

### Verify Installation

```bash
# Check MPV is installed
mpv --version

# Check python-mpv can be imported
python -c "import mpv; print('python-mpv OK')"
```

## Critical Integration Requirements

### 1. Qt Platform Backend (X11/XCB)

MPV embedding requires the X11/XCB backend. On Wayland systems, the window IDs are not directly usable by MPV's video output drivers.

**REQUIRED**: Set the environment variable BEFORE any Qt imports:

```bash
# When running tests
QT_QPA_PLATFORM=xcb python src/video/test_player.py video.mp4
```

**In Python code** (main.py demonstrates this):

```python
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"
# MUST be set BEFORE importing PyQt6
```

### 2. Locale Configuration (LC_NUMERIC="C")

MPV requires `LC_NUMERIC="C"` to prevent numeric parsing crashes (segfault). This must be set at multiple stages due to Qt resetting the locale during initialization.

**Stage 1**: Before MPV import (in player.py - automatic)

```python
import os
import locale
import ctypes

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")

# Use ctypes to call C library directly
libc = ctypes.CDLL("libc.so.6")
libc.setlocale.restype = ctypes.c_char_p
libc.setlocale(1, b"C")  # LC_NUMERIC = 1 on Linux
```

**Stage 2**: After QApplication creation (in app.py - automatic)

```python
app = QApplication(sys.argv)

# Qt resets locale during init - must restore
import os
import locale
import ctypes

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")
libc = ctypes.CDLL("libc.so.6")
libc.setlocale.restype = ctypes.c_char_p
libc.setlocale(1, b"C")
```

**Stage 3**: In test scripts (test_player.py demonstrates this)

```python
app = QApplication(sys.argv)

# Restore locale after Qt initialization
import os
import locale

os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")
```

### 3. Keyboard Input Handling

MPV's built-in keyboard bindings are DISABLED. All keyboard input is handled by Qt:

```python
self._player = mpv.MPV(
    wid=str(wid),
    vo="x11",
    input_default_bindings=False,  # Disable MPV keyboard shortcuts
    input_vo_keyboard=False,       # Let Qt handle all keyboard input
    # ... other options
)
```

This allows the application to have full control over keyboard shortcuts without conflicts.

### 4. Deferred Player Creation

The MPV player instance is created AFTER the widget is shown, not during `__init__()`:

```python
class VideoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self._player = None  # Created later
        # Set Qt attributes, initialize state...

    def _create_player(self):
        # Called by load() when first needed
        wid = int(self.winId())  # Window ID must be valid
        self._player = mpv.MPV(wid=str(wid), ...)

    def load(self, path, fps=60.0):
        self._create_player()  # Creates player if needed
        # ...
```

**Why?** The widget must have a valid native window ID before MPV can embed. This is guaranteed after the widget is shown.

**Pattern for using VideoWidget**:

```python
# Create widget
video = VideoWidget()

# Add to layout and show window
layout.addWidget(video)
window.show()

# NOW load video (triggers player creation)
video.load("video.mp4", fps=60.0)
```

## Running the Test Script

### Basic Usage

```bash
# REQUIRED: Use XCB platform
QT_QPA_PLATFORM=xcb python src/video/test_player.py /path/to/video.mp4

# Specify custom FPS (default is 60.0)
QT_QPA_PLATFORM=xcb python src/video/test_player.py /path/to/video.mp4 30.0
```

### Test Controls

The test window provides:
- **Play/Pause**: Toggle playback
- **<< Frame / Frame >>**: Step backward/forward by one frame
- **0.5x / 1.0x / 2.0x**: Change playback speed

### What to Test

1. **Video Loading**: Video should appear in window immediately
2. **Playback Control**: Play/pause should work smoothly
3. **Frame Stepping**: Should advance/rewind exactly one frame
4. **Position Updates**: Label should update ~20 times per second
5. **Duration Detection**: Should print duration when video loads
6. **Speed Control**: Video should play faster/slower as expected
7. **Keyboard Independence**: MPV shortcuts (space, arrow keys) should NOT work - only Qt buttons

## API Reference

### Signals

```python
position_changed = pyqtSignal(float)  # Emits current position in seconds
duration_changed = pyqtSignal(float)  # Emits when duration is known
playback_finished = pyqtSignal()      # Emits when video ends
```

### Methods

```python
# Loading
load(path: str | Path, fps: float = 60.0) -> None

# Playback control
play() -> None
pause() -> None
toggle_pause() -> None

# Seeking
seek(seconds: float, absolute: bool = True) -> None
seek_frame(frame: int) -> None
frame_step() -> None
frame_back_step() -> None

# Speed control
set_speed(speed: float) -> None

# Position queries
get_position() -> float
get_position_frame() -> int
get_duration() -> float

# OSD
show_osd(message: str, duration: float = 2.0) -> None

# Cleanup
cleanup() -> None  # Call before destroying widget
```

### Properties

```python
fps: float           # Frame rate (set via load())
is_paused: bool      # Read-only property
```

## Integration Notes

### Critical Qt/MPV Setup

The widget requires specific Qt attributes to be set before creating the MPV player:

```python
self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
```

These are set automatically in `__init__()`.

### Locale Configuration

The module sets `LC_NUMERIC` to "C" at multiple stages:
1. Before importing mpv (module-level code in player.py)
2. Before creating MPV player instance (_create_player method)

This is handled automatically by the module, but test scripts must also restore the locale after QApplication creation.

### Cleanup

Always call `cleanup()` before destroying the widget:

```python
def closeEvent(self, event):
    self.video_widget.cleanup()
    super().closeEvent(event)
```

The widget's `closeEvent()` handler calls this automatically.

## Known Limitations

1. **Position Timer**: Uses a 50ms timer (20 FPS) for position updates rather than MPV's property observer. This is more reliable in Qt but may have slight latency.

2. **Thread Safety**: All signal emissions go through `QTimer.singleShot(0, ...)` to ensure they happen on the main thread.

3. **Frame Accuracy**: Frame stepping pauses playback. This is MPV's default behavior.

4. **X11 Dependency**: Requires X11/XCB backend. Does not work reliably on pure Wayland (xwayland compatibility layer is OK).

## Troubleshooting

### "Could not initialize video output"

**Problem**: MPV can't create video output.

**Solution**: Check that the widget has a valid window ID before loading:
```python
widget.show()  # Must be shown first
QTimer.singleShot(100, lambda: widget.load(path))  # Load after event loop
```

### Position not updating

**Problem**: `position_changed` signal not emitting.

**Solution**: Ensure video is loaded and playing. The position timer only runs after `load()` is called.

### Import error for mpv

**Problem**: `ModuleNotFoundError: No module named 'mpv'`

**Solution**:
```bash
pip install python-mpv
```

### Segfault or numeric parsing errors

**Problem**: MPV crashes with segmentation fault or decimal parsing errors.

**Cause**: `LC_NUMERIC` is not set to "C". This can happen if:
- Environment variable is not set before running
- QApplication reset the locale
- Test script doesn't restore locale

**Solution**:
```bash
# Set environment variable
export LC_NUMERIC=C
QT_QPA_PLATFORM=xcb python src/video/test_player.py video.mp4

# Or inline
LC_NUMERIC=C QT_QPA_PLATFORM=xcb python src/video/test_player.py video.mp4
```

**In code**: Follow the three-stage pattern shown in "Locale Configuration" above.

### "Invalid winId (0)" error

**Problem**: Widget doesn't have a valid window ID when player is created.

**Cause**: Attempting to create player before widget is shown.

**Solution**: Ensure widget is shown before calling `load()`:
```python
video = VideoWidget()
layout.addWidget(video)
window.show()
# Window is now visible, widget has valid ID
video.load("video.mp4")
```

### Wayland issues

**Problem**: Video doesn't appear or window embedding fails on Wayland.

**Cause**: MPV's X11 video output doesn't work reliably with native Wayland window IDs.

**Solution**: Force X11/XCB backend:
```bash
QT_QPA_PLATFORM=xcb python src/video/test_player.py video.mp4
```

## Test Script Reference (test_player.py)

The test script demonstrates the correct pattern for using VideoWidget:

1. **Platform setup**: Forces XCB before Qt imports
2. **Locale restoration**: Restores LC_NUMERIC after QApplication creation
3. **Widget embedding**: Adds widget to layout, shows window, then loads video
4. **Signal connections**: Demonstrates all three signals
5. **Cleanup handling**: Proper cleanup in closeEvent

**Key code pattern**:

```python
# Create app
app = QApplication(sys.argv)

# Restore locale (Qt resets it)
os.environ["LC_NUMERIC"] = "C"
locale.setlocale(locale.LC_NUMERIC, "C")

# Create window with widget
win = TestWindow()
win.show()

# Load video (triggers deferred player creation)
win.load_video(video_path, fps=fps)

# Run event loop
sys.exit(app.exec())
```

## Next Steps

After verifying the player works:

1. Integrate into main window layout (Phase 3.3)
2. Add keyboard shortcuts for frame stepping (handled by Qt, not MPV)
3. Connect to timeline scrubber
4. Add visual feedback for rally boundaries
