"""Rally tracking with undo support for Pickleball Video Editor.

This module manages rally marking during video editing with:
- Start/end rally marking with automatic padding
- Undo functionality with action stack
- Rally timing adjustments for Final Review mode
- Kdenlive segment export format
- JSON serialization for session persistence

Rally Padding:
- Start: -0.5 seconds (to capture serve preparation)
- End: +1.0 seconds (to capture ball settling)

Undo Support:
- RALLY_START: Clears current rally-in-progress state
- RALLY_END: Removes completed rally and restores rally-in-progress state
"""

from dataclasses import dataclass, field
from typing import Any

from src.core.models import Rally, Action, ActionType, ScoreSnapshot


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
    START_PADDING = -0.5  # Add padding before rally start
    END_PADDING = 1.0     # Add padding after rally end

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

        # Create rally
        rally = Rally(
            start_frame=self._current_rally_start,
            end_frame=end_frame,
            score_at_start=score_at_start,
            winner=winner,
            comment=comment
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

    def update_rally_score(
        self,
        index: int,
        new_score: str,
        cascade: bool = False
    ) -> None:
        """Update a rally's score (for Final Review mode).

        Changes the score_at_start for a specific rally. Optionally cascades
        the change to recalculate all subsequent rally scores.

        Args:
            index: Rally index to update
            new_score: New score string (e.g., "5-3" or "7-4-1")
            cascade: If True, recalculate subsequent rally scores

        Raises:
            IndexError: If index is out of range

        Note:
            Cascade functionality requires integration with ScoreState and is
            left as a future enhancement.
        """
        self.rallies[index].score_at_start = new_score

        if cascade:
            # TODO: Implement cascade score recalculation
            # This requires:
            # 1. Parse new_score to ScoreState
            # 2. Replay all subsequent rallies with their winners
            # 3. Update each rally's score_at_start
            # This needs access to ScoreState instance
            pass

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

            # Seek to where rally ended
            seek_position = action.timestamp

        elif action.action_type == ActionType.RALLY_START:
            # Clear rally-in-progress state
            self._current_rally_start = None
            self._current_rally_timestamp = None

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
                "score": rally.score_at_start
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
