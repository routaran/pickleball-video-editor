"""Tests for SetupDialog session resume functionality.

Tests that when a user clicks a recent session and chooses to resume:
1. Session data populates form fields correctly (game type, victory rules, player names)
2. The _on_start_editing() method is called automatically
3. The dialog is accepted and returns proper GameConfig
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PyQt6.QtWidgets import QApplication

from src.core.models import SessionState
from src.ui.setup_dialog import SetupDialog, GameConfig
from src.ui.dialogs import ResumeSessionResult
from src.ui.widgets.saved_session_card import SavedSessionInfo


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def doubles_session_state():
    """Create a doubles session state for testing."""
    return SessionState(
        version="1.0",
        video_path="/path/to/video.mp4",
        video_hash="abc123",
        game_type="doubles",
        victory_rules="11",
        player_names={"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]},
        rallies=[],
        current_score=[5, 3],
        serving_team=0,
        server_number=1,
        last_position=120.5,
    )


@pytest.fixture
def singles_session_state():
    """Create a singles session state for testing."""
    return SessionState(
        version="1.0",
        video_path="/path/to/video.mp4",
        video_hash="def456",
        game_type="singles",
        victory_rules="9",
        player_names={"team1": ["Eve"], "team2": ["Frank"]},
        rallies=[],
        current_score=[7, 6],
        serving_team=1,
        server_number=None,
        last_position=300.0,
    )


@pytest.fixture
def highlights_session_state():
    """Create a highlights session state for testing."""
    return SessionState(
        version="1.0",
        video_path="/path/to/video.mp4",
        video_hash="ghi789",
        game_type="highlights",
        victory_rules="",
        player_names={"team1": [], "team2": []},
        rallies=[],
        current_score=[],
        serving_team=0,
        server_number=None,
        last_position=60.0,
    )


@pytest.fixture
def saved_session_info():
    """Create a SavedSessionInfo for testing."""
    return SavedSessionInfo(
        session_path=Path("/path/to/session.json"),
        session_hash="abc123",
        video_name="test_video.mp4",
        video_path="/path/to/video.mp4",
        rally_count=10,
        current_score="5-3",
        game_type="doubles",
        last_modified="2024-01-15T10:30:00",
        video_exists=True,
    )


class TestPopulateFromSession:
    """Test form field population from session state."""

    def test_populate_doubles_game_type(self, qapp, doubles_session_state):
        """Doubles game type sets combo to index 0."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(doubles_session_state)

            assert dialog.game_type_combo.currentIndex() == 0
            assert dialog.game_type_combo.currentText() == "Doubles"

    def test_populate_singles_game_type(self, qapp, singles_session_state):
        """Singles game type sets combo to index 1."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(singles_session_state)

            assert dialog.game_type_combo.currentIndex() == 1
            assert dialog.game_type_combo.currentText() == "Singles"

    def test_populate_victory_rules_11(self, qapp, doubles_session_state):
        """Victory rules '11' sets combo to index 0."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(doubles_session_state)

            assert dialog.victory_combo.currentIndex() == 0

    def test_populate_victory_rules_9(self, qapp, singles_session_state):
        """Victory rules '9' sets combo to index 1."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(singles_session_state)

            assert dialog.victory_combo.currentIndex() == 1

    def test_populate_doubles_player_names(self, qapp, doubles_session_state):
        """All four player names populated for doubles."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(doubles_session_state)

            assert dialog.team1_player1_edit.text() == "Alice"
            assert dialog.team1_player2_edit.text() == "Bob"
            assert dialog.team2_player1_edit.text() == "Carol"
            assert dialog.team2_player2_edit.text() == "Dave"

    def test_populate_singles_player_names(self, qapp, singles_session_state):
        """Only first players populated for singles."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(singles_session_state)

            assert dialog.team1_player1_edit.text() == "Eve"
            assert dialog.team2_player1_edit.text() == "Frank"

    def test_populate_highlights_game_type(self, qapp, highlights_session_state):
        """Highlights game type sets combo to index 2."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()
            dialog._populate_from_session(highlights_session_state)

            assert dialog.game_type_combo.currentIndex() == 2
            assert dialog.game_type_combo.currentText() == "Highlights"


