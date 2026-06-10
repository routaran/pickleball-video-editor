"""Rally tracking with undo support for Pickleball Video Editor.

This module manages rally marking during video editing with:
- Start/end rally marking with automatic padding
- Undo functionality with action stack
- Rally timing adjustments for Final Review mode
- Kdenlive segment export format
- JSON serialization for session persistence

Rally Padding:
- Start: -0.5 seconds (cut 0.5 seconds before marked start)
- End: +1.0 seconds (cut 1 second after marked end)

Undo Support:
- RALLY_START: Clears current rally-in-progress state
- RALLY_END: Removes completed rally and restores rally-in-progress state
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.models import Rally, Action, ActionType, ScoreSnapshot

if TYPE_CHECKING:
    from src.core.score_state import ScoreState


__all__ = ["RallyManager"]


class RallyManager:
    """Manages rally tracking with undo support for the video editor.

    This class handles:
    - Starting rallies (with -0.5s padding)
    - Ending rallies (with +1.0s padding)
    - Undo/redo with action stack
    - Rally timing adjustments
    - Conversion to Kdenlive segments
    - Serialization for session persistence

    Attributes:
        fps: Video frames per second for frame/time conversion
        rallies: List of completed rallies
        action_stack: Stack of actions for undo functionality
    """

    # Timing padding constants (in seconds)
    START_PADDING = -0.5  # Cut 0.5 seconds before marked rally start
    END_PADDING = 1.0     # Cut 1 second after marked rally end

    def __init__(self, fps: float = 60.0) -> None:
        """Initialize the rally manager.

        Args:
            fps: Video frames per second for frame/time conversion

        Raises:
            ValueError: If fps is not positive
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        self.fps = fps
        self.rallies: list[Rally] = []
        self.action_stack: list[Action] = []
        self._current_rally_start: int | None = None  # Frame number
        self._current_rally_timestamp: float | None = None  # Original timestamp before padding
        self._current_rally_start_snapshot: ScoreSnapshot | None = None

    def start_rally(self, timestamp: float, score_snapshot: ScoreSnapshot) -> int:
        """Mark the start of a rally.

        Captures the current video timestamp, applies -0.5s padding, and records
        the rally start frame. Updates internal state to "rally in progress".

        Args:
            timestamp: Current video timestamp in seconds
            score_snapshot: Current score state for undo

        Returns:
            The start frame number (with padding applied)

        Raises:
            ValueError: If a rally is already in progress
        """
        if self._current_rally_start is not None:
            raise ValueError("Rally already in progress")

        # Apply padding and convert to frame
        padded_time = max(0, timestamp + self.START_PADDING)
        start_frame = self._time_to_frame(padded_time)

        self._current_rally_start = start_frame
        self._current_rally_timestamp = timestamp
        self._current_rally_start_snapshot = score_snapshot

        # Record action for undo
        action = Action(
            action_type=ActionType.RALLY_START,
            timestamp=timestamp,
            frame=start_frame,
            score_before=score_snapshot,
            data={}
        )
        self.action_stack.append(action)

        return start_frame

    def end_rally(
        self,
        timestamp: float,
        winner: str,
        score_at_start: str,
        score_snapshot: ScoreSnapshot,
        comment: str | None = None
    ) -> Rally:
        """Mark the end of a rally.

        Captures the current video timestamp, applies +1.0s padding, creates
        a Rally object, and updates the score state.

        Args:
            timestamp: Current video timestamp in seconds
            winner: "server" or "receiver"
            score_at_start: Score string when rally started
            score_snapshot: Current score state for undo
            comment: Optional comment for the rally

        Returns:
            The created Rally object

        Raises:
            ValueError: If no rally is in progress
        """
        if self._current_rally_start is None:
            raise ValueError("No rally in progress")

        # Apply padding and convert to frame
        padded_time = timestamp + self.END_PADDING
        end_frame = self._time_to_frame(padded_time)

        # Compute raw (unpadded) frames from original timestamps
        raw_start_frame = self._time_to_frame(self._current_rally_timestamp)
        raw_end_frame = self._time_to_frame(timestamp)

        # Create rally
        rally = Rally(
            start_frame=self._current_rally_start,
            end_frame=end_frame,
            score_at_start=score_at_start,
            winner=winner,
            comment=comment,
            raw_start_seconds=self._current_rally_timestamp,
            raw_end_seconds=timestamp,
            raw_start_frame=raw_start_frame,
            raw_end_frame=raw_end_frame,
            score_snapshot_at_start=self._current_rally_start_snapshot,
        )

        self.rallies.append(rally)

        # Record action for undo
        action = Action(
            action_type=ActionType.RALLY_END,
            timestamp=timestamp,
            frame=end_frame,
            score_before=score_snapshot,
            data={"rally_index": len(self.rallies) - 1}
        )
        self.action_stack.append(action)

        # Clear current rally state
        self._current_rally_start = None
        self._current_rally_timestamp = None
        self._current_rally_start_snapshot = None

        return rally

    def is_rally_in_progress(self) -> bool:
        """Check if a rally is currently in progress.

        Returns:
            True if a rally has been started but not ended
        """
        return self._current_rally_start is not None

    def get_rally_count(self) -> int:
        """Get the total number of completed rallies.

        Returns:
            Number of completed rallies
        """
        return len(self.rallies)

    def get_rallies(self) -> list[Rally]:
        """Get all completed rallies.

        Returns:
            Copy of the rallies list
        """
        return self.rallies.copy()

    def get_rally(self, index: int) -> Rally:
        """Get a specific rally by index.

        Args:
            index: Rally index (0-based)

        Returns:
            The Rally object at the given index

        Raises:
            IndexError: If index is out of range
        """
        return self.rallies[index]

    def get_last_rally_end_position(self) -> tuple[int, float] | None:
        """Get the end frame and timestamp of the last completed rally.

        Returns:
            Tuple of (end_frame, end_seconds) for the last rally,
            or None if no rallies exist.
        """
        if not self.rallies:
            return None

        last_rally = self.rallies[-1]
        end_frame = last_rally.end_frame
        end_seconds = self._frame_to_time(end_frame)
        return (end_frame, end_seconds)

    def update_rally_timing(
        self,
        index: int,
        start_delta: float = 0.0,
        end_delta: float = 0.0
    ) -> Rally:
        """Adjust rally timing (for Final Review mode).

        Applies time deltas to the start and/or end of a rally. Ensures that
        start remains before end and both are non-negative.

        Args:
            index: Rally index to update
            start_delta: Seconds to add/subtract from start (negative = earlier)
            end_delta: Seconds to add/subtract from end (negative = earlier)

        Returns:
            The updated Rally object

        Raises:
            IndexError: If index is out of range
        """
        rally = self.rallies[index]

        # Convert deltas to frames
        start_frame_delta = self._time_to_frame(abs(start_delta))
        if start_delta < 0:
            start_frame_delta = -start_frame_delta

        end_frame_delta = self._time_to_frame(abs(end_delta))
        if end_delta < 0:
            end_frame_delta = -end_frame_delta

        # Update frames (ensure start < end and both >= 0)
        new_start = max(0, rally.start_frame + start_frame_delta)
        new_end = max(new_start + 1, rally.end_frame + end_frame_delta)

        # Update rally in-place (Rally is mutable)
        rally.start_frame = new_start
        rally.end_frame = new_end

        return rally

    def update_rally_winner(self, index: int, new_winner: str) -> None:
        """Flip the winner of a rally in-place and mark it as user-overridden.

        Sets rallies[index].winner to new_winner and rallies[index].winner_overridden
        to True.  Score cascade is the caller's responsibility (MainWindow drives it
        via ScoreState, mirroring the existing update_rally_score cascade pattern).
        The winner_overridden flag prevents prediction-aware cascade from re-deriving
        this rally's winner from predicted_team in future cascades.

        Args:
            index: Rally index to update (0-based)
            new_winner: "server" or "receiver"

        Raises:
            IndexError: If index is out of range
            ValueError: If new_winner is not "server" or "receiver"
        """
        if new_winner not in ("server", "receiver"):
            raise ValueError(f"new_winner must be 'server' or 'receiver', got {new_winner!r}")
        self.rallies[index].winner = new_winner
        self.rallies[index].winner_overridden = True

    def update_rally_score(self, index: int, new_score: str) -> None:
        """Update a single rally's score string (for non-cascade edits in Final Review mode).

        Sets score_at_start on the indexed rally without touching any other rally or
        score snapshot.  When a cascade is required (i.e. downstream rallies must be
        updated too), callers should use :meth:`cascade_scores_from` instead, passing
        the current ``ScoreState`` instance — that method owns both the string and
        snapshot update for the edited rally and all rallies after it.

        Args:
            index: Rally index to update (0-based)
            new_score: New score string (e.g. ``"5-3"`` for singles, ``"7-4-1"`` for doubles)

        Raises:
            IndexError: If index is out of range
        """
        self.rallies[index].score_at_start = new_score

    def cascade_scores_from(
        self,
        index: int,
        score_state: "ScoreState",
        new_score: str | None = None,
    ) -> list[int]:
        """Replay score state forward from rally[index], refreshing strings and snapshots.

        Seeds the score state from the indexed rally's ``score_snapshot_at_start``
        (or falls back to ``set_score(rally.score_at_start)`` for legacy rallies that
        lack a snapshot), optionally applies ``new_score`` on top of that serving-team
        perspective, then walks every rally from *index* onward updating both
        ``score_at_start`` and ``score_snapshot_at_start`` before advancing the state
        with each rally's winner.

        The snapshot-seed step is critical: it restores the absolute serving-team
        orientation that was recorded when the rally was originally marked so that
        ``set_score(new_score)`` interprets the score numbers from the correct team's
        point of view.

        Prediction-aware re-derive (F6): for each downstream rally (i > index) whose
        ``predicted_team`` is set and ``winner_overridden`` is False, the winner string
        is re-derived from the absolute model prediction relative to the cascade's
        current serving team.  The set of indices whose winner was re-derived is
        returned so callers can surface the change to the user.

        Args:
            index: Rally index to begin cascade from (0-based)
            score_state: ``ScoreState`` instance to use for replay (mutated in-place)
            new_score: If provided, overrides ``score_at_start`` on rally[index] after
                the snapshot seed.  The edit is applied via ``score_state.set_score``
                so it inherits the correct serving-team perspective.  If ``None``,
                the rally's existing ``score_at_start`` is preserved.

        Returns:
            List of downstream rally indices (all > *index*) whose winner string was
            re-derived from their ``predicted_team`` because the serving-team flipped
            relative to their original prediction context.  Empty list when no
            prediction-based re-derives occurred.

        Raises:
            IndexError: If *index* is out of range.
            ValueError: If *new_score* is an invalid score string.  The exception
                propagates before any rally data is mutated, leaving all rallies
                in their original state.
        """
        if not (0 <= index < len(self.rallies)):
            raise IndexError(f"Rally index {index} out of range (0..{len(self.rallies) - 1})")

        rally = self.rallies[index]

        # Seed: recover the correct serving-team perspective for this rally.
        # Restoring from a snapshot is preferred because it also recovers
        # first_server_player_index and server_number exactly as they were.
        if rally.score_snapshot_at_start is not None:
            score_state.restore_snapshot(rally.score_snapshot_at_start)
        else:
            # Legacy rally without a snapshot — best-effort seed from the score string.
            score_state.set_score(rally.score_at_start)

        # Apply the user's new score on top of the seeded serving-team perspective.
        # If set_score raises ValueError it propagates here — before any rally
        # mutation — so data stays unchanged.
        if new_score is not None:
            score_state.set_score(new_score)
            rally.score_at_start = new_score

        # Refresh the edited rally's snapshot from the now-correct score state.
        rally.score_snapshot_at_start = score_state.save_snapshot()

        # Replay loop: walk forward, writing score string + snapshot to each
        # downstream rally before advancing the state with that rally's winner.
        changed_indices: list[int] = []
        for i in range(index, len(self.rallies)):
            current_rally = self.rallies[i]

            if i > index:
                current_rally.score_at_start = score_state.get_score_string()
                current_rally.score_snapshot_at_start = score_state.save_snapshot()

                # F6 — prediction-aware re-derive: if this rally has a model
                # prediction and the user has NOT explicitly overridden it, check
                # whether the predicted absolute team maps to "server" or "receiver"
                # under the CURRENT serving-team orientation (which may have shifted
                # as a result of the winner flip at *index*).  If the derived string
                # differs from the stored winner, update it so downstream score math
                # stays consistent with the model.
                if (
                    current_rally.predicted_team is not None
                    and not current_rally.winner_overridden
                ):
                    expected = (
                        "server"
                        if current_rally.predicted_team == score_state.serving_team
                        else "receiver"
                    )
                    if expected != current_rally.winner:
                        current_rally.winner = expected
                        changed_indices.append(i)

            if current_rally.winner == "server":
                score_state.server_wins()
            elif current_rally.winner == "receiver":
                score_state.receiver_wins()

        return changed_indices

    def delete_rally(
        self,
        index: int,
        score_state: "ScoreState | None" = None,
    ) -> tuple["Rally", list[int]]:
        """Remove and return a rally by index, optionally cascading scores forward.

        Pops ``rallies[index]`` and returns it together with the list of indices
        whose winner was re-derived from model predictions during the cascade (see
        :meth:`cascade_scores_from`).

        If ``score_state`` is provided **and** a rally still exists at position
        *index* after the deletion (i.e. the deleted rally was not the last one),
        the cascade is seeded from the deleted rally's ``score_snapshot_at_start``
        (or its ``score_at_start`` string for legacy rallies).  That seed is copied
        onto the new ``rallies[index]`` before ``cascade_scores_from`` is called so
        the state before the deleted rally propagates correctly to all subsequent
        rallies.

        Note: the action stack is NOT rewound by review-mode deletes.  This is
        intentional — the undo stack is only used during the capture phase, not
        during final-review edits.

        Args:
            index: Rally index to remove (0-based).
            score_state: Live ``ScoreState`` instance.  When provided and rallies
                remain after deletion, a full forward cascade is performed.

        Returns:
            Tuple of (deleted_rally, changed_indices) where *deleted_rally* is the
            removed Rally object and *changed_indices* is the list of rally indices
            whose winner string was re-derived from model predictions (may be empty).

        Raises:
            IndexError: If *index* is out of range.
        """
        if not (0 <= index < len(self.rallies)):
            raise IndexError(f"Rally index {index} out of range (0..{len(self.rallies) - 1})")

        deleted = self.rallies.pop(index)
        changed: list[int] = []

        if score_state is not None and index < len(self.rallies):
            # Seed the new rallies[index] from the deleted rally's state — that
            # is, the score immediately before the deleted rally ran — so the
            # cascade replays correctly from that point.
            next_rally = self.rallies[index]
            next_rally.score_at_start = deleted.score_at_start
            next_rally.score_snapshot_at_start = deleted.score_snapshot_at_start
            changed = self.cascade_scores_from(index, score_state)

        return deleted, changed

    def insert_rally(
        self,
        index: int,
        rally: "Rally",
        score_state: "ScoreState | None" = None,
    ) -> list[int]:
        """Insert a rally at *index*, shifting existing rallies right, then cascade.

        After insertion the rally at *index* is the one passed in; the rally that
        previously occupied *index* (if any) is now at *index + 1*.

        Score seeding rules (applied only when ``score_state`` is provided):

        - ``index == 0``: copy the OLD first rally's ``score_at_start`` /
          ``score_snapshot_at_start`` (now at position 1 after insertion) onto the
          inserted rally so that the cascade replays from the correct game-opening
          state.  Then call ``cascade_scores_from(0, score_state)``.
        - ``index > 0``: call ``cascade_scores_from(index - 1, score_state)`` so
          that the inserted rally's score is re-derived from its predecessor's
          replay outcome, and all subsequent rallies are updated in turn.

        Note: the action stack is NOT updated by review-mode inserts.

        Args:
            index: Position at which to insert the rally (0-based).  Accepted
                values are ``0 .. len(rallies)`` inclusive.
            rally: The Rally object to insert.  Its score fields will be
                overwritten by the cascade when ``score_state`` is provided.
            score_state: Live ``ScoreState`` instance.  When provided, a full
                forward cascade is performed starting from the appropriate anchor.

        Returns:
            List of rally indices (> *index* − 1, i.e. from the inserted rally
            onward) whose winner string was re-derived from model predictions.
            May be empty.
        """
        self.rallies.insert(index, rally)
        changed: list[int] = []

        if score_state is None:
            return changed

        if index == 0:
            if len(self.rallies) > 1:
                # Copy the former first rally's (now at index 1) score data onto
                # the inserted rally so the cascade starts from the game-opening
                # score state.
                old_first = self.rallies[1]
                self.rallies[0].score_at_start = old_first.score_at_start
                self.rallies[0].score_snapshot_at_start = old_first.score_snapshot_at_start
            changed = self.cascade_scores_from(0, score_state)
        else:
            # Cascade from the predecessor; the inserted rally at *index* will
            # have its score re-derived as part of the forward replay.
            changed = self.cascade_scores_from(index - 1, score_state)

        return changed

    def can_undo(self) -> bool:
        """Check if there's an action to undo.

        Returns:
            True if the action stack is not empty
        """
        return len(self.action_stack) > 0

    def undo(self) -> tuple[Action, float]:
        """Undo the last action.

        Reverses the most recent action (either rally start or rally end) and
        returns information about what was undone and where to seek the video.

        For RALLY_END:
        - Removes the completed rally
        - Restores rally-in-progress state

        For RALLY_START:
        - Clears rally-in-progress state

        Returns:
            Tuple of (undone_action, seek_position) where seek_position
            is the video timestamp to seek to after undo

        Raises:
            ValueError: If there's nothing to undo
        """
        if not self.can_undo():
            raise ValueError("Nothing to undo")

        action = self.action_stack.pop()

        if action.action_type == ActionType.RALLY_END:
            # Remove the last rally
            rally_index = action.data.get("rally_index")
            if rally_index is not None and rally_index < len(self.rallies):
                self.rallies.pop(rally_index)

            # Restore rally-in-progress state
            # After undoing RALLY_END, we're back to "rally in progress"
            # Need to find the corresponding RALLY_START action
            if self.action_stack and self.action_stack[-1].action_type == ActionType.RALLY_START:
                start_action = self.action_stack[-1]
                self._current_rally_start = start_action.frame
                self._current_rally_timestamp = start_action.timestamp
                self._current_rally_start_snapshot = start_action.score_before
            else:
                self._current_rally_start_snapshot = None

            # Seek to where rally ended
            seek_position = action.timestamp

        elif action.action_type == ActionType.RALLY_START:
            # Clear rally-in-progress state
            self._current_rally_start = None
            self._current_rally_timestamp = None
            self._current_rally_start_snapshot = None

            # Seek to where rally started
            seek_position = action.timestamp

        else:
            # Other action types (score edits, side-outs, comments)
            # Currently not implemented, but provide seek position
            seek_position = action.timestamp

        return action, seek_position

    def to_segments(self) -> list[dict[str, Any]]:
        """Convert rallies to Kdenlive segment format.

        Generates a list of segment dictionaries suitable for Kdenlive XML
        generation. Each segment includes in/out points and score display.

        Returns:
            List of segment dictionaries with "in", "out", "score" keys
        """
        return [
            {
                "in": rally.start_frame,
                "out": rally.end_frame,
                "score": rally.score_at_start,
                "is_post_game": rally.is_post_game,
            }
            for rally in self.rallies
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage.

        Returns:
            Dictionary containing all rally manager state

        Note:
            action_stack is not serialized as it's only needed during active
            editing and can be reconstructed on load if needed.
        """
        return {
            "fps": self.fps,
            "rallies": [r.to_dict() for r in self.rallies],
            "current_rally_start": self._current_rally_start,
            "current_rally_timestamp": self._current_rally_timestamp,
            "current_rally_start_snapshot": (
                self._current_rally_start_snapshot.to_dict()
                if self._current_rally_start_snapshot is not None
                else None
            ),
            # Note: action_stack not serialized (rebuild on load if needed)
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RallyManager":
        """Create from dictionary.

        Reconstructs a RallyManager instance from serialized data. The action
        stack is not restored as it's only needed during active editing.

        Args:
            data: Dictionary containing rally manager state

        Returns:
            Reconstructed RallyManager instance
        """
        manager = cls(fps=data.get("fps", 60.0))
        manager.rallies = [Rally.from_dict(r) for r in data.get("rallies", [])]
        manager._current_rally_start = data.get("current_rally_start")
        manager._current_rally_timestamp = data.get("current_rally_timestamp")
        manager._current_rally_start_snapshot = None
        current_snapshot_data = data.get("current_rally_start_snapshot")
        if isinstance(current_snapshot_data, dict):
            manager._current_rally_start_snapshot = ScoreSnapshot.from_dict(
                current_snapshot_data
            )
        return manager

    def _time_to_frame(self, seconds: float) -> int:
        """Convert seconds to frame number.

        Args:
            seconds: Time in seconds

        Returns:
            Frame number (rounded down)
        """
        return int(seconds * self.fps)

    def _frame_to_time(self, frame: int) -> float:
        """Convert frame number to seconds.

        Args:
            frame: Frame number

        Returns:
            Time in seconds
        """
        return frame / self.fps

    def clear_all(self) -> None:
        """Clear all rallies and undo stack for starting a new game.

        Resets the rally manager to its initial state while preserving fps.
        """
        self.rallies.clear()
        self.action_stack.clear()
        self._current_rally_start = None
        self._current_rally_timestamp = None
        self._current_rally_start_snapshot = None
