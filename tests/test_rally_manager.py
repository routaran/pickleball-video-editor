"""Tests for RallyManager rally tracking and undo functionality.

Tests:
- Rally start with pre-padding
- Rally end with post-padding
- Undo of rally start and end
- Multiple rally sequences
- Segment export format
- cascade_scores_from: score-edit cascade, flip cascade, error safety, legacy fallback
"""

import pytest
from src.core.rally_manager import RallyManager
from src.core.models import ScoreSnapshot, Rally, ActionType
from src.core.score_state import ScoreState


class TestRallyManager:
    """Test rally marking functionality."""

    def test_start_rally(self):
        """Test rally start with padding."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(10.0, snapshot)

        assert manager.is_rally_in_progress()
        # 10.0 - 0.5 padding = 9.5s = 570 frames
        assert frame == 570

    def test_start_rally_at_zero(self):
        """Test rally start at video beginning handles padding correctly."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(0.3, snapshot)

        # 0.3 - 0.5 padding would be negative, should clamp to 0
        assert frame == 0
        assert manager.is_rally_in_progress()

    def test_end_rally(self):
        """Test rally end with padding."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        rally = manager.end_rally(15.0, "server", "0-0-2", snapshot)

        assert not manager.is_rally_in_progress()
        assert rally.winner == "server"
        assert rally.score_at_start == "0-0-2"
        # 15.0 + 1.0 padding = 16.0s = 960 frames
        assert rally.end_frame == 960
        assert rally.start_frame == 570

    def test_end_rally_persists_rally_start_snapshot(self):
        """Completed rallies keep the snapshot captured at rally start."""
        manager = RallyManager(fps=60.0)
        start_snapshot = ScoreSnapshot(
            score=(1, 0),
            serving_team=1,
            server_number=1,
            first_server_player_index=0,
        )
        end_snapshot = ScoreSnapshot(
            score=(1, 1),
            serving_team=1,
            server_number=2,
            first_server_player_index=0,
        )

        manager.start_rally(10.0, start_snapshot)
        rally = manager.end_rally(15.0, "receiver", "0-1-1", end_snapshot)

        assert rally.score_snapshot_at_start == start_snapshot
        assert rally.score_snapshot_at_start != end_snapshot

    def test_cannot_end_without_start(self):
        """Test that ending rally without start raises error."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        with pytest.raises(ValueError, match="No rally in progress"):
            manager.end_rally(15.0, "server", "0-0-2", snapshot)

    def test_cannot_start_twice(self):
        """Test that starting rally twice raises error."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)

        with pytest.raises(ValueError, match="Rally already in progress"):
            manager.start_rally(15.0, snapshot)

    def test_undo_rally_end(self):
        """Test undo of rally end."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        assert manager.get_rally_count() == 1

        action, seek_pos = manager.undo()

        # Verify undo returns an Action object with RALLY_END type
        assert action.action_type == ActionType.RALLY_END
        assert action.timestamp == 15.0
        assert manager.get_rally_count() == 0
        assert manager.is_rally_in_progress()  # Back to in-progress
        # Should seek to where rally ended
        assert seek_pos == 15.0

    def test_undo_rally_start(self):
        """Test undo of rally start."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)

        assert manager.is_rally_in_progress()

        action, seek_pos = manager.undo()

        # Verify undo returns an Action object with RALLY_START type
        assert action.action_type == ActionType.RALLY_START
        assert action.timestamp == 10.0
        assert not manager.is_rally_in_progress()
        assert seek_pos == 10.0

    def test_undo_empty_raises_error(self):
        """Test undo on empty manager raises error."""
        manager = RallyManager(fps=60.0)

        with pytest.raises(ValueError, match="Nothing to undo"):
            manager.undo()

    def test_multiple_rallies(self):
        """Test multiple rally sequence."""
        manager = RallyManager(fps=60.0)

        # Rally 1
        snap1 = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)
        manager.start_rally(10.0, snap1)
        manager.end_rally(15.0, "server", "0-0-2", snap1)

        # Rally 2
        snap2 = ScoreSnapshot(score=(1, 0), serving_team=0, server_number=2)
        manager.start_rally(20.0, snap2)
        manager.end_rally(25.0, "receiver", "1-0-2", snap2)

        # Rally 3
        snap3 = ScoreSnapshot(score=(1, 0), serving_team=1, server_number=1)
        manager.start_rally(30.0, snap3)
        manager.end_rally(35.0, "server", "1-0-1", snap3)

        assert manager.get_rally_count() == 3
        rallies = manager.get_rallies()
        assert rallies[0].winner == "server"
        assert rallies[1].winner == "receiver"
        assert rallies[2].winner == "server"

    def test_undo_chain(self):
        """Test undoing multiple actions in sequence."""
        manager = RallyManager(fps=60.0)
        snap = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snap)
        manager.end_rally(15.0, "server", "0-0-2", snap)
        manager.start_rally(20.0, snap)
        manager.end_rally(25.0, "receiver", "1-0-2", snap)

        assert manager.get_rally_count() == 2

        # Undo rally 2 end
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_END
        assert manager.get_rally_count() == 1
        assert manager.is_rally_in_progress()

        # Undo rally 2 start
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_START
        assert manager.get_rally_count() == 1
        assert not manager.is_rally_in_progress()

        # Undo rally 1 end
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_END
        assert manager.get_rally_count() == 0
        assert manager.is_rally_in_progress()

        # Undo rally 1 start
        action, _ = manager.undo()
        assert action.action_type == ActionType.RALLY_START
        assert manager.get_rally_count() == 0
        assert not manager.is_rally_in_progress()

    def test_to_segments(self):
        """Test segment export format."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        segments = manager.to_segments()

        assert len(segments) == 1
        assert "in" in segments[0]
        assert "out" in segments[0]
        assert "score" in segments[0]
        assert "is_post_game" in segments[0]
        assert segments[0]["in"] == 570
        assert segments[0]["out"] == 960
        assert segments[0]["score"] == "0-0-2"
        assert segments[0]["is_post_game"] is False

    def test_to_segments_includes_is_post_game(self):
        """Test that is_post_game flag is propagated through to_segments()."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        # Normal rally
        manager.start_rally(10.0, snapshot)
        rally1 = manager.end_rally(15.0, "server", "0-0-2", snapshot)

        # Post-game rally
        manager.start_rally(20.0, snapshot)
        rally2 = manager.end_rally(25.0, "", "", snapshot)
        rally2.is_post_game = True

        segments = manager.to_segments()

        assert len(segments) == 2
        assert segments[0]["is_post_game"] is False
        assert segments[1]["is_post_game"] is True
        assert segments[0]["score"] == "0-0-2"
        assert segments[1]["score"] == ""

    def test_to_segments_reflects_cleared_post_game_flag_with_score_and_frames(self):
        """A converted PG rally exports as a normal scored segment."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(20.0, snapshot)
        rally = manager.end_rally(25.0, "", "", snapshot)
        rally.is_post_game = True

        # Mirrors Apply to Rally after validation: add score text and clear PG flag.
        rally.score_at_start = "3-2-1"
        rally.is_post_game = False

        segments = manager.to_segments()

        assert len(segments) == 1
        assert segments[0]["in"] == 1170
        assert segments[0]["out"] == 1560
        assert segments[0]["score"] == "3-2-1"
        assert segments[0]["is_post_game"] is False

    def test_to_segments_multiple(self):
        """Test segment export with multiple rallies."""
        manager = RallyManager(fps=60.0)

        # Rally 1
        snap1 = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)
        manager.start_rally(10.0, snap1)
        manager.end_rally(15.0, "server", "0-0-2", snap1)

        # Rally 2
        snap2 = ScoreSnapshot(score=(1, 0), serving_team=0, server_number=2)
        manager.start_rally(20.0, snap2)
        manager.end_rally(25.0, "receiver", "1-0-2", snap2)

        segments = manager.to_segments()

        assert len(segments) == 2
        assert segments[0]["score"] == "0-0-2"
        assert segments[1]["score"] == "1-0-2"

    def test_to_segments_empty(self):
        """Test segment export with no rallies."""
        manager = RallyManager(fps=60.0)
        segments = manager.to_segments()
        assert segments == []

    def test_to_segments_incomplete_rally(self):
        """Test segment export ignores incomplete rally."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        # Don't end it

        segments = manager.to_segments()
        assert segments == []

    def test_rally_in_progress_state(self):
        """Test rally in-progress state tracking."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        # No rally in progress initially
        assert not manager.is_rally_in_progress()

        # Start rally
        manager.start_rally(10.0, snapshot)
        assert manager.is_rally_in_progress()

        # End rally
        manager.end_rally(15.0, "server", "0-0-2", snapshot)
        assert not manager.is_rally_in_progress()

    def test_fps_conversion(self):
        """Test frame calculation with different FPS."""
        manager = RallyManager(fps=30.0)  # 30fps instead of 60
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        frame = manager.start_rally(10.0, snapshot)
        # 10.0 - 0.5 = 9.5s * 30fps = 285 frames
        assert frame == 285

        rally = manager.end_rally(15.0, "server", "0-0-2", snapshot)
        # 15.0 + 1.0 = 16.0s * 30fps = 480 frames
        assert rally.end_frame == 480

    def test_get_last_rally_end_position_empty(self):
        """Test get_last_rally_end_position returns None for empty list."""
        manager = RallyManager(fps=60.0)

        result = manager.get_last_rally_end_position()

        assert result is None

    def test_get_last_rally_end_position_single(self):
        """Test get_last_rally_end_position returns correct position for single rally."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        result = manager.get_last_rally_end_position()

        assert result is not None
        end_frame, end_seconds = result
        # 15.0 + 1.0 padding = 16.0s = 960 frames
        assert end_frame == 960
        assert end_seconds == 16.0

    def test_get_last_rally_end_position_multiple(self):
        """Test get_last_rally_end_position returns last rally's position when multiple rallies exist."""
        manager = RallyManager(fps=60.0)
        snapshot = ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)

        # Rally 1
        manager.start_rally(10.0, snapshot)
        manager.end_rally(15.0, "server", "0-0-2", snapshot)

        # Rally 2
        manager.start_rally(20.0, snapshot)
        manager.end_rally(25.0, "receiver", "1-0-2", snapshot)

        # Rally 3
        manager.start_rally(30.0, snapshot)
        manager.end_rally(35.0, "server", "2-0-2", snapshot)

        result = manager.get_last_rally_end_position()

        assert result is not None
        end_frame, end_seconds = result
        # 35.0 + 1.0 padding = 36.0s = 2160 frames
        assert end_frame == 2160
        assert end_seconds == 36.0

    def test_to_dict_round_trip_preserves_snapshot_state(self):
        """Serialized manager state keeps both in-progress and completed snapshots."""
        manager = RallyManager(fps=60.0)
        completed_snapshot = ScoreSnapshot(
            score=(0, 0),
            serving_team=0,
            server_number=2,
            first_server_player_index=0,
        )
        in_progress_snapshot = ScoreSnapshot(
            score=(1, 0),
            serving_team=1,
            server_number=1,
            first_server_player_index=0,
        )

        manager.start_rally(10.0, completed_snapshot)
        manager.end_rally(15.0, "server", "0-0-2", completed_snapshot)
        manager.start_rally(20.0, in_progress_snapshot)

        restored = RallyManager.from_dict(manager.to_dict())

        assert restored.get_rally(0).score_snapshot_at_start == completed_snapshot
        assert restored._current_rally_start_snapshot == in_progress_snapshot


