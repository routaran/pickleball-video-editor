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

- [x] Create project directory structure per TECH_STACK.md Section 6
- [x] Create pyproject.toml with project metadata
- [x] Create requirements.txt with pinned versions
- [x] Create src/__init__.py and package structure
- [x] Create README.md with setup instructions
- [x] Set up virtual environment documentation
- [x] Verify system dependencies installed (mpv, ffmpeg, qt6-base)
- [x] Verify Python packages install correctly (PyQt6, python-mpv)
- [x] Create basic application entry point (src/main.py)
- [x] **GIT CHECKPOINT**: Commit "Set up project infrastructure and dependencies" (7542f31)

---

## Phase 2: Core Domain Classes
> Score state machine, rally management, data models

### 2.1 Data Models
- [x] Create src/core/models.py
- [x] Implement Rally dataclass
- [x] Implement ScoreSnapshot dataclass
- [x] Implement ServerInfo dataclass
- [x] Implement Action dataclass
- [x] Implement ActionType enum
- [x] Implement SessionState dataclass
- [x] **GIT CHECKPOINT**: Commit "Add core data models" (6e80163)

### 2.2 Score State Machine
- [x] Create src/core/score_state.py
- [x] Implement ScoreState.__init__() for singles/doubles
- [x] Implement server_wins() for singles
- [x] Implement receiver_wins() for singles
- [x] Implement server_wins() for doubles (server rotation)
- [x] Implement receiver_wins() for doubles (side-out logic)
- [x] Implement is_game_over() for standard games (win by 2)
- [x] Implement is_game_over() for timed games
- [x] Implement get_score_string() formatting
- [x] Implement get_server_info()
- [x] Implement set_score() for manual editing
- [x] Implement force_side_out()
- [x] Implement save_snapshot() / restore_snapshot() for undo
- [x] Implement to_dict() / from_dict() serialization
- [x] Write unit tests for ScoreState
- [x] **GIT CHECKPOINT**: Commit "Implement score state machine with tests" (d4f591c)

### 2.3 Rally Manager
- [x] Create src/core/rally_manager.py
- [x] Implement RallyManager.__init__()
- [x] Implement start_rally() with padding
- [x] Implement end_rally() with padding
- [x] Implement is_rally_in_progress()
- [x] Implement get_rally_count()
- [x] Implement get_rallies()
- [x] Implement update_rally_timing()
- [x] Implement update_rally_score()
- [x] Implement undo() with action stack
- [x] Implement can_undo()
- [x] Implement to_segments() for Kdenlive export
- [x] Implement to_dict() / from_dict() serialization
- [x] Write unit tests for RallyManager
- [x] **GIT CHECKPOINT**: Commit "Implement rally manager with tests" (ce78229)

---

## Phase 3: Video Integration
> MPV embedding and video probe utilities

### 3.1 Video Probe
- [x] Create src/video/probe.py
- [x] Implement probe_video() using ffprobe
- [x] Extract fps, duration, resolution
- [x] Extract codec info
- [x] Handle probe errors gracefully
- [x] Write unit tests for video probe
- [x] **GIT CHECKPOINT**: Commit "Add video probe utility"

### 3.2 MPV Player Widget
- [x] Create src/video/player.py
- [x] Create VideoWidget class extending QWidget
- [x] Configure MPV embedding with wid parameter
- [x] Implement load() method
- [x] Implement play() / pause() / toggle_pause()
- [x] Implement seek() by seconds
- [x] Implement seek_frame() by frame number
- [x] Implement frame_step() / frame_back_step()
- [x] Implement set_speed()
- [x] Implement get_position() / get_position_frame()
- [x] Implement get_duration()
- [x] Implement show_osd() for messages
- [x] Create position_changed signal
- [x] Create duration_changed signal
- [x] Test MPV embedding in standalone PyQt6 window
- [x] Verify arrow key navigation works (5-second skip)
- [x] **GIT CHECKPOINT**: Commit "Implement MPV player widget with embedding"

---

## Phase 4: UI Foundation
> Basic window structure, styling, common widgets

