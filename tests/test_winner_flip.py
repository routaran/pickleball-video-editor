"""Tests for the winner-control primitive in RallyManager and ReviewModeWidget.

Covers:
- Test 1: update_rally_winner mutates the correct rally in-place.
- Test 2: Cascade — downstream score strings recalculate correctly after a flip.
- Test 3: winner_set signal fires when a winner button is clicked in WinnerControlWidget.
- Test 4: Low-confidence amber style applied/withheld by set_low_confidence_indices.

Tests 1 and 2 are pure-logic and require no Qt.
Tests 3 and 4 need a QApplication; they are skipped when Qt is unavailable.

API mapping (old → new):
  winner_flipped(int)          → winner_set(int, str)
  flipWinnerButton (QPushButton) → WinnerControlWidget._server_btn / ._receiver_btn
  ScoreEditWidget              → StateAnchorWidget
  score_changed                → state_anchor_set(int, int, str)
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from src.core.models import Rally, ScoreSnapshot
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState

# ---------------------------------------------------------------------------
# Stub heavy ML dependencies so that importing src.ui.* succeeds on machines
# without torch installed.  This mirrors the pattern in test_main_window.py.
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")  # type: ignore[assignment]

if "ml.predict" not in sys.modules:
    sys.modules["ml.predict"] = types.ModuleType("ml.predict")  # type: ignore[assignment]

if "ml.auto_edit" not in sys.modules:
    _auto_edit_stub = types.ModuleType("ml.auto_edit")
    _auto_edit_stub.AutoEditSetup = MagicMock  # type: ignore[attr-defined]
    sys.modules["ml.auto_edit"] = _auto_edit_stub  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rally(score_at_start: str, winner: str) -> Rally:
    """Build a minimal Rally object for in-memory tests."""
    return Rally(
        start_frame=0,
        end_frame=60,
        score_at_start=score_at_start,
        winner=winner,
    )


def _build_five_rally_manager() -> tuple[RallyManager, list[str]]:
    """Return a RallyManager pre-populated with 5 doubles rallies (all server wins).

    Also returns the score_at_start list that was computed during build so tests
    can verify the pre-flip baseline cheaply.

    Rally sequence (doubles, 0-0-2 start, all server wins):
        0: 0-0-2  server_wins → 1-0-2
        1: 1-0-2  server_wins → 2-0-2
        2: 2-0-2  server_wins → 3-0-2
        3: 3-0-2  server_wins → 4-0-2
        4: 4-0-2  server_wins → 5-0-2
    """
    player_names = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
    ss = ScoreState("doubles", "11", player_names)

    manager = RallyManager(fps=60.0)
    original_scores: list[str] = []

    for i in range(5):
        score_str = ss.get_score_string()
        original_scores.append(score_str)

        snapshot = ScoreSnapshot(
            score=tuple(ss.score),
            serving_team=ss.serving_team,
            server_number=ss.server_number,
            first_server_player_index=ss.first_server_player_index,
        )
        start_ts = float(i * 20 + 10)
        end_ts = float(i * 20 + 15)

        manager.start_rally(start_ts, snapshot)
        manager.end_rally(end_ts, "server", score_str, snapshot)

        ss.server_wins()

    return manager, original_scores


def _cascade_scores_after_flip(
    rally_manager: RallyManager,
    flip_index: int,
    new_winner: str,
    player_names: dict,
) -> None:
    """Mirror the cascade logic that MainWindow would perform.

    Replay ScoreState from rally[0] to find each rally's score_at_start,
    honouring the flipped winner at flip_index, and write results back to
    rally_manager.rallies[i].score_at_start for i >= flip_index.

    This helper exists so Test 2 can assert on the final rally objects
    without depending on MainWindow. The real production cascade lives in
    MainWindow; this is the minimal equivalent for unit-testing.
    """
    # Apply the winner mutation first.
    rally_manager.update_rally_winner(flip_index, new_winner)

    # Determine game type / victory rules from existing data (doubles, 11).
    ss = ScoreState("doubles", "11", player_names)

    for i, rally in enumerate(rally_manager.rallies):
        # Recalculate score string from current ScoreState and write it back.
        if i >= flip_index:
            rally.score_at_start = ss.get_score_string()

        # Advance state using the (possibly flipped) winner.
        if rally.winner == "server":
            ss.server_wins()
        else:
            ss.receiver_wins()


# ---------------------------------------------------------------------------
# Test 1: update_rally_winner — simple in-place flip
# ---------------------------------------------------------------------------

class TestUpdateRallyWinnerSimple:
    """Test that update_rally_winner mutates winner without touching scores."""

    def test_flip_server_to_receiver(self):
        """Flip winner from 'server' to 'receiver'."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("0-0-2", "server"))

        manager.update_rally_winner(0, "receiver")

        assert manager.rallies[0].winner == "receiver"

    def test_flip_receiver_to_server(self):
        """Flip winner from 'receiver' to 'server'."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("0-0-2", "receiver"))

        manager.update_rally_winner(0, "server")

        assert manager.rallies[0].winner == "server"

    def test_score_at_start_unchanged(self):
        """update_rally_winner must not touch score_at_start."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("3-1-1", "server"))

        manager.update_rally_winner(0, "receiver")

        assert manager.rallies[0].score_at_start == "3-1-1"

    def test_other_rallies_unchanged(self):
        """Flipping rally 0 must not affect rally 1."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("0-0-2", "server"))
        manager.rallies.append(_make_rally("1-0-2", "receiver"))

        manager.update_rally_winner(0, "receiver")

        assert manager.rallies[1].winner == "receiver"
        assert manager.rallies[1].score_at_start == "1-0-2"

    def test_invalid_winner_raises_value_error(self):
        """update_rally_winner rejects any value other than server/receiver."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("0-0-2", "server"))

        with pytest.raises(ValueError, match="new_winner must be"):
            manager.update_rally_winner(0, "nobody")

    def test_out_of_range_raises_index_error(self):
        """update_rally_winner raises IndexError for an out-of-range index."""
        manager = RallyManager(fps=60.0)
        manager.rallies.append(_make_rally("0-0-2", "server"))

        with pytest.raises(IndexError):
            manager.update_rally_winner(5, "receiver")


