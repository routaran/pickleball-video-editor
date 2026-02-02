# Pickleball Video Editor

A desktop application for marking rally timestamps in pickleball game videos, automatically calculating scores, and exporting highlight videos with score overlays. Supports direct MP4 export with hardware acceleration or Kdenlive project generation for advanced editing.

## What It Does

**Turn hours of raw pickleball footage into polished highlight videos in minutes.**

1. **Mark rallies** - Play your video and mark the start/end of each rally with simple keyboard shortcuts
2. **Automatic scoring** - The app tracks the score using official pickleball rules (singles and doubles)
3. **Export** - Generate a ready-to-share MP4 with embedded subtitles, or a Kdenlive project for advanced editing

No more scrubbing through hours of footage. No more manually typing scores. Just mark, review, and export.

## Features

- **Embedded video player** with frame-accurate seeking and playback speed control (0.5x, 1x, 2x)
- **Singles and Doubles scoring** with automatic side-out detection and server rotation
- **Highlights mode** for creating cuts without score tracking
- **Session auto-save** - Resume editing anytime, even if you close the app
- **Review mode** - Visual clip timeline, adjust rally timing, correct scores before export
- **FFmpeg direct export** - Generate MP4 with embedded subtitles and hardware acceleration (NVENC)
- **Kdenlive XML export** - For advanced editing with sequential rally clips and ASS subtitles
- **Non-blocking export** - Continue editing while video encodes in the background
- **Configurable encoder profiles** - Customize FFmpeg settings via config file
- **Multi-game sessions** - Start new games without restarting the app
- **Configurable keyboard shortcuts** and skip durations
- **Player/team names** - Optional, can be added or updated anytime during editing

## Installation

### System Requirements

| Requirement | Version |
|-------------|---------|
| Linux | Manjaro/Arch, Ubuntu/Debian, Fedora |
| Python | 3.13+ |
| libmpv | 0.35+ |
| ffmpeg | Any recent version |
| Qt6 | 6.6+ |

### Install System Dependencies

**Arch/Manjaro:**
```bash
sudo pacman -S mpv ffmpeg qt6-base python
```

**Ubuntu/Debian:**
```bash
sudo apt install libmpv-dev ffmpeg qt6-base-dev python3.13 python3.13-venv
```

**Fedora:**
```bash
sudo dnf install mpv-devel ffmpeg qt6-qtbase-devel python3.13
```

### Build from Source

```bash
# Clone the repository
git clone https://github.com/routaran/pickleball-video-editor.git
cd pickleball-video-editor

# Configure (checks dependencies, creates virtual environment, installs packages)
./configure

# Build the executable
make

# Run tests (optional)
make test

# Install system-wide
sudo make install

# Or install to your home directory
make install PREFIX=~/.local
```

### Development Setup

```bash
# Configure with development tools (pytest, ruff, mypy, black)
./configure --enable-dev

# Run in development mode (without building)
make run

# Run linters
make lint

# Format code
make format
```

## Usage

### Quick Start

1. **Launch the application**
   ```bash
   pickleball-editor
   # Or in development mode:
   make run
   ```

2. **Create a new session**
   - Click "Browse" to select your video file
   - Choose game type: Singles, Doubles, or Highlights
   - Select victory rules: Game to 11, Game to 9, or Timed
   - Player/team names are optional (can be added later via "Names" button)
   - Click "Start Editing"

3. **Mark rallies**
   - Press **C** to mark rally start
   - Press **S** if server wins, **R** if receiver wins
   - Repeat for all rallies
   - Use **U** to undo mistakes

4. **Review and export**
   - Click "Final Review" to see the visual clip timeline
   - Adjust timing with +/- buttons if needed
   - Choose export format:
     - **Export MP4** - Direct video with embedded subtitles (recommended)
     - **Generate Kdenlive** - Project file for advanced editing

5. **Multi-game sessions**
   - Click "New Game" to start a fresh game without restarting
   - Change settings (game type, players) when starting a new game
   - Previous game data is cleared

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **C** | Mark rally start |
| **S** | Server wins (mark rally end) |
| **R** | Receiver wins (mark rally end) |
| **U** | Undo last action |
| **Space** | Play/Pause |
| **Left/Right** | Skip backward/forward |
| **Up/Down** | Large skip backward/forward |

All shortcuts are configurable in Settings.

### Playback Controls

| Control | Action |
|---------|--------|
| Skip -5s | Jump back 5 seconds |
| Skip -1s | Jump back 1 second |
| Play/Pause | Toggle playback |
| Skip +1s | Jump forward 1 second |
| Skip +5s | Jump forward 5 seconds |
| Speed | 0.5x / 1x / 2x playback |

### Scoring Rules

**Singles (X-Y format):**
- Server's score listed first
- Side-out occurs when server loses rally
- Example: `5-3` (server has 5, receiver has 3)

**Doubles (X-Y-Z format):**
- Format: Serving score - Receiving score - Server number
- Game starts at `0-0-2` (serving team begins as Server 2)
- Only serving team can score points
- First fault by Server 1 causes immediate side-out
- Example: `7-4-1` (serving team has 7, receiving has 4, Server 1 serving)

**Victory Rules:**
- **Game to 11**: First to 11 points, win by 2
- **Game to 9**: First to 9 points, win by 2
- **Timed**: Higher score when time expires

### Interventions

During editing, you can manually correct the game state:

- **Edit Score** - Fix any scoring errors
- **Force Side-Out** - Manually trigger a side-out
- **Add Comment** - Add timestamped notes (exceptional plays, referee calls)
- **Time Expired** - End timed games manually
- **Mark Game Completed** - Record final score with winner

### Highlights Mode