### 4.1 Application Shell
- [x] Create src/app.py with QApplication setup
- [x] Create src/ui/__init__.py
- [ ] Create application icon (optional)
- [x] **GIT CHECKPOINT**: Commit "Set up application shell"

### 4.2 Design System & Stylesheet
> Implement "Court Green" theme per UI_SPEC.md Section 2

- [x] Create src/ui/styles/__init__.py
- [x] Create src/ui/styles/colors.py with color constants from UI_SPEC.md Section 2.2
- [x] Create src/ui/styles/fonts.py with typography constants from UI_SPEC.md Section 2.3
- [x] Create src/ui/styles/theme.qss master stylesheet
- [x] Implement background color classes (--bg-primary, --bg-secondary, --bg-tertiary)
- [x] Implement action color classes (rally-start, server-wins, receiver-wins, undo)
- [x] Implement button state styles (active with glow, normal, disabled with opacity)
- [x] Implement text color classes (primary, secondary, accent, warning, disabled)
- [x] Implement spacing utilities per UI_SPEC.md Section 2.4
- [x] Implement border radius styles per UI_SPEC.md Section 2.5
- [x] Implement dialog styling per UI_SPEC.md Section 6.1
- [x] Implement toast notification styling per UI_SPEC.md Section 6.8
- [x] Test stylesheet loads correctly in QApplication
- [x] Verify font rendering (JetBrains Mono / IBM Plex Sans fallbacks)
- [x] **GIT CHECKPOINT**: Commit "Implement Court Green design system and stylesheet"

### 4.3 Custom Widgets
- [x] Create src/ui/widgets/__init__.py
- [ ] Create src/ui/widgets/video_widget.py (wraps VideoWidget) - Using existing player.py
- [x] Create src/ui/widgets/rally_button.py
- [x] Implement RallyButton with color states (active, normal, disabled) per UI_SPEC.md Section 2.2.4
- [x] Implement pulse animation for active state per UI_SPEC.md Section 7.1.1
- [x] Implement set_active() / set_disabled() methods
- [x] Create src/ui/widgets/status_overlay.py
- [x] Implement StatusOverlay with status dot, score, server info per UI_SPEC.md Section 4.2.2
- [x] Create src/ui/widgets/playback_controls.py
- [x] Implement playback buttons (frame step, play/pause, speed toggle group)
- [x] Implement time display label with monospace font
- [x] Create src/ui/widgets/toast.py
- [x] Implement Toast notification widget per UI_SPEC.md Section 6.8
- [x] Implement auto-dismiss timer (4 seconds)
- [x] **GIT CHECKPOINT**: Commit "Create custom UI widgets"

### 4.4 Setup Dialog
- [x] Create src/ui/setup_dialog.py
- [x] Implement file browser for video selection
- [x] Implement game type dropdown (Singles/Doubles)
- [x] Implement victory rules dropdown (11/9/Timed)
- [x] Implement player name fields (dynamic for singles/doubles)
- [x] Implement Team 1 accent border container (first server indicator) per UI_SPEC.md Section 3.1
- [x] Implement required field indicators (*) per UI_SPEC.md Section 3.1
- [x] Implement inline validation with error messages per UI_SPEC.md Section 3.3
- [x] Implement get_config() to return setup data
- [x] Style dialog per UI_SPEC.md Section 3
- [x] **GIT CHECKPOINT**: Commit "Implement setup dialog"

---

## Phase 5: Main Window - Editing Mode
> Primary editing interface with rally marking

### 5.1 Main Window Structure
- [x] Create src/ui/main_window.py
- [x] Set up QMainWindow with central widget
- [x] Create layout: video, playback, state bar, rally controls, interventions, session
- [x] Integrate VideoWidget
- [x] Integrate PlaybackControls
- [x] Integrate StatusOverlay (StateBar equivalent)
- [x] Add rally control buttons (Rally Start, Server Wins, Receiver Wins, Undo)
- [x] Add intervention buttons (Edit Score, Force Side-Out, Add Comment, Time Expired)
- [x] Add session buttons (Save Session, Final Review, Save & Quit)
- [x] Implement window title with filename
- [x] **GIT CHECKPOINT**: Commit "Create main window structure and layout"

