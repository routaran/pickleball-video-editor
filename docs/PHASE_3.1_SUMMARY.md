# Phase 3.1 Summary: Video Probe Utility

**Date:** 2026-01-14
**Status:** Complete
**Git Commit:** 969d07c

---

## Overview

Implemented the video probe utility using ffprobe (part of FFmpeg) to extract comprehensive metadata from video files. This is a critical component for the Pickleball Video Editor, enabling the application to understand video properties before playback and use accurate frame-to-timecode conversions.

---

## Files Created

### 1. `/src/video/probe.py` (330 lines)

Main implementation file containing:

#### Classes
- **`ProbeError(Exception)`**: Custom exception for probe failures
- **`VideoInfo`**: Dataclass containing video metadata
  - Properties: `resolution`, `aspect_ratio`
  - Methods: `to_dict()`, `from_dict()`

#### Functions
- **`probe_video(path: str | Path) -> VideoInfo`**: Main probing function
  - Uses ffprobe subprocess to extract metadata
  - Validates file existence before invoking ffprobe
  - Parses JSON output from ffprobe
  - Extracts: width, height, fps, duration, codec info, bitrate, frame count
  - Handles multiple frame rate formats (fraction and decimal)
  - Comprehensive error handling with clear error messages

- **`frames_to_timecode(frame: int, fps: float) -> str`**: Convert frame number to Kdenlive timecode (HH:MM:SS.mmm)

- **`timecode_to_frames(timecode: str, fps: float) -> int`**: Convert timecode to frame number

- **`_parse_frame_rate(rate_str: str) -> float`**: Internal helper to parse frame rate strings

### 2. `/tests/test_probe.py` (222 lines)

Comprehensive test suite with 17 tests:

#### Test Classes
- **`TestFrameRateParsing`**: Tests for frame rate string parsing
  - Fraction format (60/1)
  - Decimal format (59.94)
  - Zero denominator handling

- **`TestTimecodeConversion`**: Tests for timecode conversion utilities
  - Basic conversions (frame ↔ timecode)
  - Subsecond precision
  - Invalid input handling
  - Roundtrip conversion verification

- **`TestVideoInfo`**: Tests for VideoInfo dataclass
  - Resolution property
  - Aspect ratio calculation
  - Serialization/deserialization

- **`TestProbeVideo`**: Tests for probe_video function
  - Nonexistent file handling
  - Directory vs file validation
  - (Note: Real video testing requires manual execution with actual files)

### 3. `/test_probe_demo.py` (115 lines)

Manual testing script for demonstrating probe functionality:
- Interactive demo showing all extracted metadata
- Timecode conversion examples
- Serialization testing
- Usage instructions for testing with real videos

### 4. Updated Files

- **`src/video/__init__.py`**: Added exports for probe module
- **`requirements.txt`**: Added pytest>=7.4.0
- **`TODO.md`**: Marked Phase 3.1 tasks as complete
- **`tests/test_score_state.py`**: Fixed import path (src_path bug fix)

---

## Design Decisions

### 1. LBYL Pattern
Following the project's coding standards, the implementation uses "Look Before You Leap":
```python
# Check file exists BEFORE subprocess call
if not path.exists():
    raise ProbeError(f"Video file not found: {path}")
```

### 2. Modern Python 3.13 Syntax
No legacy typing imports:
```python
# ✅ Correct
def probe_video(path: str | Path) -> VideoInfo:

# ❌ Wrong (legacy)
from typing import Union
def probe_video(path: Union[str, Path]) -> VideoInfo:
```

### 3. Graceful Degradation
The probe function attempts multiple strategies:
- Try `avg_frame_rate` first, then fall back to `r_frame_rate`
- Try stream-level duration, then fall back to format-level
- Estimate frame count from duration × fps if `nb_frames` unavailable

### 4. Clear Error Messages
All errors provide actionable feedback:
```python
raise ProbeError(
    "ffprobe not found. Please install ffmpeg: sudo pacman -S ffmpeg"
)
```

### 5. Pathlib First
All path operations use `pathlib.Path`, never `os.path`:
```python
path = Path(path)  # Accept str or Path
if not path.exists():  # Use Path methods
```

---

## Testing Results

All 23 tests pass (17 new probe tests + 6 existing core tests):

