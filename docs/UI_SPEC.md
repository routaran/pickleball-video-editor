# UI/UX Specification Document
## Pickleball Video Editor Tool

**Version:** 2.1
**Date:** 2026-01-14
**Status:** Revised - Keyboard Shortcuts Added

---

## 1. Application Structure

### 1.1 Window Hierarchy

| Window | Type | Description |
|--------|------|-------------|
| Setup Dialog | Modal | Initial configuration before editing |
| Main Window | Primary | Video playback and rally marking |
| Final Review Mode | In-place | Replaces main controls for review |
| Intervention Dialogs | Modal | Edit Score, Force Side-Out, Add Comment |
| System Dialogs | Modal | Game Over, Resume Session, Unsaved Warning |

### 1.2 Application Flow

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Launch    │────▶│  Setup Dialog   │────▶│   Main Window   │
└─────────────┘     └─────────────────┘     │  (Editing Mode) │
                           │               └────────┬────────┘
                           │                        │
                   ┌───────▼───────┐        ┌───────▼───────┐
                   │Resume Session?│        │ Final Review  │
                   │   (if found)  │        │    Mode       │
                   └───────────────┘        └───────────────┘
```

---

## 2. Design System

### 2.1 Design Philosophy

**Theme:** "Court Green" - A dark, professional theme inspired by pickleball court aesthetics
- Optimized for extended video editing sessions (reduced eye strain)
- High contrast for critical action buttons
- Color palette derived from court colors and equipment

**Aesthetic Direction:**
- Industrial/utilitarian with sport-inspired accents
- Clean, functional typography optimized for timecode display
- Deliberate use of glow effects to indicate active states
- Generous spacing in control areas for accurate mouse targeting

### 2.2 Color Palette

#### 2.2.1 Background Colors

| Purpose | Color | Hex | Usage |
|---------|-------|-----|-------|
| Primary Background | Deep Slate | `#1A1D23` | Main window background |
| Secondary Background | Elevated Surface | `#252A33` | Panels, containers |
| Tertiary Background | Card Surface | `#2D3340` | Buttons, input fields |
| Border | Subtle Edge | `#3D4450` | Dividers, borders |

#### 2.2.2 Action Colors

| Purpose | Color | Hex | Usage |
|---------|-------|-----|-------|
| Rally Start | Pickle Green | `#3DDC84` | Start rally button |
| Server Wins | Court Blue | `#4FC3F7` | Server wins button |
| Receiver Wins | Ball Orange | `#FFB300` | Receiver wins button |
| Undo/Danger | Coral Red | `#EF5350` | Undo, destructive actions |
| Primary Action | Accent Green | `#3DDC84` | Primary dialog buttons |

#### 2.2.3 Text Colors

| Purpose | Color | Hex | Usage |
|---------|-------|-----|-------|
| Primary Text | Off White | `#F5F5F5` | Main content |
| Secondary Text | Muted Gray | `#9E9E9E` | Labels, hints |
| Accent Text | Pickle Green | `#3DDC84` | Highlights, links |
| Warning Text | Amber | `#FFE082` | Warnings, WAITING status |
| Success Text | Green | `#3DDC84` | IN RALLY status |

#### 2.2.4 Button State Colors

Each action button has three states:

**Rally Start (Green)**
| State | Background | Border | Text | Effect |
|-------|------------|--------|------|--------|
| Active | `#3DDC84` | `#3DDC84` | `#1A1D23` | Glow: `0 0 20px rgba(61,220,132,0.4)` |
| Normal | `#2D3340` | `#3DDC84` | `#3DDC84` | None |
| Disabled | `#2D3340` | `#3D4450` | `#5A6270` | Opacity: 0.4, cursor: not-allowed |

**Server Wins (Blue)**
| State | Background | Border | Text | Effect |
|-------|------------|--------|------|--------|
| Active | `#4FC3F7` | `#4FC3F7` | `#1A1D23` | Glow: `0 0 20px rgba(79,195,247,0.4)` |
| Normal | `#2D3340` | `#4FC3F7` | `#4FC3F7` | None |
| Disabled | `#2D3340` | `#3D4450` | `#5A6270` | Opacity: 0.4, cursor: not-allowed |