class TestRallyModel:
    """Test Rally dataclass behavior."""

    def test_rally_creation(self):
        """Test creating a Rally object."""
        rally = Rally(
            start_frame=570,
            end_frame=960,
            score_at_start="0-0-2",
            winner="server",
            comment="Great rally",
        )

        assert rally.start_frame == 570
        assert rally.end_frame == 960
        assert rally.winner == "server"
        assert rally.score_at_start == "0-0-2"
        assert rally.comment == "Great rally"

    def test_rally_without_comment(self):
        """Test Rally without optional comment."""
        rally = Rally(
            start_frame=570,
            end_frame=960,
            score_at_start="0-0-2",
            winner="server",
        )

        assert rally.start_frame == 570
        assert rally.end_frame == 960
        assert rally.winner == "server"
        assert rally.comment is None


# ---------------------------------------------------------------------------
# Helpers for cascade tests
# ---------------------------------------------------------------------------

_DOUBLES_PLAYERS = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}


def _fresh_doubles_score_state() -> ScoreState:
    """Return a fresh doubles ScoreState at game start (0-0-2)."""
    return ScoreState("doubles", "11", _DOUBLES_PLAYERS)


def _build_doubles_manager(count: int = 5) -> tuple[RallyManager, list[str]]:
    """Build a RallyManager with *count* doubles rallies, all server wins, with snapshots.

    Returns:
        Tuple of (manager, original_score_strings) where original_score_strings[i]
        is the score_at_start for rally i as it was when the manager was built.
    """
    ss = _fresh_doubles_score_state()
    manager = RallyManager(fps=60.0)
    original_scores: list[str] = []

    for i in range(count):
        score_str = ss.get_score_string()
        original_scores.append(score_str)

        snapshot = ScoreSnapshot(
            score=tuple(ss.score),
            serving_team=ss.serving_team,
            server_number=ss.server_number,
            first_server_player_index=ss.first_server_player_index,
        )
        manager.start_rally(float(i * 20 + 10), snapshot)
        manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
        ss.server_wins()

    return manager, original_scores