```
tests/test_probe.py::TestFrameRateParsing::test_parse_fraction_format PASSED
tests/test_probe.py::TestFrameRateParsing::test_parse_decimal_format PASSED
tests/test_probe.py::TestFrameRateParsing::test_parse_zero_denominator PASSED
tests/test_probe.py::TestTimecodeConversion::test_frames_to_timecode_basic PASSED
tests/test_probe.py::TestTimecodeConversion::test_frames_to_timecode_subseconds PASSED
tests/test_probe.py::TestTimecodeConversion::test_frames_to_timecode_invalid_fps PASSED
tests/test_probe.py::TestTimecodeConversion::test_timecode_to_frames_basic PASSED
tests/test_probe.py::TestTimecodeConversion::test_timecode_to_frames_subseconds PASSED
tests/test_probe.py::TestTimecodeConversion::test_timecode_to_frames_invalid_format PASSED
tests/test_probe.py::TestTimecodeConversion::test_timecode_to_frames_invalid_fps PASSED
tests/test_probe.py::TestTimecodeConversion::test_roundtrip_conversion PASSED
tests/test_probe.py::TestVideoInfo::test_resolution_property PASSED
tests/test_probe.py::TestVideoInfo::test_aspect_ratio_property PASSED
tests/test_probe.py::TestVideoInfo::test_aspect_ratio_zero_height PASSED
tests/test_probe.py::TestVideoInfo::test_serialization PASSED
tests/test_probe.py::TestProbeVideo::test_probe_nonexistent_file PASSED
tests/test_probe.py::TestProbeVideo::test_probe_directory PASSED

======================== 23 passed in 0.03s =========================
```

---

## Usage Examples

### Basic Probing
```python
from src.video import probe_video, ProbeError

try:
    info = probe_video("/path/to/video.mp4")
    print(f"Resolution: {info.resolution}")  # "1920x1080"
    print(f"FPS: {info.fps}")                # 60.0
    print(f"Duration: {info.duration}s")     # 120.5
except ProbeError as e:
    print(f"Error: {e}")
```

### Timecode Conversion
```python
from src.video import frames_to_timecode, timecode_to_frames

# Frame to timecode (for Kdenlive XML)
tc = frames_to_timecode(1800, 30.0)  # "00:01:00.000"

# Timecode to frame (for seeking)
frame = timecode_to_frames("00:01:30.500", 30.0)  # 2715
```

### Serialization
```python
# Save to JSON
data = info.to_dict()
with open("video_info.json", "w") as f:
    json.dump(data, f)

# Load from JSON
from src.video import VideoInfo
with open("video_info.json", "r") as f:
    data = json.load(f)
restored = VideoInfo.from_dict(data)
```

---

## Integration Points

This module will be used by:

1. **Setup Dialog (Phase 4.4)**: Probe video on file selection to validate format
2. **Session Manager (Phase 7.1)**: Store VideoInfo in session for consistent frame calculations
3. **Kdenlive Generator (Phase 9.2)**: Use `frames_to_timecode()` for XML timecodes
4. **Main Window (Phase 5)**: Display video metadata in UI
5. **MPV Player Widget (Phase 3.2)**: Validate video before loading

---

## Known Limitations

1. **Real Video Testing**: The automated tests don't include actual video file probing (would require test fixtures). Manual testing with `test_probe_demo.py` is recommended.

2. **Frame Count Accuracy**: For some video formats, `nb_frames` may not be available in metadata. In these cases, we estimate from `duration × fps`, which may be slightly inaccurate for variable frame rate videos.

3. **FFprobe Dependency**: The module assumes ffprobe is installed. On Manjaro/Arch, this is part of the `ffmpeg` package. Error message guides users to install it.

---

## Next Steps

**Phase 3.2: MPV Player Widget** (next in TODO.md)
- Create `src/video/player.py`
- Implement VideoWidget wrapping python-mpv
- Use VideoInfo from probe for frame calculations
- Implement playback controls and seeking

---

## Checklist Summary

All Phase 3.1 tasks completed:
- [x] Create src/video/probe.py
- [x] Implement probe_video() using ffprobe
- [x] Extract fps, duration, resolution
- [x] Extract codec info
- [x] Handle probe errors gracefully
- [x] Write unit tests for video probe
- [x] **GIT CHECKPOINT**: Commit "Add video probe utility" (969d07c)
