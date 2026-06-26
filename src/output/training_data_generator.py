"""ML training data JSON generation for Pickleball Video Editor.

Generates a .training.json file containing labeled rally data suitable
for machine learning training. The JSON includes:
- Video metadata (path, fps, duration, resolution, optional court corners)
- Game metadata (type, teams, victory rules, completion)
- Rally labels with both raw (unpadded) and padded timestamps
- winning_team field (0 or 1) derived from each rally's recorded
  rally-start snapshot when available, with ScoreState replay fallback.

Raw timestamps represent the exact moments the user marked rally
start/end events. Padded timestamps include editorial padding
(-0.5s start, +1.0s end) used for the video cut points.

Schema 1.1 adds:
- winning_team per rally (0 or 1, or None for post-game/highlights)
- court_corners in the video block (4×[x,y] pixel coords, or None)
- generated_by in the top-level metadata
"""

import json
from pathlib import Path
from typing import Any

from src.core.models import Rally, GameCompletionInfo
from src.core.score_state import ScoreState


__all__ = ["TrainingDataGenerator"]


class TrainingDataGenerator:
    """Generates ML training data JSON from rally labels.

    Stateless utility class that produces structured JSON suitable for
    training ML models on pickleball rally detection and scoring.
    """

    SCHEMA_VERSION = "1.1"

    @staticmethod
    def generate(
        video_path: str,
        fps: float,
        duration_seconds: float,
        resolution: tuple[int, int],
        game_type: str,
        victory_rules: str,
        team1_players: list[str],
        team2_players: list[str],
        rallies: list[Rally],
        game_completion: GameCompletionInfo | None = None,
        court_corners: list[list[int]] | None = None,
        generated_by: str = "manual",
    ) -> dict[str, Any]:
        """Generate training data dictionary from rally labels.

        Args:
            video_path: Absolute path to source video file
            fps: Video frames per second
            duration_seconds: Video duration in seconds
            resolution: Video resolution as (width, height)
            game_type: "singles", "doubles", or "highlights"
            victory_rules: "11", "9", or "timed"
            team1_players: Player names for team 1
            team2_players: Player names for team 2
            rallies: List of Rally objects with labels
            game_completion: Optional game completion info
            court_corners: Optional 4×[x,y] pixel coords of court corners
                (Team1-baseline-left, Team1-baseline-right,
                 Team2-baseline-right, Team2-baseline-left)
            generated_by: Source of labels ("manual" or "ml")

        Returns:
            Complete training data dictionary ready for JSON serialization
        """
        # Build a ScoreState used for re-syncing rallies that do not carry
        # a rally-start snapshot.
        score_state: ScoreState | None = None
        if game_type in ("singles", "doubles"):
            score_state = ScoreState(
                game_type=game_type,
                victory_rules=victory_rules,
                player_names={
                    "team1": team1_players,
                    "team2": team2_players,
                },
            )

        rally_labels = []
        for i, rally in enumerate(rallies):
            # Determine winning_team for ML-labelled rallies only.
            # Post-game segments and highlights have no meaningful winning_team.
            winning_team: int | None = None
            if score_state is not None and not rally.is_post_game:
                start_snapshot = getattr(rally, "score_snapshot_at_start", None)
                if start_snapshot is not None:
                    # Prefer persisted rally-start snapshot when available.
                    score_state.restore_snapshot(start_snapshot)
                else:
                    # Fallback to historical behavior for older Rally objects / JSON
                    # exports that lacked rally-start snapshots.
                    score_state.set_score(rally.score_at_start)

                serving = score_state.serving_team

                if rally.winner == "server":
                    winning_team = serving
                    score_state.server_wins()
                else:
                    winning_team = 1 - serving
                    score_state.receiver_wins()

            label: dict[str, Any] = {
                "index": i,
                "score_at_start": rally.score_at_start,
                "winner": rally.winner,
                "winning_team": winning_team,
                "is_post_game": rally.is_post_game,
                "comment": rally.comment,
                "padded": {
                    "start_frame": rally.start_frame,
                    "end_frame": rally.end_frame,
                    "start_seconds": round(rally.start_frame / fps, 4),
                    "end_seconds": round(rally.end_frame / fps, 4),
                },
            }

            if rally.raw_start_seconds is not None:
                label["raw"] = {
                    "start_frame": rally.raw_start_frame,
                    "end_frame": rally.raw_end_frame,
                    "start_seconds": round(rally.raw_start_seconds, 4),
                    "end_seconds": round(rally.raw_end_seconds, 4),
                }
            else:
                label["raw"] = None

            # Human-labelled server (optional; ground truth for service-state vision).
            server_team = getattr(rally, "server_team", None)
            if server_team is not None:
                player_idx = getattr(rally, "server_player_index", None)
                roster = team1_players if server_team == 0 else team2_players
                player_name: str | None = None
                if player_idx is not None and 0 <= player_idx < len(roster):
                    player_name = roster[player_idx]
                server_block: dict[str, Any] = {
                    "team": server_team,
                    "player_index": player_idx,
                    "player_name": player_name,
                }
                pixel = getattr(rally, "server_pixel", None)
                if pixel is not None:
                    server_block["pixel"] = [int(pixel[0]), int(pixel[1])]
                label["server"] = server_block

            rally_labels.append(label)

        return {
            "schema_version": TrainingDataGenerator.SCHEMA_VERSION,
            "generated_by": generated_by,
            "video": {
                "path": video_path,
                "fps": fps,
                "duration_seconds": round(duration_seconds, 4),
                "width": resolution[0],
                "height": resolution[1],
                "court_corners": court_corners,
            },
            "game": {
                "type": game_type,
                "victory_rules": victory_rules,
                "team1_players": team1_players,
                "team2_players": team2_players,
                "completion": game_completion.to_dict() if game_completion else None,
            },
            "rallies": rally_labels,
            "rally_count": len(rally_labels),
        }

    @staticmethod
    def write(
        output_path: Path | str,
        video_path: str,
        fps: float,
        duration_seconds: float,
        resolution: tuple[int, int],
        game_type: str,
        victory_rules: str,
        team1_players: list[str],
        team2_players: list[str],
        rallies: list[Rally],
        game_completion: GameCompletionInfo | None = None,
        court_corners: list[list[int]] | None = None,
        generated_by: str = "manual",
    ) -> Path:
        """Generate training data and write to JSON file.

        Args:
            output_path: Path to write the .training.json file
            video_path: Absolute path to source video file
            fps: Video frames per second
            duration_seconds: Video duration in seconds
            resolution: Video resolution as (width, height)
            game_type: "singles", "doubles", or "highlights"
            victory_rules: "11", "9", or "timed"
            team1_players: Player names for team 1
            team2_players: Player names for team 2
            rallies: List of Rally objects with labels
            game_completion: Optional game completion info
            court_corners: Optional 4×[x,y] pixel coords of court corners
            generated_by: Source of labels ("manual" or "ml")

        Returns:
            Path to the written file
        """
        output_path = Path(output_path)

        training_data = TrainingDataGenerator.generate(
            video_path=video_path,
            fps=fps,
            duration_seconds=duration_seconds,
            resolution=resolution,
            game_type=game_type,
            victory_rules=victory_rules,
            team1_players=team1_players,
            team2_players=team2_players,
            rallies=rallies,
            game_completion=game_completion,
            court_corners=court_corners,
            generated_by=generated_by,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(training_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return output_path
