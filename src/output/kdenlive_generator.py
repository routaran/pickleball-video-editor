"""Kdenlive project file generation for Pickleball Video Editor.

This module generates Kdenlive MLT XML project files from rally segments.
The generated project contains:
- Video cuts for each rally (placed sequentially on timeline)
- Subtitle overlay with scores
- Proper MLT structure matching Kdenlive 25.x format

The output project can be opened in Kdenlive for further editing or rendering.

Implementation is based on the reference generator in:
.claude/skills/kdenlive-generator/scripts/generate_from_template.py
"""

import hashlib
import json
import uuid
from datetime import datetime
from html import escape as xml_escape
from pathlib import Path
from typing import Any

from src.core.models import GameCompletionInfo
from src.video.probe import probe_video, frames_to_timecode


__all__ = ["KdenliveGenerator"]


def _escape_ass_text(text: str) -> str:
    """Escape text for safe inclusion in ASS subtitle files.

    ASS interprets {...} as style overrides and \\commands as control sequences.
    This function escapes these to prevent injection/corruption.

    Args:
        text: Text to escape

    Returns:
        Escaped text safe for ASS files
    """
    # Escape backslash first (before other replacements add backslashes)
    text = text.replace("\\", "\\\\")
    # Escape curly braces (style override markers)
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    return text


