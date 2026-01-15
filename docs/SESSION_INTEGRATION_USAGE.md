# Session Integration - Usage Guide

## For Users

### Starting a New Session

1. Launch the application
2. In SetupDialog, click "Browse" to select a video
3. If no session exists for this video:
   - Fill in game configuration
   - Enter player names
   - Click "Start Editing"

### Resuming an Existing Session

1. Launch the application
2. In SetupDialog, click "Browse" to select a video
3. If a session exists, you'll see "Resume Session?" dialog showing:
   - Video filename
   - Number of rallies marked
   - Current score
   - Last video position
   - Game type and victory rules
4. Choose:
   - **"Resume Session"** - Continue where you left off
   - **"Start Fresh"** - Discard saved progress and start over

### Saving Your Session

**Manual Save:**
- Click "Save Session" button in toolbar
- Or use keyboard shortcut (if configured)

**Auto-save on Close:**
- When closing with unsaved changes, you'll see a warning dialog
- Choose:
  - **"Save & Quit"** - Save changes before closing
  - **"Don't Save"** - Close without saving
  - **"Cancel"** - Return to editing

### When Changes Are Saved

Your session is marked as "unsaved" after:
- Starting a rally
- Ending a rally (Server Wins / Receiver Wins)
- Editing the score manually
- Forcing a side-out
- Adding a comment

The dirty flag is cleared after successfully saving.

## For Developers

### Session Storage Location

```
~/.local/share/pickleball-editor/sessions/
```

Each session is stored as:
```
{video_hash}.json
```

Where `video_hash` is the SHA256 hash of the first 64KB of the video file.

### Session File Format

```json
{
  "version": "1.0",
  "video_path": "/path/to/video.mp4",
  "video_hash": "abc123...",
  "game_type": "doubles",
  "victory_rules": "11",
  "player_names": {
    "team1": ["Alice", "Bob"],
    "team2": ["Carol", "Dave"]
  },
  "rallies": [
    {
      "start_frame": 100,
      "end_frame": 200,
      "score_at_start": "0-0-2",
      "winner": "server",
      "comment": null
    }
  ],
  "current_score": [1, 0, 2],
  "serving_team": 0,
  "server_number": 2,
  "last_position": 3.5,
  "created_at": "2026-01-14T10:00:00",
  "modified_at": "2026-01-14T10:15:00",
  "interventions": [],
  "comments": []
}
```

### Creating a Session Programmatically

```python
from src.core.models import SessionState, Rally
from src.core.session_manager import SessionManager

# Create session state
session = SessionState(
    version="1.0",
    video_path="/path/to/video.mp4",
    game_type="doubles",
    victory_rules="11",
    player_names={
        "team1": ["P1", "P2"],
        "team2": ["P3", "P4"]
    },
    rallies=[
        Rally(
            start_frame=100,
            end_frame=200,
            score_at_start="0-0-2",
            winner="server"
        )
    ],
    current_score=[1, 0, 2],
    serving_team=0,
    server_number=2,
    last_position=3.5,
)

# Save to disk
manager = SessionManager()
saved_path = manager.save(session, "/path/to/video.mp4")

print(f"Session saved to: {saved_path}")
```

### Loading a Session

```python
from src.core.session_manager import SessionManager

manager = SessionManager()

# Check if session exists
if manager.find_existing("/path/to/video.mp4"):
    # Load full session
    session = manager.load("/path/to/video.mp4")

    if session:
        print(f"Game type: {session.game_type}")
        print(f"Current score: {session.current_score}")
        print(f"Rallies: {len(session.rallies)}")
```

### Getting Session Info (Lightweight)

```python
from src.core.session_manager import SessionManager

manager = SessionManager()

# Get summary without loading full session
info = manager.get_session_info("/path/to/video.mp4")

if info:
    print(f"Rally count: {info['rally_count']}")
    print(f"Current score: {info['current_score']}")
    print(f"Last position: {info['last_position']}s")
    print(f"Game type: {info['game_type']}")
    print(f"Victory rules: {info['victory_rules']}")
```

### Deleting a Session

```python
from src.core.session_manager import SessionManager

manager = SessionManager()

# Delete session
success = manager.delete("/path/to/video.mp4")

if success:
    print("Session deleted")
else:
    print("Session not found or delete failed")
```

### Integrating Session Restoration in MainWindow

```python
from src.ui.main_window import MainWindow
from src.ui.setup_dialog import GameConfig
from pathlib import Path

# Config with session_state
config = GameConfig(
    video_path=Path("/path/to/video.mp4"),
    game_type="doubles",
    victory_rule="11",
    team1_players=["Alice", "Bob"],
    team2_players=["Carol", "Dave"],
    session_state=loaded_session_state  # From SessionManager.load()
)

# MainWindow will restore from session_state
window = MainWindow(config)
window.show()
```

### Tracking Dirty State

The `MainWindow._dirty` flag tracks unsaved changes:

```python
# Mark dirty after user action
self._dirty = True

# Check if dirty before closing
if self._dirty:
    # Show warning dialog
    ...

# Clear dirty after save
self._dirty = False
```

### Building Session State from Current State

```python
def _build_session_state(self) -> SessionState:
    """Build SessionState from current MainWindow state."""
    score_snapshot = self.score_state.save_snapshot()

    return SessionState(
        version="1.0",
        video_path=str(self.config.video_path),
        game_type=self.config.game_type,
        victory_rules=self.config.victory_rule,
        player_names={
            "team1": self.config.team1_players,
            "team2": self.config.team2_players,
        },
        rallies=self.rally_manager.get_rallies(),
        current_score=list(score_snapshot.score),
        serving_team=score_snapshot.serving_team,
        server_number=score_snapshot.server_number,
        last_position=self.video_widget.get_position(),
    )
```

