#!/usr/bin/env python3
"""
Kdenlive Project Generator

Generates Kdenlive project files (.kdenlive) with video cuts and subtitles.
Updated to match Kdenlive's actual project structure.

Usage:
    python generate_project.py <config.json> <output_name>

Config JSON format:
{
    "video_path": "/absolute/path/to/video.mp4",
    "segments": [
        {"in": 150, "out": 450, "score": "0-0-2"},
        {"in": 600, "out": 900, "score": "1-0-2"}
    ],
    "profile": {
        "width": 1920,
        "height": 1080,
        "frame_rate_num": 60,
        "frame_rate_den": 1
    }
}
"""

import json
import os
import subprocess
import sys
import uuid
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime


def probe_video(video_path: str) -> dict:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames,codec_name,pix_fmt",
        "-of", "json",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data["streams"][0]

    # Parse frame rate (e.g., "30/1" or "30000/1001")
    fr_parts = stream["r_frame_rate"].split("/")
    frame_rate_num = int(fr_parts[0])
    frame_rate_den = int(fr_parts[1]) if len(fr_parts) > 1 else 1

    # Get total frames
    if "nb_frames" in stream and stream["nb_frames"] != "N/A":
        total_frames = int(stream["nb_frames"])
    else:
        # Calculate from duration
        duration = float(stream.get("duration", 0))
        fps = frame_rate_num / frame_rate_den
        total_frames = int(duration * fps)

    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate_num": frame_rate_num,
        "frame_rate_den": frame_rate_den,
        "total_frames": total_frames,
        "fps": frame_rate_num / frame_rate_den,
        "duration": float(stream.get("duration", total_frames / (frame_rate_num / frame_rate_den))),
        "codec_name": stream.get("codec_name", "h264"),
        "pix_fmt": stream.get("pix_fmt", "yuv420p")
    }


def get_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of first 1MB of file for Kdenlive's cache validation."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read first 1MB only (like Kdenlive does)
        chunk = f.read(1024 * 1024)
        hash_md5.update(chunk)
    return hash_md5.hexdigest()


def frames_to_timecode(frames: int, fps: float) -> str:
    """Convert frame number to Kdenlive timecode format (HH:MM:SS.mmm)."""
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def frames_to_srt_time(frames: int, fps: float) -> str:
    """Convert frame number to SRT timestamp format (HH:MM:SS,mmm)."""
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def generate_srt(segments: list, fps: float) -> str:
    """Generate SRT subtitle content for the edited timeline."""
    srt_lines = []
    current_output_frame = 0

    for i, seg in enumerate(segments, 1):
        in_frame = seg["in"]
        out_frame = seg["out"]
        score = seg.get("score", "")

        if not score:
            current_output_frame += (out_frame - in_frame + 1)
            continue

        segment_length = out_frame - in_frame + 1
        start_time = frames_to_srt_time(current_output_frame, fps)
        end_time = frames_to_srt_time(current_output_frame + segment_length - 1, fps)

        srt_lines.append(str(i))
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(score)
        srt_lines.append("")

        current_output_frame += segment_length

    return "\n".join(srt_lines)


def calculate_timeline_length(segments: list) -> int:
    """Calculate total timeline length in frames."""
    return sum(seg["out"] - seg["in"] + 1 for seg in segments)


