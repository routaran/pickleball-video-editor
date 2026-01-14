# Tech Stack Specification
## Pickleball Video Editor Tool

**Version:** 1.0
**Date:** 2026-01-14
**Status:** Approved

---

## 1. Technology Summary

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.13.11 |
| GUI Framework | PyQt6 | Latest |
| Video Playback | python-mpv (libmpv) | Latest |
| XML Generation | Built-in xml.etree / lxml | - |
| Data Format | JSON | - |
| Video Probing | ffprobe (FFmpeg) | Latest |
| Platform | Manjaro Linux (Arch-based) | - |

---

## 2. Core Dependencies

### 2.1 System Packages (pacman)

```bash
# Core dependencies
sudo pacman -S python python-pip
sudo pacman -S mpv
sudo pacman -S ffmpeg
sudo pacman -S qt6-base

# For python-mpv
sudo pacman -S mpv libmpv
```

### 2.2 Python Packages (pip)

```bash
# GUI framework
pip install PyQt6

# MPV integration
pip install python-mpv

# Optional: Better XML handling
pip install lxml
```

### 2.3 Package Versions (requirements.txt)

```
PyQt6>=6.6.0
python-mpv>=1.0.0
lxml>=5.0.0
```

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Pickleball Video Editor                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────┐   │
│   │                 │   │                 │   │                     │   │
│   │   GUI Layer     │   │   Video Layer   │   │   Output Layer      │   │
│   │   (PyQt6)       │   │   (python-mpv)  │   │   (Kdenlive Gen)    │   │
│   │                 │   │                 │   │                     │   │
│   └────────┬────────┘   └────────┬────────┘   └──────────┬──────────┘   │
│            │                     │                       │              │
│            └─────────────────────┼───────────────────────┘              │
│                                  │                                      │
│                    ┌─────────────▼─────────────┐                        │
│                    │                           │                        │
│                    │     Application Core      │                        │
│                    │                           │                        │
│                    │  • Score State Machine    │                        │
│                    │  • Rally Manager          │                        │
│                    │  • Session Manager        │                        │
│                    │  • Event Store            │                        │
│                    │                           │                        │
│                    └─────────────┬─────────────┘                        │
│                                  │                                      │
│                    ┌─────────────▼─────────────┐                        │
│                    │                           │                        │
│                    │     Data Persistence      │                        │
│                    │     (JSON Files)          │                        │
│                    │                           │                        │
│                    └───────────────────────────┘                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Details

### 4.1 GUI Layer (PyQt6)

**Main Window Structure:**
```python
QMainWindow
├── QWidget (central widget)
│   ├── QVBoxLayout
│   │   ├── QWidget (MPV container)  # Video player embedded here
│   │   ├── QHBoxLayout (playback controls)
│   │   ├── QFrame (state bar)
│   │   ├── QHBoxLayout (rally controls)
│   │   ├── QHBoxLayout (interventions)
│   │   └── QHBoxLayout (session controls)
```

**Key PyQt6 Components:**
- `QMainWindow` - Main application window
- `QDialog` - Modal dialogs (Setup, Edit Score, etc.)
- `QPushButton` - All buttons with custom styling
- `QLabel` - State display, timestamps
- `QLineEdit` - Text inputs (scores, comments)
- `QComboBox` - Dropdowns (game type, victory rules)
- `QFileDialog` - Video file selection
- `QMessageBox` - Warnings and confirmations

**Styling:**
- Qt Style Sheets (QSS) for button colors and states
- Custom palette for dark theme compatibility

### 4.2 Video Layer (python-mpv)

**MPV Embedding in PyQt6:**
```python
import mpv

class VideoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

        self.player = mpv.MPV(
            wid=str(int(self.winId())),
            vo='gpu',
            hwdec='auto',
            input_default_bindings=True,
            input_vo_keyboard=True,  # Allow arrow keys
            osd_level=1
        )
```

**Key MPV Features Used:**
- `wid` parameter for embedding in Qt widget
- `time-pos` property for current timestamp
- `duration` property for video length
- `pause` property for play/pause control
- `speed` property for playback speed
- `frame-step` / `frame-back-step` for frame stepping
- `seek` command for navigation
- `osd-msg` for on-screen display messages

**Timestamp Precision:**
- MPV provides timestamps in seconds with millisecond precision
- Convert to frames: `frame = int(timestamp * fps)`
- Convert to timecode for Kdenlive: `HH:MM:SS.mmm`

### 4.3 Output Layer (Kdenlive Generation)

**Existing Generator:**
Located at `.claude/skills/kdenlive-generator/scripts/generate_project.py`

**Input Format (JSON config):**
```json
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
```

**Output Files:**
- `.kdenlive` - MLT XML project file
- `.srt` - Subtitle file with scores

**Key Functions to Reuse:**
- `probe_video()` - Extract video metadata via ffprobe
- `frames_to_timecode()` - Convert frames to `HH:MM:SS.mmm`
- `generate_srt()` - Create subtitle content
- `generate_kdenlive_xml()` - Create MLT XML

