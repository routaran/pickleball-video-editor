# MLT XML Templates for Kdenlive

This document describes the structure used by Kdenlive project files, based on analysis of real Kdenlive-generated projects.

## Project Structure Overview

Kdenlive projects use a nested hierarchy:

```
mlt (root)
├── profile          - Video specifications
├── producer         - Black background generator
├── chain (x3)       - Video file references (audio, video, bin)
├── playlist (x8)    - Track content containers
├── tractor (x4)     - Track mixers (audio/video pairs)
├── tractor          - Main sequence (UUID-based)
├── playlist         - main_bin with document properties
└── tractor          - Project root (kdenlive:projectTractor)
```

## Key Elements

### Profile
```xml
<profile
  description="HD 1080p 60 fps"
  width="1920"
  height="1080"
  progressive="1"
  sample_aspect_num="1"
  sample_aspect_den="1"
  display_aspect_num="16"
  display_aspect_den="9"
  frame_rate_num="60"
  frame_rate_den="1"
  colorspace="709"/>
```

### Chain Elements (Video Source)

Kdenlive uses `<chain>` instead of `<producer>` for video files, with `avformat-novalidate` service:

```xml
<chain id="chain0" out="00:14:01.417">
  <property name="length">50485</property>
  <property name="eof">pause</property>
  <property name="resource">/path/to/video.mp4</property>
  <property name="mlt_service">avformat-novalidate</property>
  <property name="seekable">1</property>
  <property name="kdenlive:id">4</property>
  <property name="kdenlive:clipname">video.mp4</property>
  <property name="kdenlive:folderid">-1</property>
  <property name="kdenlive:clip_type">0</property>
  <property name="kdenlive:file_size">1071795054</property>
  <property name="kdenlive:file_hash">ab3da0de7be19cc447595664c20a4dc4</property>
</chain>
```

**Note:** Three identical chains are created:
- `chain0` - Referenced by audio playlist
- `chain1` - Referenced by video playlist
- `chain2` - Referenced by main_bin

### Playlists with Entries

Audio and video are in separate playlists. Entries use timecode format:

```xml
<!-- Audio playlist -->
<playlist id="playlist2">
  <property name="kdenlive:audio_track">1</property>
  <entry in="00:00:00.000" out="00:00:02.483" producer="chain0">
    <property name="kdenlive:id">4</property>
  </entry>
  <entry in="00:00:05.000" out="00:00:07.483" producer="chain0">
    <property name="kdenlive:id">4</property>
  </entry>
</playlist>

<!-- Video playlist -->
<playlist id="playlist4">
  <entry in="00:00:00.000" out="00:00:02.483" producer="chain1">
    <property name="kdenlive:id">4</property>
  </entry>
  <entry in="00:00:05.000" out="00:00:07.483" producer="chain1">
    <property name="kdenlive:id">4</property>
  </entry>
</playlist>
```

### Track Tractors

Each track pair (main + mix) gets its own tractor with audio filters:

```xml
<tractor id="tractor1" in="00:00:00.000" out="00:00:13.333">
  <property name="kdenlive:audio_track">1</property>
  <property name="kdenlive:trackheight">62</property>
  <property name="kdenlive:timeline_active">1</property>
  <property name="kdenlive:collapsed">0</property>
  <track hide="video" producer="playlist2"/>
  <track hide="video" producer="playlist3"/>

  <!-- Default audio filters (disabled) -->
  <filter id="filter3">
    <property name="mlt_service">volume</property>
    <property name="disable">1</property>
  </filter>
  <filter id="filter4">
    <property name="mlt_service">panner</property>
    <property name="disable">1</property>
  </filter>
  <filter id="filter5">
    <property name="mlt_service">audiolevel</property>
    <property name="disable">1</property>
  </filter>
</tractor>
```

### Main Sequence Tractor

The sequence tractor combines all tracks with transitions:

```xml
<tractor id="{uuid}" in="00:00:00.000" out="00:00:13.333">
  <property name="kdenlive:uuid">{uuid}</property>
  <property name="kdenlive:clipname">Sequence 1</property>
  <property name="kdenlive:sequenceproperties.hasAudio">1</property>
  <property name="kdenlive:sequenceproperties.hasVideo">1</property>
  <property name="kdenlive:duration">00:00:13.333</property>
  <property name="kdenlive:producer_type">17</property>

  <!-- Tracks -->
  <track producer="producer0"/>   <!-- black background -->
  <track producer="tractor0"/>    <!-- audio track 1 -->
  <track producer="tractor1"/>    <!-- audio track 2 (content) -->
  <track producer="tractor2"/>    <!-- video track (content) -->
  <track producer="tractor3"/>    <!-- video track 2 -->

  <!-- Audio mix transitions -->
  <transition id="transition0">
    <property name="a_track">0</property>
    <property name="b_track">1</property>
    <property name="mlt_service">mix</property>
    <property name="always_active">1</property>
    <property name="sum">1</property>
  </transition>

  <!-- Video composite transitions -->
  <transition id="transition2">
    <property name="a_track">0</property>
    <property name="b_track">3</property>
    <property name="mlt_service">qtblend</property>
    <property name="always_active">1</property>
  </transition>

  <!-- Subtitle filter -->
  <filter id="filter8">
    <property name="mlt_service">avfilter.subtitles</property>
    <property name="av.filename">/path/to/subtitles.srt</property>
  </filter>
</tractor>
```

### Main Bin Playlist

Contains document properties and clip references:

```xml
<playlist id="main_bin">
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.kdenliveversion">25.12.1</property>
  <property name="kdenlive:docproperties.uuid">{sequence-uuid}</property>
  <property name="kdenlive:docproperties.profile">atsc_1080p_60</property>
  <property name="kdenlive:folder.-1.2">Sequences</property>
  <property name="kdenlive:sequenceFolder">2</property>

  <!-- Sequence reference -->
  <entry in="00:00:00.000" out="00:00:13.333" producer="{sequence-uuid}"/>
  <!-- Source clip reference -->
  <entry in="00:00:00.000" out="00:14:01.417" producer="chain2"/>
</playlist>
```

### Project Root Tractor

```xml
<tractor id="tractor4" in="00:00:00.000" out="00:00:13.333">
  <property name="kdenlive:projectTractor">1</property>
  <track in="00:00:00.000" out="00:00:13.333" producer="{sequence-uuid}"/>
</tractor>
```

## Timecode Format

Kdenlive uses `HH:MM:SS.mmm` format (note: period, not comma):

```
00:00:00.000  = 0 seconds
00:00:01.500  = 1.5 seconds
00:14:01.417  = 841.417 seconds
```

## Frame to Timecode Conversion

```python
def frames_to_timecode(frames: int, fps: float) -> str:
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
```

## Track Layout

Kdenlive's default track structure:

| Track Index | Type | Content |
|-------------|------|---------|
| 0 | - | Black background (producer0) |
| 1 | Audio | Empty audio track (tractor0) |
| 2 | Audio | Audio content track (tractor1) |
| 3 | Video | Video content track (tractor2) |
| 4 | Video | Empty video track (tractor3) |

## Transitions

- **Audio mixing**: `mix` service with `sum=1`
- **Video compositing**: `qtblend` service (Qt-based alpha blending)

Both use `always_active=1` to apply continuously.

## Important Properties

| Property | Purpose |
|----------|---------|
| `kdenlive:projectTractor` | Marks the root project tractor |
| `kdenlive:audio_track` | Marks audio-only tracks |
| `kdenlive:producer_type=17` | Identifies timeline sequences |
| `hide="video"` | Audio-only track |
| `hide="audio"` | Video-only track |
| `internal_added=237` | Kdenlive auto-generated element |
