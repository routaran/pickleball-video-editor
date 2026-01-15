"""Kdenlive project file generation for Pickleball Video Editor.

This module generates Kdenlive MLT XML project files from rally segments.
The generated project contains:
- Video cuts for each rally (placed sequentially on timeline)
- Subtitle overlay with scores
- Proper MLT structure matching Kdenlive 25.x format

The output project can be opened in Kdenlive for further editing or rendering.

Implementation is based on the reference generator in:
.claude/skills/kdenlive-generator/scripts/generate_project.py
"""

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.output.subtitle_generator import SubtitleGenerator
from src.video.probe import probe_video, frames_to_timecode


__all__ = ["KdenliveGenerator"]


class KdenliveGenerator:
    """Generates Kdenlive project files from rally segments.

    This class takes rally segments (from RallyManager.to_segments()) and
    creates a complete Kdenlive MLT XML project file with:
    - Sequential rally clips on the timeline
    - SRT subtitle overlay with scores
    - Proper audio/video track structure
    - All metadata for Kdenlive compatibility

    The generator also creates the companion SRT subtitle file.

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
        output_dir: Path | None = None
    ) -> None:
        """Initialize Kdenlive project generator.

        Args:
            video_path: Path to source video file
            segments: Rally segments from RallyManager.to_segments()
            fps: Video frames per second
            resolution: Video resolution (width, height), default 1080p
            output_dir: Output directory (default: ~/Videos/pickleball/)

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
            raise FileNotFoundError(f"Video file not found: {self.video_path}")

        self.video_path = self.video_path.resolve()
        self.segments = segments
        self.fps = fps
        self.resolution = resolution

        # Set default output directory
        if output_dir is None:
            self.output_dir = Path.home() / "Videos" / "pickleball"
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
        """Generate Kdenlive project and SRT files.

        Creates:
        1. {video_name}_rallies.kdenlive - Kdenlive project file
        2. {video_name}_scores.srt - Subtitle file

        The files are written to the output directory (default: ~/Videos/pickleball/).

        Returns:
            Tuple of (kdenlive_path, srt_path)

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
        srt_path = self.output_dir / f"{video_basename}_scores.srt"

        # Generate SRT file first (needed for XML reference)
        SubtitleGenerator.write_srt(self.segments, self.fps, srt_path)

        # Generate Kdenlive XML
        xml_content = self._build_mlt_xml(srt_path)

        # Write Kdenlive project file
        kdenlive_path.write_text(xml_content, encoding="utf-8")

        return kdenlive_path, srt_path

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
            subtitle_path: Path to the SRT subtitle file

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

        # Build XML document
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.36.1" root="{self.video_path.parent}">

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

 <!-- Black background producer -->
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

 <!-- Video chain for audio track -->
 <chain id="chain0" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{self.video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{self.video_path.name}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>

 <!-- Video chain for video track -->
 <chain id="chain1" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{self.video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{self.video_path.name}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>

 <!-- Video chain for main_bin reference -->
 <chain id="chain2" out="{source_duration_tc}">
  <property name="length">{video_info.frame_count or int(video_info.duration * self.fps)}</property>
  <property name="eof">pause</property>
  <property name="resource">{self.video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{self.video_path.name}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>

 <!-- Empty audio playlist 0 -->
 <playlist id="playlist0">
  <property name="kdenlive:audio_track">1</property>
 </playlist>

 <!-- Empty audio playlist 1 -->
 <playlist id="playlist1">
  <property name="kdenlive:audio_track">1</property>
 </playlist>

 <!-- Audio content playlist -->
 <playlist id="playlist2">
  <property name="kdenlive:audio_track">1</property>
{entries_audio}
 </playlist>

 <!-- Empty audio playlist 3 -->
 <playlist id="playlist3">
  <property name="kdenlive:audio_track">1</property>
 </playlist>

 <!-- Video content playlist -->
 <playlist id="playlist4">
{entries_video}
 </playlist>

 <!-- Empty video playlist 5 -->
 <playlist id="playlist5"/>

 <!-- Empty video playlist 6 -->
 <playlist id="playlist6"/>

 <!-- Empty video playlist 7 -->
 <playlist id="playlist7"/>

 <!-- Audio tractor 0 (empty tracks) -->
 <tractor id="tractor0" in="00:00:00.000">
  <property name="kdenlive:audio_track">1</property>
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <track hide="video" producer="playlist0"/>
  <track hide="video" producer="playlist1"/>
  <filter id="filter0">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter1">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter2">
   <property name="iec_scale">0</property>
   <property name="mlt_service">audiolevel</property>
   <property name="dbpeak">1</property>
   <property name="disable">1</property>
  </filter>
 </tractor>

 <!-- Audio tractor 1 (content track) -->
 <tractor id="tractor1" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:audio_track">1</property>
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <track hide="video" producer="playlist2"/>
  <track hide="video" producer="playlist3"/>
  <filter id="filter3">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter4">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter5">
   <property name="iec_scale">0</property>
   <property name="mlt_service">audiolevel</property>
   <property name="dbpeak">1</property>
   <property name="disable">1</property>
  </filter>
 </tractor>

 <!-- Video tractor 2 (content track) -->
 <tractor id="tractor2" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <track hide="audio" producer="playlist4"/>
  <track hide="audio" producer="playlist5"/>
 </tractor>

 <!-- Video tractor 3 (empty) -->
 <tractor id="tractor3" in="00:00:00.000">
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <track hide="audio" producer="playlist6"/>
  <track hide="audio" producer="playlist7"/>
 </tractor>

 <!-- Main sequence tractor -->
 <tractor id="{{{sequence_uuid}}}" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:uuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:clipname">Sequence 1</property>
  <property name="kdenlive:sequenceproperties.hasAudio">1</property>
  <property name="kdenlive:sequenceproperties.hasVideo">1</property>
  <property name="kdenlive:sequenceproperties.activeTrack">2</property>
  <property name="kdenlive:sequenceproperties.tracksCount">4</property>
  <property name="kdenlive:sequenceproperties.audioTarget">1</property>
  <property name="kdenlive:sequenceproperties.videoTarget">2</property>
  <property name="kdenlive:sequenceproperties.disablepreview">0</property>
  <property name="kdenlive:sequenceproperties.position">0</property>
  <property name="kdenlive:duration">{timeline_duration_tc}</property>
  <property name="kdenlive:maxduration">{timeline_frames}</property>
  <property name="kdenlive:producer_type">17</property>

  <track producer="producer0"/>
  <track producer="tractor0"/>
  <track producer="tractor1"/>
  <track producer="tractor2"/>
  <track producer="tractor3"/>

  <!-- Audio mix transitions -->
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

  <!-- Video composite transitions -->
  <transition id="transition2">
   <property name="a_track">0</property>
   <property name="b_track">3</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>
  <transition id="transition3">
   <property name="a_track">0</property>
   <property name="b_track">4</property>
   <property name="mlt_service">qtblend</property>
   <property name="kdenlive_id">qtblend</property>
   <property name="internal_added">237</property>
   <property name="always_active">1</property>
  </transition>

  <!-- Master audio filters -->
  <filter id="filter6">
   <property name="window">75</property>
   <property name="max_gain">20dB</property>
   <property name="mlt_service">volume</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>
  <filter id="filter7">
   <property name="channel">-1</property>
   <property name="mlt_service">panner</property>
   <property name="internal_added">237</property>
   <property name="disable">1</property>
  </filter>

  <!-- Subtitle filter -->
  <filter id="filter8">
   <property name="mlt_service">avfilter.subtitles</property>
   <property name="av.filename">{subtitle_path}</property>
   <property name="kdenlive:filter">subtitles</property>
  </filter>
 </tractor>

 <!-- Main bin playlist with document properties -->
 <playlist id="main_bin">
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.kdenliveversion">25.12.1</property>
  <property name="kdenlive:docproperties.uuid">{{{sequence_uuid}}}</property>
  <property name="kdenlive:docproperties.sessionid">{{{session_uuid}}}</property>
  <property name="kdenlive:docproperties.documentid">{document_id}</property>
  <property name="kdenlive:docproperties.profile">atsc_{height}p_{int(self.fps)}</property>
  <property name="kdenlive:docproperties.audioChannels">2</property>
  <property name="kdenlive:docproperties.enableproxy">0</property>
  <property name="kdenlive:docproperties.enableexternalproxy">0</property>
  <property name="kdenlive:docproperties.generateimageproxy">0</property>
  <property name="kdenlive:docproperties.generateproxy">0</property>
  <property name="kdenlive:docproperties.rendercategory">Generic (HD for web, Apache, social media streaming sites)</property>
  <property name="kdenlive:docproperties.renderprofile">MP4 - H.264/AAC</property>
  <property name="kdenlive:docproperties.seekOffset">30000</property>
  <property name="kdenlive:folder.-1.2">Sequences</property>
  <property name="kdenlive:sequenceFolder">2</property>
  <property name="kdenlive:binZoom">4</property>
  <property name="kdenlive:extraBins">project_bin:-1:0</property>
  <entry in="00:00:00.000" out="{timeline_duration_tc}" producer="{{{sequence_uuid}}}"/>
  <entry in="00:00:00.000" out="{source_duration_tc}" producer="chain2"/>
 </playlist>

 <!-- Project root tractor -->
 <tractor id="tractor4" in="00:00:00.000" out="{timeline_duration_tc}">
  <property name="kdenlive:projectTractor">1</property>
  <track in="00:00:00.000" out="{timeline_duration_tc}" producer="{{{sequence_uuid}}}"/>
 </tractor>

</mlt>'''

        return xml

    def _generate_entries(self, chain_id: str, kdenlive_id: str) -> str:
        """Generate playlist entry elements for rally cuts.

        Creates <entry> elements for each rally segment with proper in/out
        timecodes referencing the source video.

        Args:
            chain_id: ID of the chain producer ("chain0" for audio, "chain1" for video)
            kdenlive_id: Kdenlive clip ID

        Returns:
            XML string with entry elements
        """
        entries: list[str] = []

        for seg in self.segments:
            in_tc = self.frames_to_timecode(seg["in"])
            out_tc = self.frames_to_timecode(seg["out"])

            entries.append(f'''   <entry in="{in_tc}" out="{out_tc}" producer="{chain_id}">
    <property name="kdenlive:id">{kdenlive_id}</property>
   </entry>''')

        return "\n".join(entries)

    def _calculate_timeline_length(self) -> int:
        """Calculate total timeline length in frames.

        Sums the duration of all rally segments to get the total output
        timeline length (rallies placed back-to-back).

        Returns:
            Total frames in the output timeline
        """
        return sum(seg["out"] - seg["in"] + 1 for seg in self.segments)

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