For quick highlight compilations without score tracking:

- Select "Highlights" as game type during setup
- No player names or victory rules needed
- Simplified controls: just "Mark Start" and "Mark End"
- Press **C** to mark clip start, **S** to mark clip end
- Export generates video cuts without score subtitles

### Export Options

**FFmpeg Direct Export (MP4):**
- Generates a ready-to-share MP4 file with embedded score subtitles
- Hardware acceleration (NVENC) when available, falls back to libx264
- Non-blocking: continue editing while video encodes in the background
- Configurable encoder profiles (see Configuration section)

**Kdenlive Project Export:**
- Generates `.kdenlive` project file for advanced editing
- Includes separate ASS subtitle file for score overlays
- Rally clips are pre-arranged on the timeline
- Open in Kdenlive for color grading, transitions, or additional edits

### Output Files

After export, find your files:

**FFmpeg Export** (user-selected location):

| File | Description |
|------|-------------|
| `{video}.mp4` | Ready-to-share video with embedded subtitles |

**Kdenlive Export** (`~/Videos/pickleball/`):

| File | Description |
|------|-------------|
| `{video}_rallies.kdenlive` | Kdenlive project with rally clips |
| `{video}_rallies.kdenlive.ass` | Score subtitles (ASS format) |

**Rally Timing:**
- Clips start 0.5 seconds before marked rally start
- Clips end 1.0 second after marked rally end

## Configuration

Access settings via the Settings button:

| Tab | Options |
|-----|---------|
| **Shortcuts** | Customize keyboard shortcuts for rally marking |
| **Skip Durations** | Configure playback skip amounts |
| **Window Size** | Set min/max window dimensions |

**File Locations:**
- Settings: `~/.config/pickleball-editor/config.json`
- Sessions: `~/.local/share/pickleball-editor/sessions/`

### Encoder Profiles

Customize FFmpeg export by editing `~/.config/pickleball-editor/config.json`:

```json
{
  "encoder": {
    "active_profile": "auto",
    "profiles": {
      "nvenc_quality": {
        "codec": "h264_nvenc",
        "preset": "p5",
        "rate_control": ["-rc", "constqp", "-qp", "20"],
        "extra_video_opts": ["-rc-lookahead", "32", "-spatial-aq", "1"],
        "audio_codec": "aac",
        "audio_bitrate": "192k"
      }
    }
  }
}
```

| Setting | Description |
|---------|-------------|
| `active_profile` | `"auto"` for hardware detection, or a profile name |
| `profiles` | Named encoder configurations |

**Built-in profiles:**
- `nvenc_quality` - NVIDIA hardware encoding, high quality
- `nvenc_fast` - NVIDIA hardware encoding, faster
- `x264_quality` - Software encoding, high quality (CRF 18)
- `x264_fast` - Software encoding, faster (CRF 23)

**Custom profiles:** Add your own with any FFmpeg codec, preset, and rate control options.

## Build System

This project uses a GNU-style build system:

```bash
./configure [OPTIONS]    # Configure build environment
make                     # Build executable
make install             # Install to PREFIX
make uninstall           # Remove installed files
make clean               # Remove build artifacts
make distclean           # Full reset
make test                # Run tests
make lint                # Run linters
make help                # Show all targets
```

### Configure Options

| Option | Description |
|--------|-------------|
| `--prefix=DIR` | Installation prefix (default: /usr/local) |
| `--python=CMD` | Python command (default: python3.13) |
| `--enable-dev` | Install development dependencies |
| `--disable-venv` | Use system Python |
| `--help` | Show all options |

## Project Structure

```
pickleball-video-editor/
├── src/
│   ├── main.py              # Entry point
│   ├── app.py               # QApplication setup
│   ├── core/                # Business logic
│   │   ├── models.py        # Data models
│   │   ├── score_state.py   # Scoring state machine
│   │   ├── rally_manager.py # Rally tracking
│   │   └── session_manager.py
│   ├── video/               # Video playback
│   │   ├── player.py        # MPV widget
│   │   └── probe.py         # FFprobe metadata
│   ├── ui/                  # GUI components
│   │   ├── main_window.py
│   │   ├── setup_dialog.py
│   │   ├── review_mode.py
│   │   ├── dialogs/
│   │   └── widgets/
│   └── output/              # Export generators
│       ├── kdenlive_generator.py
│       ├── ffmpeg_exporter.py
│       ├── hardware_detect.py
│       └── subtitle_generator.py
├── tests/                   # 200+ unit tests
├── resources/               # Icons and assets
├── configure                # Build configuration
├── Makefile                 # Build system
└── pickleball-editor.spec   # PyInstaller spec
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| GUI | PyQt6 |
| Video Playback | python-mpv (libmpv) |
| Video Export | FFmpeg (NVENC/libx264) |
| Metadata | FFprobe |
| Kdenlive Export | lxml (MLT XML) |
| Build | PyInstaller |
| Tests | pytest |

## Development

```bash
# Run tests
make test

# Run with coverage
make test-coverage

# Type checking
make lint

# Format code
make format

# Run specific tests
.venv/bin/pytest tests/test_score_state.py -v
```

## Known Limitations

- Linux only (tested on Manjaro/Arch)
- Requires X11 for video playback (Wayland uses XWayland)
- Large 4K videos may have slower seeking

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests and linting (`make test && make lint`)
4. Commit your changes
5. Open a Pull Request

## License

[MIT License](https://mit-license.org/)

## Acknowledgments

- [MPV](https://mpv.io/) - Video player
- [Kdenlive](https://kdenlive.org/) - Video editor
- [PyQt6](https://riverbankcomputing.com/software/pyqt/) - GUI framework