### 4.4 Application Core

**Score State Machine:**
```python
class ScoreState:
    """Manages pickleball scoring rules."""

    def __init__(self, game_type: str, victory_rules: str):
        self.game_type = game_type  # "singles" | "doubles"
        self.victory_rules = victory_rules  # "11" | "9" | "timed"

        # Score state
        if game_type == "singles":
            self.score = [0, 0]  # [server_score, receiver_score]
        else:
            self.score = [0, 0, 2]  # [team1, team2, server_num]

        self.serving_team = 0  # 0 or 1
        self.server_number = 2 if game_type == "doubles" else None

    def server_wins(self) -> None:
        """Handle server winning a rally."""
        # Increment serving team's score
        # Check for game over

    def receiver_wins(self) -> None:
        """Handle receiver winning a rally."""
        # Handle side-out logic

    def is_game_over(self) -> tuple[bool, int]:
        """Check if game is over, return (is_over, winner)."""
```

**Rally Manager:**
```python
@dataclass
class Rally:
    start_frame: int
    end_frame: int
    score_at_start: str
    winner: str  # "server" | "receiver"
    comment: Optional[str] = None

class RallyManager:
    rallies: list[Rally]
    current_rally_start: Optional[int]

    def start_rally(self, frame: int) -> None
    def end_rally(self, frame: int, winner: str) -> None
    def undo_last_action(self) -> None
    def get_rally_count(self) -> int
```

**Session Manager:**
```python
@dataclass
class SessionState:
    video_path: str
    game_type: str
    victory_rules: str
    player_names: dict
    rallies: list[Rally]
    current_score: list[int]
    serving_team: int
    server_number: Optional[int]
    last_position: float
    created_at: str
    modified_at: str

class SessionManager:
    def save(self, path: str) -> None
    def load(self, path: str) -> SessionState
    def find_existing(self, video_path: str) -> Optional[str]
```

---

## 5. Data Persistence

### 5.1 Session File Format

**Location:** `~/.local/share/pickleball-editor/sessions/`
**Filename:** `{video_hash}.json`

```json
{
    "version": "1.0",
    "video_path": "/home/user/Videos/match.mp4",
    "video_hash": "abc123...",
    "game_type": "doubles",
    "victory_rules": "11",
    "player_names": {
        "team1": ["John", "Jane"],
        "team2": ["Bob", "Alice"]
    },
    "rallies": [
        {
            "start_frame": 1534,
            "end_frame": 2610,
            "score_at_start": "0-0-2",
            "winner": "server",
            "comment": null
        }
    ],
    "current_score": [1, 0, 1],
    "serving_team": 0,
    "server_number": 1,
    "last_position": 45.23,
    "created_at": "2026-01-14T10:30:00",
    "modified_at": "2026-01-14T11:45:00"
}
```

### 5.2 Debug Output Format

**Location:** `~/Videos/debug/`
**Filename:** `{video_name}.json`

```json
{
    "version": "1.0",
    "video_path": "/home/user/Videos/match.mp4",
    "game_info": {
        "type": "doubles",
        "victory_rules": "11",
        "winner": "team1",
        "final_score": "11-9"
    },
    "player_names": {
        "team1": ["John", "Jane"],
        "team2": ["Bob", "Alice"]
    },
    "rallies": [
        {
            "number": 1,
            "start_time": "00:00:25.567",
            "end_time": "00:00:43.500",
            "start_frame": 1534,
            "end_frame": 2610,
            "score": "0-0-2",
            "winner": "server",
            "result_score": "1-0-1",
            "comment": null
        }
    ],
    "interventions": [
        {
            "type": "score_edit",
            "timestamp": "00:05:30.000",
            "old_score": "5-3-2",
            "new_score": "5-4-2",
            "comment": "Missed a point"
        }
    ],
    "comments": [
        {
            "timestamp": "00:03:45.230",
            "text": "Great rally!",
            "duration": 5
        }
    ]
}
```

---

## 6. Directory Structure

