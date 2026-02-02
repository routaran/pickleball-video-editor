"""FFmpeg-based video export with hardware encoding and subtitle overlays.

This module provides direct MP4 generation using ffmpeg with:
- NVENC hardware encoding for performance (with libx264 fallback)
- VFR (variable frame rate) normalization
- ASS subtitle overlays for score display
- Audio/video synchronization fixes
- Game completion video extension using tpad filter
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess

from src.core.models import GameCompletionInfo
from src.output.hardware_detect import get_optimal_config


@dataclass
class FFmpegExporter:
    """Export rally segments to MP4 using ffmpeg with hardware encoding.

    Attributes:
        video_path: Path to source video file
        segments: Rally segments with frame ranges and scores
                  Format: [{"in": frame, "out": frame, "score": str}, ...]
        fps: Source video frame rate
        player_names: Optional player name mapping (for subtitle context)
        game_completion: Optional game completion metadata
    """

    video_path: Path
    segments: list[dict]
    fps: float
    player_names: dict | None
    game_completion: GameCompletionInfo | None

    def generate(self, output_path: Path) -> Path:
        """Generate MP4 directly using ffmpeg.

        Args:
            output_path: Destination path for output MP4

        Returns:
            Path to generated MP4 file

        Raises:
            subprocess.CalledProcessError: If ffmpeg execution fails
            FileNotFoundError: If source video doesn't exist
        """
        # Generate ASS subtitle file with score overlays
        ass_path = self._write_ass_file(output_path)

        try:
            # Execute ffmpeg with hardware encoding
            self._run_ffmpeg(output_path, ass_path)
        finally:
            # Clean up temporary ASS file
            if ass_path.exists():
                ass_path.unlink()

        return output_path

    def _escape_ffmpeg_filter_path(self, path: Path) -> str:
        """Escape path for FFmpeg filter arguments.

        FFmpeg filter syntax requires special handling for paths:
        - Backslashes must be forward slashes (Windows compatibility)
        - Colons must be escaped with \\: (conflicts with filter syntax)
        - Single quotes must be escaped as '\\''
        - Final path must be wrapped in single quotes

        Args:
            path: Path object to escape

        Returns:
            Escaped path string suitable for FFmpeg filter_complex arguments

        Example:
            >>> exporter._escape_ffmpeg_filter_path(Path("C:\\Videos\\file.mp4"))
            "'C\\:/Videos/file.mp4'"
            >>> exporter._escape_ffmpeg_filter_path(Path("/tmp/sub's.ass"))
            "'/tmp/sub'\\''s.ass'"
        """
        path_str = str(path)

        # Normalize backslashes to forward slashes (Windows compatibility)
        path_str = path_str.replace("\\", "/")

        # Escape colons with \\: (conflicts with FFmpeg filter syntax)
        path_str = path_str.replace(":", "\\:")

        # Escape single quotes by ending quote, adding escaped quote, starting new quote
        # This transforms: path's -> path'\''s
        path_str = path_str.replace("'", "'\\''")

        # Wrap entire path in single quotes
        return f"'{path_str}'"

    def _build_filter_complex(self, ass_path: Path) -> tuple[str, str]:
        """Build filter_complex with VFR normalization and A/V sync fixes.

        Constructs ffmpeg filter chain for:
        - Variable frame rate (VFR) normalization to constant frame rate (CFR)
        - ASS subtitle overlay with proper text rendering
        - Audio/video synchronization preservation

        Args:
            ass_path: Path to generated ASS subtitle file

        Returns:
            Tuple of (filter_complex_string, audio_output_label)
            The audio_output_label is "[concata]" normally, or "[paddeda]" if
            game completion extension is active.

        Filter chain structure:
            1. For each segment: fps=fps={fps} (VFR normalization FIRST)
            2. Then trim with time-based values
            3. Then reset PTS for proper concatenation
            4. Concat with interleaved [v0][a0][v1][a1]... pattern
            5. Apply ASS subtitles AFTER concat
        """
        filter_parts: list[str] = []

        # Build filter chains for each segment
        for i, segment in enumerate(self.segments):
            in_frame = segment["in"]
            out_frame = segment["out"]

            # Convert frame numbers to seconds
            start_sec = in_frame / self.fps
            end_sec = out_frame / self.fps

            # Video filter: fps -> trim -> setpts
            # CRITICAL: fps filter FIRST to normalize VFR before trimming
            video_filter = (
                f"[0:v]fps=fps={self.fps},"
                f"trim=start={start_sec:.6f}:end={end_sec:.6f},"
                f"setpts=PTS-STARTPTS[v{i}]"
            )
            filter_parts.append(video_filter)

            # Audio filter: atrim -> asetpts
            # Use explicit [0:a:0] selector (not [0:a])
            audio_filter = (
                f"[0:a:0]atrim=start={start_sec:.6f}:end={end_sec:.6f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
            filter_parts.append(audio_filter)

        # Build concat input list in interleaved order: [v0][a0][v1][a1]...
        concat_inputs = []
        for i in range(len(self.segments)):
            concat_inputs.append(f"[v{i}][a{i}]")

        concat_input_str = "".join(concat_inputs)
        num_segments = len(self.segments)

        # Concat filter with explicit v=1:a=1 output streams
        concat_filter = (
            f"{concat_input_str}concat=n={num_segments}:v=1:a=1[concatv][concata]"
        )
        filter_parts.append(concat_filter)

        # Apply tpad filter if game completion is active (extends video by cloning last frame)
        # This ensures the video extends to show the final score subtitle
        if self.game_completion is not None and self.game_completion.is_completed:
            extension_sec = self.game_completion.extension_seconds
            # tpad clones the last frame for the extension duration
            tpad_filter = f"[concatv]tpad=stop_mode=clone:stop_duration={extension_sec:.6f}[paddedv]"
            filter_parts.append(tpad_filter)
            # Also extend audio with silence using apad
            apad_filter = f"[concata]apad=pad_dur={extension_sec:.6f}[paddeda]"
            filter_parts.append(apad_filter)
            video_for_subtitle = "[paddedv]"
            audio_output_label = "[paddeda]"
        else:
            video_for_subtitle = "[concatv]"
            audio_output_label = "[concata]"

        # Apply ASS subtitles AFTER concat (and tpad if applicable)
        escaped_ass_path = self._escape_ffmpeg_filter_path(ass_path)
        subtitle_filter = f"{video_for_subtitle}ass={escaped_ass_path}[outv]"
        filter_parts.append(subtitle_filter)

        # Join all filter parts with semicolon separators
        return (";".join(filter_parts), audio_output_label)

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS timecode format (H:MM:SS.cc).

        Args:
            seconds: Time in seconds

        Returns:
            ASS timecode string in H:MM:SS.cc format (centiseconds)

        Example:
            >>> exporter._seconds_to_ass_time(5.5)
            "0:00:05.50"
            >>> exporter._seconds_to_ass_time(125.33)
            "0:02:05.33"
        """
        seconds = round(seconds, 2)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = round((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def _escape_ass_text(self, text: str) -> str:
        """Escape text for ASS subtitle format, preserving \\N newlines.

        ASS requires escaping of special characters:
        - Backslashes must be doubled
        - Curly braces must be escaped (used for tags)
        - \\N newline sequences must be preserved (not double-escaped)

        Args:
            text: Raw text string (may contain \\N for newlines)

        Returns:
            Escaped text safe for ASS format with \\N preserved

        Example:
            >>> exporter._escape_ass_text("Score: {0-0}")
            "Score: \\{0-0\\}"
            >>> exporter._escape_ass_text("Line1\\NLine2")
            "Line1\\NLine2"
        """
        # Temporarily replace \N with placeholder to protect it
        text = text.replace("\\N", "\x00NEWLINE\x00")
        # Escape actual backslashes
        text = text.replace("\\", "\\\\")
        # Restore \N sequences (they should NOT be double-escaped)
        text = text.replace("\x00NEWLINE\x00", "\\N")
        # Escape curly braces
        text = text.replace("{", "\\{")
        text = text.replace("}", "\\}")
        return text

    def _write_ass_file(self, output_path: Path) -> Path:
        """Generate ASS subtitle file with score overlays.

        Creates Advanced SubStation Alpha (ASS) subtitle file containing:
        - Score display for each rally segment
        - Styled text with court green theme colors
        - Proper timing based on frame ranges and fps
        - Player name context if available

        Args:
            output_path: Base path for naming subtitle file (will create .ass sibling)

        Returns:
            Path to generated ASS file
        """
        lines = []

        # [Script Info] section
        lines.append("[Script Info]")
        lines.append("; Script generated by Pickleball Video Editor")
        lines.append("LayoutResX: 1920")
        lines.append("LayoutResY: 1080")
        lines.append("PlayResX: 1920")
        lines.append("PlayResY: 1080")
        lines.append("ScaledBorderAndShadow: yes")
        lines.append("ScriptType: v4.00+")
        lines.append("WrapStyle: 0")
        lines.append("YCbCr Matrix: None")
        lines.append("")

        # [V4+ Styles] section
        lines.append("[V4+ Styles]")
        lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        lines.append("Style: Default,Arial,60.00,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100.00,100.00,0.00,0.00,1,1.00,0.00,2,40,40,40,1")
        lines.append("")

        # [Events] section
        lines.append("[Events]")
        lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        # Track cumulative output timeline position
        current_output_seconds = 0.0

        # Process each rally segment
        for idx, segment in enumerate(self.segments):
            in_frame = segment["in"]
            out_frame = segment["out"]
            score = segment.get("score", "")

            # Calculate segment duration
            segment_duration = (out_frame - in_frame) / self.fps

            # Calculate subtitle timing in the output timeline
            subtitle_start = current_output_seconds
            subtitle_end = current_output_seconds + segment_duration

            # Build subtitle text
            subtitle_text = ""

            # Add player name intro only on first segment
            if idx == 0 and self.player_names is not None:
                team1_names = self.player_names.get("team1", [])
                team2_names = self.player_names.get("team2", [])
                game_type = self.player_names.get("game_type", "singles")

                # Check if we have valid player names
                if team1_names and team2_names:
                    if game_type == "singles":
                        # Singles: "Name1\Nvs\NName2\N\NScore"
                        name1 = team1_names[0] if len(team1_names) > 0 else "Player 1"
                        name2 = team2_names[0] if len(team2_names) > 0 else "Player 2"
                        subtitle_text = f"{name1}\\Nvs\\N{name2}\\N\\N{score}"
                    else:
                        # Doubles: "Name1 & Name2\Nvs\NName3 & Name4\N\NScore"
                        name1 = team1_names[0] if len(team1_names) > 0 else "Player 1"
                        name2 = team1_names[1] if len(team1_names) > 1 else "Player 2"
                        name3 = team2_names[0] if len(team2_names) > 0 else "Player 3"
                        name4 = team2_names[1] if len(team2_names) > 1 else "Player 4"
                        subtitle_text = f"{name1} & {name2}\\Nvs\\N{name3} & {name4}\\N\\N{score}"
                else:
                    # No valid player names, just show score
                    subtitle_text = score
            else:
                # Regular score display for all other segments
                subtitle_text = score

            # Escape text and generate dialogue line
            if subtitle_text:
                escaped_text = self._escape_ass_text(subtitle_text)
                start_time = self._seconds_to_ass_time(subtitle_start)
                end_time = self._seconds_to_ass_time(subtitle_end)
                lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{escaped_text}")

            # Advance timeline position
            current_output_seconds += segment_duration

        # Add game completion subtitle if applicable
        if self.game_completion is not None and self.game_completion.is_completed:
            final_score = self.game_completion.final_score
            winner_names = self.game_completion.winning_team_names
            extension_seconds = self.game_completion.extension_seconds

            # Build completion text
            if winner_names:
                # Format winner names
                if len(winner_names) == 1:
                    # Singles: "Name Wins"
                    winner_text = f"{winner_names[0]} Wins"
                else:
                    # Doubles: "Name1 & Name2 Win"
                    winner_text = f"{winner_names[0]} & {winner_names[1]} Win"

                completion_text = f"{final_score}\\N{winner_text}"
            else:
                # No winner names, just show final score
                completion_text = final_score

            # Add completion subtitle
            if completion_text:
                escaped_text = self._escape_ass_text(completion_text)
                start_time = self._seconds_to_ass_time(current_output_seconds)
                end_time = self._seconds_to_ass_time(current_output_seconds + extension_seconds)
                lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{escaped_text}")

        # Write ASS file
        ass_path = output_path.with_suffix(".ass")
        ass_content = "\n".join(lines)
        ass_path.write_text(ass_content, encoding="utf-8")

        return ass_path

    def _run_ffmpeg(self, output_path: Path, ass_path: Path) -> None:
        """Execute ffmpeg with hardware encoding (NVENC or libx264 fallback).

        Runs ffmpeg subprocess with:
        - NVENC hardware encoder if available, otherwise libx264
        - Appropriate rate control for each encoder
        - Audio re-encoded to AAC 192k for compatibility

        Args:
            output_path: Destination path for output MP4
            ass_path: Path to ASS subtitle file for overlay

        Raises:
            subprocess.CalledProcessError: If ffmpeg execution fails
        """
        # Get optimal encoder configuration based on hardware
        config = get_optimal_config()

        # Build filter complex and get audio output label
        filter_complex, audio_label = self._build_filter_complex(ass_path)

        # Build ffmpeg command with dynamic encoder config
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(self.video_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", audio_label,
            "-fps_mode", "cfr",
            "-c:v", config.codec,
            "-preset", config.preset,
            *config.rate_control,
            *config.extra_opts,
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]

        # Execute ffmpeg with check=True to raise on non-zero exit
        subprocess.run(ffmpeg_cmd, check=True)
