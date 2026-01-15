# Output Generation Integration Summary

## Overview

This document describes the integration of the output generation module (`src.output`) with the MainWindow's Final Review mode. The integration enables users to generate Kdenlive project files and SRT subtitle files from marked rallies.

## Changes Made

### 1. Import Addition (Line 46)

Added import for `KdenliveGenerator`:

```python
from src.output import KdenliveGenerator
```

This imports the generator class that creates Kdenlive MLT XML project files and companion SRT subtitle files.

### 2. Method Implementation (Lines 1281-1343)

Replaced the placeholder `_on_review_generate()` method with full implementation:

```python
@pyqtSlot()
def _on_review_generate(self) -> None:
    """Handle generate Kdenlive project request.

    Generates Kdenlive project and SRT subtitle files from current rallies.
    """
    # Get segments from rally manager
    segments = self.rally_manager.to_segments()

    # Check if there are segments to export
    if not segments:
        ToastManager.show_warning(
            self,
            "No rallies to export",
            duration_ms=3000
        )
        return

    # Get video resolution from probe
    # We need to re-probe because we only stored fps/duration, not resolution
    try:
        video_info = probe_video(self.config.video_path)
        resolution = (video_info.width, video_info.height)
    except ProbeError:
        # Fall back to default HD resolution if probe fails
        resolution = (1920, 1080)
        ToastManager.show_warning(
            self,
            "Could not detect video resolution, using 1920x1080",
            duration_ms=3000
        )

    # Create generator
    generator = KdenliveGenerator(
        video_path=str(self.config.video_path),
        segments=segments,
        fps=self.video_fps,
        resolution=resolution
    )

    # Generate files
    try:
        kdenlive_path, srt_path = generator.generate()

        # Show success message
        ToastManager.show_success(
            self,
            f"Generated: {kdenlive_path.name}",
            duration_ms=5000
        )

        # Also show in OSD
        self.video_widget.show_osd(
            f"Project saved to {kdenlive_path.parent}",
            duration=4.0
        )

    except Exception as e:
        ToastManager.show_error(
            self,
            f"Generation failed: {e}",
            duration_ms=5000
        )
```

## Implementation Details

### LBYL Pattern

The implementation follows the LBYL (Look Before You Leap) pattern:

1. **Check for segments**: Validates that there are rallies to export before attempting generation
2. **Probe video**: Attempts to get resolution, falls back to default if probe fails
3. **Exception handling**: Catches exceptions at the boundary (generation can fail due to I/O errors)

### Error Handling Strategy

**Graceful degradation:**
- If video probe fails, uses default 1920x1080 resolution and shows warning
- If generation fails, catches exception and shows error toast with details

**User feedback:**
- Toast notifications for all outcomes (warning, success, error)
- OSD overlay shows where files were saved on success

### Resolution Detection

The method re-probes the video to get resolution information. This is necessary because:
- We only store `fps` and `duration` as instance variables in MainWindow
- Resolution is needed for Kdenlive project profile generation
- The probe is lightweight (only reads video metadata, not frames)

**Fallback behavior:**
- If probe fails, defaults to 1920x1080 (Full HD)
- Shows warning toast so user is aware of the assumption
- Generation continues with default resolution

### Generated Files

The `KdenliveGenerator.generate()` method creates two files in `~/Videos/pickleball/`:

1. **`{video_name}_rallies.kdenlive`** - Kdenlive MLT XML project file
2. **`{video_name}_scores.srt`** - SRT subtitle file with scores

Both files are automatically saved to the default output directory (`~/Videos/pickleball/`).

## Data Flow

```
User clicks "Generate" button in Review Mode
    ↓
_on_review_generate() called
    ↓
Get segments from rally_manager.to_segments()
    ↓
LBYL: Check if segments is non-empty
    ↓ (if empty)
    Show warning toast and return
    ↓ (if not empty)
Probe video for resolution
    ↓ (if probe fails)
    Use default 1920x1080, show warning
    ↓
Create KdenliveGenerator instance
    ↓
Call generator.generate()
    ↓ (if success)
    Show success toast + OSD with file path
    ↓ (if exception)
    Catch and show error toast
```

## User Experience

### Success Path

1. User marks rallies in editing mode
2. User enters Final Review mode
3. User adjusts timings/scores as needed
4. User clicks "Generate" button
5. Toast notification appears: "Generated: match_rallies.kdenlive"
6. OSD overlay shows: "Project saved to /home/user/Videos/pickleball"
7. Files are ready to open in Kdenlive

### No Rallies Path

1. User clicks "Generate" without marking any rallies
2. Warning toast appears: "No rallies to export"
3. No files are generated

### Probe Failure Path

1. User clicks "Generate" with marked rallies
2. Video probe fails (rare - corrupt video metadata)
3. Warning toast appears: "Could not detect video resolution, using 1920x1080"
4. Generation continues with default resolution
5. Success toast appears: "Generated: match_rallies.kdenlive"

### Generation Failure Path

1. User clicks "Generate" with marked rallies
2. File generation fails (e.g., disk full, permission error)
3. Error toast appears: "Generation failed: [error details]"
4. No files are created

## Testing

See `test_output_generation.py` for comprehensive unit tests covering:

1. **Normal generation** - Valid rallies, successful generation
2. **No rallies** - Empty segments list, warning shown
3. **Probe failure** - Fallback to default resolution
4. **Generator failure** - Exception handling, error feedback

Run tests:
```bash
python test_output_generation.py
```

## Dependencies

### Modules Used

- `src.output.KdenliveGenerator` - Generates Kdenlive project and SRT files
- `src.video.probe.probe_video` - Extracts video metadata (resolution, fps, duration)
- `src.ui.widgets.ToastManager` - Shows toast notifications
- `src.video.player.VideoWidget` - Shows OSD overlay

### External Dependencies

- `ffprobe` (from FFmpeg) - Required for video probing
- File system access to `~/Videos/pickleball/` directory

## Future Enhancements

### Possible Improvements

1. **Store video resolution**: Cache resolution in MainWindow to avoid re-probing
2. **Custom output directory**: Let user choose where to save files
3. **Auto-open in Kdenlive**: Option to launch Kdenlive with generated project
4. **Progress indication**: Show progress bar for large projects
5. **Preview before generate**: Show estimated file sizes and segment count

### Architecture Notes

The current implementation is minimal and focused. Future enhancements should maintain:
- LBYL pattern for precondition checking
- Exception handling at boundaries
- Clear user feedback for all outcomes
- Separation of concerns (generation logic in `src.output`, UI logic in `MainWindow`)

## Related Files

- `/home/rkalluri/Documents/source/pickleball_editing/src/ui/main_window.py` - MainWindow implementation
- `/home/rkalluri/Documents/source/pickleball_editing/src/output/kdenlive_generator.py` - Kdenlive generator
- `/home/rkalluri/Documents/source/pickleball_editing/src/output/subtitle_generator.py` - SRT generator
- `/home/rkalluri/Documents/source/pickleball_editing/src/core/rally_manager.py` - Rally segment conversion
- `/home/rkalluri/Documents/source/pickleball_editing/test_output_generation.py` - Integration tests

## Summary

The output generation integration is complete and tested. Users can now:

1. Mark rallies in editing mode
2. Enter Final Review mode to adjust timings
3. Click "Generate" to create Kdenlive project and SRT files
4. Receive clear feedback on success or failure

The implementation follows all project coding standards:
- LBYL pattern for precondition checking
- Type hints with modern Python 3.13 syntax
- Exception handling at boundaries
- Comprehensive user feedback
- Unit test coverage
