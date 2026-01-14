"""Core data models for Pickleball Video Editor.

This module defines all dataclasses and enums for representing:
- Rally timestamps and outcomes
- Score snapshots for undo functionality
- Actions for the undo stack
- Comments and interventions
- Complete session state for persistence

All dataclasses implement to_dict/from_dict for JSON serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


__all__ = [
    "ActionType",
    "Rally",
    "ScoreSnapshot",
    "ServerInfo",
    "Action",
    "Comment",
    "Intervention",
    "SessionState",
]


class ActionType(Enum):
    """Types of user actions that can be recorded and undone."""

    RALLY_START = "rally_start"
    RALLY_END = "rally_end"
    SCORE_EDIT = "score_edit"
    SIDE_OUT = "side_out"
    COMMENT = "comment"


@dataclass
class Rally:
    """Represents a single rally with start/end frames and score information.

    Attributes:
        start_frame: Frame number where rally begins
        end_frame: Frame number where rally ends
        score_at_start: Score string at rally start ("0-0" singles, "0-0-2" doubles)
        winner: Who won the rally ("server" or "receiver")
        comment: Optional comment about this rally
    """

    start_frame: int
    end_frame: int
    score_at_start: str
    winner: str
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing all rally data
        """
        return {
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "score_at_start": self.score_at_start,
            "winner": self.winner,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rally":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing rally data

        Returns:
            Rally instance
        """
        return cls(
            start_frame=data["start_frame"],
            end_frame=data["end_frame"],
            score_at_start=data["score_at_start"],
            winner=data["winner"],
            comment=data.get("comment"),
        )


@dataclass(frozen=True)
class ScoreSnapshot:
    """Immutable snapshot of score state for undo functionality.

    This class is frozen to ensure snapshots cannot be accidentally modified,
    preserving the integrity of the undo stack.

    Attributes:
        score: Score array ([team1, team2] or [team1, team2, server_num])
        serving_team: Index of serving team (0 or 1)
        server_number: Server number for doubles (1 or 2), None for singles
    """

    score: tuple[int, ...]  # Using tuple for immutability
    serving_team: int
    server_number: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing score snapshot data
        """
        return {
            "score": list(self.score),  # Convert tuple back to list for JSON
            "serving_team": self.serving_team,
            "server_number": self.server_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreSnapshot":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing score snapshot data

        Returns:
            ScoreSnapshot instance
        """
        return cls(
            score=tuple(data["score"]),  # Convert list to tuple for immutability
            serving_team=data["serving_team"],
            server_number=data.get("server_number"),
        )


@dataclass
class ServerInfo:
    """Information about the current server for UI display.

    Attributes:
        serving_team: Index of serving team (0 or 1)
        server_number: Server number for doubles (1 or 2), None for singles
        player_name: Name of the current server
    """

    serving_team: int
    server_number: int | None
    player_name: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing server info data
        """
        return {
            "serving_team": self.serving_team,
            "server_number": self.server_number,
            "player_name": self.player_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerInfo":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing server info data

        Returns:
            ServerInfo instance
        """
        return cls(
            serving_team=data["serving_team"],
            server_number=data.get("server_number"),
            player_name=data["player_name"],
        )


@dataclass
class Action:
    """Represents a user action for the undo stack.

    Attributes:
        action_type: Type of action performed
        timestamp: Video timestamp in seconds when action occurred
        frame: Frame number when action occurred
        score_before: Score state before this action
        data: Action-specific data (rally info, edit details, etc.)
    """

    action_type: ActionType
    timestamp: float
    frame: int
    score_before: ScoreSnapshot
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing action data
        """
        return {
            "action_type": self.action_type.value,
            "timestamp": self.timestamp,
            "frame": self.frame,
            "score_before": self.score_before.to_dict(),
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing action data

        Returns:
            Action instance
        """
        return cls(
            action_type=ActionType(data["action_type"]),
            timestamp=data["timestamp"],
            frame=data["frame"],
            score_before=ScoreSnapshot.from_dict(data["score_before"]),
            data=data["data"],
        )


@dataclass
class Comment:
    """User comment attached to a specific video timestamp.

    Attributes:
        timestamp: Video timestamp in seconds
        frame: Frame number where comment applies
        text: Comment content
        duration: How long to display comment in seconds (default: 5.0)
    """

    timestamp: float
    frame: int
    text: str
    duration: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing comment data
        """
        return {
            "timestamp": self.timestamp,
            "frame": self.frame,
            "text": self.text,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Comment":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing comment data

        Returns:
            Comment instance
        """
        return cls(
            timestamp=data["timestamp"],
            frame=data["frame"],
            text=data["text"],
            duration=data.get("duration", 5.0),
        )


@dataclass
class Intervention:
    """Manual edit/intervention logged for debugging and review.

    Attributes:
        intervention_type: Type of intervention ("score_edit", "side_out", etc.)
        timestamp: Video timestamp when intervention occurred
        old_value: Previous value before intervention
        new_value: New value after intervention
        comment: Optional explanation for the intervention
    """

    intervention_type: str
    timestamp: float
    old_value: str
    new_value: str
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing intervention data
        """
        return {
            "intervention_type": self.intervention_type,
            "timestamp": self.timestamp,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Intervention":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing intervention data

        Returns:
            Intervention instance
        """
        return cls(
            intervention_type=data["intervention_type"],
            timestamp=data["timestamp"],
            old_value=data["old_value"],
            new_value=data["new_value"],
            comment=data.get("comment"),
        )


@dataclass
class SessionState:
    """Complete session state for persistence to JSON.

    This matches the JSON schema defined in TECH_STACK.md Section 5.1.

    Attributes:
        version: Session format version (default: "1.0")
        video_path: Absolute path to video file
        video_hash: SHA256 hash for video integrity verification
        game_type: Type of game ("singles" or "doubles")
        victory_rules: Victory condition ("11", "9", or "timed")
        player_names: Player names per team ({"team1": [...], "team2": [...]})
        rallies: List of all rallies in the session
        current_score: Current score state ([team1, team2] or [team1, team2, server])
        serving_team: Index of currently serving team (0 or 1)
        server_number: Current server number for doubles (1 or 2), None for singles
        last_position: Last video position in seconds
        created_at: ISO timestamp when session was created
        modified_at: ISO timestamp when session was last modified
        interventions: List of manual interventions/edits
        comments: List of user comments
    """

    version: str = "1.0"
    video_path: str = ""
    video_hash: str = ""
    game_type: str = ""
    victory_rules: str = ""
    player_names: dict[str, list[str]] = field(default_factory=dict)
    rallies: list[Rally] = field(default_factory=list)
    current_score: list[int] = field(default_factory=list)
    serving_team: int = 0
    server_number: int | None = None
    last_position: float = 0.0
    created_at: str = ""
    modified_at: str = ""
    interventions: list[Intervention] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export.

        Returns:
            Dictionary containing complete session state
        """
        return {
            "version": self.version,
            "video_path": self.video_path,
            "video_hash": self.video_hash,
            "game_type": self.game_type,
            "victory_rules": self.victory_rules,
            "player_names": self.player_names,
            "rallies": [rally.to_dict() for rally in self.rallies],
            "current_score": self.current_score,
            "serving_team": self.serving_team,
            "server_number": self.server_number,
            "last_position": self.last_position,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "interventions": [intervention.to_dict() for intervention in self.interventions],
            "comments": [comment.to_dict() for comment in self.comments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """Deserialize from dictionary.

        Args:
            data: Dictionary containing session state data

        Returns:
            SessionState instance
        """
        return cls(
            version=data.get("version", "1.0"),
            video_path=data.get("video_path", ""),
            video_hash=data.get("video_hash", ""),
            game_type=data.get("game_type", ""),
            victory_rules=data.get("victory_rules", ""),
            player_names=data.get("player_names", {}),
            rallies=[Rally.from_dict(r) for r in data.get("rallies", [])],
            current_score=data.get("current_score", []),
            serving_team=data.get("serving_team", 0),
            server_number=data.get("server_number"),
            last_position=data.get("last_position", 0.0),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
            interventions=[Intervention.from_dict(i) for i in data.get("interventions", [])],
            comments=[Comment.from_dict(c) for c in data.get("comments", [])],
        )

    def update_modified_timestamp(self) -> None:
        """Update the modified_at timestamp to current time."""
        self.modified_at = datetime.now().isoformat()
