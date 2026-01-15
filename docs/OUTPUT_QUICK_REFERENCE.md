# Output Generation - Quick Reference

## Import

```python
from src.output import SubtitleGenerator, KdenliveGenerator
```

## SubtitleGenerator

### Generate SRT from segments
```python
from pathlib import Path

segments = rally_manager.to_segments()
fps = 60.0

# Option 1: Get content as string
srt_content = SubtitleGenerator.generate_srt(segments, fps)

# Option 2: Write directly to file
srt_path = SubtitleGenerator.write_srt(
    segments, 
    fps, 
    Path("~/Videos/pickleball/game_scores.srt")
)
```

### Convert frame to SRT timestamp
```python
timestamp = SubtitleGenerator.frames_to_srt_time(330, 60.0)
# "00:00:05,500"
```

## KdenliveGenerator

### Generate Kdenlive project
```python
from pathlib import Path

generator = KdenliveGenerator(
    video_path="/path/to/video.mp4",
    segments=rally_manager.to_segments(),
    fps=60.0,
    resolution=(1920, 1080),
    output_dir=Path("~/Videos/pickleball")  # Optional
)

kdenlive_path, srt_path = generator.generate()
# Creates:
#   ~/Videos/pickleball/video_rallies.kdenlive
#   ~/Videos/pickleball/video_scores.srt
```

### Convert frame to MLT timecode
```python
timecode = generator.frames_to_timecode(330)
# "00:00:05.500"
```

## Segment Format

Segments from `RallyManager.to_segments()`:
```python
[
    {"in": 100, "out": 500, "score": "0-0-2"},
    {"in": 800, "out": 1200, "score": "1-0-2"},
    {"in": 1500, "out": 2000, "score": "1-1-1"},
]
```

## Complete Workflow

```python
from pathlib import Path
from src.core.rally_manager import RallyManager
from src.output import KdenliveGenerator

# Get segments from rally manager
segments = rally_manager.to_segments()

# Generate output files
generator = KdenliveGenerator(
    video_path="/path/to/video.mp4",
    segments=segments,
    fps=60.0
)

kdenlive_path, srt_path = generator.generate()
print(f"Generated: {kdenlive_path}")
```

## Error Handling

```python
try:
    kdenlive_path, srt_path = generator.generate()
except FileNotFoundError:
    print("Video file not found")
except ValueError as e:
    print(f"Invalid parameters: {e}")
except OSError as e:
    print(f"Cannot write output files: {e}")
```

## Default Output Directory

`~/Videos/pickleball/` (created automatically if needed)

## File Naming

- Kdenlive: `{video_basename}_rallies.kdenlive`
- SRT: `{video_basename}_scores.srt`

Example: `tournament_final.mp4` → `tournament_final_rallies.kdenlive`

## Dependencies

- **FFmpeg** (for ffprobe): `sudo pacman -S ffmpeg`
- Python 3.13+

## Testing

```bash
python test_output_generators.py
```

## See Also

- **OUTPUT_GENERATION_USAGE.md** - Complete usage guide
- **TECH_STACK.md** - Technical specifications
- `.claude/skills/kdenlive-generator/` - Reference implementation
