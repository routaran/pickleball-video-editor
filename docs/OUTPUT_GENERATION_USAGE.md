# Output Generation Module - Usage Guide

This document provides comprehensive guidance on using the output generation module for creating Kdenlive project files and ASS subtitles from rally segments.

## Module Overview

The output generation module (`src/output/`) provides two main components:

1. **SubtitleGenerator** - Generates ASS (Advanced SubStation Alpha) subtitle files
2. **KdenliveGenerator** - Generates Kdenlive MLT XML project files

Both classes work with rally segments from `RallyManager.to_segments()`.

---

## SubtitleGenerator

### Purpose

Generates ASS (Advanced SubStation Alpha) subtitle files that display scores for each rally in the edited video. ASS format is Kdenlive's native subtitle format and provides better styling support than SRT. The subtitles are synchronized with the output timeline (rallies placed back-to-back), not the original source video.

### Basic Usage

```python
from src.output.subtitle_generator import SubtitleGenerator
from pathlib import Path

# Get segments from RallyManager
segments = rally_manager.to_segments()
# segments = [
#     {"in": 100, "out": 500, "score": "0-0-2"},
#     {"in": 800, "out": 1200, "score": "1-0-2"},
# ]

fps = 60.0
output_path = Path("~/Videos/pickleball/game1_scores.ass").expanduser()

# Generate and write ASS file
ass_path = SubtitleGenerator.write_ass(segments, fps, output_path)
print(f"ASS file created: {ass_path}")
```

### API Reference

#### `frames_to_ass_time(frame: int, fps: float) -> str`

Convert a frame number to ASS timestamp format.

**Parameters:**
- `frame` (int): Frame number (0-based)
- `fps` (float): Video frames per second

**Returns:**
- `str`: Timestamp in `H:MM:SS.cc` format (centiseconds, note period separator)

**Example:**
```python
timestamp = SubtitleGenerator.frames_to_ass_time(330, 60.0)
# "0:00:05.50"
```

#### `generate_ass(segments: list[dict], fps: float) -> str`

Generate complete ASS file content from rally segments.

**Parameters:**
- `segments` (list[dict]): Rally segments with "in", "out", "score" keys
- `fps` (float): Video frames per second

**Returns:**
- `str`: Complete ASS file content with proper header and events

**Example:**
```python
segments = [
    {"in": 0, "out": 300, "score": "0-0-2"},
    {"in": 500, "out": 800, "score": "1-0-2"},
]

ass_content = SubtitleGenerator.generate_ass(segments, 60.0)
print(ass_content)
# [Script Info]
# ScriptType: v4.00+
# ...
# [Events]
# Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
# Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,0-0-2
# Dialogue: 0,0:00:05.01,0:00:10.01,Default,,0,0,0,,1-0-2
```

#### `write_ass(segments: list[dict], fps: float, output_path: Path | str) -> Path`

Generate and write ASS file to disk.

**Parameters:**
- `segments` (list[dict]): Rally segments
- `fps` (float): Video frames per second
- `output_path` (Path | str): Output file path

**Returns:**
- `Path`: Path to the written file

**Raises:**
- `ValueError`: If fps is non-positive or segments are invalid
- `OSError`: If file cannot be written

**Example:**
```python
from pathlib import Path

output_path = Path("~/Videos/game_scores.ass")
result = SubtitleGenerator.write_ass(segments, 60.0, output_path)
# Creates parent directories if needed
```

### Important Notes

1. **Cumulative Timeline**: The ASS timestamps are based on the output timeline (rallies back-to-back), not source video timestamps.

2. **ASS Format**:
   - Uses period (`.`) as centisecond separator
   - Includes proper header with [Script Info] and [V4+ Styles] sections
   - Default style: White text, black outline, centered at bottom
   - Compatible with Kdenlive's native subtitle support

3. **Kdenlive Integration**: ASS format is Kdenlive's native subtitle format and provides better rendering and styling support than SRT.

4. **Encoding**: Always uses UTF-8 encoding with BOM for proper character handling.

5. **Empty Scores**: Segments without scores are skipped in the output.

---

## KdenliveGenerator

### Purpose

