# Final Review Mode Implementation

**File:** `src/ui/review_mode.py`
**Status:** Current
**Date:** 2026-06-16

## Overview

The Final Review Mode UI provides a comprehensive interface for users to verify and adjust rally timings, winners, and game state before generating Kdenlive output or exporting an MP4. This replaces the Rally Controls and Toolbar sections when activated from the Main Window's "Final Review" button.

The module exposes six public widgets:

```python
__all__ = [
    "RallyHeaderWidget",
    "TimingControlWidget",
    "WinnerControlWidget",
    "StateAnchorWidget",
    "RallyListWidget",
    "ReviewModeWidget",
]
```

## Components

### 1. RallyHeaderWidget

**Purpose:** Display current rally progress and the review-exit controls
**Features:**
- Large "FINAL REVIEW MODE" title in accent color
- Rally counter showing "Rally X of Y" (1-based display); appends " (post-game)" for post-game rallies
- "Main Menu" button and "Exit Review" button on the right
- Accent border styling

**Signals:**
- `exit_requested()`: User clicked Exit Review button
- `return_to_menu_requested()`: User clicked Main Menu button

**Methods:**
- `set_rally(current: int, total: int, is_post_game: bool = False)`: Update the displayed rally count (current is 0-based; display is 1-based)

### 2. TimingControlWidget

**Purpose:** Adjust rally start/end times with precision, via either nudge buttons or direct entry
**Features:**
- Configurable nudge **step** selector (`_step_combo`, a `QComboBox`) — options `0.1 / 0.25 / 0.5 / 1.0 s` (`_STEP_OPTIONS` / `_STEP_LABELS`); nudge-button labels update when the step changes
- `±step` nudge buttons for both start and end
- Direct numeric entry `QLineEdit`s for start, end, and duration (`_start_entry`, `_end_entry`, `_duration_entry`); editing duration moves end (`end = start + duration`)
- Offset captions ("+0.42s from original") that appear only when timing differs from the loaded original
- Reset button that restores the original timing (disabled until modified)
- Monospace timestamp font for all time fields (MM:SS.s format)

**Signals:**
- `timing_adjusted(field: str, delta: float)`: A nudge was applied
  - `field`: `"start"` or `"end"`
  - `delta`: change in seconds (the current step, signed)
- `timing_set(field: str, absolute_seconds: float)`: A direct entry was committed
  - `field`: `"start"` or `"end"` (duration edits emit an `"end"` set)
  - `absolute_seconds`: the new absolute time

**Methods:**
- `set_times(start_seconds: float, end_seconds: float)`: Set the displayed times and store them as the originals (the reference for Reset and the offset captions)

**Implementation Details:**
- Direct-entry text is parsed by the module-level `_parse_time_input()` (LBYL); invalid text reverts the field to the current internal value rather than raising
- Prevents negative start times; clamps start `<= end` and end `>= start`
- Reset emits corrective `timing_adjusted` deltas so the parent/model stay in sync
- `_sync_entry_fields()` blocks signals while repainting the three fields to avoid recursive commits

### 3. WinnerControlWidget

**Purpose:** Explicitly assign the rally winner (replaces the old single "Flip Winner" button)
**Features:**
- Two buttons labeled with the actual team names: "`<serving team>` Won" and "`<returning team>` Won"
- A read-only "Serving: `<name>`" info line
- Low-confidence rallies are highlighted with an amber outline (`RECEIVER_WINS`); reviewed/normal rallies use the blue outline (`SERVER_WINS`)

**Signals:**
- `winner_selected(str)`: emits `"server"` or `"receiver"`

**Methods:**
- `set_teams(serving_name: str, returning_name: str)`: Update both button labels and the serving info line
- `set_low_confidence(low: bool)`: Toggle the amber (low) / blue (normal) outline styling

### 4. StateAnchorWidget

**Purpose:** Set the game state (serving team + score) at the start of a rally. Replaces `ScoreEditWidget`.

State-anchor edits **always cascade** to later rallies — the old "Cascade to later rallies" checkbox has been removed. The widget only emits the anchor; `MainWindow` owns the cascade logic.

**Features:**
- Mutually-exclusive serving-team toggle (two checkable buttons, labeled with team names)
- Score entry `QLineEdit` validated by a `QRegularExpressionValidator`:
  - doubles: `^\d{1,2}-\d{1,2}-[12]$`
  - singles / highlights: `^\d{1,2}-\d{1,2}$`
