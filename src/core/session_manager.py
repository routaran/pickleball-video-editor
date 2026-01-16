"""Session persistence manager for Pickleball Video Editor.

This module handles saving and loading session state to/from JSON files.
Sessions are identified by a SHA256 hash of the first 64KB of the video file,
allowing fast detection of existing sessions without requiring full file hashing.

Session files are stored in: ~/.local/share/pickleball-editor/sessions/
Filename format: {video_hash}.json

Typical usage:
    manager = SessionManager()

    # Check if session exists
    if manager.find_existing(video_path):
        state = manager.load(video_path)
    else:
        # Create new session
        state = SessionState(...)

    # Save session
    manager.save(state, video_path)
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import SessionState

__all__ = ["SessionManager"]


class SessionManager:
    """Manages session persistence for the Pickleball Video Editor.

    Handles saving and loading session state to/from JSON files in the
    user's local data directory. Sessions are identified by a hash of
    the video file to enable automatic session detection and resumption.

    Attributes:
        session_dir: Path to the directory containing session files
    """

    def __init__(self, session_dir: Path | None = None) -> None:
        """Initialize the SessionManager.

        Args:
            session_dir: Optional custom session directory path.
                        If None, uses ~/.local/share/pickleball-editor/sessions/
        """
        if session_dir is None:
            self.session_dir = Path.home() / ".local" / "share" / "pickleball-editor" / "sessions"
        else:
            self.session_dir = session_dir

        # Create session directory if it doesn't exist (LBYL)
        if not self.session_dir.exists():
            self.session_dir.mkdir(parents=True, exist_ok=True)

    def _get_video_hash(self, video_path: str) -> str:
        """Generate SHA256 hash of the first 64KB of a video file.

        This provides fast hashing for session identification without needing
        to hash the entire video file. 64KB is sufficient to uniquely identify
        video files in practice.

        Args:
            video_path: Path to the video file

        Returns:
            Hexadecimal SHA256 hash string (lowercase)
            Returns empty string if file doesn't exist or can't be read
        """
        path = Path(video_path)

        # Check if file exists before attempting to read (LBYL)
        if not path.exists():
            return ""

        if not path.is_file():
            return ""

        # Hash first 64KB
        hash_obj = hashlib.sha256()
        chunk_size = 64 * 1024  # 64KB

        with path.open("rb") as f:
            chunk = f.read(chunk_size)
            if not chunk:
                return ""
            hash_obj.update(chunk)

        return hash_obj.hexdigest()

    def get_video_hash(self, video_path: str) -> str:
        """Get SHA256 hash of video file for session identification.

        Public wrapper for hash generation, used for validating video files
        match existing sessions (e.g., when re-linking missing videos).

        Args:
            video_path: Path to the video file

        Returns:
            Hexadecimal SHA256 hash string (lowercase)
            Returns empty string if file doesn't exist or can't be read
        """
        return self._get_video_hash(video_path)

    def _get_session_path(self, video_path: str) -> Path | None:
        """Get the session file path for a given video.

        Args:
            video_path: Path to the video file

        Returns:
            Path to the session file, or None if video hash cannot be generated
        """
        video_hash = self._get_video_hash(video_path)
        if not video_hash:
            return None

        return self.session_dir / f"{video_hash}.json"

    def save(self, state: SessionState, video_path: str) -> Path | None:
        """Save session state to JSON file.

        Updates the session's video_hash and modified_at timestamp before saving.

        Args:
            state: Session state to save
            video_path: Path to the video file (used for generating hash)

        Returns:
            Path to the saved session file, or None if save failed
        """
        session_path = self._get_session_path(video_path)
        if session_path is None:
            return None

        # Update video hash and modified timestamp
        state.video_hash = self._get_video_hash(video_path)
        state.modified_at = datetime.now().isoformat()

        # Set created_at if this is a new session
        if not state.created_at:
            state.created_at = state.modified_at

        # Serialize to JSON
        data = state.to_dict()

        # Write to file
        session_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        return session_path

    def load(self, video_path: str) -> SessionState | None:
        """Load existing session for a video file.

        Args:
            video_path: Path to the video file

        Returns:
            Loaded SessionState, or None if session doesn't exist or can't be loaded
        """
        session_path = self._get_session_path(video_path)
        if session_path is None:
            return None

        # Check if session file exists (LBYL)
        if not session_path.exists():
            return None

        # Read and parse JSON
        content = session_path.read_text(encoding="utf-8")
        if not content:
            return None

        data = json.loads(content)
        if not data:
            return None

        # Deserialize from dictionary
        return SessionState.from_dict(data)

    def find_existing(self, video_path: str) -> Path | None:
        """Check if a session exists for a video file.

        Args:
            video_path: Path to the video file

        Returns:
            Path to the session file if it exists, None otherwise
        """
        session_path = self._get_session_path(video_path)
        if session_path is None:
            return None

        if session_path.exists():
            return session_path

        return None

    def delete(self, video_path: str) -> bool:
        """Delete the session file for a video.

        Args:
            video_path: Path to the video file

        Returns:
            True if session was deleted, False if it didn't exist or deletion failed
        """
        session_path = self._get_session_path(video_path)
        if session_path is None:
            return False

        # Check if session exists before attempting to delete (LBYL)
        if not session_path.exists():
            return False

        session_path.unlink()
        return True

    def get_session_info(self, video_path: str) -> dict[str, Any] | None:
        """Get summary information about a session.

        Useful for displaying session info in dialogs (e.g., "Resume Session" dialog).

        Args:
            video_path: Path to the video file

        Returns:
            Dictionary containing session summary, or None if session doesn't exist
            Dictionary keys:
                - rally_count: Number of rallies in session
                - current_score: Current score string
                - last_position: Last video position in seconds
                - last_modified: ISO timestamp of last modification
                - game_type: "singles" or "doubles"
                - victory_rules: Victory condition ("11", "9", or "timed")
                - video_path: Path to video file
        """
        state = self.load(video_path)
        if state is None:
            return None

        # Build score string
        if state.game_type == "doubles" and state.server_number is not None:
            score_str = f"{state.current_score[0]}-{state.current_score[1]}-{state.server_number}"
        elif len(state.current_score) >= 2:
            score_str = f"{state.current_score[0]}-{state.current_score[1]}"
        else:
            score_str = "0-0"

        return {
            "rally_count": len(state.rallies),
            "current_score": score_str,
            "last_position": state.last_position,
            "last_modified": state.modified_at,
            "game_type": state.game_type,
            "victory_rules": state.victory_rules,
            "video_path": state.video_path,
        }

    def list_all_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List all session files with metadata.

        Scans the session directory for .json files, extracts metadata from each,
        and returns a sorted list of session summaries. Useful for displaying
        available sessions in a "Resume Session" or session management dialog.

        Args:
            limit: Maximum number of sessions to return (most recent first)

        Returns:
            List of dictionaries containing session metadata, sorted by last_modified
            (most recent first). Each dictionary contains:
                - session_path: Path to the session JSON file
                - session_hash: Video hash extracted from filename
                - video_path: Path to video file (empty string if not set)
                - video_name: Filename of video (empty string if path invalid)
                - rally_count: Number of rallies in session
                - current_score: Current score string (e.g., "5-3" or "7-4-2")
                - last_modified: ISO timestamp of last modification
                - game_type: "singles" or "doubles"
                - video_exists: True if video file exists at video_path

            Empty list if session directory doesn't exist or has no valid sessions.
        """
        # Check if session directory exists (LBYL)
        if not self.session_dir.exists():
            return []

        sessions: list[dict[str, Any]] = []

        # Iterate through all JSON files in session directory
        for session_path in self.session_dir.glob("*.json"):
            # Extract hash from filename (without .json extension)
            session_hash = session_path.stem

            # Try to parse the session file
            try:
                content = session_path.read_text(encoding="utf-8")
                if not content:
                    continue

                data = json.loads(content)
                if not data:
                    continue

                # Extract video path with guard against missing/empty value
                video_path_str = data.get("video_path", "")
                if not video_path_str:
                    video_path_str = ""

                # Check if video file exists (LBYL)
                video_exists = False
                video_name = ""
                if video_path_str:
                    video_path_obj = Path(video_path_str)
                    if video_path_obj.exists():
                        video_exists = True
                        video_name = video_path_obj.name
                    else:
                        video_name = video_path_obj.name

                # Extract rally count
                rallies = data.get("rallies", [])
                rally_count = len(rallies) if isinstance(rallies, list) else 0

                # Build score string (same logic as get_session_info)
                current_score = data.get("current_score", [0, 0])
                game_type = data.get("game_type", "singles")
                server_number = data.get("server_number")

                if game_type == "doubles" and server_number is not None:
                    score_str = f"{current_score[0]}-{current_score[1]}-{server_number}"
                elif len(current_score) >= 2:
                    score_str = f"{current_score[0]}-{current_score[1]}"
                else:
                    score_str = "0-0"

                # Extract last modified timestamp
                last_modified = data.get("modified_at", "")

                # Add to sessions list
                sessions.append({
                    "session_path": session_path,
                    "session_hash": session_hash,
                    "video_path": video_path_str,
                    "video_name": video_name,
                    "rally_count": rally_count,
                    "current_score": score_str,
                    "last_modified": last_modified,
                    "game_type": game_type,
                    "video_exists": video_exists,
                })

            except (json.JSONDecodeError, OSError):
                # Skip corrupt or unreadable files
                continue

        # Sort by last_modified descending (most recent first)
        sessions.sort(key=lambda s: s["last_modified"], reverse=True)

        # Limit to requested number of sessions
        if limit > 0:
            sessions = sessions[:limit]

        return sessions

    def load_from_session_file(self, session_path: Path) -> SessionState | None:
        """Load session directly from a session file path.

        This method bypasses the video hash lookup and loads a session directly
        from its file path. Useful when the video file is missing or has been
        moved, but the user still wants to view or re-link the session.

        Args:
            session_path: Path to the session JSON file

        Returns:
            Loaded SessionState, or None if file doesn't exist or can't be loaded
        """
        # Check if session file exists (LBYL)
        if not session_path.exists():
            return None

        if not session_path.is_file():
            return None

        # Try to read and parse JSON
        try:
            content = session_path.read_text(encoding="utf-8")
            if not content:
                return None

            data = json.loads(content)
            if not data:
                return None

            # Deserialize from dictionary
            return SessionState.from_dict(data)

        except (json.JSONDecodeError, OSError):
            # Return None if file is corrupt or unreadable
            return None

    def delete_session_file(self, session_path: Path) -> bool:
        """Delete a session file directly by path.

        This method deletes a session file by its path rather than by video file.
        Useful for cleaning up sessions when the video file is missing or when
        managing sessions directly from a session list.

        Args:
            session_path: Path to the session JSON file to delete

        Returns:
            True if session was deleted, False if it didn't exist or deletion failed
        """
        # Check if session exists before attempting to delete (LBYL)
        if not session_path.exists():
            return False

        if not session_path.is_file():
            return False

        # Try to delete the file
        try:
            session_path.unlink()
            return True
        except OSError:
            # Return False if deletion failed
            return False
