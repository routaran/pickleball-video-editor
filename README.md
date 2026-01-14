# Pickleball Video Editor

A desktop application for marking rally timestamps in pickleball videos, calculating scores automatically, and generating Kdenlive project files.

## Features

- Mark rally start/end points with keyboard shortcuts
- Automatic pickleball score calculation (Singles and Doubles)
- Embedded video playback with libmpv
- Generate Kdenlive XML project files with rally-only clips
- Session persistence (save/load work in progress)
- Review mode with rally timeline navigation

## System Dependencies

### Manjaro Linux / Arch-based

Install required system packages:

```bash
sudo pacman -S mpv ffmpeg qt6-base python
```

### Other Linux Distributions

Ensure you have:
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
# From the project root with venv activated
python -m src.main

# Or using the entry point (after pip install -e .)
pickleball-editor
```

### Workflow

1. **Setup**: Select video file, choose game type (Singles/Doubles), set initial score
2. **Mark Rallies**: Use keyboard shortcuts to mark rally start/end and outcomes
3. **Review**: Navigate through marked rallies, make adjustments
4. **Export**: Generate Kdenlive project file with rally clips and score overlays

## Project Structure

```
pickleball_editing/
├── src/
│   ├── main.py              # Application entry point
│   ├── app.py               # QApplication setup
│   ├── core/                # Business logic (models, scoring, rally management)
│   ├── video/               # Video playback (MPV wrapper, FFprobe)
│   ├── ui/                  # GUI components (PyQt6 widgets, dialogs, styles)
│   └── output/              # Export generators (Kdenlive XML, subtitles)
├── resources/               # Icons and assets
├── tests/                   # Unit and integration tests
├── docs/                    # Design documents and specifications
├── requirements.txt         # Python dependencies
└── pyproject.toml          # Project metadata and build config
```

## Development

### Type Checking

```bash
mypy src/
```

### Code Formatting

```bash
black src/
ruff check src/
```

### Running Tests

```bash
pytest tests/
```

## Technology Stack

- **GUI Framework**: PyQt6
- **Video Playback**: python-mpv (libmpv bindings)
- **Video Metadata**: FFprobe
- **XML Generation**: lxml
- **Persistence**: JSON

## License

MIT

## Contributing

This project is in active development. See `TODO.md` for current tasks and `docs/` for detailed specifications.