- Inline error label for non-empty invalid input
- "Apply to Rally" button, disabled until the score is valid

**Signals:**
- `state_anchor_applied(serving_team: int, score: str)`: Emitted on Apply with a valid score
  - `serving_team`: `0` or `1`
  - `score`: validated score string

**Methods:**
- `set_mode(mode: str)`: Set the game mode (`"doubles"`, `"singles"`, or `"highlights"`) and rebuild the score validator
- `set_state(score: str, serving_team: int)`: Prefill the widget for the current rally
- `set_team_names(team1_name: str, team2_name: str)`: Relabel the serving-team toggle buttons

### 5. Rally Cards (rendered within RallyListWidget)

**Note:** There is no standalone `RallyCardWidget` class. Rally cards are rendered as items in `RallyListWidget`'s `QListWidget` (IconMode); the bullets below describe each rendered cell.

**Each cell shows:**
- Rally number (large, centered)
- Score at start (small) — or "PG" for post-game rallies
- Selection state with accent border
- Hover effect
- Click to select

### 6. RallyListWidget

**Purpose:** Horizontal scrolling strip of rally cards
**Features:**
- Single-row `QListWidget` in IconMode (`setWrapping(False)`) so the control panel keeps full vertical height
- Horizontal scroll for overflow, custom scrollbar styling, vertical scrollbar off
- Current rally highlighted; auto-scrolls to keep the selected card visible
- Click any card to navigate

**Signals:**
- `rally_selected(rally_index: int)`: Rally card clicked (0-based index)

**Methods:**
- `set_rallies(rallies: list[Rally])`: Populate with rally data (selects rally 0 if non-empty)
- `set_current_rally(index: int)`: Update selection state and scroll into view

### 7. ReviewModeWidget (Main Container)

**Purpose:** Compose all review components into a single interface

**Layout:**

The header sits at the top. Below it, the body uses one of two splitter arrangements, chosen ONCE on first show based on the window aspect ratio and then frozen for the session (re-arrangement on resize is deliberately unsupported because mpv native-window reparenting is fragile). The component grouping is the same in both arrangements:

```
┌──────────────────────────────────────────────┐
│ RallyHeaderWidget        (Main Menu / Exit)    │
├──────────────────────────────────────────────┤
│ Video placeholder  │  Control panel:           │
│ (mpv target)       │   • PLAY RALLY            │
│                    │   • WinnerControlWidget   │
│                    │   • Delete / Insert row   │
│                    │   • TimingControlWidget   │
│                    │   • StateAnchorWidget     │
├──────────────────────────────────────────────┤
│ Rally strip:  RALLY LIST title · Prev · Next   │
│               RallyListWidget                  │
├──────────────────────────────────────────────┤
│ Export widget:  "Ready to generate output"     │
│   Mark Game Completed · final-score label      │
│   Export Options:                              │
│     Kdenlive card: path · Browse · GENERATE    │
│     FFmpeg card:   EXPORT MP4                   │
└──────────────────────────────────────────────┘
```

- **Tall** (default): outer **vertical** splitter — video + control panel on top (an inner **horizontal** splitter), rally strip + export in a scrollable bottom section.
- **Wide** (aspect >= `ASPECT_ULTRAWIDE`): a **horizontal** master splitter — video + rally strip on the left (not scrolled), control panel + export in a scrollable right column (min 460 px).

**mpv Safety Contract:** `_video_placeholder` is the X11 native-window target for mpv and is NEVER placed inside a `QScrollArea` in either arrangement.

Splitter sizes are persisted to `AppSettings` (`display.review_splitter_v` / `review_splitter_h`) on a debounced timer and restored on the next entry.

**Signals:**
- `rally_changed(int)`: Current rally index changed
- `timing_adjusted(int, str, float)`: Nudge applied — `rally_idx, field ("start"|"end"), delta`
- `timing_set(int, str, float)`: Direct entry committed — `rally_idx, field ("start"|"end"), absolute_seconds`
- `winner_set(int, str)`: Winner explicitly set — `rally_idx, "server"|"receiver"`
- `state_anchor_set(int, int, str)`: Game-state anchor applied — `rally_idx, serving_team (0|1), score`
- `delete_rally_requested(int)`: Delete the given rally
- `insert_rally_requested(int)`: Insert a new rally after the given index
- `exit_requested()`: Exit review mode
- `return_to_menu_requested()`: Return to the main menu
- `generate_requested()`: Generate Kdenlive project
- `export_ffmpeg_requested()`: Export MP4 via FFmpeg
- `play_rally_requested(int)`: Play the specified rally
- `navigate_previous()`: Navigate to previous rally
- `navigate_next()`: Navigate to next rally
- `game_completed_toggled(bool)`: "Mark Game Completed" toggled
- `export_path_changed(str)`: Export path field changed