# ---------------------------------------------------------------------------
# Test 2: update_rally_winner cascade — downstream scores update correctly
# ---------------------------------------------------------------------------

class TestWinnerFlipCascade:
    """Cascade recalculation after flipping rally index 2 in a 5-rally session."""

    # Expected cascade values, pre-computed by running ScoreState forward:
    #
    #   Original (all server wins):  0-0-2, 1-0-2, 2-0-2, 3-0-2, 4-0-2
    #   Flip rally 2 → receiver:
    #     Rally 0 score_at_start: 0-0-2  (unchanged)
    #     Rally 1 score_at_start: 1-0-2  (unchanged)
    #     Rally 2 score_at_start: 2-0-2  (unchanged — same position as flip)
    #     Rally 3 score_at_start: 0-2-1  (team1 now serving after side-out)
    #     Rally 4 score_at_start: 1-2-1  (team1 scores one point)

    PLAYER_NAMES = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}

    def test_rallies_before_flip_index_are_unchanged(self):
        """Rallies 0 and 1 keep their original score strings after flip."""
        manager, original_scores = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        assert manager.rallies[0].score_at_start == original_scores[0]  # 0-0-2
        assert manager.rallies[1].score_at_start == original_scores[1]  # 1-0-2

    def test_flipped_rally_score_at_start_unchanged(self):
        """Rally 2's own score_at_start is preserved — only its winner changes."""
        manager, original_scores = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        assert manager.rallies[2].score_at_start == original_scores[2]  # 2-0-2

    def test_flipped_rally_winner_is_updated(self):
        """Rally 2's winner field is set to 'receiver'."""
        manager, _ = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        assert manager.rallies[2].winner == "receiver"

    def test_rally_3_score_cascades_to_sideout_value(self):
        """Rally 3 score_at_start becomes 0-2-1 (team1 serving after side-out)."""
        manager, _ = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        # After receiver wins at 2-0-2 (server_number=2) → side-out → team1 server1
        # team1's score=0, team0's score=2 → "0-2-1" from team1's perspective
        assert manager.rallies[3].score_at_start == "0-2-1"

    def test_rally_4_score_cascades_correctly(self):
        """Rally 4 score_at_start becomes 1-2-1 after team1 wins rally 3."""
        manager, _ = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        # Team1 (serving) wins rally 3 → their score becomes 1 → "1-2-1"
        assert manager.rallies[4].score_at_start == "1-2-1"

    def test_total_rally_count_unchanged(self):
        """Flip + cascade must not add or remove rallies."""
        manager, _ = _build_five_rally_manager()
        original_count = manager.get_rally_count()
        _cascade_scores_after_flip(manager, 2, "receiver", self.PLAYER_NAMES)

        assert manager.get_rally_count() == original_count

    def test_cascade_from_first_rally(self):
        """Flipping rally 0 cascades all 4 downstream rallies."""
        manager, _ = _build_five_rally_manager()
        _cascade_scores_after_flip(manager, 0, "receiver", self.PLAYER_NAMES)

        # After receiver wins at 0-0-2 → side-out to team1 server1
        # team1's score=0, team0's score=0 → "0-0-1"
        assert manager.rallies[1].score_at_start == "0-0-1"
        # Sanity: rally 0 winner changed
        assert manager.rallies[0].winner == "receiver"


