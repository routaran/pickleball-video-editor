#!/usr/bin/env python3
"""
Kdenlive Project Generator (Template-Based)

Uses an existing Kdenlive project as a template and modifies the segments.
This approach preserves all Kdenlive-specific elements correctly.

Usage:
    python generate_from_template.py <template.kdenlive> <config.json> <output.kdenlive>

Config JSON format:
{
    "video_path": "/path/to/new_video.mp4",  // Optional: change video source
    "segments": [
        {"in_seconds": 5.0, "out_seconds": 15.0, "subtitle": "0-0-2"},
        {"in_seconds": 20.0, "out_seconds": 35.5, "subtitle": "1-0-2"}
    ]
}

Or with frame numbers:
{
    "segments": [
        {"in": 300, "out": 900, "subtitle": "0-0-2"},
        {"in": 1200, "out": 2130, "subtitle": "1-0-2"}
    ]
}

Subtitle duration can be limited independently from segment duration:
{
    "segments": [
        {
            "in": 1800, "out": 50773,
            "subtitle": "Team 1 vs Team 2",
            "subtitle_duration": 5.0  // Show subtitle for only 5 seconds
        }
    ]
}

Or use subtitle_duration_frames for frame-based duration.

For multiple subtitles with independent timing, use a top-level "subtitles" array:
{
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

Subtitle timing options (all in seconds unless noted):
- start/end: Explicit start and end times
- start + duration: Start time plus duration
- start_frames/end_frames: Frame-based timing
- duration_frames: Frame-based duration
"""

import json
import os
import sys
import subprocess
import hashlib
import xml.etree.ElementTree as ET