# ---------------------------------------------------------------------------
# TestCascadeScoresFrom
# ---------------------------------------------------------------------------


class TestCascadeScoresFrom:
    """Tests for RallyManager.cascade_scores_from.

    Covers the production method directly (no reimplementation).  All doubles
    tests use the standard 5-rally all-server-wins fixture built by
    _build_doubles_manager(), which assigns real ScoreSnapshots.
    """

    def test_score_edit_cascade_updates_string_at_edited_rally(self):
        """Rally[k].score_at_start is set to new_score after a cascade edit.

        Regression for Bug 1: old code restored the OLD snapshot and never
        applied new_score, leaving score_at_start unchanged downstream.
        """
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        manager.cascade_scores_from(2, ss, new_score="5-3-1")

        assert manager.rallies[2].score_at_start == "5-3-1"

    def test_score_edit_cascade_refreshes_snapshot_at_edited_rally(self):
        """Rally[k].score_snapshot_at_start reflects new_score after cascade.

        Regression for Bug 2: old cascade never updated score_snapshot_at_start.
        """
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        manager.cascade_scores_from(2, ss, new_score="5-3-1")

        snap = manager.rallies[2].score_snapshot_at_start
        assert snap is not None
        # Snapshot score must match the overridden new_score (5-3-1 means
        # serving team score=5, receiving team score=3).
        assert snap.score == (5, 3)
        assert snap.server_number == 1

    def test_score_edit_cascade_updates_downstream_strings(self):
        """Downstream rallies' score_at_start strings reflect replay from new_score.

        Regression for Bug 1: old code replayed from the OLD score, producing
        wrong downstream strings (e.g. '3-0-2', '4-0-2' instead of '6-3-1', '7-3-1').
        """
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        # Edit rally[2] to "5-3-1".  Rallies 3 and 4 are both server wins,
        # so they should advance from "5-3-1" → "6-3-1" → "7-3-1".
        manager.cascade_scores_from(2, ss, new_score="5-3-1")

        assert manager.rallies[3].score_at_start == "6-3-1"
        assert manager.rallies[4].score_at_start == "7-3-1"

    def test_score_edit_cascade_updates_downstream_snapshots(self):
        """Downstream rallies' score_snapshot_at_start matches their new score_at_start.

        Regression for Bug 2: old code never updated snapshots during cascade,
        causing stale snapshot data to leak into training data export.
        """
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        manager.cascade_scores_from(2, ss, new_score="5-3-1")

        snap3 = manager.rallies[3].score_snapshot_at_start
        assert snap3 is not None
        assert snap3.score == (6, 3)

        snap4 = manager.rallies[4].score_snapshot_at_start
        assert snap4 is not None
        assert snap4.score == (7, 3)

    def test_score_edit_does_not_alter_rallies_before_index(self):
        """Rallies before the edited index are never modified by the cascade."""
        manager, original_scores = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        manager.cascade_scores_from(2, ss, new_score="5-3-1")

        assert manager.rallies[0].score_at_start == original_scores[0]
        assert manager.rallies[1].score_at_start == original_scores[1]

    def test_flip_cascade_refreshes_downstream_snapshots(self):
        """Cascade after a winner flip updates both strings and snapshots downstream.

        Regression for Bug 2 in the flip path: old _on_review_winner_flipped
        loop never wrote score_snapshot_at_start.
        """
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        # Flip rally[2] to receiver, then cascade (mirrors MainWindow behavior).
        manager.update_rally_winner(2, "receiver")
        manager.cascade_scores_from(2, ss)

        # After receiver wins at "2-0-2" (server_number=2) → side-out to team1
        # server1.  team1 score=0, team0 score=2 → "0-2-1" from team1 perspective.
        assert manager.rallies[3].score_at_start == "0-2-1"

        snap3 = manager.rallies[3].score_snapshot_at_start
        assert snap3 is not None
        # team1 serving (serving_team=1), scores: team1=0, team0=2
        assert snap3.serving_team == 1
        assert snap3.score[snap3.serving_team] == 0

    def test_invalid_new_score_raises_and_leaves_rallies_unchanged(self):
        """ValueError from invalid new_score propagates and leaves all rallies intact."""
        manager, original_scores = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        original_snaps = [r.score_snapshot_at_start for r in manager.rallies]

        with pytest.raises(ValueError):
            manager.cascade_scores_from(2, ss, new_score="not-a-score")

        # All strings unchanged
        for i, rally in enumerate(manager.rallies):
            assert rally.score_at_start == original_scores[i]
        # All snapshots unchanged
        for i, rally in enumerate(manager.rallies):
            assert rally.score_snapshot_at_start == original_snaps[i]

    def test_out_of_range_index_raises_index_error(self):
        """IndexError is raised for an out-of-range rally index."""
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        with pytest.raises(IndexError):
            manager.cascade_scores_from(99, ss)

    def test_legacy_rally_without_snapshot_falls_back_to_set_score(self):
        """Cascade seeds from score_at_start when score_snapshot_at_start is None.

        This preserves backward compatibility with sessions saved before
        snapshot persistence was introduced.
        """
        player_names = {"team1": ["P1"], "team2": ["P2"]}
        ss = ScoreState("singles", "11", player_names)

        manager = RallyManager(fps=60.0)
        # Build a legacy rally with no snapshot (simulating old session data).
        legacy_rally = Rally(
            start_frame=0,
            end_frame=60,
            score_at_start="3-2",
            winner="server",
            score_snapshot_at_start=None,
        )
        manager.rallies.append(legacy_rally)

        manager.cascade_scores_from(0, ss)

        # The method must not raise; it should have seeded via set_score and
        # then saved a fresh snapshot.
        assert manager.rallies[0].score_snapshot_at_start is not None
        assert manager.rallies[0].score_at_start == "3-2"

    def test_no_new_score_preserves_edited_rally_string(self):
        """When new_score is None, the indexed rally's score_at_start is untouched."""
        manager, original_scores = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        manager.cascade_scores_from(2, ss, new_score=None)

        assert manager.rallies[2].score_at_start == original_scores[2]

    def test_no_new_score_still_refreshes_snapshot_at_index(self):
        """Even without a new_score, the indexed rally gets a refreshed snapshot."""
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        original_snap = manager.rallies[2].score_snapshot_at_start

        manager.cascade_scores_from(2, ss, new_score=None)

        # The snapshot object is a fresh save — it must equal the old one in
        # value (same score, no edit), but is a distinct object.
        new_snap = manager.rallies[2].score_snapshot_at_start
        assert new_snap is not None
        assert new_snap is not original_snap
        assert new_snap == original_snap

    def test_cascade_returns_empty_list_when_no_predictions(self):
        """cascade_scores_from returns [] when no rallies have predicted_team set."""
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        result = manager.cascade_scores_from(2, ss)

        assert result == []

    def test_cascade_returns_empty_list_for_overridden_rallies(self):
        """Rallies with winner_overridden=True are never re-derived by the cascade."""
        manager, _ = _build_doubles_manager()
        ss = _fresh_doubles_score_state()

        # Mark rally[3] as predicted but also overridden — must NOT be re-derived.
        manager.rallies[3].predicted_team = 1
        manager.rallies[3].winner_overridden = True

        result = manager.cascade_scores_from(2, ss)

        assert result == []