# ---------------------------------------------------------------------------
# Qt fixtures and test infrastructure
# ---------------------------------------------------------------------------

def _qt_available() -> bool:
    """Return True if a QApplication can be created in this environment."""
    try:
        from PyQt6.QtWidgets import QApplication
        return True
    except Exception:
        return False


_QT_SKIP_REASON = "Qt not available in this test environment"


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication fixture; skips the module if Qt is absent."""
    if not _qt_available():
        pytest.skip(_QT_SKIP_REASON)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app


def _make_stub_rallies(count: int = 3) -> list[Rally]:
    """Build a list of minimal Rally objects for widget tests."""
    scores = ["0-0-2", "1-0-2", "0-1-1"]
    winners = ["server", "receiver", "server"]
    return [
        _make_rally(scores[i % len(scores)], winners[i % len(winners)])
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Test 3: winner_set signal fires on button click (replaces winner_flipped)
#
# Intent preserved: verify the correct rally index and winner string are
# emitted when the user explicitly selects a winner via WinnerControlWidget.
# The old test clicked a single "Flip Winner" toggle; the new API exposes two
# explicit buttons ("Serving Team Won" / "Returning Team Won"), each of which
# emits winner_set(rally_idx, "server"|"receiver").
# ---------------------------------------------------------------------------

class TestWinnerSetSignal:
    """WinnerControlWidget buttons emit winner_set(rally_index, winner_string).

    Note: _winner_control is accessed directly because Qt's findChild requires
    the widget to be in the tree (which happens only after showEvent triggers
    the deferred arrangement).  Accessing the attribute bypasses that constraint
    while still testing the real widget and signal.
    """

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_server_button_emits_server_winner_at_current_index(self, qapp):
        """Click 'Serving Team Won' on rally 1 → winner_set emits (1, 'server')."""
        from src.ui.review_mode import ReviewModeWidget

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(1)

        emitted: list[tuple[int, str]] = []
        widget.winner_set.connect(lambda idx, w: emitted.append((idx, w)))

        winner_control = widget._winner_control
        assert winner_control is not None, "_winner_control not set on ReviewModeWidget"
        winner_control._server_btn.click()

        assert len(emitted) == 1
        assert emitted[0] == (1, "server")

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_receiver_button_emits_receiver_winner_at_current_index(self, qapp):
        """Click 'Returning Team Won' on rally 0 → winner_set emits (0, 'receiver')."""
        from src.ui.review_mode import ReviewModeWidget

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(0)

        emitted: list[tuple[int, str]] = []
        widget.winner_set.connect(lambda idx, w: emitted.append((idx, w)))

        winner_control = widget._winner_control
        assert winner_control is not None
        winner_control._receiver_btn.click()

        assert len(emitted) == 1
        assert emitted[0] == (0, "receiver")

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_multiple_clicks_each_emit_one_signal(self, qapp):
        """Each winner button click emits exactly one winner_set signal."""
        from src.ui.review_mode import ReviewModeWidget

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(2)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(0)

        emitted: list[tuple[int, str]] = []
        widget.winner_set.connect(lambda idx, w: emitted.append((idx, w)))

        winner_control = widget._winner_control
        assert winner_control is not None
        winner_control._server_btn.click()
        winner_control._receiver_btn.click()

        assert emitted == [(0, "server"), (0, "receiver")]


# ---------------------------------------------------------------------------
# Test 4: low-confidence amber flag styling on WinnerControlWidget
#
# Intent preserved: amber styling is applied to the winner control when the
# current rally is in the low-confidence set and removed when it is not.
# The old test checked the single "flipWinnerButton"; the new test checks
# WinnerControlWidget's server button (both buttons receive the same style).
# ---------------------------------------------------------------------------

class TestLowConfidenceAmberStyle:
    """set_low_confidence_indices applies/withholds amber styling on WinnerControlWidget.

    Note: _winner_control is accessed directly (same reason as TestWinnerSetSignal).
    """

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_amber_style_applied_for_low_confidence_rally(self, qapp):
        """Winner buttons show amber border when current rally is low-confidence."""
        from src.ui.review_mode import ReviewModeWidget
        from src.ui.styles import RECEIVER_WINS  # orange / amber

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(0)

        widget.set_low_confidence_indices({0, 2})

        winner_control = widget._winner_control
        assert winner_control is not None

        stylesheet = winner_control._server_btn.styleSheet()
        assert RECEIVER_WINS.lower() in stylesheet.lower(), (
            f"Expected amber color {RECEIVER_WINS!r} in stylesheet, got: {stylesheet!r}"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_amber_style_absent_for_normal_rally(self, qapp):
        """Winner buttons do NOT show amber when current rally is not low-confidence."""
        from src.ui.review_mode import ReviewModeWidget
        from src.ui.styles import RECEIVER_WINS, SERVER_WINS

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(1)  # rally 1 — not in low-confidence set

        widget.set_low_confidence_indices({0, 2})  # 1 is excluded

        winner_control = widget._winner_control
        assert winner_control is not None

        stylesheet = winner_control._server_btn.styleSheet()
        assert RECEIVER_WINS.lower() not in stylesheet.lower(), (
            f"Amber color {RECEIVER_WINS!r} must NOT appear for normal rally"
        )
        # The neutral blue indicator should be present instead.
        assert SERVER_WINS.lower() in stylesheet.lower(), (
            f"Expected blue color {SERVER_WINS!r} in stylesheet for normal rally"
        )

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_style_updates_when_navigating_between_rallies(self, qapp):
        """Navigating from a low-confidence rally to a normal one updates the style."""
        from src.ui.review_mode import ReviewModeWidget
        from src.ui.styles import RECEIVER_WINS, SERVER_WINS

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)

        widget.set_low_confidence_indices({0, 2})

        winner_control = widget._winner_control
        assert winner_control is not None

        # Navigate to low-confidence rally 0 → amber expected.
        widget.set_current_rally(0)
        assert RECEIVER_WINS.lower() in winner_control._server_btn.styleSheet().lower()

        # Navigate to normal rally 1 → blue expected.
        widget.set_current_rally(1)
        assert RECEIVER_WINS.lower() not in winner_control._server_btn.styleSheet().lower()
        assert SERVER_WINS.lower() in winner_control._server_btn.styleSheet().lower()

        # Navigate to low-confidence rally 2 → amber expected again.
        widget.set_current_rally(2)
        assert RECEIVER_WINS.lower() in winner_control._server_btn.styleSheet().lower()

    @pytest.mark.skipif(not _qt_available(), reason=_QT_SKIP_REASON)
    def test_empty_low_confidence_set_applies_normal_style(self, qapp):
        """An empty set leaves all rallies in normal (non-amber) style."""
        from src.ui.review_mode import ReviewModeWidget
        from src.ui.styles import RECEIVER_WINS, SERVER_WINS

        widget = ReviewModeWidget()
        rallies = _make_stub_rallies(3)
        widget.set_rallies(rallies, fps=60.0)
        widget.set_current_rally(0)

        widget.set_low_confidence_indices(set())

        winner_control = widget._winner_control
        assert winner_control is not None

        stylesheet = winner_control._server_btn.styleSheet()
        assert RECEIVER_WINS.lower() not in stylesheet.lower()
        assert SERVER_WINS.lower() in stylesheet.lower()