**Methods:**
- `set_rallies(rallies: list[Rally], fps: float = 60.0, is_highlights: bool = False, game_mode: str = "doubles")`: Populate all rallies; passes the real `fps` for frame↔second conversion; hides the winner/state-anchor controls in highlights mode; enables/disables the generate/export/delete buttons based on rally count
- `set_current_rally(index: int)`: Set the current rally and refresh every child control
- `set_team_names(team1: list[str], team2: list[str])`: Supply per-team player name lists (joined with " & "; fall back to "Team 1"/"Team 2"); relabels the winner buttons and state-anchor toggle
- `get_current_rally_index() -> int`: Get the current index
- `navigate_to_previous()` / `navigate_to_next()`: Programmatic navigation (no nav signal)
- `set_low_confidence_indices(indices: set[int])` / `get_low_confidence_indices() -> set[int]`: Manage the set of rallies whose winner classification is low-confidence (drives the amber winner styling)
- `set_game_completion_info(final_score: str, winning_team_names: list[str])`: Set the completion display text
- `is_game_completed() -> bool` / `get_game_completion_info() -> tuple[str, list[str]]`: Read game-completion state for export
- `set_game_completed(checked: bool, announce: bool = False)`: Set the checkbox; optionally show an info toast
- `hide_game_completion_controls()`: Hide game-completion controls (highlights mode)
- `get_export_path() -> str` / `set_export_path(path: str)`: Read/write the Kdenlive export path field
- `get_video_placeholder() -> QWidget`: Return the mpv embedding target
- `get_inner_splitter() -> QSplitter | None` / `get_outer_splitter() -> QSplitter | None`: Splitter handles (tall arrangement only)

**Control Panel:**
- "PLAY RALLY" button (prominent green outline) → `play_rally_requested`
- `WinnerControlWidget`
- "Delete Rally" (danger outline) / "Insert Rally After" row
- `TimingControlWidget`
- `StateAnchorWidget`

**Rally Strip:**
- "RALLY LIST (click to navigate)" title with "Prev" / "Next" buttons (boundary-guarded)
- `RallyListWidget`

**Export Widget:**
- "Ready to generate output" summary line
- "Mark Game Completed" checkbox; a centered final-score / winner label shown when completed
- "Export Options" with two cards:
  - **Kdenlive Project** — export-path field, "Browse" (`QFileDialog`), and "GENERATE PROJECT" button
  - **MP4 Video** — "EXPORT MP4" button (FFmpeg, hardware encoding)
- Generate/Export buttons are disabled until at least one rally exists

## Helper Functions

### `_format_time(seconds: float) -> str`
Converts seconds to MM:SS.s format.

**Examples:**
- `_format_time(0.0)` → "00:00.0"
- `_format_time(125.7)` → "02:05.7"
- `_format_time(3665.2)` → "61:05.2"

### `_parse_time_input(text: str) -> float | None`
Parses user-entered timing text into seconds (LBYL, no exception-based flow; backed by the module-level compiled regexes `_COLON_TIME_RE` and `_PLAIN_NUM_RE`).

**Accepts:**
- Plain float seconds: `"42.5"` → `42.5`
- `MM:SS` / `MM:SS.s`: `"00:42.5"` → `42.5`, `"1:23"` → `83.0`

**Returns `None`** on empty input, non-numeric input, negative values, or colon-format with seconds `>= 60`.

## Integration Points

### With MainWindow
When "Final Review" is entered, `MainWindow` shows `_review_widget`, embeds the mpv video into `get_video_placeholder()`, and wires every signal to a handler. The connections (see `main_window.py`):

