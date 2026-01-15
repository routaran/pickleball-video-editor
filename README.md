# Pickleball Video Editor

A desktop application for marking rally timestamps in pickleball videos, calculating scores automatically, and generating Kdenlive project files with rally-only clips and score overlays.

## Features

- **Rally Marking**: Mark rally start/end points with one-click buttons
- **Automatic Scoring**: Full pickleball score calculation for Singles and Doubles
- **Embedded Playback**: Video playback with libmpv (frame-accurate seeking)
- **Kdenlive Export**: Generate professional Kdenlive XML projects with rally clips
- **Session Persistence**: Save and resume editing sessions automatically
- **Final Review Mode**: Review rallies, adjust timings, edit scores before export

## Quick Start

```bash
# Install system dependencies (Arch/Manjaro)
sudo pacman -S mpv ffmpeg qt6-base python

# Clone and setup
git clone <repository-url>
cd pickleball_editing
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the application
python -m src.main
```

## System Dependencies

### Manjaro Linux / Arch-based

```bash
sudo pacman -S mpv ffmpeg qt6-base python
```

### Ubuntu/Debian

```bash
sudo apt install libmpv-dev ffmpeg libqt6-dev python3.13
```

### Requirements

- `libmpv` (version 0.35+)
- `ffmpeg` (for video probing)
- Qt6 libraries
- Python 3.13+

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd pickleball_editing
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   Or for development with testing tools:
   ```bash
   pip install -e ".[dev]"
   ```

## Usage

### Running the Application

```bash
# From project root with venv activated
python -m src.main

# Or using the entry point (after pip install -e .)
pickleball-editor
```

### Editing Workflow

1. **Setup Dialog**
   - Select your pickleball video file
   - Choose game type: Singles or Doubles
   - Select victory rules: Game to 11, Game to 9, or Timed
   - Enter player names
   - If a previous session exists, choose to Resume or Start Fresh

2. **Rally Marking (Main Window)**
   - Use playback controls to navigate to rally start
   - Click **Rally Start** to mark the beginning
   - Navigate to rally end
   - Click **Server Wins** or **Receiver Wins** to complete the rally
   - Score updates automatically based on pickleball rules
   - Use **Undo** to correct mistakes

3. **Interventions**
   - **Edit Score**: Manually correct any scoring errors
   - **Force Side-Out**: Fix serving errors
   - **Add Comment**: Add notes at specific timestamps
   - **Time Expired**: End timed games manually

4. **Final Review Mode**
   - Click **Final Review** to enter review mode
   - Navigate through all rallies using Previous/Next
   - Adjust timing with +/- 0.1s buttons
   - Edit scores with optional cascade to later rallies
   - Click **Generate Kdenlive** to export

5. **Export**
   - Generates `{video}_rallies.kdenlive` project file
   - Generates `{video}_scores.srt` subtitle file
   - Files saved to `~/Videos/pickleball/`

### Playback Controls

| Control | Action |
|---------|--------|
| ◀◀ | Skip back 5 seconds |
| ◀ | Skip back 1 second |
| ▶/⏸ | Play/Pause toggle |
| ▶ | Skip forward 1 second |
| ▶▶ | Skip forward 5 seconds |
| Speed | 0.5x / 1x / 2x playback |
| Arrow Keys | ±5 second skip (MPV native) |

### Session Management

Sessions are automatically saved to `~/.local/share/pickleball-editor/sessions/`. When you select a video with an existing session, you'll be prompted to resume or start fresh.

- **Save Session**: Manually save current progress
- **Auto-save prompt**: Asked before closing with unsaved changes

## Output Files

### Kdenlive Project (.kdenlive)

The generated project file includes:
- Rally clips extracted from the original video
- Score overlay subtitles
- Proper timeline structure for Kdenlive 25.x

### SRT Subtitles (.srt)

Standard SRT format subtitles showing the score at each rally:
```
1
00:00:00,000 --> 00:00:05,500
0-0-2

2
00:00:05,500 --> 00:00:12,300
1-0-2
```

## Project Structure

```
pickleball_editing/
├── src/
│   ├── main.py              # Application entry point
│   ├── app.py               # QApplication setup
│   ├── core/                # Business logic
│   │   ├── models.py        # Data models (Rally, ScoreSnapshot, etc.)
│   │   ├── score_state.py   # Pickleball scoring state machine
│   │   ├── rally_manager.py # Rally tracking with undo
│   │   └── session_manager.py # Session persistence
│   ├── video/               # Video handling
│   │   ├── player.py        # MPV wrapper widget
│   │   └── probe.py         # FFprobe metadata extraction
│   ├── ui/                  # GUI components
│   │   ├── main_window.py   # Main editing interface
│   │   ├── setup_dialog.py  # Initial configuration
│   │   ├── review_mode.py   # Final review interface
│   │   ├── dialogs/         # Modal dialogs
│   │   ├── widgets/         # Custom widgets
│   │   └── styles/          # Court Green theme
│   └── output/              # Export generators
│       ├── kdenlive_generator.py  # Kdenlive XML
│       └── subtitle_generator.py  # SRT subtitles
├── tests/                   # Test suite (54+ tests)
├── docs/                    # Design documents
├── requirements.txt         # Python dependencies
└── pyproject.toml          # Project metadata
```

## Development

### Running Tests

```bash
# Run all tests
./run_tests.sh

# Or with pytest directly
pytest tests/ -v

# Run specific test file
pytest tests/test_score_state.py
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Formatting
black src/
```

### Design Documents

See the `docs/` directory for detailed specifications:
- `PRD.md` - Product requirements
- `UI_SPEC.md` - UI/UX specifications
- `TECH_STACK.md` - Technology decisions
- `DETAILED_DESIGN.md` - Architecture details

## Technology Stack

| Component | Technology |
|-----------|------------|
| GUI Framework | PyQt6 |
| Video Playback | python-mpv (libmpv) |
| Video Metadata | FFprobe |
| XML Generation | Standard library |
| Persistence | JSON |
| Testing | pytest |

## Pickleball Scoring Rules

The application implements official pickleball scoring:

### Singles
- Server's score is called first, then receiver's
- Side-out on receiver win (serve switches)
- Score format: `X-Y` (e.g., "5-3")

### Doubles
- Game starts at 0-0-2 (server 2)
- First fault causes immediate side-out
- Server 1 → Server 2 → Side-out rotation
- Score format: `X-Y-Z` (e.g., "7-4-1")

### Win Conditions
- **Standard**: First to 11 (or 9), win by 2
- **Timed**: Higher score when time expires

## Known Limitations

- Requires manual installation of system dependencies
- Video playback requires X11 (Wayland support via XWayland)
- Large videos (4K+) may have slower seeking

## License

MIT

## Contributing

This project is in active development. See `TODO.md` for current tasks and open issues.

---

*Built with PyQt6 and libmpv for the pickleball community*