## Architecture

### Session Detection Flow

```
User selects video
    ↓
SetupDialog._browse_video()
    ↓
SessionManager.get_session_info(video_path)
    ↓
Session exists? ──No──→ Continue with empty form
    ↓ Yes
ResumeSessionDialog shown
    ↓
User chooses Resume or Start Fresh
    ↓
Resume: SessionManager.load() → Populate form
Start Fresh: SessionManager.delete() → Empty form
    ↓
GameConfig created with session_state
    ↓
MainWindow receives config
```

### Session Restoration Flow

```
MainWindow.__init__(config)
    ↓
_init_core_components()
    ↓
config.session_state exists? ──No──→ Initialize fresh
    ↓ Yes
Restore ScoreState from snapshot
    ↓
Restore RallyManager from rallies
    ↓
Store _restore_position
    ↓
_load_video()
    ↓
Video loaded successfully
    ↓
_restore_position exists? ──Yes──→ Seek to position
    ↓
Show "Resumed session at X.Xs"
```

### Session Save Flow

```
User clicks "Save Session"
    ↓
_on_save_session()
    ↓
_build_session_state()
    ↓
Collect current state:
  - Score snapshot
  - Rally list
  - Video position
  - Player names
    ↓
SessionManager.save(state, video_path)
    ↓
Success? ──No──→ Show error toast
    ↓ Yes
Clear _dirty flag
    ↓
Show success toast
    ↓
Emit session_saved signal
```

### Close with Unsaved Changes Flow

```
User closes window
    ↓
closeEvent()
    ↓
_dirty flag set? ──No──→ Close normally
    ↓ Yes
Show UnsavedWarningDialog
    ↓
User choice:
  ├─ SAVE_AND_QUIT → Save → Close
  ├─ DONT_SAVE → Close without save
  └─ CANCEL → event.ignore() (stay open)
```

## Troubleshooting

### Session Not Detected

**Problem:** Selecting a video doesn't show resume dialog

**Possible causes:**
1. Video file has changed (different first 64KB)
2. Session directory doesn't exist or isn't writable
3. Session file is corrupted

**Solutions:**
```python
# Check session directory
from src.core.session_manager import SessionManager
manager = SessionManager()
print(f"Session dir: {manager.session_dir}")
print(f"Exists: {manager.session_dir.exists()}")

# Check for session file
video_path = "/path/to/video.mp4"
session_path = manager._get_session_path(video_path)
print(f"Session path: {session_path}")
print(f"Exists: {session_path.exists() if session_path else False}")
```

### Session Won't Save

**Problem:** Save Session shows error

**Possible causes:**
1. Session directory not writable
2. Disk full
3. Video path is invalid

**Solutions:**
```python
# Test save manually
from src.core.session_manager import SessionManager
from src.core.models import SessionState

manager = SessionManager()
test_session = SessionState()
result = manager.save(test_session, "/path/to/video.mp4")

if result is None:
    print("Save failed - check permissions and disk space")
else:
    print(f"Save succeeded: {result}")
```

### Score State Not Restored

**Problem:** Session loads but score is wrong

**Possible causes:**
1. Session state score fields are incorrect
2. ScoreState.restore_snapshot() not called
3. Score snapshot format mismatch

**Solutions:**
```python
# Verify session state
session = manager.load("/path/to/video.mp4")
print(f"Current score: {session.current_score}")
print(f"Serving team: {session.serving_team}")
print(f"Server number: {session.server_number}")

# Test snapshot restoration
from src.core.models import ScoreSnapshot
snapshot = ScoreSnapshot(
    score=tuple(session.current_score),
    serving_team=session.serving_team,
    server_number=session.server_number
)
score_state.restore_snapshot(snapshot)
```

### Video Position Not Restored

**Problem:** Video doesn't seek to last position

**Possible causes:**
1. `_restore_position` not set
2. Video not loaded before seek
3. MPV not ready

**Solutions:**
- Ensure `_restore_position` is set in `_init_core_components()`
- Verify seek happens in `_load_video()` after successful load
- Check MPV is initialized with `video_widget.load()` before seeking

## Best Practices

### For Users

1. **Save frequently** - Use "Save Session" button regularly
2. **Don't force quit** - Close normally to trigger save prompt
3. **Check resume details** - Verify score and position before resuming
4. **Start fresh if unsure** - When in doubt, start a new session

### For Developers

1. **Always use SessionManager** - Don't directly access session files
2. **Check return values** - SessionManager methods return None on failure
3. **Set dirty flag consistently** - Mark dirty after all state changes
4. **Clear dirty after save** - Only clear if save succeeds
5. **Handle restore_position carefully** - Only seek after video loads
6. **Use LBYL pattern** - Check conditions before acting

## FAQ

**Q: What happens if I move the video file?**
A: Session detection is based on video hash, not path. Moving the file breaks the link.

**Q: Can I have multiple sessions for the same video?**
A: No, one session per video (identified by hash).

**Q: What if I edit the video file?**
A: If the first 64KB changes, it's treated as a new video with no session.

**Q: Can I edit session files manually?**
A: Yes, they're JSON, but be careful with format. Use SessionState.from_dict() to validate.

**Q: How do I backup my sessions?**
A: Copy `~/.local/share/pickleball-editor/sessions/` directory.

**Q: What happens to undo history on resume?**
A: Undo stack starts empty. You can't undo actions from previous sessions.

**Q: Can I export/import sessions?**
A: Not yet implemented. Planned for future phase.

**Q: How much disk space do sessions use?**
A: Typically <1MB per session (mostly rally data).
