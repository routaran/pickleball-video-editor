# Setup Dialog Guide

## Overview

The **SetupDialog** is the first interface users encounter when starting a new editing session. It collects all necessary configuration before launching the main editing window.

## Features

### 1. Video Source Selection
- **File browser** integration for selecting MP4 video files
- **Path validation** ensures the selected file exists
- **Visual feedback** with red border for invalid paths

### 2. Game Configuration
Two side-by-side configuration panels:

**Game Type:**
- Doubles (default)
- Singles

**Victory Rules:**
- Game to 11 (default)
- Game to 9
- Timed

### 3. Team Configuration

**Team 1 (First Server):**
- Highlighted with **accent green border** (#3DDC84)
- Indicates this team serves first
- Player 1 (required)
- Player 2 (required for Doubles, hidden for Singles)

**Team 2:**
- Standard border
- Player 1 (required)
- Player 2 (required for Doubles, hidden for Singles)

### 4. Dynamic Validation
- **Real-time validation** as you type
- **Red borders** on invalid fields
- **Start Editing button** disabled until all fields valid
- **Field visibility** changes based on Singles/Doubles selection

## User Interface

```
┌───────────────────────────────────────────────────────────────────────┐
│   New Editing Session                                           [×]   │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   SOURCE VIDEO                                                        │
│   ┌─────────────────────────────────────────────────────┐             │
│   │ /home/user/Videos/match.mp4                         │  [Browse]   │
│   └─────────────────────────────────────────────────────┘             │
│                                                                       │
│   ┌─────────────────────────┐   ┌─────────────────────────┐           │
│   │  GAME TYPE              │   │  VICTORY RULES          │           │
│   │  ┌───────────────────┐  │   │  ┌───────────────────┐  │           │
│   │  │ Doubles        ▼  │  │   │  │ Game to 11     ▼  │  │           │
│   │  └───────────────────┘  │   │  └───────────────────┘  │           │
│   └─────────────────────────┘   └─────────────────────────┘           │
│                                                                       │
│   ╔═══════════════════════════════════════════════════════════════╗   │
│   ║  TEAM 1 (First Server)                                        ║   │
│   ╠═══════════════════════════════════════════════════════════════╣   │
│   ║  Player 1 *  ┌─────────────────────────────────────────────┐  ║   │
│   ║              │                                             │  ║   │
│   ║              └─────────────────────────────────────────────┘  ║   │
│   ║  Player 2 *  ┌─────────────────────────────────────────────┐  ║   │
│   ║              │                                             │  ║   │
│   ║              └─────────────────────────────────────────────┘  ║   │
│   ╚═══════════════════════════════════════════════════════════════╝   │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │  TEAM 2                                                       │   │
│   │  Player 1 *  ┌─────────────────────────────────────────────┐  │   │
│   │              │                                             │  │   │
│   │              └─────────────────────────────────────────────┘  │   │
│   │  Player 2 *  ┌─────────────────────────────────────────────┐  │   │
│   │              │                                             │  │   │
│   │              └─────────────────────────────────────────────┘  │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                                     ┌──────────┐  ╔════════════════╗  │
│                                     │  Cancel  │  ║ Start Editing  ║  │
│                                     └──────────┘  ╚════════════════╝  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

## Validation Rules

### Required Fields (All Modes)
1. **Video file** must be selected and exist on disk
2. **Team 1 Player 1** name must be non-empty
3. **Team 2 Player 1** name must be non-empty

### Additional Requirements (Doubles Mode)
4. **Team 1 Player 2** name must be non-empty
5. **Team 2 Player 2** name must be non-empty

### Visual Feedback
- **Invalid fields**: Red border (`#EF5350`)
- **Valid fields**: Normal border
- **Start Editing button**: Disabled (grayed) until all validation passes

## Behavior

### Singles Mode
When "Singles" is selected:
- Player 2 fields **hidden** for both teams
- Only Player 1 names required
- Validation updates automatically

### Doubles Mode
When "Doubles" is selected:
- All 4 player fields **visible**
- All 4 player names required
- Validation enforces all fields

### File Selection
1. Click **Browse** button
2. File dialog opens at `~/Videos` by default
3. Filter shows `*.mp4` files
4. Selected path populates the text field
5. Path validated immediately

## Code Example

```python
from PyQt6.QtWidgets import QApplication
from src.ui.setup_dialog import SetupDialog

app = QApplication([])

# Create and show dialog
dialog = SetupDialog()
result = dialog.exec()

# Check if user accepted
if result == dialog.DialogCode.Accepted:
    config = dialog.get_config()

    if config:
        print(f"Video: {config.video_path}")
        print(f"Game Type: {config.game_type}")
        print(f"Victory Rule: {config.victory_rule}")
        print(f"Team 1: {config.team1_players}")
        print(f"Team 2: {config.team2_players}")
else:
    print("Dialog cancelled")
```

## GameConfig Dataclass

```python
@dataclass
class GameConfig:
    video_path: Path                # Full path to video file
    game_type: str                  # "singles" or "doubles"
    victory_rule: str               # "11", "9", or "timed"
    team1_players: list[str]        # 1-2 player names
    team2_players: list[str]        # 1-2 player names
```

## Styling

The dialog uses the **Court Green** theme:

- **Background**: Dark slate (#252A33)
- **Input fields**: Card surface (#2D3340)
- **Team 1 border**: Accent green (#3DDC84) - indicates first server
- **Team 2 border**: Standard border (#3D4450)
- **Primary button**: Green background with glow effect
- **Error state**: Red border (#EF5350)

## Testing

Run the test script:

```bash
python test_setup_dialog.py
```

This will:
1. Open the SetupDialog
2. Allow you to interact with all controls
3. Print the configuration when you click "Start Editing"
4. Show "cancelled" if you click "Cancel" or close the window

## Design Decisions

### Why Team 1 is Highlighted
In pickleball, the starting team is significant:
- **Doubles**: First team starts with server #2 (0-0-2)
- **Singles**: First team serves first

The green accent border makes this immediately clear.

### Why Player 2 Fields Are Hidden (Not Disabled)
- **Cleaner UI** when fields aren't needed
- **Reduces visual noise** in Singles mode
- **Follows platform conventions** (iOS, macOS)

### Why Validation is Real-Time
- **Immediate feedback** prevents user confusion
- **Button state** clearly indicates when form is complete
- **No error dialogs** needed on submit
- **Better UX** than submit-time validation

## Future Enhancements

Potential improvements:
- [ ] Remember last used video directory
- [ ] Recent video files list
- [ ] Player name autocomplete from previous sessions
- [ ] Preset templates for common configurations
- [ ] Video preview thumbnail
- [ ] Drag-and-drop video file support

## Related Files

- **Implementation**: `src/ui/setup_dialog.py`
- **Test script**: `test_setup_dialog.py`
- **Color definitions**: `src/ui/styles/colors.py`
- **UI specification**: `docs/UI_SPEC.md` (Section 3)
- **Core models**: `src/core/models.py`