### 5.2 Rally Marking Logic
- [x] Connect Rally Start button to on_rally_start()
- [x] Implement on_rally_start() - capture timestamp, update state
- [x] Connect Server Wins button to on_server_wins()
- [x] Implement on_server_wins() - end rally, update score
- [x] Connect Receiver Wins button to on_receiver_wins()
- [x] Implement on_receiver_wins() - end rally, update score
- [x] Connect Undo button to on_undo()
- [x] Implement on_undo() - revert action, seek video
- [x] Implement button state management (highlight/dim based on rally state)
- [x] Implement OSD feedback for rally events
- [x] Implement state bar updates after each action

### 5.3 Playback Integration
- [x] Connect playback controls to VideoWidget
- [x] Implement play/pause toggle
- [x] Implement frame step forward/backward
- [x] Implement speed selection (0.5x, 1x, 2x)
- [x] Implement time display updates
- [x] Verify MPV arrow keys still work for 5-second skip
- [x] **GIT CHECKPOINT**: Commit "Implement rally marking and playback controls"

---

## Phase 6: Modal Dialogs
> Intervention and system dialogs

### 6.1 Intervention Dialogs
- [x] Create src/ui/dialogs/__init__.py
- [x] Create src/ui/dialogs/edit_score.py
- [x] Implement Edit Score dialog per UI_PROTOTYPES.md Section 4.1
- [x] Implement score format validation
- [x] Create src/ui/dialogs/force_sideout.py
- [x] Implement Force Side-Out dialog with optional score field
- [x] Create src/ui/dialogs/add_comment.py
- [x] Implement Add Comment dialog with duration field

### 6.2 System Dialogs
- [x] Create src/ui/dialogs/game_over.py
- [x] Implement Game Over dialog (standard and timed variants)
- [x] Implement Continue Editing vs Finish Game options
- [x] Create src/ui/dialogs/resume_session.py
- [x] Implement Resume Session dialog with session details
- [x] Implement Start Fresh vs Resume options
- [x] Create src/ui/dialogs/unsaved_warning.py
- [x] Implement Unsaved Changes warning dialog
- [x] **GIT CHECKPOINT**: Commit "Create all modal dialog UIs" (00bd07a)

### 6.3 Dialog Integration
- [x] Connect Edit Score button to dialog
- [x] Apply score changes from dialog
- [x] Connect Force Side-Out button to dialog
- [x] Apply side-out changes from dialog
- [x] Connect Add Comment button to dialog
- [ ] Store comments with timestamp (pending session persistence)
- [x] Connect Time Expired button (timed games only)
- [x] Trigger Game Over on winning condition
- [ ] Show Unsaved Warning on close if dirty (pending session persistence)
- [x] **GIT CHECKPOINT**: Commit "Integrate modal dialogs with main window" (e884f29)

---

## Phase 7: Session Management
> Save, load, and resume functionality

### 7.1 Session Manager
- [x] Create src/core/session_manager.py
- [x] Implement SessionManager.__init__() with session directory
- [x] Implement _get_video_hash() for session identification
- [x] Implement save() - serialize state to JSON
- [x] Implement load() - deserialize state from JSON
- [x] Implement find_existing() - check for existing session
- [x] Implement delete() - remove session file
- [x] Create session directory if not exists (~/.local/share/pickleball-editor/sessions/)
- [x] **GIT CHECKPOINT**: Commit "Implement session manager" (34ea808)

**Note:** Phase 7.2 was committed with hash 9e4d6bf

### 7.2 Session Integration
- [x] Add session_state field to GameConfig
- [x] Check for existing session on video selection in Setup
- [x] Show Resume Session dialog if session exists
- [x] Implement _handle_existing_session() and _populate_from_session()
- [x] Implement session restore in MainWindow._init_core_components()
- [x] Restore score state from session using ScoreSnapshot
- [x] Restore rally list from session using RallyManager.from_dict()
- [x] Seek video to last position after loading
- [x] Implement _build_session_state() helper
- [x] Connect Save Session button with full implementation
- [x] Add dirty state tracking (mark dirty on all changes)
- [x] Implement unsaved warning on close (UnsavedWarningDialog)
- [x] Handle Save & Quit / Don't Save / Cancel in closeEvent()
- [x] Update SessionManager.get_session_info() to include victory_rules
- [x] Write test_session_integration.py with automated tests
- [x] **GIT CHECKPOINT**: Commit "Integrate session save/load with application"