class TestValidationBypassOnResume:
    """Test that validation is bypassed when resuming a session.

    This is critical because sessions may have empty player names (highlights)
    or the video path may not exist yet when resuming.
    """

    def test_resume_highlights_session_accepts_without_player_names(
        self, qapp, highlights_session_state
    ):
        """Highlights session with empty player names still accepts dialog."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Set session state (simulates resume)
            dialog._session_state = highlights_session_state
            dialog.video_path_edit.setText("/path/to/video.mp4")
            dialog._populate_from_session(highlights_session_state)

            # Player fields are empty - validation would normally fail
            assert dialog.team1_player1_edit.text() == ""
            assert dialog.team2_player1_edit.text() == ""

            # But with session_state set, _on_start_editing should succeed
            with patch.object(dialog, 'accept') as mock_accept:
                dialog._on_start_editing()
                # Dialog should be accepted despite empty player names
                mock_accept.assert_called_once()

            # Config should be created
            config = dialog.get_config()
            assert config is not None
            assert config.game_type == "highlights"
            assert config.session_state is highlights_session_state

    def test_resume_session_skips_validation(self, qapp, doubles_session_state):
        """Session resume skips validation entirely."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Set session state but DON'T populate form - fields are invalid
            dialog._session_state = doubles_session_state
            dialog.video_path_edit.setText("")  # Empty path - would fail validation

            # _validate would return False here
            assert dialog._validate() is False

            # But _on_start_editing should still accept when session_state is set
            with patch.object(dialog, 'accept') as mock_accept:
                dialog._on_start_editing()
                mock_accept.assert_called_once()

    def test_new_session_still_validates(self, qapp):
        """New session (no session_state) still requires validation."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # No session state - this is a new session
            dialog._session_state = None
            dialog.video_path_edit.setText("")  # Invalid - empty path

            # _on_start_editing should NOT accept due to validation failure
            with patch.object(dialog, 'accept') as mock_accept:
                dialog._on_start_editing()
                mock_accept.assert_not_called()

            # No config created
            assert dialog.get_config() is None


class TestSessionResumeAutoStart:
    """Test that resuming a session automatically starts editing."""

    def test_handle_existing_session_from_card_calls_start_editing(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Resuming from card click calls _on_start_editing."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Set valid video path so validation passes
            dialog.video_path_edit.setText("/path/to/video.mp4")

            # Mock dependencies
            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                # Mock the resume dialog to return RESUME
                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.RESUME
                    mock_dialog_class.return_value = mock_dialog

                    # Mock _on_start_editing to track if it's called
                    with patch.object(dialog, '_on_start_editing') as mock_start:
                        # Mock file existence check
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                        # Verify _on_start_editing was called
                        mock_start.assert_called_once()

    def test_handle_existing_session_from_card_populates_form(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Resuming from card click populates form fields."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Set valid video path
            dialog.video_path_edit.setText("/path/to/video.mp4")

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.RESUME
                    mock_dialog_class.return_value = mock_dialog

                    # Don't mock _on_start_editing but mock accept to prevent closing
                    with patch.object(dialog, 'accept'):
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                    # Verify form was populated
                    assert dialog.game_type_combo.currentIndex() == 0  # Doubles
                    assert dialog.team1_player1_edit.text() == "Alice"
                    assert dialog.team1_player2_edit.text() == "Bob"

    def test_handle_existing_session_calls_start_editing(
        self, qapp, doubles_session_state
    ):
        """Browsing video with existing session calls _on_start_editing on resume."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Set valid video path
            video_path = Path("/path/to/video.mp4")
            dialog.video_path_edit.setText(str(video_path))

            # Create complete session_info dict
            session_info = {
                "rally_count": 5,
                "current_score": "5-3-1",
                "last_position": 120.5,
                "game_type": "doubles",
                "victory_rules": "11"
            }

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.RESUME
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, '_on_start_editing') as mock_start:
                        dialog._handle_existing_session(str(video_path), session_info)

                        mock_start.assert_called_once()


class TestDialogAcceptance:
    """Test dialog acceptance and GameConfig creation."""

    def test_start_editing_creates_game_config_with_session_state(
        self, qapp, doubles_session_state
    ):
        """_on_start_editing creates GameConfig with session_state."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Populate form with valid data
            dialog.video_path_edit.setText("/path/to/video.mp4")
            dialog._session_state = doubles_session_state
            dialog._populate_from_session(doubles_session_state)

            # Mock file existence for validation
            with patch('pathlib.Path.exists', return_value=True):
                # Mock accept to prevent dialog from closing
                with patch.object(dialog, 'accept'):
                    dialog._on_start_editing()

            # Verify GameConfig was created with session state
            config = dialog.get_config()
            assert config is not None
            assert config.session_state is doubles_session_state
            assert config.game_type == "doubles"
            assert config.victory_rule == "11"
            assert config.team1_players == ["Alice", "Bob"]
            assert config.team2_players == ["Carol", "Dave"]

    def test_start_editing_accepts_dialog(self, qapp, doubles_session_state):
        """_on_start_editing calls accept() to close dialog."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            # Populate form
            dialog.video_path_edit.setText("/path/to/video.mp4")
            dialog._session_state = doubles_session_state
            dialog._populate_from_session(doubles_session_state)

            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(dialog, 'accept') as mock_accept:
                    dialog._on_start_editing()

                    mock_accept.assert_called_once()

    def test_singles_session_creates_correct_config(self, qapp, singles_session_state):
        """Singles session creates GameConfig with single players per team."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/video.mp4")
            dialog._session_state = singles_session_state
            dialog._populate_from_session(singles_session_state)

            with patch('pathlib.Path.exists', return_value=True):
                with patch.object(dialog, 'accept'):
                    dialog._on_start_editing()

            config = dialog.get_config()
            assert config is not None
            assert config.game_type == "singles"
            assert config.victory_rule == "9"
            assert config.team1_players == ["Eve"]
            assert config.team2_players == ["Frank"]


class TestStartFreshBehavior:
    """Test that Start Fresh does NOT auto-start editing."""

    def test_start_fresh_does_not_call_start_editing(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Choosing Start Fresh does not call _on_start_editing."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/video.mp4")

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    # Return START_FRESH instead of RESUME
                    mock_dialog.get_result.return_value = ResumeSessionResult.START_FRESH
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, '_on_start_editing') as mock_start:
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                        # Verify _on_start_editing was NOT called
                        mock_start.assert_not_called()

    def test_start_fresh_deletes_session(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Choosing Start Fresh deletes the session file."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/video.mp4")

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.START_FRESH
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, '_reload_sessions'):
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                    # Verify session was deleted
                    mock_manager.delete_session_file.assert_called_once_with(
                        saved_session_info.session_path
                    )

    def test_start_fresh_clears_session_state(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Choosing Start Fresh clears the _session_state attribute."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/video.mp4")

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.START_FRESH
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, '_reload_sessions'):
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                    # Verify session state was cleared
                    assert dialog._session_state is None

    def test_start_fresh_populates_video_path(
        self, qapp, doubles_session_state, saved_session_info
    ):
        """Choosing Start Fresh still populates the video path field."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load_from_session_file.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.START_FRESH
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, '_reload_sessions'):
                        with patch('pathlib.Path.exists', return_value=True):
                            dialog._handle_existing_session_from_card(saved_session_info)

                    # Verify video path was set
                    assert dialog.video_path_edit.text() == doubles_session_state.video_path


