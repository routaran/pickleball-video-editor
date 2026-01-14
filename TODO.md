# Project TODO Tracker
## Pickleball Video Editor Tool

**Legend:**
- `[ ]` - Not started
- `[-]` - In progress
- `[x]` - Completed

**Last Updated:** 2026-01-14

---

## Phase 0: Project Planning & Documentation
> Design documents and specifications

- [x] Create INCEPTION.md with initial concept
- [x] Conduct PRD interview and create docs/PRD.md
- [x] Define UI/UX details and create docs/UI_SPEC.md
- [x] Design UI prototypes in docs/UI_PROTOTYPES.md
- [x] Finalize tech stack in docs/TECH_STACK.md
- [x] Create detailed design docs/DETAILED_DESIGN.md
- [x] Create this TODO.md tracker
- [x] **GIT CHECKPOINT**: Commit "Complete project planning and documentation"

---

## Phase 1: Project Setup & Infrastructure
> Basic project structure, dependencies, and configuration

- [ ] Create project directory structure per TECH_STACK.md Section 6
- [ ] Create pyproject.toml with project metadata
- [ ] Create requirements.txt with pinned versions
- [ ] Create src/__init__.py and package structure
- [ ] Create README.md with setup instructions
- [ ] Set up virtual environment documentation
- [ ] Verify system dependencies installed (mpv, ffmpeg, qt6-base)
- [ ] Verify Python packages install correctly (PyQt6, python-mpv)
- [ ] Create basic application entry point (src/main.py)
- [ ] **GIT CHECKPOINT**: Commit "Set up project infrastructure and dependencies"

---

## Phase 2: Core Domain Classes
> Score state machine, rally management, data models

### 2.1 Data Models
- [ ] Create src/core/models.py
- [ ] Implement Rally dataclass
- [ ] Implement ScoreSnapshot dataclass
- [ ] Implement ServerInfo dataclass
- [ ] Implement Action dataclass
- [ ] Implement ActionType enum
- [ ] Implement SessionState dataclass
- [ ] **GIT CHECKPOINT**: Commit "Add core data models"

### 2.2 Score State Machine
- [ ] Create src/core/score_state.py
- [ ] Implement ScoreState.__init__() for singles/doubles
- [ ] Implement server_wins() for singles
- [ ] Implement receiver_wins() for singles
- [ ] Implement server_wins() for doubles (server rotation)
- [ ] Implement receiver_wins() for doubles (side-out logic)
- [ ] Implement is_game_over() for standard games (win by 2)
- [ ] Implement is_game_over() for timed games
- [ ] Implement get_score_string() formatting
- [ ] Implement get_server_info()
- [ ] Implement set_score() for manual editing
- [ ] Implement force_side_out()
- [ ] Implement save_snapshot() / restore_snapshot() for undo
- [ ] Implement to_dict() / from_dict() serialization
- [ ] Write unit tests for ScoreState
- [ ] **GIT CHECKPOINT**: Commit "Implement score state machine with tests"

### 2.3 Rally Manager
- [ ] Create src/core/rally_manager.py
- [ ] Implement RallyManager.__init__()
- [ ] Implement start_rally() with padding
- [ ] Implement end_rally() with padding
- [ ] Implement is_rally_in_progress()
- [ ] Implement get_rally_count()
- [ ] Implement get_rallies()
- [ ] Implement update_rally_timing()
- [ ] Implement update_rally_score()
- [ ] Implement undo() with action stack
- [ ] Implement can_undo()
- [ ] Implement to_segments() for Kdenlive export
- [ ] Implement to_dict() / from_dict() serialization
- [ ] Write unit tests for RallyManager
- [ ] **GIT CHECKPOINT**: Commit "Implement rally manager with tests"

---

## Phase 3: Video Integration
> MPV embedding and video probe utilities

### 3.1 Video Probe
- [ ] Create src/video/probe.py
- [ ] Implement probe_video() using ffprobe
- [ ] Extract fps, duration, resolution
- [ ] Extract codec info
- [ ] Handle probe errors gracefully
- [ ] Write unit tests for video probe
- [ ] **GIT CHECKPOINT**: Commit "Add video probe utility"