**Receiver Wins (Orange)**
| State | Background | Border | Text | Effect |
|-------|------------|--------|------|--------|
| Active | `#FFB300` | `#FFB300` | `#1A1D23` | Glow: `0 0 20px rgba(255,179,0,0.4)` |
| Normal | `#2D3340` | `#FFB300` | `#FFB300` | None |
| Disabled | `#2D3340` | `#3D4450` | `#5A6270` | Opacity: 0.4, cursor: not-allowed |

**Undo (Red)** - Always same state
| State | Background | Border | Text | Effect |
|-------|------------|--------|------|--------|
| Normal | `#2D3340` | `#EF5350` | `#EF5350` | None |
| Hover | `#EF5350` | `#EF5350` | `#1A1D23` | None |

### 2.3 Typography

#### 2.3.1 Font Stack

```css
/* Display / Timecodes / Score */
--font-display: "JetBrains Mono", "Fira Code", "Consolas", monospace;

/* Body / Labels / Buttons */
--font-body: "IBM Plex Sans", "Segoe UI", "Roboto", sans-serif;
```

**Rationale:**
- Monospace for timecodes ensures consistent width as digits change
- JetBrains Mono has excellent number differentiation (0 vs O, 1 vs l)
- IBM Plex Sans is technical yet readable, good for UI labels

#### 2.3.2 Font Sizes

| Element | Size | Weight | Font |
|---------|------|--------|------|
| Score Display | 32px | Bold (700) | Display |
| Button Text (Rally) | 18px | SemiBold (600) | Body |
| Button Text (Other) | 14px | Medium (500) | Body |
| State Labels | 14px | Regular (400) | Body |
| Input Text | 14px | Regular (400) | Body |
| Secondary/Hints | 12px | Regular (400) | Body |
| Timestamps | 16px | Medium (500) | Display |
| Dialog Titles | 18px | SemiBold (600) | Body |

#### 2.3.3 Tabular Figures

All numeric displays MUST use tabular (monospaced) figures:
```css
font-variant-numeric: tabular-nums;
```

This prevents layout shift when scores update (e.g., "7-5-2" to "10-5-2").

### 2.4 Spacing System

Base unit: 8px

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | 4px | Tight gaps, icon padding |
| `--space-sm` | 8px | Between related elements |
| `--space-md` | 16px | Section padding |
| `--space-lg` | 24px | Between sections |
| `--space-xl` | 32px | Major section separation |
| `--space-2xl` | 48px | Panel margins |

### 2.5 Border Radius

| Element | Radius |
|---------|--------|
| Buttons | 6px |
| Cards/Panels | 8px |
| Input Fields | 4px |
| Dialogs | 12px |

---

## 3. Setup Dialog

### 3.1 Layout

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   New Editing Session                                           [×]   │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   SOURCE VIDEO                                                        │
│   ┌─────────────────────────────────────────────────────┐             │
│   │ /home/user/Videos/match_2026-01-14.mp4              │  [Browse]   │
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
│   ║              │ John Smith                                  │  ║   │
│   ║              └─────────────────────────────────────────────┘  ║   │
│   ║  Player 2 *  ┌─────────────────────────────────────────────┐  ║   │
│   ║              │ Jane Doe                                    │  ║   │
│   ║              └─────────────────────────────────────────────┘  ║   │
│   ╚═══════════════════════════════════════════════════════════════╝   │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │  TEAM 2                                                       │   │
│   ├───────────────────────────────────────────────────────────────┤   │
│   │  Player 1 *  ┌─────────────────────────────────────────────┐  │   │
│   │              │ Bob Johnson                                 │  │   │
│   │              └─────────────────────────────────────────────┘  │   │
│   │  Player 2 *  ┌─────────────────────────────────────────────┐  │   │
│   │              │ Alice Williams                              │  │   │
│   │              └─────────────────────────────────────────────┘  │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                                                                       │
│                                     ┌──────────┐  ╔════════════════╗  │
│                                     │  Cancel  │  ║ Start Editing  ║  │
│                                     └──────────┘  ╚════════════════╝  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

  * = Required field
  Team 1 container has accent border (first server indicator)
  Player 2 fields hidden in Singles mode
```

### 3.2 Controls

| Control | Type | Options/Behavior |
|---------|------|------------------|
| Source Video | File browser | MP4 files, shows full path |
| Game Type | Dropdown | Singles, Doubles |
| Victory Rules | Dropdown | Game to 11, Game to 9, Timed |
| Team 1 Container | Visual indicator | Accent border (`#3DDC84`) to indicate first server |
| Player Names | Text inputs | Required fields marked with `*`, Player 2 hidden in Singles |
| Cancel | Secondary Button | Close dialog, no action |
| Start Editing | Primary Button | Validate inputs, launch main window |

