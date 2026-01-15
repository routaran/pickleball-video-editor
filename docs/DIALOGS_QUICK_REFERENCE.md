# Intervention Dialogs - Quick Reference

Quick reference for using the three intervention dialogs in the Pickleball Video Editor.

---

## Edit Score Dialog

**Purpose:** Correct a rally score when automatic tracking makes an error.

### Import
```python
from src.ui.dialogs import EditScoreDialog, EditScoreResult
```

### Usage
```python
dialog = EditScoreDialog(
    current_score="7-5-2",      # Current score string
    is_doubles=True,            # True for X-Y-Z, False for X-Y
    parent=main_window          # Parent widget
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        print(f"New score: {result.new_score}")
        print(f"Comment: {result.comment}")
```

### Result Fields
- `new_score: str` - Corrected score string
- `comment: str | None` - Optional explanation

### Validation
- Singles: `X-Y` (e.g., "7-5")
- Doubles: `X-Y-Z` (e.g., "7-5-2")
- Apply button disabled until valid

---

## Force Side-Out Dialog

**Purpose:** Manually force a side-out when serving state tracking fails.

### Import
```python
from src.ui.dialogs import ForceSideOutDialog, ForceSideOutResult
```

### Usage
```python
dialog = ForceSideOutDialog(
    current_server_info="Team 1 - Server 2",   # Current server display
    next_server_info="Team 2 - Server 1",      # Server after side-out
    current_score="7-5-2",                     # Current score
    is_doubles=True,                           # Format validation
    parent=main_window                         # Parent widget
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        print(f"New score: {result.new_score or 'keep current'}")
        print(f"Comment: {result.comment}")
```

### Result Fields
- `new_score: str | None` - Optional corrected score (None = keep current)
- `comment: str | None` - Optional explanation

### Validation
- Score field is optional (blank = keep current)
- If provided, same validation as Edit Score

---

## Add Comment Dialog

**Purpose:** Add a commentary marker at a specific video timestamp.

### Import
```python
from src.ui.dialogs import AddCommentDialog, AddCommentResult
```

### Usage
```python
# Get current video position
current_time = player.get_position()

dialog = AddCommentDialog(
    timestamp=current_time,    # Timestamp in seconds
    parent=main_window         # Parent widget
)

if dialog.exec() == QDialog.DialogCode.Accepted:
    result = dialog.get_result()
    if result:
        print(f"Timestamp: {result.timestamp}")
        print(f"Comment: {result.comment}")
        print(f"Duration: {result.duration}")
```

### Result Fields
- `timestamp: float` - Video timestamp in seconds
- `comment: str` - Comment text (required)
- `duration: float` - Display duration in seconds (1-60)

### Validation
- Comment must be non-empty
- Duration range: 1-60 seconds (default: 5)
- Add button disabled until comment entered

---

## Common Pattern

All dialogs follow the same usage pattern:

```python
# 1. Create dialog with parameters
dialog = SomeDialog(params..., parent=main_window)

# 2. Execute modally
if dialog.exec() == QDialog.DialogCode.Accepted:
    # 3. Get result object
    result = dialog.get_result()

    # 4. Check if result exists (should always be true if accepted)
    if result:
        # 5. Use result fields
        # ...
else:
    # User cancelled
    pass
```

---

## Keyboard Shortcuts

All dialogs support:
- **Enter** - Submit (if validation passes)
- **Escape** - Cancel

---

## Visual States

### Primary Button (Apply/Add)
- **Valid input:** Green background, enabled
- **Invalid input:** Gray background, disabled, opacity 0.4
- **Hover (valid):** Brighter green, subtle glow

### Cancel Button
- **Always enabled**
- Border-only style
- Hover: Lighter background

### Input Fields
- **Normal:** Gray border
- **Focus:** Green border (#3DDC84)
- **Error:** Red inline message below field

---

## Testing

### Run Smoke Test
```bash
python test_dialogs.py
```

### Run Visual Test
```bash
python test_dialogs_visual.py
```

The visual test provides an interactive launcher to test each dialog manually.

---

## Integration Checklist

When integrating into main window:

- [ ] Import dialog and result classes
- [ ] Create button/menu item to launch dialog
- [ ] Connect to slot that creates and shows dialog
- [ ] Handle accepted case (get_result())
- [ ] Handle cancelled case (optional)
- [ ] Update UI after dialog closes
- [ ] Test with both valid and invalid inputs
- [ ] Test cancel behavior
- [ ] Test keyboard shortcuts (Enter/Escape)

---

## Example Integration

```python
from PyQt6.QtWidgets import QMainWindow, QPushButton
from src.ui.dialogs import EditScoreDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create Edit Score button
        self.edit_score_btn = QPushButton("Edit Score")
        self.edit_score_btn.clicked.connect(self._on_edit_score)

    def _on_edit_score(self):
        """Handle Edit Score button click."""
        # Get current state
        current = self.rally_manager.get_current_score()
        is_doubles = self.game_config.is_doubles

        # Create and show dialog
        dialog = EditScoreDialog(
            current_score=current,
            is_doubles=is_doubles,
            parent=self
        )

        # Handle result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result:
                # Apply the correction
                self.rally_manager.edit_score(
                    result.new_score,
                    result.comment
                )

                # Update UI
                self._update_score_display()

                # Save session
                self.session_manager.save()
```

---

## Tips

1. **Always pass parent:** Ensures proper modal behavior and dialog positioning
2. **Check result exists:** Although rare, always check `if result:` after accepted
3. **Update UI after dialog:** Dialog doesn't auto-refresh parent window
4. **Save after changes:** Remember to save session after applying dialog results
5. **Log interventions:** Consider logging manual corrections for audit trail

---

## Troubleshooting

### Dialog doesn't appear
- Check parent is valid QWidget
- Ensure dialog.exec() is called (not dialog.show())

### Apply button stays disabled
- Check validation logic matches input format
- For Edit Score/Force Side-Out: score must match X-Y or X-Y-Z
- For Add Comment: comment must be non-empty

### Result is None after accepting
- Should not happen, but check dialog._on_apply() is setting self.result
- File a bug if this occurs

### Styling looks wrong
- Ensure QApplication is created before dialog
- Check color/font imports are correct
- Verify QSS stylesheet is applied

---

## File Locations

```
src/ui/dialogs/
├── edit_score.py              # Edit Score Dialog
├── force_sideout.py           # Force Side-Out Dialog
└── add_comment.py             # Add Comment Dialog

test_dialogs.py                # Smoke test
test_dialogs_visual.py         # Visual test
```

---

**Last Updated:** 2026-01-14
**Version:** 1.0