### 3.2 MPV Player Widget
- [ ] Create src/video/player.py
- [ ] Create VideoWidget class extending QWidget
- [ ] Configure MPV embedding with wid parameter
- [ ] Implement load() method
- [ ] Implement play() / pause() / toggle_pause()
- [ ] Implement seek() by seconds
- [ ] Implement seek_frame() by frame number
- [ ] Implement frame_step() / frame_back_step()
- [ ] Implement set_speed()
- [ ] Implement get_position() / get_position_frame()
- [ ] Implement get_duration()
- [ ] Implement show_osd() for messages
- [ ] Create position_changed signal
- [ ] Create duration_changed signal
- [ ] Test MPV embedding in standalone PyQt6 window
- [ ] Verify arrow key navigation works (5-second skip)
- [ ] **GIT CHECKPOINT**: Commit "Implement MPV player widget with embedding"

---

## Phase 4: UI Foundation
> Basic window structure, styling, common widgets

### 4.1 Application Shell
- [ ] Create src/app.py with QApplication setup
- [ ] Create src/ui/__init__.py
- [ ] Create application icon (optional)
- [ ] **GIT CHECKPOINT**: Commit "Set up application shell"

### 4.2 Design System & Stylesheet
> Implement "Court Green" theme per UI_SPEC.md Section 2

- [ ] Create src/ui/styles/__init__.py
- [ ] Create src/ui/styles/colors.py with color constants from UI_SPEC.md Section 2.2
- [ ] Create src/ui/styles/fonts.py with typography constants from UI_SPEC.md Section 2.3
- [ ] Create src/ui/styles/theme.qss master stylesheet
- [ ] Implement background color classes (--bg-primary, --bg-secondary, --bg-tertiary)
- [ ] Implement action color classes (rally-start, server-wins, receiver-wins, undo)
- [ ] Implement button state styles (active with glow, normal, disabled with opacity)
- [ ] Implement text color classes (primary, secondary, accent, warning, disabled)
- [ ] Implement spacing utilities per UI_SPEC.md Section 2.4
- [ ] Implement border radius styles per UI_SPEC.md Section 2.5
- [ ] Implement dialog styling per UI_SPEC.md Section 6.1
- [ ] Implement toast notification styling per UI_SPEC.md Section 6.8
- [ ] Test stylesheet loads correctly in QApplication
- [ ] Verify font rendering (JetBrains Mono / IBM Plex Sans fallbacks)
- [ ] **GIT CHECKPOINT**: Commit "Implement Court Green design system and stylesheet"

### 4.3 Custom Widgets
- [ ] Create src/ui/widgets/__init__.py
- [ ] Create src/ui/widgets/video_widget.py (wraps VideoWidget)
- [ ] Create src/ui/widgets/rally_button.py
- [ ] Implement RallyButton with color states (active, normal, disabled) per UI_SPEC.md Section 2.2.4
- [ ] Implement pulse animation for active state per UI_SPEC.md Section 7.1.1
- [ ] Implement set_active() / set_disabled() methods
- [ ] Create src/ui/widgets/status_overlay.py
- [ ] Implement StatusOverlay with status dot, score, server info per UI_SPEC.md Section 4.2.2
- [ ] Create src/ui/widgets/playback_controls.py
- [ ] Implement playback buttons (frame step, play/pause, speed toggle group)
- [ ] Implement time display label with monospace font
- [ ] Create src/ui/widgets/toast.py
- [ ] Implement Toast notification widget per UI_SPEC.md Section 6.8
- [ ] Implement auto-dismiss timer (4 seconds)
- [ ] **GIT CHECKPOINT**: Commit "Create custom UI widgets"

### 4.4 Setup Dialog
- [ ] Create src/ui/setup_dialog.py
- [ ] Implement file browser for video selection
- [ ] Implement game type dropdown (Singles/Doubles)
- [ ] Implement victory rules dropdown (11/9/Timed)
- [ ] Implement player name fields (dynamic for singles/doubles)
- [ ] Implement Team 1 accent border container (first server indicator) per UI_SPEC.md Section 3.1
- [ ] Implement required field indicators (*) per UI_SPEC.md Section 3.1
- [ ] Implement inline validation with error messages per UI_SPEC.md Section 3.3
- [ ] Implement get_config() to return setup data
- [ ] Style dialog per UI_SPEC.md Section 3
- [ ] **GIT CHECKPOINT**: Commit "Implement setup dialog"