### 3.3 Validation Rules

- Source Video: Must be selected and file must exist
- Player Names: All visible fields must be non-empty
- Start Editing: Disabled (grayed) until all validation passes
- Show inline error messages below invalid fields

### 3.4 Visual States

| State | Start Editing Button |
|-------|---------------------|
| Invalid | Disabled state (opacity 0.4, no hover) |
| Valid | Primary action state (accent color, glow on hover) |

---

## 4. Main Window (Editing Mode)

### 4.1 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Pickleball Video Editor - match_2026-01-14.mp4               [─]  [□]  [×] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                                                                       │  │
│  │                                                                       │  │
│  │                        MPV VIDEO PLAYER                               │  │
│  │                          (16:9 area)                                  │  │
│  │                                                                       │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │  ● IN RALLY    Score: 7-5-2    Server: Team 1 (John) #2        │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  |◀   ◀◀   [     ▶     ]   ▶▶   ▶|      0.5x  1x  2x    03:45/09:15 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║                        RALLY CONTROLS                                 ║  │
│  ║                                                                       ║  │
│  ║   ╔════════════════╗   ┌────────────────┐   ┌──────────────────┐     ║  │
│  ║   ║  RALLY START   ║   │  SERVER WINS   │   │  RECEIVER WINS   │     ║  │
│  ║   ║    (active)    ║   │   (disabled)   │   │    (disabled)    │     ║  │
│  ║   ╚════════════════╝   └────────────────┘   └──────────────────┘     ║  │
│  ║                                                                       ║  │
│  ║                                                    ┌──────────────┐   ║  │
│  ║   Rally: 12                                        │     UNDO     │   ║  │
│  ║                                                    └──────────────┘   ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Edit Score   Force Side-Out   Add Comment   Time Expired*           │  │
│  │                                                                       │  │
│  │                          Save Session    Final Review    Save & Quit  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
  * Time Expired only visible for timed games
```

### 4.2 Component Sections

#### 4.2.1 Video Player Area

- Embedded MPV player
- Maintains 16:9 aspect ratio
- Resizes with window (min width: 640px)
- MPV arrow keys (5-second skip) remain functional
- **Status overlay** at bottom of video area (semi-transparent background)

#### 4.2.2 Status Overlay (Inside Video Area)

The status information is displayed as an overlay inside the video player area:

```
┌─────────────────────────────────────────────────────────────────────┐
│  ● IN RALLY    Score: 7-5-2    Server: Team 1 (John) #2            │
└─────────────────────────────────────────────────────────────────────┘
```

| Element | Style |
|---------|-------|
| Container | `background: rgba(26, 29, 35, 0.85)`, padding: 8px 16px |
| Status Indicator | Colored dot (`●`) + text, `#FFE082` for WAITING, `#3DDC84` for IN RALLY |
| Score | Large text (24px), bold, monospace |
| Server Info | Regular text (14px) |

#### 4.2.3 Playback Controls

| Control | Icon | Action |
|---------|------|--------|
| Frame Back | `\|◀` | Step back one frame |
| Slow Back | `◀◀` | Skip back 1 second |
| Play/Pause | `▶` / `\|\|` | Toggle playback |
| Slow Forward | `▶▶` | Skip forward 1 second |
| Frame Forward | `▶\|` | Step forward one frame |
| Speed 0.5x | `[0.5x]` | Half speed playback (toggle button) |
| Speed 1x | `[1x]` | Normal speed playback (toggle button) |
| Speed 2x | `[2x]` | Double speed playback (toggle button) |
| Time Display | `03:45/09:15` | Current position / Total duration (monospace) |

Speed buttons use toggle group behavior - one is always selected.

#### 4.2.4 Rally Controls Panel

This is the primary interaction zone - visually emphasized with a container border.

**Layout:**
```
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   ╔════════════════╗   ┌────────────────┐   ┌──────────────────┐     ║
║   ║  RALLY START   ║   │  SERVER WINS   │   │  RECEIVER WINS   │     ║
║   ╚════════════════╝   └────────────────┘   └──────────────────┘     ║
║                                                                       ║
║   Rally: 12                                        ┌──────────────┐   ║
║                                                    │     UNDO     │   ║
║                                                    └──────────────┘   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

**Container Styling:**
- Border: 2px solid `#3D4450`
- Border-radius: 8px
- Background: `#252A33`
- Padding: 24px