def seconds_to_timecode(seconds: float) -> str:
    """Convert seconds to Kdenlive timecode format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def frames_to_timecode(frames: int, fps: float) -> str:
    """Convert frame number to Kdenlive timecode format."""
    return seconds_to_timecode(frames / fps)


def timecode_to_seconds(tc: str) -> float:
    """Convert Kdenlive timecode (HH:MM:SS.mmm) to seconds."""
    parts = tc.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def probe_video(video_path: str) -> dict:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,nb_frames",
        "-of", "json",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data["streams"][0]

    fr_parts = stream["r_frame_rate"].split("/")
    frame_rate_num = int(fr_parts[0])
    frame_rate_den = int(fr_parts[1]) if len(fr_parts) > 1 else 1

    if "nb_frames" in stream and stream["nb_frames"] != "N/A":
        total_frames = int(stream["nb_frames"])
    else:
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
        "duration": float(stream.get("duration", 0))
    }


def get_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of first 1MB of file."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        chunk = f.read(1024 * 1024)
        hash_md5.update(chunk)
    return hash_md5.hexdigest()


def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format (H:MM:SS.cc)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def generate_ass(segments: list, fps: float, subtitles: list = None) -> str:
    """Generate ASS subtitle content for the edited timeline.

    Args:
        segments: List of segment definitions (used for segment-based subtitles)
        fps: Frames per second
        subtitles: Optional list of explicit subtitle definitions with start/end times.
                   If provided, these are used instead of segment-based subtitles.

    Segment-based subtitle options:
        - subtitle_duration (seconds): Limit subtitle display time
        - subtitle_duration_frames: Same but in frames

    Explicit subtitle format:
        {"start": 0, "end": 5, "text": "..."} - times in seconds
        {"start_frames": 0, "end_frames": 300, "text": "..."} - times in frames
    """
    lines = []

    # Script Info section
    lines.append("[Script Info]")
    lines.append("; Script generated by Kdenlive project generator")
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

    if subtitles:
        # Use explicit subtitle definitions
        for sub in subtitles:
            text = sub.get("text", sub.get("subtitle", ""))
            if not text:
                continue

            # Get start time
            if "start" in sub:
                start_sec = sub["start"]
            elif "start_frames" in sub:
                start_sec = sub["start_frames"] / fps
            else:
                start_sec = 0

            # Get end time
            if "end" in sub:
                end_sec = sub["end"]
            elif "end_frames" in sub:
                end_sec = sub["end_frames"] / fps
            elif "duration" in sub:
                end_sec = start_sec + sub["duration"]
            elif "duration_frames" in sub:
                end_sec = start_sec + sub["duration_frames"] / fps
            else:
                continue  # No end time specified

            start_time = seconds_to_ass_time(start_sec)
            end_time = seconds_to_ass_time(end_sec)
            lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
    else:
        # Use segment-based subtitles
        current_output_seconds = 0.0

        for seg in segments:
            # Get segment duration
            if "in" in seg and "out" in seg:
                in_sec = seg["in"] / fps
                out_sec = seg["out"] / fps
            else:
                in_sec = seg["in_seconds"]
                out_sec = seg["out_seconds"]

            segment_duration = out_sec - in_sec
            text = seg.get("score", seg.get("subtitle", seg.get("text", "")))

            if text:
                # Check for explicit subtitle duration
                if "subtitle_duration" in seg:
                    subtitle_duration = seg["subtitle_duration"]
                elif "subtitle_duration_frames" in seg:
                    subtitle_duration = seg["subtitle_duration_frames"] / fps
                else:
                    # Default: subtitle lasts for the entire segment
                    subtitle_duration = segment_duration

                # Clamp subtitle duration to segment duration
                subtitle_duration = min(subtitle_duration, segment_duration)

                start_time = seconds_to_ass_time(current_output_seconds)
                end_time = seconds_to_ass_time(current_output_seconds + subtitle_duration)
                lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")

            current_output_seconds += segment_duration

    lines.append("")
    return "\n".join(lines)


def generate_avsplit_groups(num_segments: int, fps: float, segments: list) -> str:
    """Generate AVSplit groups JSON for linking audio/video clips.

    Format: "data": "TRACK:TIMELINE_FRAME:-1"
    - Track 1 = audio track (tractor1/playlist2)
    - Track 2 = video track (tractor2/playlist4)
    - TIMELINE_FRAME = cumulative frame position on OUTPUT timeline
    """
    groups = []
    current_frame = 0

    for i, seg in enumerate(segments):
        # Calculate the start frame on the output timeline
        if "in" in seg and "out" in seg:
            duration_frames = seg["out"] - seg["in"]
        else:
            in_sec = seg["in_seconds"]
            out_sec = seg["out_seconds"]
            duration_frames = int((out_sec - in_sec) * fps)

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


def get_property(element: ET.Element, name: str) -> str:
    """Get property value from an element."""
    for prop in element.findall('property'):
        if prop.get('name') == name:
            return prop.text or ""
    return ""


def set_property(element: ET.Element, name: str, value: str):
    """Set or create a property on an element."""
    for prop in element.findall('property'):
        if prop.get('name') == name:
            prop.text = value
            return
    # Create new property
    new_prop = ET.SubElement(element, 'property')
    new_prop.set('name', name)
    new_prop.text = value


def clear_playlist_entries(playlist: ET.Element):
    """Remove all entry elements from a playlist."""
    entries = playlist.findall('entry')
    for entry in entries:
        playlist.remove(entry)


def add_playlist_entry(playlist: ET.Element, producer: str, in_tc: str, out_tc: str, kdenlive_id: str):
    """Add an entry to a playlist."""
    entry = ET.SubElement(playlist, 'entry')
    entry.set('in', in_tc)
    entry.set('out', out_tc)
    entry.set('producer', producer)

    prop = ET.SubElement(entry, 'property')
    prop.set('name', 'kdenlive:id')
    prop.text = kdenlive_id


def find_element_by_id(root: ET.Element, elem_id: str) -> ET.Element:
    """Find element by id attribute."""
    for elem in root.iter():
        if elem.get('id') == elem_id:
            return elem
    return None


def update_video_source(root: ET.Element, new_video_path: str, video_info: dict):
    """Update all chain elements to reference the new video."""

    video_filename = os.path.basename(new_video_path)
    file_size = os.path.getsize(new_video_path)
    file_hash = get_file_hash(new_video_path)
    total_frames = video_info["total_frames"]
    duration_tc = frames_to_timecode(total_frames, video_info["fps"])

    # Update all chain elements
    for chain in root.findall('chain'):
        chain.set('out', duration_tc)
        set_property(chain, 'length', str(total_frames))
        set_property(chain, 'resource', video_filename)  # Use relative path like Kdenlive does
        set_property(chain, 'kdenlive:file_size', str(file_size))
        set_property(chain, 'kdenlive:file_hash', file_hash)

        # Update media metadata
        set_property(chain, 'meta.media.width', str(video_info["width"]))
        set_property(chain, 'meta.media.height', str(video_info["height"]))
        set_property(chain, 'meta.media.frame_rate_num', str(video_info["frame_rate_num"]))
        set_property(chain, 'meta.media.frame_rate_den', str(video_info["frame_rate_den"]))

    # Update main_bin entry for the video clip
    main_bin = find_element_by_id(root, 'main_bin')
    if main_bin is not None:
        for entry in main_bin.findall('entry'):
            producer = entry.get('producer', '')
            # Update video clip entry (chain2)
            if producer == 'chain2':
                entry.set('out', duration_tc)

    # Update root path
    new_root = os.path.dirname(new_video_path)
    root.set('root', new_root)


def generate_project(template_path: str, config_path: str, output_path: str):
    """Generate a new Kdenlive project from template with new segments."""

    # Load config
    with open(config_path, 'r') as f:
        config = json.load(f)

    segments = config["segments"]
    new_video_path = config.get("video_path")
    subtitles = config.get("subtitles")  # Optional explicit subtitle definitions

    # Parse template
    tree = ET.parse(template_path)
    root = tree.getroot()

    # Get FPS from profile
    profile = root.find('profile')
    fps_num = int(profile.get('frame_rate_num', 60))
    fps_den = int(profile.get('frame_rate_den', 1))
    fps = fps_num / fps_den

    # If new video specified, update the source
    if new_video_path:
        new_video_path = os.path.abspath(new_video_path)
        video_info = probe_video(new_video_path)
        update_video_source(root, new_video_path, video_info)
        # Use video's FPS
        fps = video_info["fps"]

    # Convert segments to timecodes
    segment_timecodes = []
    total_duration_seconds = 0.0

    for seg in segments:
        if "in" in seg and "out" in seg:
            # Frame numbers
            in_tc = frames_to_timecode(seg["in"], fps)
            out_tc = frames_to_timecode(seg["out"], fps)
            duration = (seg["out"] - seg["in"]) / fps
        else:
            # Seconds
            in_tc = seconds_to_timecode(seg["in_seconds"])
            out_tc = seconds_to_timecode(seg["out_seconds"])
            duration = seg["out_seconds"] - seg["in_seconds"]

        segment_timecodes.append({
            "in": in_tc,
            "out": out_tc,
            "text": seg.get("score", seg.get("subtitle", seg.get("text", "")))
        })
        total_duration_seconds += duration

    timeline_duration_tc = seconds_to_timecode(total_duration_seconds)
    timeline_frames = int(total_duration_seconds * fps)

    # Find the kdenlive:id used for clips (from existing entries)
    playlist2 = find_element_by_id(root, 'playlist2')
    existing_entries = playlist2.findall('entry')
    if existing_entries:
        kdenlive_id = get_property(existing_entries[0], 'kdenlive:id')
    else:
        kdenlive_id = "4"  # Default

    # Get producer names from existing entries
    audio_producer = existing_entries[0].get('producer') if existing_entries else 'chain0'

    playlist4 = find_element_by_id(root, 'playlist4')
    existing_video_entries = playlist4.findall('entry')
    video_producer = existing_video_entries[0].get('producer') if existing_video_entries else 'chain1'

    # Clear and rebuild playlist2 (audio)
    clear_playlist_entries(playlist2)
    for seg in segment_timecodes:
        add_playlist_entry(playlist2, audio_producer, seg["in"], seg["out"], kdenlive_id)

    # Clear and rebuild playlist4 (video)
    clear_playlist_entries(playlist4)
    for seg in segment_timecodes:
        add_playlist_entry(playlist4, video_producer, seg["in"], seg["out"], kdenlive_id)

    # Update tractor1 out (audio tractor with content)
    tractor1 = find_element_by_id(root, 'tractor1')
    if tractor1 is not None:
        tractor1.set('out', timeline_duration_tc)

    # Update tractor2 out (video tractor with content)
    tractor2 = find_element_by_id(root, 'tractor2')
    if tractor2 is not None:
        tractor2.set('out', timeline_duration_tc)

    # Find main sequence tractor (has kdenlive:uuid property)
    main_sequence = None
    for tractor in root.findall('tractor'):
        if get_property(tractor, 'kdenlive:uuid'):
            main_sequence = tractor
            break

    if main_sequence is not None:
        main_sequence.set('out', timeline_duration_tc)
        set_property(main_sequence, 'kdenlive:duration', timeline_duration_tc)
        set_property(main_sequence, 'kdenlive:maxduration', str(timeline_frames))

        # Generate proper AVSplit groups for A/V linking
        groups_json = generate_avsplit_groups(len(segments), fps, segments)
        set_property(main_sequence, 'kdenlive:sequenceproperties.groups', groups_json)

    # Update tractor4 (project tractor)
    tractor4 = find_element_by_id(root, 'tractor4')
    if tractor4 is not None:
        tractor4.set('out', timeline_duration_tc)
        # Update track inside tractor4
        track = tractor4.find('track')
        if track is not None:
            track.set('out', timeline_duration_tc)

    # Update main_bin entry for sequence
    main_bin = find_element_by_id(root, 'main_bin')
    if main_bin is not None:
        for entry in main_bin.findall('entry'):
            producer = entry.get('producer', '')
            # Update sequence entry (has UUID-style producer)
            if producer.startswith('{'):
                entry.set('out', timeline_duration_tc)

    # Generate ASS subtitle file (Kdenlive uses ASS format internally)
    output_dir = os.path.dirname(os.path.abspath(output_path))
    output_basename = os.path.basename(output_path)
    ass_filename = f"{output_basename}.ass"  # Relative filename for av.filename
    ass_path = os.path.abspath(os.path.join(output_dir, ass_filename))

    ass_content = generate_ass(segments, fps, subtitles)
    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    print(f"Generated: {ass_path}")

    # Add subtitle filter to main sequence if not present
    if main_sequence is not None:
        # Update subtitlesList property with absolute path
        subtitles_list = [
            {
                "file": ass_path,
                "id": 0,
                "name": "Subtitles"
            }
        ]
        set_property(main_sequence, 'kdenlive:sequenceproperties.subtitlesList',
                     json.dumps(subtitles_list, indent=4))

        # Check if subtitle filter exists
        has_subtitle = False
        for filt in main_sequence.findall('filter'):
            if get_property(filt, 'mlt_service') == 'avfilter.subtitles':
                # Update existing filter with relative filename
                set_property(filt, 'av.filename', ass_filename)
                has_subtitle = True
                break

        if not has_subtitle:
            # Find highest filter id
            max_filter_id = 0
            for elem in root.iter():
                elem_id = elem.get('id', '')
                if elem_id.startswith('filter'):
                    try:
                        num = int(elem_id[6:])
                        max_filter_id = max(max_filter_id, num)
                    except ValueError:
                        pass

            # Add new subtitle filter with relative filename
            subtitle_filter = ET.SubElement(main_sequence, 'filter')
            subtitle_filter.set('id', f'filter{max_filter_id + 1}')

            svc_prop = ET.SubElement(subtitle_filter, 'property')
            svc_prop.set('name', 'mlt_service')
            svc_prop.text = 'avfilter.subtitles'

            alpha_prop = ET.SubElement(subtitle_filter, 'property')
            alpha_prop.set('name', 'av.alpha')
            alpha_prop.text = '1'

            internal_prop = ET.SubElement(subtitle_filter, 'property')
            internal_prop.set('name', 'internal_added')
            internal_prop.text = '237'

            file_prop = ET.SubElement(subtitle_filter, 'property')
            file_prop.set('name', 'av.filename')
            file_prop.text = ass_filename

            kf_prop = ET.SubElement(subtitle_filter, 'property')
            kf_prop.set('name', 'kdenlive:filter')
            kf_prop.text = 'subtitles'

    # Write output file
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"Generated: {output_path}")

    # Summary
    print(f"\nProject Summary:")
    print(f"  Template: {template_path}")
    if new_video_path:
        print(f"  Video: {new_video_path}")
    print(f"  Segments: {len(segments)}")
    print(f"  Timeline duration: {total_duration_seconds:.1f}s ({timeline_frames} frames)")
    print(f"  FPS: {fps}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    template_path = sys.argv[1]
    config_path = sys.argv[2]
    output_path = sys.argv[3]

    generate_project(template_path, config_path, output_path)
