# StatusOverlay Widget - Usage Guide

## Overview

The `StatusOverlay` widget displays the current game status on top of the video player. It shows:
- Rally status (WAITING or IN RALLY) with a colored indicator dot
- Current score in large tabular numerals
- Server information (team, player, server number)

## Visual Design

```
┌───────────────────────────────────────────────────────────┐
│  ● IN RALLY    Score: 7-5-2    Server: Team 1 (John) #2  │
└───────────────────────────────────────────────────────────┘
```

**Color Scheme:**
- Background: `rgba(26, 29, 35, 0.85)` - semi-transparent dark
- Border: `rgba(255, 255, 255, 0.1)` - subtle white
- Status dot (waiting): `#FFE082` - amber
- Status dot (in rally): `#3DDC84` - green
- Text: `#F5F5F5` - off-white

**Typography:**
- Status text: IBM Plex Sans, 14px, medium (500)
- Score value: JetBrains Mono, 24px, bold (700), tabular numerals
- Labels: IBM Plex Sans, 14px, regular (400)
- Server info: IBM Plex Sans, 14px, regular (400)

## API Reference

### Class: `StatusOverlay(QFrame)`

#### Methods

##### `__init__(parent=None)`
```python
overlay = StatusOverlay(parent=video_widget)
```
Creates a new status overlay widget.

**Args:**
- `parent` (QWidget, optional): Parent widget (typically the video player container)

---

##### `set_status(in_rally: bool) -> None`
```python
overlay.set_status(in_rally=True)  # Show "IN RALLY" with green dot
overlay.set_status(in_rally=False) # Show "WAITING" with amber dot
```
Updates the status indicator and text.

**Args:**
- `in_rally` (bool): True if currently in a rally, False if waiting

---

##### `set_score(score_text: str) -> None`
```python
overlay.set_score("7-5-2")  # Doubles
overlay.set_score("10-9")   # Singles
```
Updates the score display.

**Args:**
- `score_text` (str): Score string (e.g., "7-5-2" for doubles, "7-5" for singles)

---

##### `set_server_info(server_info: str) -> None`
```python
overlay.set_server_info("Team 1 (Alice) #2")
overlay.set_server_info("Server (Bob)")
```
Updates the server information display.

**Args:**
- `server_info` (str): Server description (team, player name, server number)

---

##### `update_display(in_rally: bool, score: str, server_info: str) -> None`
```python
overlay.update_display(
    in_rally=True,
    score="7-5-2",
    server_info="Team 1 (Alice) #1"
)
```
Updates all status fields at once (preferred method).

**Args:**
- `in_rally` (bool): True if currently in a rally
- `score` (str): Score string
- `server_info` (str): Server description

## Usage Examples

### Basic Integration

```python
from PyQt6.QtWidgets import QStackedLayout, QWidget
from src.ui.widgets import StatusOverlay
from src.video.player import VideoWidget

class VideoPanel(QWidget):
    def __init__(self):
        super().__init__()

        # Create video player
        self.player = VideoWidget()

        # Create overlay
        self.overlay = StatusOverlay(parent=self)

        # Stack overlay on top of video
        layout = QStackedLayout(self)
        layout.addWidget(self.player)
        layout.addWidget(self.overlay)

        # Position overlay at top
        self.overlay.move(10, 10)

        # Initialize display
        self.overlay.update_display(
            in_rally=False,
            score="0-0-2",
            server_info="Team 1 #1"
        )
```

### Connecting to Rally Manager

```python
from src.core.rally_manager import RallyManager
from src.ui.widgets import StatusOverlay

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create rally manager
        self.rally_manager = RallyManager()

        # Create overlay
        self.overlay = StatusOverlay()

        # Connect signals
        self.rally_manager.rally_started.connect(self._on_rally_started)
        self.rally_manager.rally_ended.connect(self._on_rally_ended)
        self.rally_manager.score_changed.connect(self._on_score_changed)

    def _on_rally_started(self, rally):
        """Handle rally start."""
        self.overlay.set_status(in_rally=True)

    def _on_rally_ended(self, rally):
        """Handle rally end."""
        self.overlay.set_status(in_rally=False)
        self.overlay.set_score(rally.score_after)

    def _on_score_changed(self, score_text, server_info):
        """Handle score change."""
        self.overlay.set_score(score_text)
        self.overlay.set_server_info(server_info)
```

