# Output Generation - Quick Reference

## Import

```python
from src.output import (
    SubtitleGenerator,
    KdenliveGenerator,
    FFmpegExporter,
    TrainingDataGenerator,
)
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

kdenlive_path, ass_path = generator.generate()
# Creates:
#   ~/Videos/pickleball/video.kdenlive
#   ~/Videos/pickleball/video.kdenlive.ass
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

kdenlive_path, ass_path = generator.generate()
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

Export basenames are produced by `generate_export_basename()` in
`src.core.models`:

- If the video stem begins with 8 digits (a YYYYMMDD date prefix), the
  basename is `YYYY-MM-DD_{Team1Players}_vs_{Team2Players}` (or
  `YYYY-MM-DD_Highlights` for highlights mode).
- Otherwise the basename falls back to the original video stem.

Output files:
- Kdenlive: `{basename}.kdenlive`
- ASS:      `{basename}.kdenlive.ass`

Example: `20250308_match.mp4` with players Alice/Charlie vs Bob/Dave →
`2025-03-08_AliceCharlie_vs_BobDave.kdenlive`.

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
