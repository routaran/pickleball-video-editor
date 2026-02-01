"""Tests for ClipTimelineWidget."""

import pytest
from unittest.mock import MagicMock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from src.core.models import Rally
from src.ui.widgets.clip_timeline import (
    ClipTimelineWidget,
    _ClipCell,
    _format_time,
    _calculate_cell_width,
    CELL_WIDTH,
)


# Ensure QApplication exists for widget tests
@pytest.fixture(scope="module")
def qapp():
    """Create QApplication if not already exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def timeline(qapp):
    """Create a ClipTimelineWidget for testing."""
    widget = ClipTimelineWidget()
    yield widget
    widget.deleteLater()


@pytest.fixture
def sample_rallies():
    """Create sample Rally objects for testing (highlights mode - no scores used)."""
    return [
        Rally(start_frame=0, end_frame=120, score_at_start="", winner=""),
        Rally(start_frame=180, end_frame=300, score_at_start="", winner=""),
        Rally(start_frame=360, end_frame=480, score_at_start="", winner=""),
    ]


@pytest.fixture
def singles_rallies():
    """Create sample Rally objects with singles scores."""
    return [
        Rally(start_frame=0, end_frame=120, score_at_start="0-0", winner="server"),
        Rally(start_frame=180, end_frame=300, score_at_start="1-0", winner="receiver"),
        Rally(start_frame=360, end_frame=480, score_at_start="1-1", winner="server"),
    ]


@pytest.fixture
def doubles_rallies():
    """Create sample Rally objects with doubles scores."""
    return [
        Rally(start_frame=0, end_frame=120, score_at_start="0-0-2", winner="server"),
        Rally(start_frame=180, end_frame=300, score_at_start="1-0-2", winner="receiver"),
        Rally(start_frame=360, end_frame=480, score_at_start="1-0-1", winner="server"),
    ]


class TestFormatTime:
    """Tests for the _format_time helper function."""

    def test_format_zero(self):
        """Test formatting zero seconds."""
        assert _format_time(0) == "0:00"

    def test_format_seconds_only(self):
        """Test formatting less than a minute."""
        assert _format_time(45) == "0:45"

    def test_format_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert _format_time(125) == "2:05"

    def test_format_exact_minute(self):
        """Test formatting exact minutes."""
        assert _format_time(60) == "1:00"

    def test_format_large_time(self):
        """Test formatting large time values."""
        assert _format_time(3661) == "61:01"


class TestClipTimelineWidget:
    """Tests for ClipTimelineWidget."""

    def test_set_clips_creates_correct_buttons(self, timeline, sample_rallies):
        """Test that set_clips creates the correct number of cells."""
        timeline.set_clips(sample_rallies, fps=60.0)
        assert timeline.get_clip_count() == 3

    def test_empty_state_shows_placeholder(self, timeline):
        """Test that empty state shows placeholder text."""
        timeline.set_clips([], fps=60.0)
        # Check visibility state relative to parent (not absolute visibility)
        assert not timeline._placeholder.isHidden()
        assert timeline._scroll_area.isHidden()

    def test_with_clips_hides_placeholder(self, timeline, sample_rallies):
        """Test that placeholder is hidden when clips exist."""
        timeline.set_clips(sample_rallies, fps=60.0)
        # Check visibility state relative to parent (not absolute visibility)
        assert timeline._placeholder.isHidden()
        assert not timeline._scroll_area.isHidden()

    def test_find_active_clip_returns_correct_index(self, timeline, sample_rallies):
        """Test finding active clip by position."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Position in first clip (0-2 seconds)
        assert timeline._find_active_clip(1.0) == 0

        # Position in second clip (3-5 seconds)
        assert timeline._find_active_clip(4.0) == 1

        # Position in third clip (6-8 seconds)
        assert timeline._find_active_clip(7.0) == 2

    def test_find_active_clip_returns_none_between_clips(self, timeline, sample_rallies):
        """Test that None is returned when position is between clips."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Position between first and second clip (2.5 seconds)
        assert timeline._find_active_clip(2.5) is None

        # Position before first clip
        assert timeline._find_active_clip(-1.0) is None

        # Position after all clips (10 seconds)
        assert timeline._find_active_clip(10.0) is None

    def test_click_emits_signal_with_index(self, timeline, sample_rallies, qtbot):
        """Test that clicking a cell emits clip_clicked signal."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Connect signal to mock
        with qtbot.waitSignal(timeline.clip_clicked, timeout=1000) as blocker:
            # Simulate the click timeout (single click detection)
            timeline._pending_click_index = 1
            timeline._on_click_timeout()

        assert blocker.args == [1]

    def test_update_position_highlights_active_cell(self, timeline, sample_rallies):
        """Test that update_position highlights the correct cell."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Initially no cell is active
        assert timeline._active_index is None

        # Update position to be inside first clip
        timeline.update_position(1.0)
        assert timeline._active_index == 0
        assert timeline._cells[0].is_active()

        # Update position to be inside second clip
        timeline.update_position(4.0)
        assert timeline._active_index == 1
        assert not timeline._cells[0].is_active()
        assert timeline._cells[1].is_active()

    def test_update_position_clears_highlight_between_clips(self, timeline, sample_rallies):
        """Test that highlight is cleared when between clips."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # First, activate a cell
        timeline.update_position(1.0)
        assert timeline._active_index == 0

        # Move to between clips
        timeline.update_position(2.5)
        assert timeline._active_index is None
        assert not timeline._cells[0].is_active()

    def test_set_in_progress_shows_indicator(self, timeline, sample_rallies):
        """Test that in-progress indicator is shown."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Initially no in-progress indicator
        assert timeline._in_progress_cell is None

        # Enable in-progress
        timeline.set_in_progress(True, label="4")
        assert timeline._in_progress_cell is not None

    def test_set_in_progress_hides_indicator(self, timeline, sample_rallies):
        """Test that in-progress indicator is hidden."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # Enable then disable
        timeline.set_in_progress(True, label="4")
        timeline.set_in_progress(False)
        assert timeline._in_progress_cell is None

    def test_cells_have_correct_tooltips(self, timeline, sample_rallies):
        """Test that cells have correct time range tooltips."""
        timeline.set_clips(sample_rallies, fps=60.0)

        # First clip: 0-2 seconds
        assert "0:00 - 0:02" in timeline._cells[0].toolTip()

        # Second clip: 3-5 seconds
        assert "0:03 - 0:05" in timeline._cells[1].toolTip()

    def test_multiple_set_clips_stays_left_justified(self, timeline, sample_rallies):
        """Test that calling set_clips multiple times doesn't shift cells right.

        This was a bug where each set_clips call added a stretch, pushing cells right.
        """
        # Call set_clips multiple times (simulating adding clips one by one)
        for i in range(5):
            timeline.set_clips(sample_rallies[:i+1] if i < len(sample_rallies) else sample_rallies, fps=60.0)

        # Count stretch items in layout - should only be 1
        stretch_count = 0
        for i in range(timeline._cell_layout.count()):
            item = timeline._cell_layout.itemAt(i)
            if item is not None and item.widget() is None:
                # This is a spacer/stretch item
                stretch_count += 1

        assert stretch_count == 1, f"Expected 1 stretch, found {stretch_count}"

    def test_set_clips_with_in_progress_maintains_layout(self, timeline, sample_rallies):
        """Test that set_clips with in_progress doesn't duplicate stretches."""
        timeline._in_progress = True
        timeline.set_clips(sample_rallies, fps=60.0)

        # Count stretch items - should still only be 1
        stretch_count = 0
        for i in range(timeline._cell_layout.count()):
            item = timeline._cell_layout.itemAt(i)
            if item is not None and item.widget() is None:
                stretch_count += 1

        assert stretch_count == 1, f"Expected 1 stretch, found {stretch_count}"

        # Verify in-progress cell is present
        assert timeline._in_progress_cell is not None