**Rally Button Sizing:**
| Button | Min Width | Height |
|--------|-----------|--------|
| Rally Start | 160px | 56px |
| Server Wins | 160px | 56px |
| Receiver Wins | 180px | 56px |
| Undo | 100px | 40px |

#### 4.2.5 Button State Behavior

**When Status = WAITING:**
```
╔════════════════╗   ┌────────────────┐   ┌──────────────────┐   ┌────────┐
║  RALLY START   ║   │  SERVER WINS   │   │  RECEIVER WINS   │   │  UNDO  │
║   (ACTIVE)     ║   │   (disabled)   │   │    (disabled)    │   │        │
║   [glow]       ║   │   [no hover]   │   │    [no hover]    │   │        │
╚════════════════╝   └────────────────┘   └──────────────────┘   └────────┘
     Green                Gray                   Gray                Red
```

**When Status = IN RALLY:**
```
┌────────────────┐   ╔════════════════╗   ╔══════════════════╗   ┌────────┐
│  RALLY START   │   ║  SERVER WINS   ║   ║  RECEIVER WINS   ║   │  UNDO  │
│   (disabled)   │   ║   (ACTIVE)     ║   ║    (ACTIVE)      ║   │        │
│   [no hover]   │   ║   [glow]       ║   ║    [glow]        ║   │        │
└────────────────┘   ╚════════════════╝   ╚══════════════════╝   └────────┘
      Gray                Blue                  Orange               Red
```

#### 4.2.6 Toolbar (Interventions + Session)

Combined into a single toolbar row for reduced visual complexity:

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Edit Score   Force Side-Out   Add Comment   Time Expired*               │
│                                                                           │
│                            Save Session    Final Review    Save & Quit    │
└───────────────────────────────────────────────────────────────────────────┘
```

| Button | Type | Visibility |
|--------|------|------------|
| Edit Score | Secondary | Always |
| Force Side-Out | Secondary | Always |
| Add Comment | Secondary | Always |
| Time Expired | Warning (Amber) | Timed games only |
| Names | Secondary | Hidden in highlights mode |
| New Game | Secondary | Hidden in highlights mode |
| Mark Court Corners | Secondary | Always |
| Save Session | Secondary | Always |
| Final Review | Primary | Always |
| Save & Quit | Secondary | Always |

---

## 5. Final Review Mode

### 5.1 Mode Indicator

When entering Final Review, display a persistent mode header:

```
╔═══════════════════════════════════════════════════════════════════════════╗
║  📋 FINAL REVIEW MODE                                    [Exit Review]    ║
║     Rally 5 of 23                                                         ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

- Icon + "FINAL REVIEW MODE" in accent color
- Exit button in header (always visible)
- Current rally indicator prominent

### 5.2 Layout (Replaces Rally Controls and Toolbar)