class KdenliveGenerator:
    """Generates Kdenlive project files from rally segments.

    This class takes rally segments (from RallyManager.to_segments()) and
    creates a complete Kdenlive MLT XML project file with:
    - Sequential rally clips on the timeline
    - ASS subtitle overlay with scores
    - Proper audio/video track structure
    - All metadata for Kdenlive compatibility

    The generator also creates the companion ASS subtitle file.

    Attributes:
        video_path: Absolute path to source video file
        segments: Rally segments from RallyManager.to_segments()
        fps: Video frames per second
        resolution: Video resolution as (width, height) tuple
        output_dir: Directory for output files
    """

    def __init__(
        self,
        video_path: str | Path,
        segments: list[dict[str, Any]],
        fps: float,
        resolution: tuple[int, int] = (1920, 1080),
        output_dir: Path | None = None,
        team1_players: list[str] | None = None,
        team2_players: list[str] | None = None,
        game_type: str = "doubles",
        game_completion: GameCompletionInfo | None = None,
    ) -> None:
        """Initialize Kdenlive project generator.

        Args:
            video_path: Path to source video file
            segments: Rally segments from RallyManager.to_segments()
            fps: Video frames per second
            resolution: Video resolution (width, height), default 1080p
            output_dir: Output directory (default: ~/Videos/pickleball/)
            team1_players: List of Team 1 player names (for intro subtitle)
            team2_players: List of Team 2 player names (for intro subtitle)
            game_type: "singles" or "doubles"
            game_completion: Game completion info for final subtitle and extension

        Raises:
            ValueError: If fps is non-positive or resolution is invalid
            FileNotFoundError: If video_path doesn't exist
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        if resolution[0] <= 0 or resolution[1] <= 0:
            raise ValueError(f"Invalid resolution: {resolution}")

        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.video_path = self.video_path.resolve()
        self.segments = segments
        self.fps = fps
        self.resolution = resolution
        self.team1_players = team1_players or []
        self.team2_players = team2_players or []
        self.game_type = game_type
        self.game_completion = game_completion

        # Set default output directory
        if output_dir is None:
            self.output_dir = Path("/home/rkalluri/Videos")
        else:
            self.output_dir = Path(output_dir)

    def frames_to_timecode(self, frame: int) -> str:
        """Convert frame to MLT timecode (HH:MM:SS.mmm).

        Uses the frames_to_timecode utility from video.probe module.

        Args:
            frame: Frame number

        Returns:
            MLT timecode string (e.g., "00:01:23.456")
        """
        return frames_to_timecode(frame, self.fps)

    def generate(self) -> tuple[Path, Path]:
        """Generate Kdenlive project and ASS subtitle files.

        Creates:
        1. {video_name}_rallies.kdenlive - Kdenlive project file
        2. {video_name}_rallies.kdenlive.ass - ASS subtitle file

        The files are written to the output directory (default: ~/Videos/pickleball/).

        Returns:
            Tuple of (kdenlive_path, ass_path)

        Raises:
            ValueError: If segments are invalid or video info cannot be extracted
            OSError: If files cannot be written
        """
        # Ensure output directory exists
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filenames
        video_basename = self.video_path.stem
        kdenlive_path = self.output_dir / f"{video_basename}_rallies.kdenlive"
        ass_path = self.output_dir / f"{video_basename}_rallies.kdenlive.ass"

        # Generate ASS file first (needed for XML reference)
        self._write_ass_file(ass_path)

        # Generate Kdenlive XML
        xml_content = self._build_mlt_xml(ass_path)

        # Write Kdenlive project file
        kdenlive_path.write_text(xml_content, encoding="utf-8")

        return kdenlive_path, ass_path

    def _write_ass_file(self, ass_path: Path) -> None:
        """Generate ASS subtitle file.

        Args:
            ass_path: Path where ASS file should be written
        """
        lines = []

        # Script Info section
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

        # Kdenlive Extradata section
        lines.append("[Kdenlive Extradata]")
        lines.append("MaxLayer: 0")
        lines.append("DefaultStyles: Default")
        lines.append("")

        # V4+ Styles section
        lines.append("[V4+ Styles]")
        lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
        lines.append("Style: Default,Arial,60.00,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100.00,100.00,0.00,0.00,1,1.00,0.00,2,40,40,40,1")
        lines.append("")

        # Events section
        lines.append("[Events]")
        lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        # Generate subtitles based on segments
        # IMPORTANT: Calculate timing from MLT timecodes to stay synchronized
        # with video/audio entries. MLT calculates entry duration as (out_tc - in_tc)
        # where timecodes are rounded to milliseconds. We must use the same math.
        current_output_seconds = 0.0
        is_first_segment = True

        for seg in self.segments:
            # Calculate segment duration using the SAME method as MLT:
            # Convert frames to timecode (which rounds to milliseconds),
            # then parse back to get the actual duration MLT will use.
            in_tc = self.frames_to_timecode(seg["in"])
            out_tc = self.frames_to_timecode(seg["out"])
            in_seconds = self._timecode_to_seconds(in_tc)
            out_seconds = self._timecode_to_seconds(out_tc)
            segment_duration = out_seconds - in_seconds

            score = seg.get("score", "")

            if score:
                start_time = self._seconds_to_ass_time(current_output_seconds)
                end_time = self._seconds_to_ass_time(current_output_seconds + segment_duration)

                # First segment includes player names
                if is_first_segment and (self.team1_players or self.team2_players):
                    subtitle_text = self._format_intro_subtitle(score)
                    is_first_segment = False
                else:
                    subtitle_text = score

                lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{subtitle_text}")

            current_output_seconds += segment_duration

        # Add final score subtitle if game is marked as completed
        if self.game_completion is not None and self.game_completion.is_completed:
            # Calculate start time (end of last segment in output timeline)
            final_start_time = self._seconds_to_ass_time(current_output_seconds)

            # Calculate end time (start + extension duration)
            final_end_seconds = current_output_seconds + self.game_completion.extension_seconds
            final_end_time = self._seconds_to_ass_time(final_end_seconds)

            # Format the final score subtitle
            final_subtitle = self._format_final_score_subtitle()

            lines.append(f"Dialogue: 0,{final_start_time},{final_end_time},Default,,0,0,0,,{final_subtitle}")

        lines.append("")
        ass_path.write_text("\n".join(lines), encoding="utf-8")

    def _format_intro_subtitle(self, score: str) -> str:
        """Format the intro subtitle with player names and score.

        Args:
            score: The score string (e.g., "0-0-2")

        Returns:
            Formatted subtitle text with player names, vs, and score.
            Uses \\N for ASS line breaks.

        Example output for doubles:
            "Alice & Bob\\Nvs\\NCharlie & Dana\\N\\N0-0-2"

        Example output for singles:
            "Alice\\Nvs\\NBob\\N\\N0-0-2"
        """
        # Format team 1 players with ASS escaping
        if self.game_type == "singles":
            team1_str = _escape_ass_text(self.team1_players[0]) if self.team1_players else "Team 1"
        else:
            escaped_t1 = [_escape_ass_text(p) for p in self.team1_players] if self.team1_players else []
            team1_str = " & ".join(escaped_t1) if escaped_t1 else "Team 1"

        # Format team 2 players with ASS escaping
        if self.game_type == "singles":
            team2_str = _escape_ass_text(self.team2_players[0]) if self.team2_players else "Team 2"
        else:
            escaped_t2 = [_escape_ass_text(p) for p in self.team2_players] if self.team2_players else []
            team2_str = " & ".join(escaped_t2) if escaped_t2 else "Team 2"

        # Build subtitle with line breaks (\\N is ASS line break)
        return f"{team1_str}\\Nvs\\N{team2_str}\\N\\N{score}"

    def _format_final_score_subtitle(self) -> str:
        """Format the final score subtitle with score and winner.

        Returns:
            Formatted subtitle text like "11-9\\NJane & Joe Win"
        """
        if self.game_completion is None:
            return ""

        final_score = self.game_completion.final_score

        # Format winner names with ASS escaping
        if self.game_completion.winning_team_names:
            escaped_names = [_escape_ass_text(name) for name in self.game_completion.winning_team_names]
            if len(escaped_names) == 1:
                winner_str = f"{escaped_names[0]} Wins"
            else:
                winner_str = " & ".join(escaped_names) + " Win"
        else:
            winner_str = "Game Over"

        # Use \\N for ASS line break
        return f"{final_score}\\N{winner_str}"

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.cc).

        Note: ASS format uses centiseconds (2 decimal places), while MLT uses
        milliseconds (3 decimal places). We round to nearest centisecond to
        minimize drift, rather than truncating.
        """
        # Round to nearest centisecond to minimize drift
        seconds = round(seconds, 2)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = round((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def _timecode_to_seconds(self, timecode: str) -> float:
        """Convert MLT timecode (HH:MM:SS.mmm) to seconds.

        This is used to ensure subtitle timing matches MLT entry timing exactly.

        Args:
            timecode: MLT timecode string (e.g., "00:01:23.456")

        Returns:
            Time in seconds
        """
        parts = timecode.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    def _build_mlt_xml(self, subtitle_path: Path) -> str:
        """Build the MLT XML document.

        Creates a complete Kdenlive project file with:
        - MLT root element and profile
        - Producer for source video
        - Playlist with rally cuts (entries)
        - Tractor with audio/video tracks
        - Subtitle filter overlay
        - Main bin and document properties

        Args:
            subtitle_path: Path to the ASS subtitle file

        Returns:
            Complete MLT XML as string

        Raises:
            ValueError: If video cannot be probed or segments are invalid
        """
        # Probe video for metadata
        video_info = probe_video(self.video_path)

        # Calculate timeline properties
        timeline_frames = self._calculate_timeline_length()
        timeline_duration_tc = self.frames_to_timecode(timeline_frames)
        source_duration_tc = self.frames_to_timecode(
            video_info.frame_count or int(video_info.duration * self.fps)
        )

        # Generate UUIDs and IDs
        sequence_uuid = str(uuid.uuid4())
        session_uuid = str(uuid.uuid4())
        document_id = str(int(datetime.now().timestamp() * 1000))

        # Get video file metadata
        file_size = self.video_path.stat().st_size
        file_hash = self._get_file_hash(self.video_path)

        # Calculate aspect ratio
        width, height = self.resolution
        aspect_num, aspect_den = self._calculate_aspect_ratio(width, height)

        # Generate playlist entries
        entries_audio = self._generate_entries("chain0", "4")
        entries_video = self._generate_entries("chain1", "4")

        # Generate AVSplit groups for A/V linking
        groups_json = self._generate_avsplit_groups()

        # XML-escape file paths to handle special characters
        video_path_escaped = xml_escape(str(self.video_path))
        video_name_escaped = xml_escape(self.video_path.name)
        video_parent_escaped = xml_escape(str(self.video_path.parent))

        # Use RELATIVE path for subtitle (Kdenlive's behavior)
        subtitle_filename = subtitle_path.name

        # Build subtitlesList property with ABSOLUTE path
        subtitles_list = [
            {
                "file": str(subtitle_path.absolute()),
                "id": 0,
                "name": "Subtitles"
            }
        ]
        subtitles_list_json = json.dumps(subtitles_list, indent=4)

        # Build XML document
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.36.1" root="{video_parent_escaped}">
 <profile
   description="HD {height}p {int(self.fps)} fps"
   width="{width}"
   height="{height}"
   progressive="1"
   sample_aspect_num="1"
   sample_aspect_den="1"
   display_aspect_num="{aspect_num}"
   display_aspect_den="{aspect_den}"
   frame_rate_num="{int(self.fps)}"
   frame_rate_den="1"
   colorspace="709"/>
 <producer id="producer0" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="length">2147483647</property>
  <property name="eof">continue</property>
  <property name="resource">black</property>
  <property name="aspect_ratio">1</property>
  <property name="mlt_service">color</property>
  <property name="kdenlive:playlistid">black_track</property>
  <property name="mlt_image_format">rgba</property>
  <property name="set.test_audio">0</property>
 </producer>
 <playlist id="playlist0">
  <property name="kdenlive:audio_track">1</property>
 </playlist>
 <playlist id="playlist1">
  <property name="kdenlive:audio_track">1</property>
 </playlist>
 <tractor id="tractor0" in="00:00:00.000">
  <property name="kdenlive:audio_track">1</property>
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="video" producer="playlist0"/>
  <track hide="video" producer="playlist1"/>
  <filter id="filter0">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="channel_mask">-1</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter1">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="start">0.5</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter2">
   <property name="iec_scale">0</property>
   <property name="mlt_service">audiolevel</property>
   <property name="dbpeak">1</property>
   <property name="disable">1</property>
  </filter>
 </tractor>
 <chain id="chain0" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path_escaped}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{video_name_escaped}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>
 <playlist id="playlist2">
  <property name="kdenlive:audio_track">1</property>
{entries_audio}
 </playlist>
 <playlist id="playlist3">
  <property name="kdenlive:audio_track">1</property>
 </playlist>
 <tractor id="tractor1" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:audio_track">1</property>
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="video" producer="playlist2"/>
  <track hide="video" producer="playlist3"/>
  <filter id="filter3">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="channel_mask">-1</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter4">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="start">0.5</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter5">
   <property name="iec_scale">0</property>
   <property name="mlt_service">audiolevel</property>
   <property name="dbpeak">1</property>
   <property name="disable">1</property>
  </filter>
 </tractor>
 <chain id="chain1" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path_escaped}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{video_name_escaped}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>
 <playlist id="playlist4">
{entries_video}
 </playlist>
 <playlist id="playlist5"/>
 <tractor id="tractor2" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="audio" producer="playlist4"/>
  <track hide="audio" producer="playlist5"/>
 </tractor>
 <playlist id="playlist6"/>
 <playlist id="playlist7"/>
 <tractor id="tractor3" in="00:00:00.000">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <property name="kdenlive:thumbs_format"/>
  <property name="kdenlive:audio_rec"/>
  <track hide="audio" producer="playlist6"/>
  <track hide="audio" producer="playlist7"/>
 </tractor>
 <chain id="chain2" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path_escaped}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{video_name_escaped}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>
 <tractor id="tractor4" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:duration">{timeline_duration_tc}</property>
  <property name="kdenlive:maxduration">{timeline_frames}</property>
  <property name="kdenlive:clipname">Sequence 1</property>
  <property name="kdenlive:description"/>
  <property name="kdenlive:uuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:producer_type">17</property>
  <property name="kdenlive:control_uuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:id">3</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_hash">{self._get_sequence_hash(sequence_uuid)}</property>
  <property name="kdenlive:folderid">2</property>
  <property name="kdenlive:sequenceproperties.activeTrack">2</property>
  <property name="kdenlive:sequenceproperties.audioTarget">1</property>
  <property name="kdenlive:sequenceproperties.disablepreview">0</property>
  <property name="kdenlive:sequenceproperties.documentuuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:sequenceproperties.hasAudio">1</property>
  <property name="kdenlive:sequenceproperties.hasVideo">1</property>
  <property name="kdenlive:sequenceproperties.position">0</property>
  <property name="kdenlive:sequenceproperties.scrollPos">0</property>
  <property name="kdenlive:sequenceproperties.subtitlesList">{subtitles_list_json}