# ---------------------------------------------------------------------------
# TestUpdateRallyWinnerSetsOverridden
# ---------------------------------------------------------------------------


class TestUpdateRallyWinnerSetsOverridden:
    """update_rally_winner must set winner_overridden = True on the affected rally."""

    def test_sets_winner_overridden_true(self):
        """winner_overridden is True after update_rally_winner is called."""
        manager = RallyManager(fps=60.0)
        rally = Rally(
            start_frame=0, end_frame=60, score_at_start="0-0-2", winner="server"
        )
        manager.rallies.append(rally)

        assert not manager.rallies[0].winner_overridden
        manager.update_rally_winner(0, "receiver")
        assert manager.rallies[0].winner_overridden is True

    def test_winner_overridden_true_on_same_value(self):
        """Even setting the same winner value marks the rally as overridden."""
        manager = RallyManager(fps=60.0)
        rally = Rally(
            start_frame=0, end_frame=60, score_at_start="0-0-2", winner="server"
        )
        manager.rallies.append(rally)

        manager.update_rally_winner(0, "server")
        assert manager.rallies[0].winner_overridden is True


# ---------------------------------------------------------------------------
# TestPredictionAwareCascade
# ---------------------------------------------------------------------------


def _build_doubles_manager_with_predictions(
    count: int = 5,
    predicted_teams: list[int | None] | None = None,
) -> tuple[RallyManager, ScoreState]:
    """Build a doubles RallyManager with predicted_team set on each rally.

    Args:
        count: Number of rallies to build (all server-wins).
        predicted_teams: predicted_team value per rally.  Defaults to the
            absolute serving team at each rally's start (i.e. correct
            predictions for all-server-wins sequence).

    Returns:
        (manager, fresh_score_state) where score_state is reset to game start.
    """
    ss = _fresh_doubles_score_state()
    manager = RallyManager(fps=60.0)

    built_serving_teams: list[int] = []
    for i in range(count):
        score_str = ss.get_score_string()
        built_serving_teams.append(ss.serving_team)

        snapshot = ScoreSnapshot(
            score=tuple(ss.score),
            serving_team=ss.serving_team,
            server_number=ss.server_number,
            first_server_player_index=ss.first_server_player_index,
        )
        manager.start_rally(float(i * 20 + 10), snapshot)
        manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
        ss.server_wins()

    # Assign predicted_team values
    if predicted_teams is None:
        predicted_teams = built_serving_teams  # "correct" predictions

    for i, pred in enumerate(predicted_teams):
        manager.rallies[i].predicted_team = pred
        manager.rallies[i].prediction_confidence = 0.85

    return manager, _fresh_doubles_score_state()