```python
self._review_widget.rally_changed.connect(self._on_review_rally_changed)
self._review_widget.timing_adjusted.connect(self._on_review_timing_adjusted)
self._review_widget.timing_set.connect(self._on_review_timing_set)
self._review_widget.winner_set.connect(self._on_review_winner_set)
self._review_widget.state_anchor_set.connect(self._on_review_state_anchor_set)
self._review_widget.delete_rally_requested.connect(self._on_review_rally_deleted)
self._review_widget.insert_rally_requested.connect(self._on_review_rally_inserted)
self._review_widget.play_rally_requested.connect(self._on_review_play_rally)
self._review_widget.exit_requested.connect(self.exit_review_mode)
self._review_widget.generate_requested.connect(self._on_review_generate)
self._review_widget.export_ffmpeg_requested.connect(self._on_export_ffmpeg)
self._review_widget.game_completed_toggled.connect(self._on_game_completed_toggled)
self._review_widget.return_to_menu_requested.connect(self.return_to_menu_requested.emit)
```

Population: `set_rallies(rallies, fps=self.video_fps, is_highlights=...)`, then `set_team_names(...)`, `set_export_path(...)`, and (for non-highlights) `set_game_completion_info(...)`.

**Handler behavior (MainWindow):**
- `_on_review_rally_changed(index)`: Delegates to `_on_review_play_rally` (seeks to the rally start and auto-plays).
- `_on_review_play_rally(index)`: Seeks to `start_frame / fps`, plays, and arms a one-shot `QTimer` to pause at the rally end.
- `_on_review_timing_adjusted(index, which, delta)`: Calls `rally_manager.update_rally_timing(...)` with the signed delta.
- `_on_review_timing_set(index, field, seconds)`: The widget shows *padded* boundary times; the handler converts back to raw mark times (subtracting `RallyManager.START_PADDING` / `END_PADDING`) before `set_rally_timing(...)`, then refreshes the widget so the display reflects frame-snapping.
- `_on_review_winner_set(index, winner)`: Applies the explicit winner and recomputes downstream scores.
- `_on_review_state_anchor_set(index, serving_team, score)`: Always cascades via `rally_manager.cascade_scores_from(index, score_state, new_score=score, serving_team=serving_team)`, refreshing both `score_at_start` strings and `score_snapshot_at_start` snapshots; re-populates the widget and extends the low-confidence attention set with the re-derived indices.
- `_on_review_rally_deleted` / `_on_review_rally_inserted`: Mutate the rally list, re-populate the widget, and re-map the low-confidence indices.

### With VideoWidget (mpv)
- Video is embedded into `get_video_placeholder()` (a native window; never inside a scroll area).
- Rally selection and "PLAY RALLY" both route through `_on_review_play_rally`, which seeks/plays/auto-pauses.

### With RallyManager
- `timing_adjusted` / `timing_set` → `update_rally_timing` / `set_rally_timing`
- `winner_set` → winner reassignment + downstream score recompute
- `state_anchor_set` → `cascade_scores_from` (always cascades)
- `delete_rally_requested` / `insert_rally_requested` → list mutation + score recalculation

### Frame/Time Conversion
FPS is supplied at runtime via `set_rallies(rallies, fps=...)` (default `60.0`) and stored on `self._fps`; `set_current_rally()` converts `start_frame`/`end_frame` to seconds using it. FPS is no longer hardcoded.

## Design Adherence

### Color Scheme
- **Backgrounds:** `BG_PRIMARY`, `BG_SECONDARY`, `BG_TERTIARY`, `BG_HOVER`, `BG_BORDER`
- **Borders / focus:** `BORDER_COLOR`, `FOCUS_RING`
- **Accent / primary action:** `PRIMARY_ACTION` (and `PRIMARY_ACTION_TINT`), `TEXT_ACCENT`
- **Winner outlines:** `SERVER_WINS` (normal) and `RECEIVER_WINS` (amber / low-confidence)
- **Danger:** `DANGER_TEXT` (Delete Rally, score-input errors)
- **Text:** `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TEXT_TERTIARY`, `TEXT_DISABLED`, `TEXT_WARNING`

### Typography
- **Display / timestamp:** monospace (via `Fonts.display()` / `Fonts.timestamp()`) for times and scores
- **Body / labels / buttons:** `Fonts.body()`, `Fonts.label()`, `Fonts.button_other()`, `Fonts.button_rally()`
- Section labels and roles applied via `set_label_role(...)` / `set_class(...)`

