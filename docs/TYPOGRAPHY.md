# Typography System

**Module:** `src/ui/styles/fonts.py`

Typography constants and utilities for the Pickleball Video Editor, implementing the "Court Green" design system.

## Font Families

### Display Font (Monospace)
Primary: **JetBrains Mono**
Fallbacks: Fira Code, Consolas, monospace

Used for:
- Timecodes and timestamps
- Score displays
- Numeric values that need consistent width

### Body Font (Sans-Serif)
Primary: **IBM Plex Sans**
Fallbacks: Segoe UI, Roboto, sans-serif

Used for:
- UI labels and buttons
- Dialog text
- Body content

## Usage

### Basic Import

```python
from ui.styles.fonts import Fonts, SIZE_BUTTON_RALLY, WEIGHT_SEMIBOLD
```

### Creating Fonts

The `Fonts` class provides factory methods for creating QFont instances:

```python
# Predefined font types
score_font = Fonts.score_display()        # 32px bold monospace
button_font = Fonts.button_rally()        # 18px semibold sans-serif
timestamp = Fonts.timestamp()             # 16px medium monospace
label = Fonts.label()                     # 14px regular sans-serif

# Custom fonts
custom_display = Fonts.display(
    size=SIZE_BUTTON_RALLY,
    weight=WEIGHT_SEMIBOLD,
    tabular=True  # Enable monospace numbers
)

custom_body = Fonts.body(
    size=SIZE_STATE_LABELS,
    weight=WEIGHT_REGULAR
)
```

### Applying to Widgets

```python
from PyQt6.QtWidgets import QLabel
from ui.styles.fonts import Fonts

score_label = QLabel("11-9-2")
score_label.setFont(Fonts.score_display())

button = QPushButton("RALLY START")
button.setFont(Fonts.button_rally())
```

## Constants Reference

### Font Sizes (pixels)

| Constant | Value | Usage |
|----------|-------|-------|
| `SIZE_SCORE_DISPLAY` | 32px | Score overlay display |
| `SIZE_BUTTON_RALLY` | 18px | Rally action buttons |
| `SIZE_BUTTON_OTHER` | 14px | Secondary buttons |
| `SIZE_STATE_LABELS` | 14px | Status labels |
| `SIZE_INPUT` | 14px | Input fields |
| `SIZE_SECONDARY` | 12px | Helper text, captions |
| `SIZE_TIMESTAMPS` | 16px | Video timeline |
| `SIZE_DIALOG_TITLE` | 18px | Modal headers |

### Font Weights

| Constant | Value | Usage |
|----------|-------|-------|
| `WEIGHT_BOLD` | 700 | Strong emphasis, scores |
| `WEIGHT_SEMIBOLD` | 600 | Buttons, dialog titles |
| `WEIGHT_MEDIUM` | 500 | Timestamps, light emphasis |
| `WEIGHT_REGULAR` | 400 | Body text, labels |

### Spacing System (8px base unit)

| Constant | Value | Usage |
|----------|-------|-------|
| `SPACE_XS` | 4px | Tight gaps, icon padding |
| `SPACE_SM` | 8px | Between related elements |
| `SPACE_MD` | 16px | Section padding |
| `SPACE_LG` | 24px | Between sections |
| `SPACE_XL` | 32px | Major separation |
| `SPACE_2XL` | 48px | Panel margins |

### Border Radius

| Constant | Value | Usage |
|----------|-------|-------|
| `RADIUS_SM` | 4px | Input fields |
| `RADIUS_MD` | 6px | Buttons |
| `RADIUS_LG` | 8px | Cards/panels |
| `RADIUS_XL` | 12px | Modal dialogs |

## Design Rationale

### Monospace for Numbers
All numeric displays use tabular (monospace) figures to prevent layout shift when values change:
- "7-5-2" → "10-5-2" maintains alignment
- Ensures consistent button widths
- Critical for video timecodes

### Font Selection
- **JetBrains Mono**: Excellent number differentiation (0 vs O, 1 vs l)
- **IBM Plex Sans**: Technical yet readable, good for UI labels
- Both fonts support a wide range of weights

### Fallback Strategy
PyQt6 automatically selects the first available font from the fallback chain:
1. Try primary font (JetBrains Mono or IBM Plex Sans)
2. Try first fallback (Fira Code or Segoe UI)
3. Continue through fallback list
4. Use system default monospace/sans-serif

## Checking Font Availability

```python
from ui.styles.fonts import Fonts

available = Fonts.get_available_fonts()

if not available["JetBrains Mono"]:
    print("Warning: Primary display font not installed")
    print("Will use fallback fonts")
```

## Installing Recommended Fonts

### Arch Linux / Manjaro
```bash
# AUR packages
yay -S ttf-jetbrains-mono ttf-ibm-plex
```

### Ubuntu / Debian
```bash
# JetBrains Mono
sudo apt install fonts-jetbrains-mono

# IBM Plex (may need manual install)
# Download from: https://github.com/IBM/plex/releases
```

### Manual Installation
1. Download fonts:
   - JetBrains Mono: https://www.jetbrains.com/lp/mono/
   - IBM Plex: https://github.com/IBM/plex/releases

2. Install to `~/.local/share/fonts/` (Linux) or system fonts directory

3. Refresh font cache:
   ```bash
   fc-cache -fv
   ```

## Testing

Run the test script to verify font functionality:

```bash
python test_fonts.py
```

This checks:
- All constants are defined
- QFont instances can be created
- Which design system fonts are available on your system

## See Also

- **UI_SPEC.md**: Full visual design specification
- **colors.py**: Color constants for the "Court Green" theme
- **Design System**: Section 2.3 Typography in UI_SPEC.md
