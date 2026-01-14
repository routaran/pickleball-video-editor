# SRT Subtitle Format Reference

## Format Structure

SRT (SubRip Text) is a simple text-based subtitle format.

```
SEQUENCE_NUMBER
START_TIME --> END_TIME
SUBTITLE_TEXT

```

Each subtitle entry consists of:
1. **Sequence number**: Integer starting from 1
2. **Timestamps**: Start and end times separated by ` --> `
3. **Text**: One or more lines of text
4. **Blank line**: Separates entries

## Timestamp Format

```
HH:MM:SS,mmm
```

- HH = hours (00-99)
- MM = minutes (00-59)
- SS = seconds (00-59)
- mmm = milliseconds (000-999)

**Important**: Use comma (,) not period (.) for milliseconds separator.

## Example SRT File

```srt
1
00:00:05,000 --> 00:00:15,500
0-0-2

2
00:00:15,500 --> 00:00:28,333
1-0-2

3
00:00:28,333 --> 00:00:45,000
1-0-1

4
00:00:45,000 --> 00:01:02,166
2-0-1
```

## Time Calculations for Edited Video

When generating subtitles for an edited video with cuts, the subtitle times refer to the **output timeline**, not the source video.

### Example Scenario

Source video segments kept:
- Rally 1: source frames 150-450 (10 seconds at 30fps)
- Rally 2: source frames 600-900 (10 seconds at 30fps)
- Rally 3: source frames 1100-1500 (13.3 seconds at 30fps)

Output timeline positions:
- Rally 1: 0:00:00,000 - 0:00:10,000 (score: 0-0-2)
- Rally 2: 0:00:10,000 - 0:00:20,000 (score: 1-0-2)
- Rally 3: 0:00:20,000 - 0:00:33,333 (score: 1-0-1)

### Conversion Functions

```python
def frames_to_srt_time(frames: int, fps: float) -> str:
    """Convert frame number to SRT timestamp format."""
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
```

## Generating SRT for Cut Segments

```python
def generate_srt(segments: list, scores: list, fps: float) -> str:
    """
    Generate SRT content for edited video.

    Args:
        segments: List of (in_frame, out_frame) tuples from source
        scores: List of score strings, one per segment
        fps: Frame rate of the video

    Returns:
        SRT file content as string
    """
    srt_lines = []
    current_output_frame = 0

    for i, ((in_frame, out_frame), score) in enumerate(zip(segments, scores), 1):
        segment_length = out_frame - in_frame + 1

        start_time = frames_to_srt_time(current_output_frame, fps)
        end_time = frames_to_srt_time(current_output_frame + segment_length, fps)

        srt_lines.append(f"{i}")
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(score)
        srt_lines.append("")  # Blank line separator

        current_output_frame += segment_length

    return "\n".join(srt_lines)
```

## Subtitle Positioning (Optional)

SRT supports basic positioning tags (not all players support these):

```srt
1
00:00:05,000 --> 00:00:15,500
{\an8}0-0-2
```

Position codes (`\an#`):
```
7 8 9   (top-left, top-center, top-right)
4 5 6   (middle-left, middle-center, middle-right)
1 2 3   (bottom-left, bottom-center, bottom-right)
```

Default is `\an2` (bottom-center).

## Styling Notes

For Kdenlive's avfilter.subtitles:
- Basic SRT styling tags may not render
- For styled subtitles, use ASS format instead
- Plain text scores like "7-5-2" work reliably

## File Encoding

- Use UTF-8 encoding
- Unix line endings (LF) preferred
- BOM optional but not recommended

## Common Pitfalls

1. **Wrong millisecond separator**: Use comma (,) not period (.)
2. **Missing blank line**: Each entry must end with a blank line
3. **Wrong timeline reference**: Subtitles should match output timeline, not source
4. **Sequence gaps**: Numbers should be consecutive starting from 1