---

## Phase 5: Main Window - Editing Mode
> Primary editing interface with rally marking

### 5.1 Main Window Structure
- [ ] Create src/ui/main_window.py
- [ ] Set up QMainWindow with central widget
- [ ] Create layout: video, playback, state bar, rally controls, interventions, session
- [ ] Integrate VideoWidget
- [ ] Integrate PlaybackControls
- [ ] Integrate StateBar
- [ ] Add rally control buttons (Rally Start, Server Wins, Receiver Wins, Undo)
- [ ] Add intervention buttons (Edit Score, Force Side-Out, Add Comment, Time Expired)
- [ ] Add session buttons (Save Session, Final Review, Save & Quit)
- [ ] Implement window title with filename
- [ ] **GIT CHECKPOINT**: Commit "Create main window structure and layout"

### 5.2 Rally Marking Logic
- [ ] Connect Rally Start button to on_rally_start()
- [ ] Implement on_rally_start() - capture timestamp, update state
- [ ] Connect Server Wins button to on_server_wins()
- [ ] Implement on_server_wins() - end rally, update score
- [ ] Connect Receiver Wins button to on_receiver_wins()
- [ ] Implement on_receiver_wins() - end rally, update score
- [ ] Connect Undo button to on_undo()
- [ ] Implement on_undo() - revert action, seek video
- [ ] Implement button state management (highlight/dim based on rally state)
- [ ] Implement OSD feedback for rally events
- [ ] Implement state bar updates after each action

### 5.3 Playback Integration
- [ ] Connect playback controls to VideoWidget
- [ ] Implement play/pause toggle
- [ ] Implement frame step forward/backward
- [ ] Implement speed selection (0.5x, 1x, 2x)
- [ ] Implement time display updates
- [ ] Verify MPV arrow keys still work for 5-second skip
- [ ] **GIT CHECKPOINT**: Commit "Implement rally marking and playback controls"

---

## Phase 6: Modal Dialogs
> Intervention and system dialogs

### 6.1 Intervention Dialogs
- [ ] Create src/ui/dialogs/__init__.py
- [ ] Create src/ui/dialogs/edit_score.py
- [ ] Implement Edit Score dialog per UI_PROTOTYPES.md Section 4.1
- [ ] Implement score format validation
- [ ] Create src/ui/dialogs/force_sideout.py
- [ ] Implement Force Side-Out dialog with optional score field
- [ ] Create src/ui/dialogs/add_comment.py
- [ ] Implement Add Comment dialog with duration field

### 6.2 System Dialogs
- [ ] Create src/ui/dialogs/game_over.py
- [ ] Implement Game Over dialog (standard and timed variants)
- [ ] Implement Continue Editing vs Finish Game options
- [ ] Create src/ui/dialogs/resume_session.py
- [ ] Implement Resume Session dialog with session details
- [ ] Implement Start Fresh vs Resume options
- [ ] Create src/ui/dialogs/unsaved_warning.py
- [ ] Implement Unsaved Changes warning dialog
- [ ] **GIT CHECKPOINT**: Commit "Create all modal dialog UIs"

### 6.3 Dialog Integration
- [ ] Connect Edit Score button to dialog
- [ ] Apply score changes from dialog
- [ ] Connect Force Side-Out button to dialog
- [ ] Apply side-out changes from dialog
- [ ] Connect Add Comment button to dialog
- [ ] Store comments with timestamp
- [ ] Connect Time Expired button (timed games only)
- [ ] Trigger Game Over on winning condition
- [ ] Show Unsaved Warning on close if dirty
- [ ] **GIT CHECKPOINT**: Commit "Integrate modal dialogs with main window"

---

## Phase 7: Session Management
> Save, load, and resume functionality