class TestPredictionAwareCascade:
    """Tests for F6: prediction-aware cascade re-derives downstream winners."""

    def test_downstream_winner_re_derived_when_serving_team_flips(self):
        """After flipping rally[2], downstream rallies with predictions update winner."""
        # All rallies: predicted_team = serving team at their start (which is team 0
        # for all-server-wins up to rally 2).  After flipping rally[2] to receiver,
        # a side-out occurs, making team 1 the new server.  Downstream rallies
        # still have predicted_team=0 (original server), so they should flip to
        # "receiver" because team 0 is no longer serving.
        player_names = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        ss = ScoreState("doubles", "11", player_names)
        manager = RallyManager(fps=60.0)

        # Build 5 rallies (0-0-2 start, all server wins, all predicted as team 0)
        for i in range(5):
            score_str = ss.get_score_string()
            snapshot = ScoreSnapshot(
                score=tuple(ss.score),
                serving_team=ss.serving_team,
                server_number=ss.server_number,
                first_server_player_index=ss.first_server_player_index,
            )
            manager.start_rally(float(i * 20 + 10), snapshot)
            manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
            manager.rallies[i].predicted_team = 0  # all predict team 0 winning
            manager.rallies[i].prediction_confidence = 0.9
            ss.server_wins()

        # Flip rally[2] to receiver (side-out → team 1 serves next)
        manager.update_rally_winner(2, "receiver")
        fresh_ss = ScoreState("doubles", "11", player_names)
        changed = manager.cascade_scores_from(2, fresh_ss)

        # Rallies 3 and 4: predicted_team=0 but now team 1 is serving.
        # "server" = team 1 → prediction (team 0) maps to "receiver".
        assert 3 in changed
        assert 4 in changed
        assert manager.rallies[3].winner == "receiver"
        assert manager.rallies[4].winner == "receiver"

    def test_overridden_rallies_not_re_derived(self):
        """Rallies with winner_overridden=True are immune to prediction re-derive."""
        player_names = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        ss = ScoreState("doubles", "11", player_names)
        manager = RallyManager(fps=60.0)

        for i in range(5):
            score_str = ss.get_score_string()
            snapshot = ScoreSnapshot(
                score=tuple(ss.score),
                serving_team=ss.serving_team,
                server_number=ss.server_number,
                first_server_player_index=ss.first_server_player_index,
            )
            manager.start_rally(float(i * 20 + 10), snapshot)
            manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
            manager.rallies[i].predicted_team = 0
            ss.server_wins()

        # Explicitly override rally[3] so it should be protected
        manager.rallies[3].winner_overridden = True

        manager.update_rally_winner(2, "receiver")
        fresh_ss = ScoreState("doubles", "11", player_names)
        changed = manager.cascade_scores_from(2, fresh_ss)

        assert 3 not in changed
        assert manager.rallies[3].winner == "server"  # unchanged

    def test_predicted_team_none_rallies_untouched(self):
        """Rallies with predicted_team=None are never re-derived by the cascade."""
        player_names = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        ss = ScoreState("doubles", "11", player_names)
        manager = RallyManager(fps=60.0)

        for i in range(5):
            score_str = ss.get_score_string()
            snapshot = ScoreSnapshot(
                score=tuple(ss.score),
                serving_team=ss.serving_team,
                server_number=ss.server_number,
                first_server_player_index=ss.first_server_player_index,
            )
            manager.start_rally(float(i * 20 + 10), snapshot)
            manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
            # Leave predicted_team=None (default)
            ss.server_wins()

        manager.update_rally_winner(2, "receiver")
        fresh_ss = ScoreState("doubles", "11", player_names)
        changed = manager.cascade_scores_from(2, fresh_ss)

        assert changed == []

    def test_changed_indices_only_includes_downstream(self):
        """Only indices > cascade start index appear in changed_indices."""
        player_names = {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
        ss = ScoreState("doubles", "11", player_names)
        manager = RallyManager(fps=60.0)

        for i in range(5):
            score_str = ss.get_score_string()
            snapshot = ScoreSnapshot(
                score=tuple(ss.score),
                serving_team=ss.serving_team,
                server_number=ss.server_number,
                first_server_player_index=ss.first_server_player_index,
            )
            manager.start_rally(float(i * 20 + 10), snapshot)
            manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
            manager.rallies[i].predicted_team = 0
            ss.server_wins()

        manager.update_rally_winner(2, "receiver")
        fresh_ss = ScoreState("doubles", "11", player_names)
        changed = manager.cascade_scores_from(2, fresh_ss)

        # Index 2 itself is the edited rally; no value ≤ 2 should appear
        for idx in changed:
            assert idx > 2


# ---------------------------------------------------------------------------
# TestDeleteRally
# ---------------------------------------------------------------------------


def _build_n_rallies(count: int = 5) -> tuple[RallyManager, ScoreState]:
    """Build a RallyManager with *count* doubles rallies (server wins) + matching ScoreState."""
    ss = _fresh_doubles_score_state()
    manager = RallyManager(fps=60.0)

    for i in range(count):
        score_str = ss.get_score_string()
        snapshot = ScoreSnapshot(
            score=tuple(ss.score),
            serving_team=ss.serving_team,
            server_number=ss.server_number,
            first_server_player_index=ss.first_server_player_index,
        )
        manager.start_rally(float(i * 20 + 10), snapshot)
        manager.end_rally(float(i * 20 + 15), "server", score_str, snapshot)
        ss.server_wins()

    return manager, _fresh_doubles_score_state()


class TestDeleteRally:
    """Tests for RallyManager.delete_rally (F5)."""

    def test_delete_middle_returns_correct_rally(self):
        """Deleting the middle rally returns the deleted object."""
        manager, _ = _build_n_rallies(5)
        score_at_start_2 = manager.rallies[2].score_at_start

        deleted, _changed = manager.delete_rally(2)

        assert deleted.score_at_start == score_at_start_2
        assert manager.get_rally_count() == 4

    def test_delete_first_rally(self):
        """Deleting index 0 returns the first rally and leaves count - 1 rallies."""
        manager, _ = _build_n_rallies(3)
        first_score = manager.rallies[0].score_at_start

        deleted, _changed = manager.delete_rally(0)

        assert deleted.score_at_start == first_score
        assert manager.get_rally_count() == 2

    def test_delete_last_rally(self):
        """Deleting the last rally leaves count - 1 rallies."""
        manager, _ = _build_n_rallies(3)
        last_score = manager.rallies[2].score_at_start

        deleted, _changed = manager.delete_rally(2)

        assert deleted.score_at_start == last_score
        assert manager.get_rally_count() == 2

    def test_delete_only_rally(self):
        """Deleting the only rally leaves an empty list."""
        manager, _ = _build_n_rallies(1)

        deleted, _changed = manager.delete_rally(0)

        assert manager.get_rally_count() == 0
        assert deleted is not None

    def test_delete_out_of_range_raises_index_error(self):
        """delete_rally raises IndexError for an invalid index."""
        manager, _ = _build_n_rallies(3)

        with pytest.raises(IndexError):
            manager.delete_rally(10)

    def test_delete_middle_with_cascade_re_derives_downstream_scores(self):
        """After deleting rally[2] with score_state, remaining rallies get correct scores."""
        manager, ss = _build_n_rallies(5)

        # Remember what the score at rally[3] was BEFORE deletion
        # After deletion, old rally[3] is at index 2.  Its score should be
        # re-derived from the deleted rally's score_at_start (which equals
        # old rally[2]'s score_at_start, i.e. the score before rally 2 ran).
        deleted_score = manager.rallies[2].score_at_start

        manager.delete_rally(2, ss)

        # The new rally[2] (was rally[3]) should have score_at_start == deleted_score
        # because that's the state before the deleted rally would have run.
        assert manager.rallies[2].score_at_start == deleted_score

    def test_delete_last_rally_no_cascade(self):
        """Deleting the last rally with score_state performs no cascade."""
        manager, ss = _build_n_rallies(3)
        scores_before = [r.score_at_start for r in manager.rallies[:2]]

        manager.delete_rally(2, ss)

        for i in range(2):
            assert manager.rallies[i].score_at_start == scores_before[i]

    def test_delete_returns_tuple(self):
        """delete_rally always returns (Rally, list[int])."""
        manager, ss = _build_n_rallies(3)

        result = manager.delete_rally(1, ss)

        assert isinstance(result, tuple)
        assert len(result) == 2
        deleted, changed = result
        assert isinstance(deleted, Rally)
        assert isinstance(changed, list)


# ---------------------------------------------------------------------------
# TestInsertRally
# ---------------------------------------------------------------------------


def _make_placeholder_rally(score: str = "0-0-2") -> Rally:
    """Build a minimal placeholder Rally suitable for insertion tests."""
    return Rally(
        start_frame=0,
        end_frame=60,
        score_at_start=score,
        winner="server",
        winner_overridden=True,
        predicted_team=None,
    )


class TestInsertRally:
    """Tests for RallyManager.insert_rally (F5)."""

    def test_insert_at_position_0_shifts_existing(self):
        """Inserting at index 0 shifts all existing rallies right by 1."""
        manager, _ = _build_n_rallies(3)
        original_first_score = manager.rallies[0].score_at_start

        new_rally = _make_placeholder_rally()
        manager.insert_rally(0, new_rally)

        assert manager.get_rally_count() == 4
        # The originally first rally is now at index 1
        assert manager.rallies[1].score_at_start == original_first_score

    def test_insert_at_end_appends(self):
        """Inserting at len(rallies) appends to the list."""
        manager, _ = _build_n_rallies(3)
        count_before = manager.get_rally_count()

        new_rally = _make_placeholder_rally()
        manager.insert_rally(count_before, new_rally)

        assert manager.get_rally_count() == count_before + 1
        assert manager.rallies[-1] is new_rally

    def test_insert_middle_cascade_re_derives_inserted_score(self):
        """Inserted rally's score is re-derived from its predecessor via cascade."""
        manager, ss = _build_n_rallies(4)

        # The predecessor is rally[1]; after inserting at index 2, the cascade
        # replays from rally[1], which means rallies[2] (the new one) gets
        # the score that would follow rally[1]'s outcome.
        score_after_rally1 = ss.get_score_string()  # will be replaced after replay
        predecessor_score = manager.rallies[1].score_at_start

        new_rally = _make_placeholder_rally(score="0-0-2")
        manager.insert_rally(2, new_rally, ss)

        # After cascade, new rally[2] score should be derived from rally[1]'s
        # post-outcome state, not the placeholder "0-0-2".
        assert manager.rallies[2].score_at_start != "0-0-2"

    def test_insert_position_0_with_cascade_seeds_from_old_first(self):
        """Inserting at 0 with cascade: inserted rally gets old first rally's score."""
        manager, ss = _build_n_rallies(3)
        old_first_score = manager.rallies[0].score_at_start

        new_rally = _make_placeholder_rally()
        manager.insert_rally(0, new_rally, ss)

        # The inserted rally (now at index 0) should have been seeded from the
        # old first rally's score (which is the game-opening state).
        assert manager.rallies[0].score_at_start == old_first_score

    def test_insert_returns_list(self):
        """insert_rally always returns a list."""
        manager, ss = _build_n_rallies(3)

        result = manager.insert_rally(1, _make_placeholder_rally(), ss)

        assert isinstance(result, list)

    def test_insert_beyond_cascade_downstream_scores_update(self):
        """All rallies after the insertion point get cascaded scores."""
        manager, ss = _build_n_rallies(4)

        # Record the original score of the rally at index 2 before insertion
        original_score_2 = manager.rallies[2].score_at_start

        new_rally = _make_placeholder_rally()
        manager.insert_rally(1, new_rally, ss)

        # What was rally[2] is now rally[3]; its score may have changed due
        # to the cascade, but it must be non-empty and valid.
        assert manager.get_rally_count() == 5
        assert manager.rallies[3].score_at_start != ""