### Dynamic Updates During Video Playback

```python
from src.core.score_state import ScoreState
from src.ui.widgets import StatusOverlay

class EditorController:
    def __init__(self):
        self.score_state = ScoreState(game_mode="doubles")
        self.overlay = StatusOverlay()
        self.in_rally = False

        # Update overlay with initial state
        self._update_overlay()

    def start_rally(self, timestamp: float) -> None:
        """Mark rally start."""
        self.in_rally = True
        self._update_overlay()

    def end_rally_server_wins(self, timestamp: float) -> None:
        """Mark rally end - server wins."""
        self.score_state.server_wins()
        self.in_rally = False
        self._update_overlay()

    def end_rally_receiver_wins(self, timestamp: float) -> None:
        """Mark rally end - receiver wins."""
        self.score_state.receiver_wins()
        self.in_rally = False
        self._update_overlay()

    def _update_overlay(self) -> None:
        """Update overlay to reflect current state."""
        score = self.score_state.get_display_string()
        server_info = self._format_server_info()

        self.overlay.update_display(
            in_rally=self.in_rally,
            score=score,
            server_info=server_info
        )

    def _format_server_info(self) -> str:
        """Format server information for display."""
        if self.score_state.game_mode == "singles":
            return f"Server ({self.score_state.current_server})"
        else:
            team = "Team 1" if self.score_state.serving_team == 0 else "Team 2"
            server_num = self.score_state.server_number
            return f"{team} #{ server_num}"
```

## Positioning

The overlay is designed to be positioned on top of the video player. There are several approaches:

### 1. Absolute Positioning (Simple)
```python
# Place overlay at top-left of video player
overlay = StatusOverlay(parent=video_player)
overlay.move(10, 10)
overlay.raise_()  # Ensure it's on top
```

### 2. Stacked Layout (Recommended)
```python
container = QWidget()
layout = QStackedLayout(container)
layout.addWidget(video_player)
layout.addWidget(overlay)
layout.setStackingMode(QStackedLayout.StackAll)
```

### 3. Grid Layout with Span
```python
layout = QGridLayout()
layout.addWidget(video_player, 0, 0)
layout.addWidget(overlay, 0, 0, Qt.AlignTop | Qt.AlignLeft)
```

## Styling Customization

If you need to customize the appearance, you can override styles:

```python
overlay = StatusOverlay()

# Customize with QSS
overlay.setStyleSheet("""
    QFrame#status_overlay {
        background-color: rgba(0, 0, 0, 0.9);
        border: 2px solid #3DDC84;
        border-radius: 8px;
    }

    QLabel#score_value {
        color: #3DDC84;
        font-size: 32px;
    }
""")
```

## Testing

Run the demo script to see the overlay in action:

```bash
python test_status_overlay.py
```

**Demo Controls:**
- `t` - Toggle rally state (WAITING ↔ IN RALLY)
- `s` - Cycle through score examples
- `q` - Quit

## Implementation Notes

1. **Semi-Transparency**: The overlay uses `rgba(26, 29, 35, 0.85)` for the background, allowing video content to be partially visible underneath.

2. **Tabular Numerals**: The score uses tabular numerals (monospace digits) to prevent layout shift when the score changes (e.g., "7-5-2" → "10-5-2").

3. **Performance**: The overlay is lightweight and won't impact video playback performance.

4. **Accessibility**: All text uses sufficient contrast ratios (4.5:1+) for readability.

5. **Responsive**: The overlay's width adjusts based on content length.

## Related Files

- **Implementation**: `/src/ui/widgets/status_overlay.py`
- **Colors**: `/src/ui/styles/colors.py`
- **Fonts**: `/src/ui/styles/fonts.py`
- **Demo**: `/test_status_overlay.py`