Generates complete Kdenlive MLT XML project files with:
- Sequential rally clips on the timeline
- ASS subtitle overlay (Kdenlive's native format)
- Proper audio/video track structure with AVSplit groups for linking
- All metadata for Kdenlive 25.x compatibility

### Basic Usage

```python
from src.output.kdenlive_generator import KdenliveGenerator
from pathlib import Path

# Initialize generator
generator = KdenliveGenerator(
    video_path="/path/to/source_video.mp4",
    segments=rally_manager.to_segments(),
    fps=60.0,
    resolution=(1920, 1080),
    output_dir=Path("~/Videos/pickleball")
)

# Generate project files
kdenlive_path, srt_path = generator.generate()

print(f"Kdenlive project: {kdenlive_path}")
print(f"Subtitle file: {srt_path}")
```

### API Reference

#### Constructor: `__init__(...)`

```python
KdenliveGenerator(
    video_path: str | Path,
    segments: list[dict[str, Any]],
    fps: float,
    resolution: tuple[int, int] = (1920, 1080),
    output_dir: Path | None = None
)
```

**Parameters:**
- `video_path` (str | Path): Absolute path to source video file
- `segments` (list[dict]): Rally segments from RallyManager.to_segments()
- `fps` (float): Video frames per second
- `resolution` (tuple[int, int]): Video resolution (width, height)
- `output_dir` (Path | None): Output directory (default: `~/Videos/pickleball/`)

**Raises:**
- `ValueError`: If fps is non-positive or resolution is invalid
- `FileNotFoundError`: If video_path doesn't exist

**Example:**
```python
gen = KdenliveGenerator(
    video_path="/home/user/videos/rally_game.mp4",
    segments=segments,
    fps=60.0,
    resolution=(1920, 1080),
    output_dir=Path("~/Videos/pickleball")
)
```

#### `generate() -> tuple[Path, Path]`

Generate Kdenlive project and ASS subtitle files.

**Returns:**
- `tuple[Path, Path]`: (kdenlive_path, ass_path)

**Output Files:**
1. `{video_name}_rallies.kdenlive` - Kdenlive project file
2. `{video_name}_rallies.kdenlive.ass` - ASS subtitle file (linked to project)

**Raises:**
- `ValueError`: If segments are invalid or video cannot be probed
- `OSError`: If files cannot be written

**Example:**
```python
kdenlive_path, ass_path = generator.generate()

# Files created:
# ~/Videos/pickleball/rally_game_rallies.kdenlive
# ~/Videos/pickleball/rally_game_rallies.kdenlive.ass
```

#### `frames_to_timecode(frame: int) -> str`

Convert frame to MLT timecode format.

**Parameters:**
- `frame` (int): Frame number

**Returns:**
- `str`: MLT timecode (HH:MM:SS.mmm) - note period separator

**Example:**
```python
timecode = generator.frames_to_timecode(330)
# "00:00:05.500"
```

### Output Structure

The generated Kdenlive project contains:

1. **Profile Element**: Video resolution, fps, aspect ratio
2. **Producers/Chains**: Source video references (3 chains for different tracks)
3. **Playlists**: Empty tracks and content track with rally cuts
4. **Tractors**: Audio and video track groups
5. **AVSplit Groups**: Proper audio/video linking for each clip
6. **Main Sequence**: Combined timeline with all tracks
7. **Subtitle Filter**: ASS overlay applied to main sequence (using Kdenlive's native format)
8. **Main Bin**: Document properties and metadata

### Output Directory

- **Default**: `~/Videos/pickleball/`
- **Custom**: Specified via `output_dir` parameter
- Automatically created if it doesn't exist

### File Naming Convention

```
{video_basename}_rallies.kdenlive
{video_basename}_rallies.kdenlive.ass
```

Example:
- Video: `/home/user/videos/tournament_final.mp4`
- Output: `tournament_final_rallies.kdenlive`, `tournament_final_rallies.kdenlive.ass`

Note: The ASS file uses the `.kdenlive.ass` extension to indicate it's linked to the Kdenlive project.

---

## Integration Example

Complete workflow from session to output:

```python
from pathlib import Path
from src.core.rally_manager import RallyManager
from src.core.session_manager import SessionManager
from src.output.kdenlive_generator import KdenliveGenerator

# Load existing session
session_manager = SessionManager()
session = session_manager.load_session(video_hash="abc123...")

# Create rally manager from session
rally_manager = RallyManager.from_dict(session.to_dict())

# Get segments
segments = rally_manager.to_segments()

# Generate output files
generator = KdenliveGenerator(
    video_path=session.video_path,
    segments=segments,
    fps=rally_manager.fps,
    resolution=(1920, 1080)
)

kdenlive_path, ass_path = generator.generate()

print(f"Project files created:")
print(f"  Kdenlive: {kdenlive_path}")
print(f"  Subtitles: {ass_path}")
print(f"\nYou can now open {kdenlive_path} in Kdenlive for final editing.")
```

---

## Error Handling

### Common Errors

1. **Invalid FPS**
```python
try:
    gen = KdenliveGenerator(video_path, segments, fps=-1)
except ValueError as e:
    print(f"Error: {e}")  # fps must be positive
```

2. **Missing Video File**
```python
try:
    gen = KdenliveGenerator("/nonexistent.mp4", segments, fps=60)
except FileNotFoundError as e:
    print(f"Error: {e}")  # Video file not found
```

3. **Invalid Segments**
```python
try:
    segments = [{"in": 100}]  # Missing "out" field
    ass = SubtitleGenerator.generate_ass(segments, 60)
except ValueError as e:
    print(f"Error: {e}")  # Segment missing 'out' field
```

4. **Video Probe Failure**
```python
try:
    kdenlive_path, srt_path = generator.generate()
except ValueError as e:
    print(f"Error probing video: {e}")
```

### Best Practices

1. **Validate Segments**: Ensure all segments have required fields
```python
def validate_segments(segments: list[dict]) -> bool:
    for seg in segments:
        if "in" not in seg or "out" not in seg or "score" not in seg:
            return False
    return True

if validate_segments(segments):
    generator.generate()
else:
    print("Invalid segments detected")
```

2. **Check Video File**: Verify video exists before initializing
```python
from pathlib import Path

video_path = Path("/path/to/video.mp4")
if not video_path.exists():
    print(f"Video not found: {video_path}")
else:
    gen = KdenliveGenerator(video_path, segments, fps=60)
```

3. **Handle Output Directory Permissions**
```python
output_dir = Path("~/Videos/pickleball").expanduser()
if not output_dir.exists():
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created output directory: {output_dir}")
```

---

## Advanced Usage

### Custom Output Directory

```python
from pathlib import Path

# Use project-specific directory
project_dir = Path("~/Documents/pickleball_projects/tournament_2024")
project_dir.mkdir(parents=True, exist_ok=True)

generator = KdenliveGenerator(
    video_path=video_path,
    segments=segments,
    fps=60.0,
    output_dir=project_dir
)

kdenlive_path, srt_path = generator.generate()
```

### Working with Different Frame Rates

```python
# Variable frame rate video
from src.video.probe import probe_video

video_info = probe_video(video_path)
print(f"Detected FPS: {video_info.fps}")

generator = KdenliveGenerator(
    video_path=video_path,
    segments=segments,
    fps=video_info.fps,  # Use detected FPS
    resolution=(video_info.width, video_info.height)
)
```

### Batch Processing

```python
from pathlib import Path

videos = Path("~/Videos/tournaments").glob("*.mp4")

for video_path in videos:
    # Load session for this video
    session = session_manager.load_session_by_path(str(video_path))

    if session:
        rally_manager = RallyManager.from_dict(session.to_dict())
        segments = rally_manager.to_segments()

        generator = KdenliveGenerator(
            video_path=str(video_path),
            segments=segments,
            fps=rally_manager.fps
        )

        kdenlive_path, ass_path = generator.generate()
        print(f"Generated project for: {video_path.name}")
```

---

## Testing

Run the test suite to verify output generation:

```bash
python test_output_generators.py
```

Expected output:
```
============================================================
Output Generation Module Tests
============================================================

Testing frames_to_ass_time()...
  ✓ Frame 0 @ 60.0fps = 0:00:00.00 (expected: 0:00:00.00)
  ...
  All timestamp conversions passed!

Testing generate_ass()...
  ✓ ASS structure valid
  ✓ Proper header sections ([Script Info], [V4+ Styles], [Events])
  ✓ Timing is cumulative (output timeline)
  ✓ Scores embedded correctly
  ...

Total: 6/6 tests passed
🎉 All tests passed!
```

---

## Dependencies

The output module requires:

- **Python 3.13+**: Modern type syntax
- **pathlib**: File path operations (stdlib)
- **hashlib**: MD5 hashing for Kdenlive cache (stdlib)
- **uuid**: Unique IDs for Kdenlive elements (stdlib)
- **datetime**: Timestamp generation (stdlib)
- **src.video.probe**: Video metadata extraction (ffprobe wrapper)

External dependencies:
- **ffprobe** (from FFmpeg): Video metadata extraction

Install FFmpeg:
```bash
sudo pacman -S ffmpeg  # Manjaro/Arch
```

---

## Related Documentation

- **TECH_STACK.md**: Technical specifications
- **DETAILED_DESIGN.md**: Architecture details
- **SESSION_MANAGER_USAGE.md**: Session persistence
- **Kdenlive Generator Reference**: `.claude/skills/kdenlive-generator/scripts/generate_project.py`

---

## Troubleshooting

### Issue: Generated project won't open in Kdenlive

**Solution**: Verify video file path is absolute and accessible
```python
video_path = Path(video_path).resolve()
generator = KdenliveGenerator(str(video_path), segments, fps)
```

### Issue: Subtitles not displaying

**Solution**: Ensure ASS file is in the same location as the Kdenlive project and uses the correct naming convention (`{video}_rallies.kdenlive.ass`). The file uses UTF-8 encoding with BOM for proper character handling.

### Issue: Timeline duration mismatch

**Solution**: Verify segments are sequential and non-overlapping
```python
for i, seg in enumerate(segments):
    duration = seg["out"] - seg["in"] + 1
    print(f"Segment {i}: {duration} frames")
```

### Issue: ffprobe not found

**Solution**: Install FFmpeg
```bash
sudo pacman -S ffmpeg
which ffprobe  # Verify installation
```

---

## Summary

The output generation module provides a clean, type-safe API for converting rally segments into deliverable formats:

- **SubtitleGenerator**: Create ASS (Advanced SubStation Alpha) files with score overlays using Kdenlive's native subtitle format
- **KdenliveGenerator**: Create complete Kdenlive projects with proper AVSplit groups and subtitle integration

Key improvements in the current implementation:
- ASS format provides better styling and rendering support than SRT
- Native Kdenlive subtitle format integration
- Proper AVSplit groups ensure audio/video clips remain linked
- XML structure updated to match Kdenlive 25.x format

Both classes follow LBYL error handling, use modern Python 3.13 syntax, and integrate seamlessly with the rest of the application.