---

## Phase 8: Final Review Mode
> Rally verification and adjustment interface

### 8.1 Review Mode UI
- [x] Create src/ui/review_mode.py
- [x] Implement ReviewMode widget/panel
- [x] Display "Rally X of Y" header
- [x] Implement timing adjustment controls (+/- 0.1s buttons)
- [x] Implement score adjustment text field
- [x] Implement cascade checkbox
- [x] Implement rally list grid (clickable)
- [x] Highlight current rally in list
- [x] Implement Previous/Next navigation buttons
- [x] Implement Play Rally button
- [x] Implement Exit Review button
- [x] Implement Generate Kdenlive button

### 8.2 Review Mode Logic
- [x] Implement navigate_to_rally() - seek video, update display
- [x] Implement click-to-navigate on rally list
- [x] Implement adjust_start_timing()
- [x] Implement adjust_end_timing()
- [x] Implement edit_score() with cascade logic
- [x] Implement Play Rally - play from start to end
- [x] Implement score cascade recalculation
- [x] **GIT CHECKPOINT**: Commit "Implement final review mode UI and logic"

### 8.3 Mode Switching
- [x] Implement enter_review_mode() - swap UI panels
- [x] Implement exit_review_mode() - restore editing UI
- [x] Connect Final Review button to enter_review_mode()
- [x] Connect Exit Review button to exit_review_mode()
- [x] Integrate ReviewModeWidget with MainWindow
- [x] Add video fps support to ReviewModeWidget
- [x] Implement _on_review_rally_changed() handler
- [x] Implement _on_review_timing_adjusted() handler
- [x] Implement _on_review_score_changed() handler with cascade
- [x] Implement _on_review_play_rally() handler with QTimer
- [x] Add _on_review_generate() placeholder
- [x] Create test_review_integration.py test script
- [x] Create REVIEW_MODE_INTEGRATION.md documentation
- [x] Create REVIEW_MODE_USAGE.md user guide
- [x] **GIT CHECKPOINT**: Commit "Integrate review mode with main window"

---

## Phase 9: Output Generation
> Kdenlive project and subtitle file creation

### 9.1 Subtitle Generator
- [x] Create src/output/__init__.py
- [x] Create src/output/subtitle_generator.py
- [x] Implement frames_to_srt_time()
- [x] Implement generate_srt() from segments
- [x] Handle output timeline (cumulative timing)

### 9.2 Kdenlive Generator
- [x] Create src/output/kdenlive_generator.py
- [x] Port/adapt existing generate_project.py code
- [x] Implement frames_to_timecode()
- [x] Implement generate_kdenlive_xml()
- [x] Include subtitle filter in XML
- [x] Implement generate() main function
- [x] Write files to ~/Videos/pickleball/
- [x] **GIT CHECKPOINT**: Commit "Implement Kdenlive and subtitle generators"

### 9.3 Debug Exporter
- [ ] Create src/output/debug_export.py
- [ ] Implement export() - full session data to JSON
- [ ] Include rallies, interventions, comments
- [ ] Write to ~/Videos/debug/

### 9.4 Output Integration
- [x] Connect Generate Kdenlive button to generator
- [x] Convert rally list to segments format
- [x] Call generator with video path, segments, profile
- [x] Show success message with file paths
- [ ] Auto-export debug JSON after generation (deferred)
- [x] **GIT CHECKPOINT**: Commit "Integrate output generation with application"

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
| 1 | Project Setup & Infrastructure | 1 | Complete |
| 2 | Core Domain Classes | 3 | Complete |
| 3 | Video Integration | 2 | Complete |
| 4 | UI Foundation | 4 | Complete |
| 5 | Main Window - Editing Mode | 2 | Complete |
| 6 | Modal Dialogs | 2 | Complete |
| 7 | Session Management | 2 | Complete |
| 8 | Final Review Mode | 2 | Complete |
| 9 | Output Generation | 2 | Complete |
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
*Completed: ~200 (Phase 0-9)*
