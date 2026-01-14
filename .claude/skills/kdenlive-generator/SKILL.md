---
name: kdenlive-generator
description: Generates Kdenlive project files (.kdenlive) with video cuts and subtitles. Use when creating video editing projects, generating MLT XML, or building timelines with cuts and score overlays.
allowed-tools: Read, Write, Bash
context: fork
agent: kdenlive-generator
---

# Kdenlive Project File Generator

Generate valid Kdenlive/MLT XML project files with video cuts and subtitle tracks.

## Usage

```bash
python .claude/skills/kdenlive-generator/scripts/generate_from_template.py \
  <template.kdenlive> <config.json> <output.kdenlive>
```

**Template:** `.claude/skills/kdenlive-generator/templates/base_template.kdenlive`

## Config Format

### Basic (segment-based subtitles)
```json
{
    "video_path": "path/to/video.mp4",
    "segments": [
        {"in": 1800, "out": 50773, "subtitle": "Team 1 vs Team 2", "subtitle_duration": 5.0}
    ]
}
```

### Advanced (independent subtitles)
```json
{
    "video_path": "path/to/video.mp4",
    "segments": [
        {"in": 1800, "out": 2700},
        {"in": 3000, "out": 3780}
    ],
    "subtitles": [
        {"start": 0, "end": 5, "text": "Team 1 vs Team 2"},
        {"start": 5, "end": 15, "text": "0-0-2"},
        {"start": 15, "end": 28, "text": "0-0-1"}
    ]
}
```

## Output Files

1. `project_name.kdenlive` - MLT XML project file
2. `project_name.kdenlive.ass` - ASS subtitle file

## Key Features

- **A/V Grouping**: Generates AVSplit groups to link audio/video clips
- **ASS Subtitles**: Uses ASS format with relative paths (Kdenlive's native format)
- **Multiple Segments**: Supports cutting and keeping multiple video sections
- **Independent Subtitles**: Subtitle timing can be separate from segment boundaries

## Frame/Time Conversion

For 60fps video:
- 1 second = 60 frames
- 30 seconds = 1800 frames

For detailed XML templates, see [templates.md](templates.md).