class TestClipCell:
    """Tests for _ClipCell."""

    def test_cell_displays_correct_label(self, qapp):
        """Test that cell displays the provided label."""
        cell = _ClipCell(0, 0.0, 2.0, "1")
        assert cell.text() == "1"

        cell2 = _ClipCell(4, 10.0, 12.0, "5")
        assert cell2.text() == "5"

        # Score labels
        cell3 = _ClipCell(0, 0.0, 2.0, "5-3")
        assert cell3.text() == "5-3"

    def test_cell_has_tooltip(self, qapp):
        """Test that cell has time range tooltip."""
        cell = _ClipCell(0, 45.0, 48.0, "1")
        assert "0:45 - 0:48" in cell.toolTip()

    def test_cell_active_state(self, qapp):
        """Test cell active state toggling."""
        cell = _ClipCell(0, 0.0, 2.0, "1")

        assert not cell.is_active()

        cell.set_active(True)
        assert cell.is_active()

        cell.set_active(False)
        assert not cell.is_active()


class TestCellWidthCalculation:
    """Tests for dynamic cell width calculation."""

    def test_short_labels_use_default_width(self):
        """Test 1-2 char labels use CELL_WIDTH."""
        assert _calculate_cell_width("1") == CELL_WIDTH
        assert _calculate_cell_width("12") == CELL_WIDTH

    def test_medium_labels_use_36px(self):
        """Test 3-4 char labels use 36px."""
        assert _calculate_cell_width("0-0") == 36
        assert _calculate_cell_width("11-9") == 36

    def test_long_labels_use_48px(self):
        """Test 5-6 char labels use 48px."""
        assert _calculate_cell_width("0-0-2") == 48
        assert _calculate_cell_width("11-9-2") == 48

    def test_very_long_labels_use_56px(self):
        """Test 7+ char labels use 56px."""
        assert _calculate_cell_width("11-11-2") == 56