</property>
  <property name="kdenlive:sequenceproperties.tracks">4</property>
  <property name="kdenlive:sequenceproperties.tracksCount">4</property>
  <property name="kdenlive:sequenceproperties.verticalzoom">1</property>
  <property name="kdenlive:sequenceproperties.videoTarget">2</property>
  <property name="kdenlive:sequenceproperties.zonein">0</property>
  <property name="kdenlive:sequenceproperties.zoneout">75</property>
  <property name="kdenlive:sequenceproperties.zoom">8</property>
  <property name="kdenlive:sequenceproperties.groups">{groups_json}
</property>
  <property name="kdenlive:sequenceproperties.guides">[]
</property>
  <track producer="producer0"/>
  <track producer="tractor0"/>
  <track producer="tractor1"/>
  <track producer="tractor2"/>
  <track producer="tractor3"/>
  <transition id="transition0">
   <property name="a_track">0</property>
   <property name="b_track">1</property>
   <property name="mlt_service">mix</property>
   <property name="kdenlive_id">mix</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
   <property name="accepts_blanks">1</property>
   <property name="sum">1</property>
  </transition>
  <transition id="transition1">
   <property name="a_track">0</property>
   <property name="b_track">2</property>
   <property name="mlt_service">mix</property>
   <property name="kdenlive_id">mix</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
   <property name="accepts_blanks">1</property>
   <property name="sum">1</property>
  </transition>
  <transition id="transition2">
   <property name="a_track">0</property>
   <property name="b_track">3</property>
   <property name="compositing">0</property>
   <property name="distort">0</property>
   <property name="rotate_center">0</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>
  <transition id="transition3">
   <property name="a_track">0</property>
   <property name="b_track">4</property>
   <property name="compositing">0</property>
   <property name="distort">0</property>
   <property name="rotate_center">0</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>
  <filter id="filter6">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="channel_mask">-1</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter7">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="start">0.5</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter8">
   <property name="mlt_service">avfilter.subtitles</property>
   <property name="av.alpha">1</property>
   <property name="internal_added">237</property>
   <property name="av.filename">{subtitle_filename}</property>
  </filter>
 </tractor>
 <playlist id="main_bin">
  <property name="kdenlive:folder.-1.2">Sequences</property>
  <property name="kdenlive:sequenceFolder">2</property>
  <property name="kdenlive:docproperties.activetimeline">{{{sequence_uuid}}}</property>
  <property name="kdenlive:docproperties.audioChannels">2</property>
  <property name="kdenlive:docproperties.documentid">{document_id}</property>
  <property name="kdenlive:docproperties.enableexternalproxy">0</property>
  <property name="kdenlive:docproperties.enableproxy">0</property>
  <property name="kdenlive:docproperties.generateimageproxy">0</property>
  <property name="kdenlive:docproperties.generateproxy">0</property>
  <property name="kdenlive:docproperties.kdenliveversion">25.12.1</property>
  <property name="kdenlive:docproperties.profile">atsc_{height}p_{int(self.fps)}</property>
  <property name="kdenlive:docproperties.seekOffset">30000</property>
  <property name="kdenlive:docproperties.sessionid">{{{session_uuid}}}</property>
  <property name="kdenlive:docproperties.uuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:binZoom">4</property>
  <property name="kdenlive:extraBins">project_bin:-1:0</property>
  <property name="xml_retain">1</property>
  <entry in="00:00:00.000" out="{source_duration_tc}" producer="chain2"/>
  <entry in="00:00:00.000" out="{timeline_duration_tc}" producer="tractor4"/>
 </playlist>
 <tractor id="tractor5" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:projectTractor">1</property>
  <track in="00:00:00.000" out="{timeline_duration_tc}" producer="tractor4"/>
 </tractor>