```
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║  📋 FINAL REVIEW MODE                                  [Exit Review]  ║  │
│  ║     Rally 5 of 23                                                     ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  TIMING                                                                 ││
│  │                                                                         ││
│  │   Start: 01:23.45                          End: 01:45.67               ││
│  │   [−0.1s]  [+0.1s]                         [−0.1s]  [+0.1s]            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  SCORE                                                                  ││
│  │                                                                         ││
│  │   CURRENT           NEW SCORE                                          ││
│  │   ┌───────┐         ┌──────────────────┐                               ││
│  │   │ 3-2-1 │    →    │                  │   ☑ Cascade to subsequent     ││
│  │   └───────┘         └──────────────────┘                               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  RALLY LIST (click to navigate)                                         ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │ Rally 1  │ Rally 2  │ Rally 3  │ Rally 4  │[Rally 5] │ Rally 6  │   ││
│  │  │  0-0-2   │  1-0-1   │  1-0-2   │  2-0-1   │  3-2-1   │  3-2-2   │   ││
│  │  ├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤   ││
│  │  │ Rally 7  │ Rally 8  │ Rally 9  │ Rally 10 │ Rally 11 │ ...      │   ││
│  │  │  3-3-1   │  4-3-1   │  4-3-2   │  5-3-1   │  5-3-2   │          │   ││
│  │  └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  NAVIGATION                                                             ││
│  │                                                                         ││
│  │   [◀ Previous]     [▶ Play Rally]     [Next ▶]                         ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ╔═════════════════════════════════════════════════════════════════════════╗│
│  ║  COMPLETE REVIEW                                                        ║│
│  ║                                                                         ║│
│  ║   ✓ 23 rallies marked                                                  ║│
│  ║   ✓ Score progression valid                                            ║│
│  ║                                                                         ║│
│  ║                  ╔═══════════════════════════════════╗                  ║│
│  ║                  ║         GENERATE PROJECT          ║                  ║│
│  ║                  ╚═══════════════════════════════════╝                  ║│
│  ║                                                                         ║│
│  ╚═════════════════════════════════════════════════════════════════════════╝│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Components

#### 5.3.1 Timing Adjustment

| Control | Action |
|---------|--------|
| Start −0.1s | Decrease rally start time by 0.1 seconds |
| Start +0.1s | Increase rally start time by 0.1 seconds |
| End −0.1s | Decrease rally end time by 0.1 seconds |
| End +0.1s | Increase rally end time by 0.1 seconds |

Time displays use monospace font for consistent width.

#### 5.3.2 Score Adjustment

| Control | Behavior |
|---------|----------|
| Current Score | Read-only display in muted box |
| Arrow | Visual `→` showing transformation |
| New Score Input | Text field, format validated |
| Cascade Checkbox | When checked, recalculates subsequent scores |

#### 5.3.3 Rally List

- Grid layout, wrapping rows
- Each cell shows Rally number + Score
- **Current rally highlighted** with accent border and background
- **Click any rally** to navigate and seek video
- Scrollable if many rallies

**Rally Cell States:**
| State | Style |
|-------|-------|
| Normal | Background: `#2D3340`, Border: `#3D4450` |
| Hover | Background: `#3D4450`, Border: `#4FC3F7` |
| Selected | Background: `#252A33`, Border: `#3DDC84` (2px), Glow effect |

#### 5.3.4 Navigation Controls

| Button | Action |
|--------|--------|
| ◀ Previous | Go to previous rally, seek video |
| ▶ Play Rally | Play video from rally start to end |
| Next ▶ | Go to next rally, seek video |

#### 5.3.5 Complete Review Section

Validation summary before export:
- Shows count of rallies marked
- Shows validation status (score progression)
- **Generate Project** as prominent primary action button

---

## 6. Modal Dialogs

### 6.1 Dialog Design Standards

All dialogs share common styling:

| Property | Value |
|----------|-------|
| Background | `#252A33` |
| Border | 1px solid `#3D4450` |
| Border Radius | 12px |
| Shadow | `0 8px 32px rgba(0,0,0,0.4)` |
| Title Font | 18px SemiBold |
| Padding | 24px |

**Button Placement:**
- Cancel (secondary) on left
- Primary action on right
- Primary action uses accent styling

### 6.2 Edit Score Dialog

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Edit Score                                                          │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   CURRENT                              NEW SCORE *                    │
│   ┌─────────────┐                      ┌───────────────────────────┐  │
│   │    7-5-2    │          →          │                           │  │
│   │   (frozen)  │                      └───────────────────────────┘  │
│   └─────────────┘                      Format: X-Y-Z (doubles)        │
│                                                                       │
│   ───────────────────────────────────────────────────────────────     │
│                                                                       │
│   COMMENT (optional)                                                  │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                                                               │   │
│   │                                                               │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                                                                       │
│                                      ┌──────────┐  ╔══════════════╗   │
│                                      │  Cancel  │  ║    Apply     ║   │
│                                      └──────────┘  ╚══════════════╝   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

  * Required field
