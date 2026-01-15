# Toast Notification Widget

## Overview

The Toast widget provides non-blocking, temporary feedback messages for user actions. Toasts appear at the top-center of the window, auto-dismiss after 4 seconds, and support four message types with color-coded styling.

## Features

- **Auto-dismiss**: Configurable timeout (default 4 seconds)
- **Smooth animations**: Fade in/out with slide down/up effects
- **Color-coded types**: SUCCESS (green), INFO (blue), WARNING (amber), ERROR (red)
- **Manual dismiss**: Close button for immediate dismissal
- **Court Green theme**: Consistent with app design system

## Usage

### Basic Usage (Recommended)

Use the `ToastManager` convenience methods for simple toast notifications:

```python
from src.ui.widgets import ToastManager

# Success toast
ToastManager.show_success(self, "Rally saved successfully")

# Info toast
ToastManager.show_info(self, "Video loaded: pickleball_match.mp4")

# Warning toast
ToastManager.show_warning(self, "Cannot end rally - no rally in progress")

# Error toast
ToastManager.show_error(self, "Failed to load video file")
```

### Custom Duration

Specify a custom auto-dismiss duration (in milliseconds):

```python
# Show for 6 seconds instead of default 4
ToastManager.show_warning(self, "Large file - processing may take time", duration_ms=6000)

# No auto-dismiss (duration_ms=0)
ToastManager.show_error(self, "Critical error - manual dismiss required", duration_ms=0)
```

### Manual Control

For advanced use cases, create and control Toast instances directly:

```python
from src.ui.widgets import Toast, ToastType

# Create toast
toast = Toast(
    message="Custom message",
    toast_type=ToastType.INFO,
    duration_ms=5000,
    parent=self
)

# Show with animation
toast.show_toast()

# Connect to closed signal
toast.closed.connect(lambda: print("Toast dismissed"))

# Manual dismiss (optional - auto-dismisses after duration)
toast.dismiss()
```

## Toast Types

### SUCCESS
- **Use for**: Successful operations, confirmations
- **Color**: Green (`#3DDC84`)
- **Icon**: ✓
- **Examples**:
  - "Rally saved successfully"
  - "Video exported to Downloads"
  - "Session loaded"

### INFO
- **Use for**: Informational messages, status updates
- **Color**: Blue (`#4FC3F7`)
- **Icon**: ℹ
- **Examples**:
  - "Video loaded: match_2024.mp4"
  - "Processing 45 rallies"
  - "Auto-save enabled"

### WARNING
- **Use for**: Non-critical issues, important notices
- **Color**: Amber (`#FFB300`)
- **Icon**: ⚠
- **Examples**:
  - "Cannot end rally - no rally in progress"
  - "Low disk space"
  - "Video file is large - may take time to load"

### ERROR
- **Use for**: Failures, critical issues
- **Color**: Red (`#EF5350`)
- **Icon**: ✕
- **Examples**:
  - "Failed to load video file"
  - "Cannot save session - permission denied"
  - "Network connection lost"

## Visual Design

### Layout
```
┌─────────────────────────────────────────────────────────────┐
│  ⚠  Cannot end rally - no rally in progress            [×] │
└─────────────────────────────────────────────────────────────┘
 ↑   ↑                                                     ↑
 │   │                                                     │
 │   └─ Message text                                      └─ Dismiss button
 └─ Type icon
```

### Dimensions
- **Width**: 320px (fixed)
- **Height**: 48px (fixed)
- **Position**: Top-center, 16px from top
- **Accent border**: 4px left border (colored by type)

### Animations
- **Enter**: 200ms fade in + slide down from above
- **Exit**: 150ms fade out + slide up

### Typography
- **Icon**: 16pt bold
- **Message**: IBM Plex Sans 11pt
- **Dismiss button**: 16pt bold "×"

## Implementation Details

### Architecture

**Toast** (QFrame)
- Self-contained widget with layout, styling, and animations
- Emits `closed` signal when dismissed
- Handles both auto-dismiss and manual dismiss

**ToastManager** (Static utility class)
- Provides convenience methods for common toast types
- Tracks active toasts for future stacking support
- Handles positioning relative to parent widget

### Stacking (Future Enhancement)

Currently, showing multiple toasts simultaneously will overlay them. The `_active_toasts` list in `ToastManager` is prepared for implementing vertical stacking:

```python
# Future: Stack toasts with 8px spacing
for i, toast in enumerate(ToastManager._active_toasts):
    y_position = 16 + (i * (Toast.TOAST_HEIGHT + 8))
    toast.move(toast.x(), y_position)
```

### Animation Properties

Uses `QPropertyAnimation` on two properties:
1. `windowOpacity`: Fade effect (0.0 to 1.0)
2. `geometry`: Slide effect (position change)

Both animations run simultaneously for smooth appearance.

## Testing

Run the demo script to see all toast types:

```bash
python test_toast_demo.py
```

The demo shows:
- Individual buttons for each toast type
- Auto-sequence button to show all types with timing
- Dark background matching the app theme

## Integration Examples

### Rally Actions

```python
def on_rally_start_clicked(self) -> None:
    """Handle rally start button click."""
    if self.rally_manager.has_active_rally():
        ToastManager.show_warning(self, "Rally already in progress")
        return

    timestamp = self.video_player.get_position()
    self.rally_manager.start_rally(timestamp)
    ToastManager.show_success(self, "Rally started")
```

### Video Loading

```python
def load_video(self, video_path: Path) -> None:
    """Load a video file."""
    if not video_path.exists():
        ToastManager.show_error(self, "Video file not found")
        return

    try:
        self.video_player.load_video(video_path)
        ToastManager.show_info(self, f"Loaded: {video_path.name}")
    except Exception as e:
        ToastManager.show_error(self, f"Failed to load video: {e}")
```

### Session Save

```python
def save_session(self) -> None:
    """Save the current editing session."""
    try:
        self.session_manager.save()
        ToastManager.show_success(self, "Session saved")
    except PermissionError:
        ToastManager.show_error(self, "Cannot save - permission denied")
    except Exception as e:
        ToastManager.show_error(self, f"Save failed: {e}")
```

## Best Practices

1. **Use appropriate types**: Match the toast type to the message severity
2. **Keep messages concise**: Single line, under 60 characters when possible
3. **Don't spam**: Avoid showing multiple toasts for the same action
4. **Longer duration for important messages**: Use 6+ seconds for critical warnings
5. **Test positioning**: Ensure toasts don't cover important UI elements

## Files

- **Implementation**: `/src/ui/widgets/toast.py`
- **Colors**: `/src/ui/styles/colors.py`
- **Demo**: `/test_toast_demo.py`
- **Documentation**: `/docs/TOAST_WIDGET.md` (this file)