def generate_kdenlive_xml(
    video_path: str,
    segments: list,
    subtitle_path: str,
    profile: dict,
    video_info: dict,
    project_root: str
) -> str:
    """Generate the Kdenlive/MLT XML project file matching Kdenlive's structure."""

    clip_name = os.path.basename(video_path)
    timeline_frames = calculate_timeline_length(segments)
    timeline_length = timeline_frames - 1  # 0-indexed
    total_source_frames = video_info["total_frames"]
    fps = video_info["fps"]

    # Generate UUIDs for sequence and session
    sequence_uuid = str(uuid.uuid4())
    session_uuid = str(uuid.uuid4())
    document_id = str(int(datetime.now().timestamp() * 1000))

    # Get file info
    file_size = os.path.getsize(video_path)
    file_hash = get_file_hash(video_path)

    # Timecodes
    source_duration_tc = frames_to_timecode(total_source_frames, fps)
    timeline_duration_tc = frames_to_timecode(timeline_frames, fps)

    # Calculate display aspect ratio
    width = profile["width"]
    height = profile["height"]
    from math import gcd
    divisor = gcd(width, height)
    aspect_num = width // divisor
    aspect_den = height // divisor

    # Generate playlist entries for audio and video
    def generate_entries(chain_id: str, kdenlive_id: str) -> str:
        entries = []
        for seg in segments:
            in_tc = frames_to_timecode(seg["in"], fps)
            out_tc = frames_to_timecode(seg["out"], fps)
            entries.append(f'''   <entry in="{in_tc}" out="{out_tc}" producer="{chain_id}">
    <property name="kdenlive:id">{kdenlive_id}</property>
   </entry>''')
        return "\n".join(entries)

    # Build the XML
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.36.1" root="{project_root}">

 <profile
   description="HD {height}p {int(fps)} fps"
   width="{width}"
   height="{height}"
   progressive="1"
   sample_aspect_num="1"
   sample_aspect_den="1"
   display_aspect_num="{aspect_num}"
   display_aspect_den="{aspect_den}"
   frame_rate_num="{profile['frame_rate_num']}"
   frame_rate_den="{profile['frame_rate_den']}"
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
  <property name="length">{total_source_frames}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{clip_name}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>

 <!-- Video chain for video track -->
 <chain id="chain1" out="{source_duration_tc}">
  <property name="length">{total_source_frames}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{clip_name}</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">{file_size}</property>
  <property name="kdenlive:file_hash">{file_hash}</property>
 </chain>

 <!-- Video chain for main_bin reference -->
 <chain id="chain2" out="{source_duration_tc}">
  <property name="length">{total_source_frames}</property>
  <property name="eof">pause</property>
  <property name="resource">{video_path}</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">{clip_name}</property>
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
{generate_entries("chain0", "4")}
 </playlist>

 <!-- Empty audio playlist 3 -->
 <playlist id="playlist3">
  <property name="kdenlive:audio_track">1</property>
 </playlist>

 <!-- Video content playlist -->
 <playlist id="playlist4">
{generate_entries("chain1", "4")}
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
  <property name="kdenlive:docproperties.profile">atsc_{height}p_{int(fps)}</property>
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


def generate_project(config_path: str, output_name: str, output_dir: Optional[str] = None):
    """
    Main function to generate Kdenlive project from config.

    Args:
        config_path: Path to JSON config file
        output_name: Base name for output files (without extension)
        output_dir: Directory for output files (defaults to config file directory)
    """
    # Load config
    with open(config_path, "r") as f:
        config = json.load(f)

    video_path = os.path.abspath(config["video_path"])
    segments = config["segments"]

    # Determine output directory
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(config_path))
        if not output_dir:
            output_dir = os.getcwd()

    project_root = os.path.dirname(video_path)

    # Probe video for metadata (always probe for complete info)
    video_info = probe_video(video_path)

    # Use config profile if provided, otherwise use probed values
    if "profile" in config:
        profile = config["profile"]
        # Ensure frame_rate_den exists
        if "frame_rate_den" not in profile:
            profile["frame_rate_den"] = 1
    else:
        profile = {
            "width": video_info["width"],
            "height": video_info["height"],
            "frame_rate_num": video_info["frame_rate_num"],
            "frame_rate_den": video_info["frame_rate_den"]
        }

    fps = profile["frame_rate_num"] / profile.get("frame_rate_den", 1)

    # Generate output paths (use absolute paths)
    kdenlive_path = os.path.abspath(os.path.join(output_dir, f"{output_name}.kdenlive"))
    srt_path = os.path.abspath(os.path.join(output_dir, f"{output_name}.srt"))

    # Generate SRT
    srt_content = generate_srt(segments, fps)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    print(f"Generated: {srt_path}")

    # Generate Kdenlive XML
    xml_content = generate_kdenlive_xml(
        video_path=video_path,
        segments=segments,
        subtitle_path=srt_path,
        profile=profile,
        video_info=video_info,
        project_root=project_root
    )
    with open(kdenlive_path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"Generated: {kdenlive_path}")

    # Summary
    timeline_frames = calculate_timeline_length(segments)
    timeline_seconds = timeline_frames / fps
    print(f"\nProject Summary:")
    print(f"  Source video: {video_path}")
    print(f"  Segments: {len(segments)}")
    print(f"  Timeline duration: {timeline_seconds:.1f}s ({timeline_frames} frames)")
    print(f"  Profile: {profile['width']}x{profile['height']} @ {fps}fps")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    config_path = sys.argv[1]
    output_name = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) > 3 else None

    generate_project(config_path, output_name, output_dir)