### 7.1 Session Manager
- [ ] Create src/core/session_manager.py
- [ ] Implement SessionManager.__init__() with session directory
- [ ] Implement _get_video_hash() for session identification
- [ ] Implement save() - serialize state to JSON
- [ ] Implement load() - deserialize state from JSON
- [ ] Implement find_existing() - check for existing session
- [ ] Implement delete() - remove session file
- [ ] Create session directory if not exists (~/.local/share/pickleball-editor/sessions/)
- [ ] **GIT CHECKPOINT**: Commit "Implement session manager"

### 7.2 Session Integration
- [ ] Check for existing session on video selection in Setup
- [ ] Show Resume Session dialog if session exists
- [ ] Implement session restore in MainWindow
- [ ] Restore score state from session
- [ ] Restore rally list from session
- [ ] Seek video to last position
- [ ] Connect Save Session button
- [ ] Connect Save & Quit button
- [ ] Auto-save prompt on close with unsaved changes
- [ ] **GIT CHECKPOINT**: Commit "Integrate session save/load with application"

---

## Phase 8: Final Review Mode
> Rally verification and adjustment interface

### 8.1 Review Mode UI
- [ ] Create src/ui/review_mode.py
- [ ] Implement ReviewMode widget/panel
- [ ] Display "Rally X of Y" header
- [ ] Implement timing adjustment controls (+/- 0.1s buttons)
- [ ] Implement score adjustment text field
- [ ] Implement cascade checkbox
- [ ] Implement rally list grid (clickable)
- [ ] Highlight current rally in list
- [ ] Implement Previous/Next navigation buttons
- [ ] Implement Play Rally button
- [ ] Implement Exit Review button
- [ ] Implement Generate Kdenlive button

### 8.2 Review Mode Logic
- [ ] Implement navigate_to_rally() - seek video, update display
- [ ] Implement click-to-navigate on rally list
- [ ] Implement adjust_start_timing()
- [ ] Implement adjust_end_timing()
- [ ] Implement edit_score() with cascade logic
- [ ] Implement Play Rally - play from start to end
- [ ] Implement score cascade recalculation
- [ ] **GIT CHECKPOINT**: Commit "Implement final review mode UI and logic"

### 8.3 Mode Switching
- [ ] Implement enter_review_mode() - swap UI panels
- [ ] Implement exit_review_mode() - restore editing UI
- [ ] Connect Final Review button to enter_review_mode()
- [ ] Connect Exit Review button to exit_review_mode()
- [ ] **GIT CHECKPOINT**: Commit "Add mode switching between editing and review"

---

## Phase 9: Output Generation
> Kdenlive project and subtitle file creation

### 9.1 Subtitle Generator
- [ ] Create src/output/__init__.py
- [ ] Create src/output/subtitle_generator.py
- [ ] Implement frames_to_srt_time()
- [ ] Implement generate_srt() from segments
- [ ] Handle output timeline (cumulative timing)

### 9.2 Kdenlive Generator
- [ ] Create src/output/kdenlive_generator.py
- [ ] Port/adapt existing generate_project.py code
- [ ] Implement frames_to_timecode()
- [ ] Implement generate_kdenlive_xml()
- [ ] Include subtitle filter in XML
- [ ] Implement generate() main function
- [ ] Write files to ~/Videos/pickleball/
- [ ] **GIT CHECKPOINT**: Commit "Implement Kdenlive and subtitle generators"

### 9.3 Debug Exporter
- [ ] Create src/output/debug_export.py
- [ ] Implement export() - full session data to JSON
- [ ] Include rallies, interventions, comments
- [ ] Write to ~/Videos/debug/

### 9.4 Output Integration
- [ ] Connect Generate Kdenlive button to generator
- [ ] Convert rally list to segments format
- [ ] Call generator with video path, segments, profile
- [ ] Show success message with file paths
- [ ] Auto-export debug JSON after generation
- [ ] **GIT CHECKPOINT**: Commit "Integrate output generation with application"

---

## Phase 10: Polish & Edge Cases
> Error handling, validation, user experience improvements

### 10.1 Error Handling
- [ ] Handle video file not found
- [ ] Handle video load failure
- [ ] Handle invalid score format input
- [ ] Handle session save/load failures
- [ ] Handle Kdenlive generation failures
- [ ] Display appropriate error dialogs