```
pickleball-editor/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Application entry point
│   ├── app.py                  # QApplication setup
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py      # Main editing window
│   │   ├── setup_dialog.py     # Initial setup dialog
│   │   ├── review_mode.py      # Final review UI
│   │   ├── dialogs/
│   │   │   ├── __init__.py
│   │   │   ├── edit_score.py
│   │   │   ├── force_sideout.py
│   │   │   ├── add_comment.py
│   │   │   ├── game_over.py
│   │   │   ├── resume_session.py
│   │   │   └── unsaved_warning.py
│   │   ├── widgets/
│   │   │   ├── __init__.py
│   │   │   ├── video_widget.py     # MPV embed widget
│   │   │   ├── playback_controls.py
│   │   │   ├── state_bar.py
│   │   │   ├── rally_controls.py
│   │   │   └── rally_button.py     # Custom styled button
│   │   └── styles/
│   │       └── theme.qss           # Qt stylesheet
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── score_state.py      # Scoring state machine
│   │   ├── rally_manager.py    # Rally tracking
│   │   ├── session_manager.py  # Save/load sessions
│   │   └── models.py           # Data classes
│   │
│   ├── video/
│   │   ├── __init__.py
│   │   ├── player.py           # MPV player wrapper
│   │   └── probe.py            # Video metadata extraction
│   │
│   └── output/
│       ├── __init__.py
│       ├── kdenlive_generator.py   # Kdenlive XML generation
│       ├── subtitle_generator.py   # SRT generation
│       └── debug_export.py         # Debug JSON export
│
├── resources/
│   └── icons/                  # Button icons (optional)
│
├── tests/
│   ├── __init__.py
│   ├── test_score_state.py
│   ├── test_rally_manager.py
│   └── test_kdenlive_generator.py
│
├── docs/
│   ├── PRD.md
│   ├── UI_SPEC.md
│   ├── UI_PROTOTYPES.md
│   └── TECH_STACK.md
│
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 7. MPV Integration Details

### 7.1 Embedding MPV in PyQt6

```python
class VideoWidget(QWidget):
    """Widget that embeds MPV player."""

    position_changed = pyqtSignal(float)  # Current position in seconds
    duration_changed = pyqtSignal(float)  # Video duration

    def __init__(self, parent=None):
        super().__init__(parent)

        # Required for proper MPV embedding
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)

        # Create MPV player
        self.player = mpv.MPV(
            wid=str(int(self.winId())),
            vo='gpu',
            hwdec='auto-safe',
            input_default_bindings=True,
            input_vo_keyboard=True,
            osd_level=1,
            keep_open=True,
            idle=True
        )

        # Observe properties
        self.player.observe_property('time-pos', self._on_position)
        self.player.observe_property('duration', self._on_duration)

    def load(self, path: str):
        self.player.play(path)

    def play(self):
        self.player.pause = False

    def pause(self):
        self.player.pause = True

    def toggle_pause(self):
        self.player.pause = not self.player.pause

    def seek(self, seconds: float):
        self.player.seek(seconds, reference='absolute')

    def frame_step(self):
        self.player.frame_step()

    def frame_back_step(self):
        self.player.frame_back_step()

    def set_speed(self, speed: float):
        self.player.speed = speed

    def show_osd(self, message: str, duration: float = 2.0):
        self.player.show_text(message, int(duration * 1000))

    @property
    def position(self) -> float:
        return self.player.time_pos or 0.0

    @property
    def duration(self) -> float:
        return self.player.duration or 0.0
```

### 7.2 Frame-Accurate Timestamps

```python
def seconds_to_frame(seconds: float, fps: float) -> int:
    """Convert seconds to frame number."""
    return int(seconds * fps)

def frame_to_seconds(frame: int, fps: float) -> float:
    """Convert frame number to seconds."""
    return frame / fps

def frame_to_timecode(frame: int, fps: float) -> str:
    """Convert frame to Kdenlive timecode (HH:MM:SS.mmm)."""
    total_seconds = frame / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
```

---

## 8. Build and Distribution

> **Note:** Development setup instructions (virtual environment, installation, running the app) are in `README.md`.

### 8.1 PyInstaller (Optional)

For standalone executable distribution:

```bash
pip install pyinstaller

pyinstaller --onefile \
    --name="pickleball-editor" \
    --add-data="resources:resources" \
    src/main.py
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

- **Score State Machine**: Test all scoring rules for singles/doubles
- **Rally Manager**: Test rally start/end, undo functionality
- **Kdenlive Generator**: Test XML output validity

### 9.2 Integration Tests

- **MPV Integration**: Test video loading, seeking, frame stepping
- **Session Persistence**: Test save/load cycle
- **End-to-End**: Mark rallies, generate Kdenlive, verify output

### 9.3 Manual Testing

- Test with real pickleball footage
- Verify Kdenlive opens generated projects without errors
- Verify subtitle timing matches rallies

---

## 10. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| MPV embedding issues | Fall back to IPC socket if embedding fails |
| PyQt6 version conflicts | Pin specific version in requirements.txt |
| Kdenlive XML format changes | Template-based generation, easy to update |
| Large video file handling | Use memory-mapped file access, lazy loading |

---

## Appendix A: Existing Code Assets

### Kdenlive Generator
- **Location:** `.claude/skills/kdenlive-generator/scripts/generate_project.py`
- **Status:** Fully functional, can be imported directly
- **Capabilities:** Generates valid .kdenlive files with cuts and SRT subtitles

### Template
- **Location:** `.claude/skills/kdenlive-generator/templates/base_template.kdenlive`
- **Status:** Reference for XML structure
- **Note:** Generator creates XML programmatically, template for reference only

---

*Document Version: 1.0*
*Created: 2026-01-14*