class TestSessionResumeEdgeCases:
    """Test edge cases and error handling."""

    def test_session_load_failure_shows_warning(
        self, qapp, saved_session_info
    ):
        """Shows warning when session file is corrupted."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            with patch.object(dialog, '_session_manager') as mock_manager:
                # Return None to simulate corrupted session
                mock_manager.load_from_session_file.return_value = None

                with patch('src.ui.setup_dialog.QMessageBox.warning') as mock_warning:
                    dialog._handle_existing_session_from_card(saved_session_info)

                    # Verify warning was shown
                    mock_warning.assert_called_once()
                    args = mock_warning.call_args[0]
                    assert "Session Load Error" in args[1]

    def test_resume_from_browse_loads_full_session(
        self, qapp, doubles_session_state
    ):
        """Browsing for video with existing session loads full state."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            video_path = "/path/to/video.mp4"
            session_info = {
                "rally_count": 10,
                "current_score": "5-3-1",
                "last_position": 120.5,
                "game_type": "doubles",
                "victory_rules": "11"
            }

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.RESUME
                    mock_dialog_class.return_value = mock_dialog

                    with patch.object(dialog, 'accept'):
                        dialog._handle_existing_session(video_path, session_info)

                    # Verify session was loaded
                    assert dialog._session_state is doubles_session_state

    def test_resume_from_browse_deletes_on_start_fresh(
        self, qapp, doubles_session_state
    ):
        """Browsing for video and choosing Start Fresh deletes session."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            video_path = "/path/to/video.mp4"
            session_info = {
                "rally_count": 10,
                "current_score": "5-3-1",
                "last_position": 120.5,
                "game_type": "doubles",
                "victory_rules": "11"
            }

            with patch.object(dialog, '_session_manager') as mock_manager:
                mock_manager.load.return_value = doubles_session_state

                with patch('src.ui.setup_dialog.ResumeSessionDialog') as mock_dialog_class:
                    mock_dialog = MagicMock()
                    mock_dialog.exec.return_value = None
                    mock_dialog.get_result.return_value = ResumeSessionResult.START_FRESH
                    mock_dialog_class.return_value = mock_dialog

                    dialog._handle_existing_session(video_path, session_info)

                    # Verify session was deleted
                    mock_manager.delete.assert_called_once_with(video_path)


class TestValidationWithResumedSession:
    """Test that validation works correctly with resumed sessions."""

    def test_resumed_session_validates_correctly(
        self, qapp, doubles_session_state
    ):
        """Resumed session with valid data passes validation."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/video.mp4")
            dialog._session_state = doubles_session_state
            dialog._populate_from_session(doubles_session_state)

            # Mock file existence
            with patch('pathlib.Path.exists', return_value=True):
                is_valid = dialog._validate()

            # Should be valid
            assert is_valid
            assert dialog.start_button.isEnabled()

    def test_resumed_session_with_missing_video_fails_validation(
        self, qapp, doubles_session_state
    ):
        """Resumed session with missing video fails validation."""
        with patch.object(SetupDialog, '_load_saved_sessions'):
            dialog = SetupDialog()

            dialog.video_path_edit.setText("/path/to/missing_video.mp4")
            dialog._session_state = doubles_session_state
            dialog._populate_from_session(doubles_session_state)

            # Mock file not existing
            with patch('pathlib.Path.exists', return_value=False):
                is_valid = dialog._validate()

            # Should be invalid
            assert not is_valid
            assert not dialog.start_button.isEnabled()