```

**Validation:**
- Score format must match game type (X-Y for singles, X-Y-Z for doubles)
- Show inline error message if invalid
- Apply button disabled until valid

### 6.3 Force Side-Out Dialog

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Force Side-Out                                                      │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   Current Server                       After Side-Out                 │
│   ┌─────────────────────┐              ┌─────────────────────┐        │
│   │  Team 1 - Server 2  │      →      │  Team 2 - Server 1  │        │
│   └─────────────────────┘              └─────────────────────┘        │
│                                                                       │
│   ───────────────────────────────────────────────────────────────     │
│                                                                       │
│   NEW SCORE (optional)                                                │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                                                               │   │
│   └───────────────────────────────────────────────────────────────┘   │
│   Leave blank to keep current score                                   │
│                                                                       │
│   ───────────────────────────────────────────────────────────────     │
│                                                                       │
│   COMMENT (optional)                                                  │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                                                               │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                                                                       │
│                                      ┌──────────┐  ╔══════════════╗   │
│                                      │  Cancel  │  ║    Apply     ║   │
│                                      └──────────┘  ╚══════════════╝   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Shows preview of server change
- Optional score correction
- If score provided, validated same as Edit Score

### 6.4 Add Comment Dialog

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Add Comment                                                         │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   TIMESTAMP                                                           │
│   ┌───────────────┐                                                   │
│   │   03:45.23    │                                                   │
│   └───────────────┘                                                   │
│                                                                       │
│   ───────────────────────────────────────────────────────────────     │
│                                                                       │
│   COMMENT *                                                           │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │                                                               │   │
│   │                                                               │   │
│   │                                                               │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│   DURATION                                                            │
│   ┌─────────┐  seconds                                                │
│   │    5    │                                                         │
│   └─────────┘                                                         │
│                                                                       │
│                                                                       │
│                                      ┌──────────┐  ╔══════════════╗   │
│                                      │  Cancel  │  ║     Add      ║   │
│                                      └──────────┘  ╚══════════════╝   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘

  * Required field
  Default duration: 5 seconds
```

### 6.5 Game Over Dialog

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Game Over                                                           │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│                                                                       │
│                    ╔═══════════════════════════════╗                  │
│                    ║                               ║                  │
│                    ║        TEAM 1 WINS!           ║                  │
│                    ║                               ║                  │
│                    ╚═══════════════════════════════╝                  │
│                                                                       │
│                         Final Score: 11-9                             │
│                                                                       │
│                           23 rallies                                  │
│                                                                       │
│                                                                       │
│   ┌─────────────────────────┐          ╔═════════════════════════╗    │
│   │    Continue Editing     │          ║     Finish Game         ║    │
│   │   (in case of miscount) │          ╚═════════════════════════╝    │
│   └─────────────────────────┘                                         │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**Variant for Timed Games:**
- Title: "Time Expired - Game Over"
- Subtitle: "(Highest score wins)"

### 6.6 Resume Session Dialog

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Resume Session?                                                     │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   Found saved session for:                                            │
│                                                                       │
│   ┌───────────────────────────────────────────────────────────────┐   │
│   │  match_2026-01-14.mp4                                         │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│   ───────────────────────────────────────────────────────────────     │
│                                                                       │
│   SESSION DETAILS                                                     │
│                                                                       │
│   • Progress:       15 rallies marked                                 │
│   • Current Score:  8-6-1                                             │
│   • Last Position:  05:23.45                                          │
│   • Game Type:      Doubles                                           │
│   • Victory Rules:  Game to 11                                        │
│                                                                       │
│                                                                       │
│   ┌─────────────────────────┐          ╔═════════════════════════╗    │
│   │      Start Fresh        │          ║    Resume Session       ║    │
│   └─────────────────────────┘          ╚═════════════════════════╝    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### 6.7 Unsaved Changes Warning

```
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   Unsaved Changes                                                     │
│                                                                       │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│                                                                       │
│              You have unsaved changes that will be lost.              │
│                                                                       │
│                                                                       │
│                                                                       │
│   ┌─────────────┐     ┌─────────────┐     ╔═════════════════════╗     │
│   │ Don't Save  │     │   Cancel    │     ║    Save & Quit      ║     │
│   └─────────────┘     └─────────────┘     ╚═════════════════════╝     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### 6.8 Error/Warning Toast

For non-blocking warnings, use a toast notification:

```
┌───────────────────────────────────────────────────────────────────┐
│  ⚠  Cannot end rally - no rally in progress                  [×] │
└───────────────────────────────────────────────────────────────────┘
```

- Position: Top-center, below title bar
- Auto-dismiss after 4 seconds
- Background: `#2D3340` with amber left border
- Dismiss button on right

---

## 7. Animations & Micro-interactions

### 7.1 Button Interactions

#### 7.1.1 Active Rally Button Pulse

When a rally button is in ACTIVE state, apply subtle pulse animation:

```css
@keyframes rally-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--button-glow-color);
  }
  50% {
    box-shadow: 0 0 20px 4px var(--button-glow-color);
  }
}

.rally-button.active {
  animation: rally-pulse 2s ease-in-out infinite;
}
```

#### 7.1.2 Button Hover

```css
.button:hover:not(:disabled) {
  transform: translateY(-1px);
  transition: transform 0.15s ease;
}

.button:active:not(:disabled) {
  transform: translateY(0);
}
```

### 7.2 State Transitions

#### 7.2.1 Status Change

When status changes (WAITING ↔ IN RALLY):

```css
.status-indicator {
  transition: color 0.3s ease, background-color 0.3s ease;
}

.score-display {
  transition: transform 0.2s ease;
}

.score-display.updated {
  animation: score-flash 0.4s ease;
}

@keyframes score-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(61, 220, 132, 0.2); }
}
```

#### 7.2.2 Mode Switch (Editing ↔ Review)

```css
.editing-controls {
  animation: slide-out-down 0.3s ease forwards;
}

.review-controls {
  animation: slide-in-up 0.3s ease forwards;
}

@keyframes slide-out-down {
  from { opacity: 1; transform: translateY(0); }
  to { opacity: 0; transform: translateY(20px); }
}

@keyframes slide-in-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### 7.3 Rally List Interactions

```css
.rally-cell {
  transition: transform 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.rally-cell:hover {
  transform: scale(1.02);
}

.rally-cell.selected {
  transform: scale(1.05);
}
```

### 7.4 Dialog Animations

```css
.modal-backdrop {
  animation: fade-in 0.2s ease;
}

.modal-dialog {
  animation: scale-in 0.2s ease;
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes scale-in {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}
```

---

## 8. Visual Feedback

### 8.1 MPV OSD Messages

| Event | OSD Message | Duration |
|-------|-------------|----------|
| Rally Start | "Rally started..." | Until rally ends |
| Server Wins | "Server wins - [new score]" | 2 seconds |
| Receiver Wins | "Receiver wins - [new score]" | 2 seconds |
| Score Update | Current score in large text | Persistent |

### 8.2 Application Feedback

| Event | Feedback |
|-------|----------|
| Rally started | Status changes to IN RALLY (green), Rally Start stops pulsing, Server/Receiver start pulsing |
| Rally ended | Status changes to WAITING (amber), score flashes, Rally Start starts pulsing |
| Score edited | Score display flashes briefly |
| Session saved | Toast: "Session saved" |
| Kdenlive generated | Toast: "Project saved to ~/Videos/pickleball/" |

### 8.3 Error Prevention

| Condition | Feedback |
|-----------|----------|
| Rally End without Start | Toast warning, disabled button has no hover |
| Rally Start while in rally | Toast warning, disabled button has no hover |
| Invalid score format | Inline error below input, Apply disabled |
| Empty required field | Field border turns red, Apply disabled |

---

## 9. Keyboard and Mouse Interaction

### 9.1 Global Keyboard Shortcuts (Editing Mode)

The application implements global keyboard shortcuts that work throughout the editing mode, regardless of button focus state. The shortcuts are registered as window-level `QShortcut`s, so they fire regardless of which widget owns focus; rally buttons use `StrongFocus` policy to support Tab navigation.

**Playback Control:**

| Key | Action | Notes |
|-----|--------|-------|
| Space | Pause/Unpause video | Toggle playback state |
| K | Pause/Unpause video | Secondary play/pause |
| ← (Left Arrow) | Seek back 5 seconds | Same as MPV default |
| → (Right Arrow) | Seek forward 5 seconds | Same as MPV default |
| ↓ (Down Arrow) | Seek back (long) | Configurable large skip |
| ↑ (Up Arrow) | Seek forward (long) | Configurable large skip |

**Rally Actions:**

| Key | Action | When Available |
|-----|--------|----------------|
| C | Rally Start | When status is WAITING |
| S | Server Wins | When status is IN RALLY |
| R | Receiver Wins | When status is IN RALLY |
| U | Undo | When there is action to undo (also pauses video) |

**Touch Counters:**

| Key | Action | When Available |
|-----|--------|----------------|
| J | Increment Ravi touch count | Editing mode (key configurable) |
| E | Increment Partner touch count | Editing mode (key configurable) |
| Shift+J / Shift+E | Undo last touch for that player | Editing mode |

**Important Notes:**
- Shortcuts only work in editing mode, NOT in review mode
- All rally buttons use `setFocusPolicy(Qt.FocusPolicy.StrongFocus)` so they support Tab navigation; window-level `QShortcut`s (C/S/R/U/K/Space) fire regardless of which widget owns focus
- Keyboard shortcuts work even if a button appears focused from mouse interaction
- Undo (U) automatically pauses video playback for review

### 9.2 Mouse Controls

All application functions are fully accessible via mouse:
- All buttons are clickable
- Text inputs accept keyboard input when focused
- Rally buttons show hover states regardless of focus policy

### 9.3 Dialog Keyboard Behavior

| Key | Action |
|-----|--------|
| Escape | Close dialog (same as Cancel) |
| Enter | Submit primary action (if valid) |
| Tab | Navigate between inputs |

---

## 10. Window Behavior

### 10.1 Main Window

| Property | Value |
|----------|-------|
| Minimum Size | 800 × 540 px |
| Default Size | 1280 × 900 px |
| Resizable | Yes |
| Video Aspect | 16:9 maintained |

- Video player scales with window width
- Control panels maintain fixed heights
- Close button triggers Unsaved Changes dialog if dirty

### 10.2 Modal Dialogs

- Centered over main window
- Block interaction with main window (modal)
- Max width: 500px
- Escape key closes (equivalent to Cancel)

---

## 11. Accessibility

### 11.1 Color & Contrast

| Pair | Contrast Ratio | WCAG Level |
|------|----------------|------------|
| Primary Text on Background | 13.5:1 | AAA |
| Secondary Text on Background | 4.8:1 | AA |
| Button Text on Active | 8.2:1 | AAA |
| Disabled Text | 2.5:1 | (intentionally low) |

### 11.2 Non-Color Indicators

All states have non-color redundancy:
- Active buttons have glow + filled background
- Disabled buttons have reduced opacity + no hover cursor
- Status has colored dot + text label
- Errors have icon + text + border color

### 11.3 Focus Indicators

```css
:focus-visible {
  outline: 2px solid #3DDC84;
  outline-offset: 2px;
}
```

---

## Appendix A: CSS Custom Properties Reference

```css
:root {
  /* Backgrounds */
  --bg-primary: #1A1D23;
  --bg-secondary: #252A33;
  --bg-tertiary: #2D3340;
  --bg-border: #3D4450;

  /* Action Colors */
  --color-rally-start: #3DDC84;
  --color-server-wins: #4FC3F7;
  --color-receiver-wins: #FFB300;
  --color-undo: #EF5350;
  --color-primary: #3DDC84;

  /* Text */
  --text-primary: #F5F5F5;
  --text-secondary: #9E9E9E;
  --text-accent: #3DDC84;
  --text-warning: #FFE082;
  --text-disabled: #5A6270;

  /* Typography */
  --font-display: "JetBrains Mono", "Fira Code", "Consolas", monospace;
  --font-body: "IBM Plex Sans", "Segoe UI", "Roboto", sans-serif;

  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  /* Borders */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;

  /* Shadows */
  --shadow-sm: 0 2px 4px rgba(0,0,0,0.2);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.3);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.4);

  /* Glows */
  --glow-green: 0 0 20px rgba(61, 220, 132, 0.4);
  --glow-blue: 0 0 20px rgba(79, 195, 247, 0.4);
  --glow-orange: 0 0 20px rgba(255, 179, 0, 0.4);

  /* Transitions */
  --transition-fast: 0.15s ease;
  --transition-normal: 0.3s ease;
}
```

---

## Appendix B: UI Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Theme | Dark "Court Green" | Reduces eye strain, sport-inspired |
| Color System | Custom palette | Avoids generic Material look |
| Typography | JetBrains Mono + IBM Plex | Optimized for timecodes and readability |
| Button States | Glow + opacity | Clear active/disabled distinction |
| Status Display | Overlay in video | Always visible during playback |
| Rally Controls | Emphasized container | Primary actions need visual prominence |
| Toolbar | Combined row | Reduced visual complexity |
| Final Review | Mode indicator header | Clear mode awareness |
| Dialogs | Visual flow (current → new) | Clearer transformation preview |
| Animations | Subtle micro-interactions | Polish without distraction |

---

*Document Version: 2.1*
*Created: 2026-01-14*
*Revised: 2026-01-14 (Keyboard Shortcuts Added)*