</mlt>'''

        return xml

    def _generate_entries(self, chain_id: str, kdenlive_id: str) -> str:
        """Generate playlist entry elements for rally cuts.

        Creates <entry> elements for each rally segment with proper in/out
        timecodes referencing the source video. If the game is completed,
        extends the last segment by the extension duration.

        Args:
            chain_id: ID of the chain producer ("chain0" for audio, "chain1" for video)
            kdenlive_id: Kdenlive clip ID

        Returns:
            XML string with entry elements (indented properly)
        """
        entries: list[str] = []

        for i, seg in enumerate(self.segments):
            in_tc = self.frames_to_timecode(seg["in"])

            # For the last segment, add extension if game is completed
            is_last = (i == len(self.segments) - 1)
            if is_last and self.game_completion is not None and self.game_completion.is_completed:
                extension_frames = int(self.game_completion.extension_seconds * self.fps)
                out_tc = self.frames_to_timecode(seg["out"] + extension_frames)
            else:
                out_tc = self.frames_to_timecode(seg["out"])

            entries.append(f'''  <entry in="{in_tc}" out="{out_tc}" producer="{chain_id}">
   <property name="kdenlive:id">{kdenlive_id}</property>
  </entry>''')

        return "\n".join(entries)

    def _generate_avsplit_groups(self) -> str:
        """Generate AVSplit groups JSON for linking audio/video clips.

        Format: "data": "TRACK:TIMELINE_FRAME:-1"
        - Track 1 = audio track (tractor1/playlist2)
        - Track 2 = video track (tractor2/playlist4)
        - TIMELINE_FRAME = cumulative frame position on OUTPUT timeline

        If the game is completed, the last segment's duration includes the
        extension frames for the final score display.

        Returns:
            JSON string with AVSplit groups
        """
        groups = []
        current_frame = 0

        for i, seg in enumerate(self.segments):
            duration_frames = seg["out"] - seg["in"]

            # For the last segment, add extension if game is completed
            is_last = (i == len(self.segments) - 1)
            if is_last and self.game_completion is not None and self.game_completion.is_completed:
                extension_frames = int(self.game_completion.extension_seconds * self.fps)
                duration_frames += extension_frames

            # Create AVSplit group for this clip pair
            group = {
                "type": "AVSplit",
                "children": [
                    {"data": f"1:{current_frame}:-1", "leaf": "clip", "type": "Leaf"},
                    {"data": f"2:{current_frame}:-1", "leaf": "clip", "type": "Leaf"}
                ]
            }
            groups.append(group)

            current_frame += duration_frames

        return json.dumps(groups, indent=4)

    def _calculate_timeline_length(self) -> int:
        """Calculate total timeline length in frames.

        Sums the duration of all rally segments to get the total output
        timeline length (rallies placed back-to-back). If the game is
        completed, adds extension frames to the end.

        Returns:
            Total frames in the output timeline
        """
        base_length = sum(seg["out"] - seg["in"] for seg in self.segments)

        # Add extension for game completion
        if self.game_completion is not None and self.game_completion.is_completed:
            extension_frames = int(self.game_completion.extension_seconds * self.fps)
            return base_length + extension_frames

        return base_length

    def _calculate_aspect_ratio(self, width: int, height: int) -> tuple[int, int]:
        """Calculate simplified aspect ratio.

        Args:
            width: Video width in pixels
            height: Video height in pixels

        Returns:
            Tuple of (aspect_num, aspect_den) in simplified form
        """
        from math import gcd
        divisor = gcd(width, height)
        return width // divisor, height // divisor

    def _get_file_hash(self, filepath: Path) -> str:
        """Calculate MD5 hash of first 1MB of file.

        Kdenlive uses this for cache validation. Only the first 1MB is
        hashed for performance (matching Kdenlive's behavior).

        Args:
            filepath: Path to file to hash

        Returns:
            MD5 hash as hex string
        """
        hash_md5 = hashlib.md5()
        with filepath.open("rb") as f:
            # Read first 1MB only (like Kdenlive does)
            chunk = f.read(1024 * 1024)
            hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _get_sequence_hash(self, sequence_uuid: str) -> str:
        """Calculate hash for sequence based on UUID.

        Args:
            sequence_uuid: Sequence UUID string

        Returns:
            MD5 hash as hex string
        """
        return hashlib.md5(sequence_uuid.encode()).hexdigest()