### Spacing & Radius
- Spacing tokens `SPACE_SM` / `SPACE_MD` / `SPACE_LG`
- Radius tokens `RADIUS_SM` / `RADIUS_MD` / `RADIUS_LG`

### Button / Input Styling
- Buttons use `ButtonStyles.compact()`, `ButtonStyles.outline(color)`, `ButtonStyles.primary()`
- Inputs use `InputStyles.line_edit()`
- The step combo and team-selector buttons use local QSS constants (`_COMBO_QSS`, `_TEAM_BTN_QSS`)

## Testing Recommendations

1. **Unit Tests:**
   - `_format_time()` edge cases (0, fractional, large values)
   - `_parse_time_input()` (plain seconds, MM:SS, MM:SS.s, empty, negative, `>= 60` seconds, junk)
   - `TimingControlWidget` bounds (negative start, end < start) and `timing_set` from the duration field
   - `StateAnchorWidget` validation (doubles vs singles patterns; Apply enable/disable)

2. **Integration Tests:**
   - Load many rallies, navigate, and verify the single-row strip scrolls
   - Adjust timings (nudge and direct entry) and verify the emitted signals/indices
   - Apply a state anchor and verify downstream cascade
   - Delete/insert rallies and verify re-population

3. **Visual Tests:**
   - Tall vs wide arrangement selection at entry
   - Low-confidence amber winner styling
   - Hover/selection states; custom scrollbar

4. **Edge Cases:**
   - Empty rally list (generate/export disabled)
   - Highlights mode (winner / state-anchor / game-completion controls hidden)
   - Post-game rallies (header suffix; "PG" card)

## Known Limitations

1. **Frozen arrangement:** The tall/wide layout is decided once at entry and is not re-arranged on resize (intentional, for mpv native-window stability).
2. **No video-boundary clamp:** Timing entry/nudge does not validate against the video's total duration.

## Future Enhancements

1. **Keyboard Navigation:** Arrow keys to navigate, Enter to play, Esc to exit.
2. **Export Preview:** Total output duration, segment count, subtitle preview.
3. **Batch Operations:** Multi-select rallies for bulk timing/score correction.

## File Dependencies

```python
import re

from PyQt6.QtCore import Qt, QSize, QTimer, QRegularExpression, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QRegularExpressionValidator, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from src.core.app_config import AppSettings
from src.core.models import Rally
from src.ui.styles.components import ButtonStyles, InputStyles, set_class, set_label_role
from src.ui.widgets.toast import ToastManager
from src.ui.styles import (  # colors, spacing, radius, fonts, icon/pixmap helpers
    BG_BORDER, BG_BORDER_HOVER, BG_HOVER, BG_PRIMARY, BG_SECONDARY, BG_TERTIARY,
    BORDER_COLOR, FOCUS_RING, PRIMARY_ACTION, PRIMARY_ACTION_TINT,
    RADIUS_LG, RADIUS_MD, RADIUS_SM, RECEIVER_WINS, SERVER_WINS,
    SPACE_LG, SPACE_MD, SPACE_SM, TEXT_ACCENT, TEXT_DISABLED, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_TERTIARY, TEXT_WARNING, DANGER_TEXT,
    Fonts, icon as make_icon, pixmap as make_pixmap,
)
from src.ui.styles.fonts import ASPECT_ULTRAWIDE
```

## Code Style Compliance

- **Modern Python typing:** `list[Rally]`, `str | None`, `set[int]`, `tuple[str, list[str]]`; no `from typing import`.
- **LBYL:** bounds checks before list access; `_parse_time_input` validates instead of catching; PyQt validators gate score input.
- **PyQt6 practices:** signals declared at class level, `@pyqtSlot` on slots, QSS in stylesheets, object names for CSS targeting, validator references retained to avoid GC.
- **Docstrings:** module, class, and method docstrings with Args/Returns and signal documentation.

## Summary

Final Review Mode is the editing surface used between rally detection and output generation. It composes a header, an mpv video pane, a control panel (play / winner / delete-insert / timing / state-anchor), a rally strip, and an export panel into a frozen tall or wide splitter arrangement. All edits are surfaced as signals that `MainWindow` translates into `RallyManager` / `ScoreState` mutations, with state-anchor edits always cascading downstream. Score and timing input are validated, FPS is supplied at runtime, and the widget additionally handles game-completion marking and dual Kdenlive / FFmpeg export paths.
