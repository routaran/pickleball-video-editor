# SessionManager Usage Guide

## Overview

The `SessionManager` class handles persistence of editing sessions to JSON files. Sessions are automatically identified by a hash of the first 64KB of the video file, enabling automatic session detection and resumption.

## Basic Usage

```python
from src.core import SessionManager, SessionState

# Initialize manager (uses default directory ~/.local/share/pickleball-editor/sessions/)
manager = SessionManager()

# Or use custom directory
manager = SessionManager(session_dir=Path("/custom/path"))
```

## Common Workflows

### 1. Starting a New Session

```python
from src.core import SessionManager, SessionState

manager = SessionManager()
video_path = "/path/to/match.mp4"

# Check if session already exists
if manager.find_existing(video_path):
    print("Session exists - use resume workflow instead")
else:
    # Create new session state
    state = SessionState(
        video_path=video_path,
        game_type="doubles",
        victory_rules="11",
        player_names={
            "team1": ["Alice", "Bob"],
            "team2": ["Charlie", "Diana"]
        },
        current_score=[0, 0, 2],
        serving_team=0,
        server_number=2,
    )

    # Save initial session
    manager.save(state, video_path)
```

### 2. Resuming an Existing Session

```python
# Check for existing session
session_path = manager.find_existing(video_path)

if session_path:
    # Get summary info for display
    info = manager.get_session_info(video_path)
    print(f"Found session with {info['rally_count']} rallies")
    print(f"Current score: {info['current_score']}")
    print(f"Last position: {info['last_position']:.1f}s")

    # Load full session
    state = manager.load(video_path)

    # Restore UI state
    restore_score(state.current_score)
    restore_rallies(state.rallies)
    video_player.seek(state.last_position)
```

### 3. Saving During Editing

```python
# Update session state during editing
state.current_score = [5, 3, 1]
state.last_position = video_player.get_position()
state.rallies.append(new_rally)

# Save updated state
manager.save(state, video_path)
```

### 4. Auto-Save on Exit

```python
def on_window_close():
    """Save session automatically when closing window."""
    # Collect current state
    state.last_position = video_player.get_position()
    state.current_score = score_state.get_score()
    state.rallies = rally_manager.get_rallies()

    # Save before exit
    manager.save(state, video_path)
```

### 5. Starting Fresh (Delete Old Session)

```python
# User clicks "Start Fresh" instead of "Resume"
video_path = "/path/to/match.mp4"

if manager.find_existing(video_path):
    # Delete old session
    manager.delete(video_path)

# Create new session
state = SessionState(...)
manager.save(state, video_path)
```

## Session File Format

Sessions are stored as JSON in `~/.local/share/pickleball-editor/sessions/`

**Filename:** `{video_hash}.json` (SHA256 hash of first 64KB of video)

**Example:** `a3f2aae005979fde2c5f9861ed30924e891845c5564c27b8bc171fb1d1e1749c.json`

**Contents:**
```json
{
  "version": "1.0",
  "video_path": "/path/to/video.mp4",
  "video_hash": "a3f2aae005979fde...",
  "game_type": "doubles",
  "victory_rules": "11",
  "player_names": {
    "team1": ["Alice", "Bob"],
    "team2": ["Charlie", "Diana"]
  },
  "rallies": [
    {
      "start_frame": 100,
      "end_frame": 500,
      "score_at_start": "0-0-2",
      "winner": "server",
      "comment": null
    }
  ],
  "current_score": [3, 2, 1],
  "serving_team": 0,
  "server_number": 1,
  "last_position": 45.5,
  "created_at": "2026-01-14T10:30:00",
  "modified_at": "2026-01-14T11:45:23",
  "interventions": [],
  "comments": []
}
```

## Integration with MainWindow

```python
class MainWindow(QMainWindow):
    def __init__(self, video_path: str, config: dict):
        super().__init__()

        self.video_path = video_path
        self.session_manager = SessionManager()

        # Try to resume existing session
        if self.session_manager.find_existing(video_path):
            self._resume_session()
        else:
            self._start_new_session(config)

    def _resume_session(self):
        """Resume from saved session."""
        state = self.session_manager.load(self.video_path)

        # Restore state
        self.score_state = ScoreState.from_dict(state.to_dict())
        self.rally_manager.rallies = state.rallies

        # Restore video position
        self.video_widget.seek(state.last_position)

    def _start_new_session(self, config: dict):
        """Start fresh session."""
        self.state = SessionState(
            video_path=self.video_path,
            game_type=config["game_type"],
            victory_rules=config["victory_rules"],
            player_names=config["player_names"],
        )

    def save_session(self):
        """Save current session state."""
        # Collect current state
        self.state.current_score = self.score_state.score
        self.state.serving_team = self.score_state.serving_team
        self.state.server_number = self.score_state.server_number
        self.state.rallies = self.rally_manager.get_rallies()
        self.state.last_position = self.video_widget.get_position()

        # Save to disk
        path = self.session_manager.save(self.state, self.video_path)

        # Show confirmation
        self.show_toast(f"Session saved: {path.name}")

    def closeEvent(self, event):
        """Auto-save on window close."""
        self.save_session()
        event.accept()
```

## Error Handling

The `SessionManager` uses the LBYL (Look Before You Leap) pattern and returns `None` or `False` for errors rather than raising exceptions:

```python
# All these return None gracefully
manager.load("/nonexistent/video.mp4")      # Returns None
manager.load("")                             # Returns None
manager.find_existing("/invalid/path")       # Returns None
manager.get_session_info("/missing.mp4")     # Returns None

# Delete returns False if file doesn't exist
manager.delete("/nonexistent.mp4")           # Returns False
```

**Check results before using:**

```python
state = manager.load(video_path)
if state is None:
    # Handle missing/corrupt session
    print("Could not load session, starting fresh")
    state = create_new_session()
```

## Performance Notes

1. **Fast Hashing**: Only the first 64KB of the video file is hashed, making session detection instant even for large video files.

2. **Collision Risk**: The 64KB hash is sufficient to uniquely identify video files in practice. True collisions (different videos with identical first 64KB) are extremely unlikely.

3. **File I/O**: Session saves are fast (typically <50ms) due to JSON serialization and small file sizes (typically <50KB even with hundreds of rallies).

## Testing

Run the test suite:

```bash
python test_session_manager.py
```

Expected output:
```
Session directory: /tmp/tmpxxx
Created test video: /tmp/tmpxxx/test_video.mp4

--- Test 1: Check for existing session ---
...
✅ All tests passed!
```