class TestClipTimelineWithScores:
    """Tests for ClipTimelineWidget with score display."""

    def test_highlights_mode_shows_sequential_numbers(self, timeline, sample_rallies):
        """Test that highlights mode displays 1, 2, 3..."""
        timeline.set_clips(sample_rallies, fps=60.0, game_type="highlights")
        assert timeline._cells[0].text() == "1"
        assert timeline._cells[1].text() == "2"
        assert timeline._cells[2].text() == "3"

    def test_singles_mode_shows_scores(self, timeline, singles_rallies):
        """Test that singles mode displays score strings."""
        timeline.set_clips(singles_rallies, fps=60.0, game_type="singles")
        assert timeline._cells[0].text() == "0-0"
        assert timeline._cells[1].text() == "1-0"
        assert timeline._cells[2].text() == "1-1"

    def test_doubles_mode_shows_scores(self, timeline, doubles_rallies):
        """Test that doubles mode displays score strings with server number."""
        timeline.set_clips(doubles_rallies, fps=60.0, game_type="doubles")
        assert timeline._cells[0].text() == "0-0-2"
        assert timeline._cells[1].text() == "1-0-2"
        assert timeline._cells[2].text() == "1-0-1"

    def test_cell_width_varies_by_label_length(self, timeline, singles_rallies, doubles_rallies):
        """Test that cell width adjusts based on label length."""
        # Singles scores (3-4 chars) get medium width
        timeline.set_clips(singles_rallies, fps=60.0, game_type="singles")
        assert timeline._cells[0].width() == 36  # "0-0" = 3 chars

        # Doubles scores (5-6 chars) get larger width
        timeline.set_clips(doubles_rallies, fps=60.0, game_type="doubles")
        assert timeline._cells[0].width() == 48  # "0-0-2" = 5 chars

    def test_fallback_to_index_when_no_score(self, timeline):
        """Test fallback to sequential number when score_at_start is empty."""
        rallies = [Rally(start_frame=0, end_frame=120, score_at_start="", winner="server")]
        timeline.set_clips(rallies, fps=60.0, game_type="singles")
        assert timeline._cells[0].text() == "1"  # Fallback to index

    def test_tooltips_still_show_time_range(self, timeline, singles_rallies):
        """Test that tooltips show time range regardless of game_type."""
        timeline.set_clips(singles_rallies, fps=60.0, game_type="singles")
        # First clip: 0-2 seconds
        assert "0:00 - 0:02" in timeline._cells[0].toolTip()

    def test_in_progress_with_score_label(self, timeline, singles_rallies):
        """Test in-progress indicator with score label."""
        timeline.set_clips(singles_rallies, fps=60.0, game_type="singles")
        timeline.set_in_progress(True, label="2-1")
        assert timeline._in_progress_cell is not None
        assert timeline._in_progress_cell._label == "2-1"
