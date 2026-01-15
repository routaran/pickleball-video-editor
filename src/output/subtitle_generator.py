"""SRT subtitle generation for Pickleball Video Editor.

This module generates SRT (SubRip Text) subtitle files from rally segments
for display in the output video. Each subtitle displays the score at the
start of each rally.

SRT Format Example:
    1
    00:00:00,000 --> 00:00:05,500
    0-0-2

    2
    00:00:05,500 --> 00:00:12,300
    1-0-2

Timing Notes:
- Input segments use source video frame numbers
- Output timeline is cumulative (rallies placed back-to-back)
- Subtitle timing matches the output timeline, not source video
"""

from pathlib import Path
from typing import Any


__all__ = ["SubtitleGenerator"]


class SubtitleGenerator:
    """Generates SRT subtitle files from rally segments.

    This is a stateless utility class that generates subtitle content
    based on rally segments provided by RallyManager.to_segments().

    The output timeline is cumulative - rallies are placed consecutively
    in the edited output video, so subtitle timestamps reflect this
    edited timeline, not the original source video timestamps.
    """

    @staticmethod
    def frames_to_srt_time(frame: int, fps: float) -> str:
        """Convert frame number to SRT timestamp format (HH:MM:SS,mmm).

        SRT uses comma as the millisecond separator (unlike other formats
        that may use a period).

        Args:
            frame: Frame number (0-based)
            fps: Video frames per second

        Returns:
            SRT formatted timestamp string (e.g., "00:01:23,456")

        Raises:
            ValueError: If fps is non-positive
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        total_seconds = frame / fps
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    @staticmethod
    def generate_srt(segments: list[dict[str, Any]], fps: float) -> str:
        """Generate SRT content from rally segments.

        Creates SRT subtitle content where each segment displays its score
        for the duration of that rally in the output timeline.

        Each segment dict must have:
        - "in": start frame (source video frame number)
        - "out": end frame (source video frame number)
        - "score": score string to display (e.g., "0-0-2", "5-3")

        Note: Output timeline is cumulative. If segment 1 is frames 100-200
        and segment 2 is frames 500-600, in the output:
        - Segment 1 appears at frames 0-100
        - Segment 2 appears at frames 100-200

        Args:
            segments: List of segment dictionaries from RallyManager.to_segments()
            fps: Video frames per second

        Returns:
            Complete SRT file content as string

        Raises:
            ValueError: If fps is non-positive or segments are invalid
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        srt_lines: list[str] = []
        current_output_frame = 0

        for i, seg in enumerate(segments, start=1):
            # Validate segment structure
            if "in" not in seg or "out" not in seg:
                raise ValueError(f"Segment {i} missing 'in' or 'out' field: {seg}")

            in_frame = seg["in"]
            out_frame = seg["out"]
            score = seg.get("score", "")

            # Skip segments without scores (edge case)
            if not score:
                current_output_frame += (out_frame - in_frame + 1)
                continue

            # Calculate segment length and output timeline positions
            segment_length = out_frame - in_frame + 1
            start_time = SubtitleGenerator.frames_to_srt_time(current_output_frame, fps)
            end_time = SubtitleGenerator.frames_to_srt_time(
                current_output_frame + segment_length - 1, fps
            )

            # Add SRT entry (sequence number, timestamp range, text, blank line)
            srt_lines.append(str(i))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(score)
            srt_lines.append("")  # Blank line separator

            current_output_frame += segment_length

        return "\n".join(srt_lines)

    @staticmethod
    def write_srt(
        segments: list[dict[str, Any]],
        fps: float,
        output_path: Path | str
    ) -> Path:
        """Write SRT file to disk.

        Generates SRT content and writes it to the specified path with
        UTF-8 encoding (required for proper subtitle handling).

        Args:
            segments: List of segment dictionaries from RallyManager.to_segments()
            fps: Video frames per second
            output_path: Path to write SRT file

        Returns:
            Path to the written file (as Path object)

        Raises:
            ValueError: If fps is non-positive or segments are invalid
            OSError: If file cannot be written
        """
        output_path = Path(output_path)

        # Generate SRT content
        srt_content = SubtitleGenerator.generate_srt(segments, fps)

        # Ensure parent directory exists
        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file with UTF-8 encoding
        output_path.write_text(srt_content, encoding="utf-8")

        return output_path