### 10.2 Validation & Warnings
- [ ] Prevent Rally End without Rally Start
- [ ] Prevent Rally Start while rally in progress
- [ ] Validate score format in Edit Score dialog
- [ ] Warn on close with unsaved changes
- [ ] Confirm before Start Fresh (deleting session)

### 10.3 User Experience
- [ ] Show OSD message on rally start ("Rally started...")
- [ ] Show OSD message on rally end with result
- [ ] Display current score persistently on video
- [ ] Ensure button colors match UI_SPEC.md
- [ ] Test window resizing and video aspect ratio
- [ ] Set minimum window size (1024x768)

### 10.4 Edge Cases
- [ ] Handle very short rallies
- [ ] Handle overlapping rally timestamps (validation)
- [ ] Handle game already over (Continue Editing flow)
- [ ] Handle empty rally list in Final Review
- [ ] Handle timed game with tied score
- [ ] **GIT CHECKPOINT**: Commit "Add error handling, validation, and polish"

---

## Phase 11: Testing
> Unit tests, integration tests, manual testing

### 11.1 Unit Tests
- [ ] Create tests/__init__.py
- [ ] Create tests/test_score_state.py
- [ ] Test singles scoring rules
- [ ] Test doubles scoring rules (server rotation)
- [ ] Test game over conditions
- [ ] Test undo functionality
- [ ] Create tests/test_rally_manager.py
- [ ] Test rally start/end with padding
- [ ] Test undo for rallies
- [ ] Test to_segments() output
- [ ] Create tests/test_kdenlive_generator.py
- [ ] Test XML output validity
- [ ] Test SRT output format

### 11.2 Integration Tests
- [ ] Test full session save/load cycle
- [ ] Test video load and playback
- [ ] Test rally marking end-to-end
- [ ] Test Kdenlive file opens in Kdenlive

### 11.3 Manual Testing
- [ ] Test with real pickleball footage (singles)
- [ ] Test with real pickleball footage (doubles)
- [ ] Verify subtitle timing in Kdenlive
- [ ] Verify cut points in Kdenlive
- [ ] Test session resume after restart
- [ ] Test all modal dialogs
- [ ] **GIT CHECKPOINT**: Commit "Add comprehensive test suite"

---

## Phase 12: Documentation & Release
> Final documentation and packaging

- [ ] Complete README.md with full instructions
- [ ] Add screenshots to documentation
- [ ] Document known limitations
- [ ] Create sample/demo workflow
- [ ] **GIT CHECKPOINT**: Commit "Complete documentation"
- [ ] Tag version 1.0.0 in git
- [ ] Optional: Create PyInstaller executable

---

## Summary

| Phase | Description | Checkpoints | Status |
|-------|-------------|-------------|--------|
| 0 | Project Planning & Documentation | 1 | Complete |
| 1 | Project Setup & Infrastructure | 1 | Not Started |
| 2 | Core Domain Classes | 3 | Not Started |
| 3 | Video Integration | 2 | Not Started |
| 4 | UI Foundation | 4 | Not Started |
| 5 | Main Window - Editing Mode | 2 | Not Started |
| 6 | Modal Dialogs | 2 | Not Started |
| 7 | Session Management | 2 | Not Started |
| 8 | Final Review Mode | 2 | Not Started |
| 9 | Output Generation | 2 | Not Started |
| 10 | Polish & Edge Cases | 1 | Not Started |
| 11 | Testing | 1 | Not Started |
| 12 | Documentation & Release | 1 | Not Started |

---

## Checkpoint Strategy

**Frequent Checkpoints (2-4 per phase):**
- Phase 2 (Core Classes): Complex logic, high risk of bugs
- Phase 3-4 (Video/UI Foundation): Critical infrastructure, design system
- Phase 5-9 (Main Features): Each feature should be rollback-able

**Single Checkpoint (1 per phase):**
- Phase 1 (Setup): Config only, low risk
- Phase 10 (Polish): Can rollback all polish if needed
- Phase 11 (Tests): Tests shouldn't break production code
- Phase 12 (Docs): Documentation only

**Total Checkpoints: 24**

---

*Total Tasks: ~215 (including checkpoints)*
*Completed: ~8 (Phase 0)*
