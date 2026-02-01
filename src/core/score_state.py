"""Pickleball score state machine.

This module implements the complete pickleball scoring rules for both singles
and doubles games, including:
- Server/receiver win logic
- Side-out mechanics (singles and doubles)
- Server rotation (doubles only)
- Win conditions (standard and timed games)
- Score interventions and manual overrides
- Undo functionality via snapshots

All score calculations follow official pickleball rules as documented in PRD.md.
"""

from typing import Any

from .models import ScoreSnapshot, ServerInfo


__all__ = [
    "ScoreState",
]


class ScoreState:
    """Manages pickleball scoring rules for singles and doubles.

    This class encapsulates all scoring logic and state transitions according
    to official pickleball rules. It maintains the current score, serving team,
    and server number (for doubles), and handles all rally outcomes.

    Attributes:
        game_type: Type of game ("singles" or "doubles")
        victory_rules: Win condition ("11", "9", or "timed")
        player_names: Player names per team {"team1": [...], "team2": [...]}
        score: Current score [team1_score, team2_score]
        serving_team: Index of serving team (0 or 1)
        server_number: Server number for doubles (1 or 2), None for singles
    """

    def __init__(
        self,
        game_type: str,
        victory_rules: str,
        player_names: dict[str, list[str]]
    ) -> None:
        """Initialize score state.

        Args:
            game_type: "singles" or "doubles"
            victory_rules: "11", "9", or "timed"
            player_names: {"team1": ["Player1"], "team2": ["Player2"]} for singles
                         {"team1": ["P1", "P2"], "team2": ["P3", "P4"]} for doubles

        Raises:
            ValueError: If game_type is not "singles" or "doubles"
            ValueError: If victory_rules is not "11", "9", or "timed"
        """
        if game_type not in ("singles", "doubles"):
            raise ValueError(f"Invalid game_type: {game_type}")
        if victory_rules not in ("11", "9", "timed"):
            raise ValueError(f"Invalid victory_rules: {victory_rules}")

        self.game_type = game_type
        self.victory_rules = victory_rules
        self.player_names = player_names

        # Initialize scores
        self.score = [0, 0]  # [team1_score, team2_score]
        self.serving_team = 0  # Team 0 serves first

        if game_type == "singles":
            self.server_number = None
            self.first_server_player_index = None
        else:  # doubles
            # Doubles starts with server 2 (one fault causes immediate side-out)
            self.server_number = 2
            # At game start (0-0-2), the server is player[0] (on right at even score).
            # Since we use Server 2 = 1 - first_server, we set first_server = 1
            # so that Server 2 = 1 - 1 = 0 = player[0]
            self.first_server_player_index = 1

    def server_wins(self) -> None:
        """Handle server winning the rally.

        When the server wins:
        - Serving team's score increases by 1
        - Server continues serving (same team, same server number)
        - No side-out occurs

        This method works identically for both singles and doubles.
        """
        # Server's team scores a point
        self.score[self.serving_team] += 1
        # Server continues serving (no changes to serving_team or server_number)

    def receiver_wins(self) -> None:
        """Handle receiver winning the rally.

        Singles:
            - Side-out occurs: receiver becomes the new server
            - Scores remain unchanged
            - Serving team switches

        Doubles:
            - If server 1 loses: Switch to server 2 (same team)
            - If server 2 loses: Side-out to other team's server 1
            - Exception: At 0-0-2 (game start), first fault causes immediate side-out
        """
        if self.game_type == "singles":
            self._handle_singles_receiver_wins()
        else:  # doubles
            self._handle_doubles_receiver_wins()

    def is_game_over(self) -> tuple[bool, int | None]:
        """Check if game is over according to victory rules.

        Standard games (11 or 9):
            - Winner must reach target score
            - Winner must win by at least 2 points

        Timed games:
            - No automatic game-over detection
            - User must manually trigger via "Time Expired" button
            - This method always returns False for timed games during normal play

        Returns:
            Tuple of (is_over, winner_team) where:
                - is_over: True if game has ended
                - winner_team: 0 for team1, 1 for team2, None if not over
        """
        if self.victory_rules == "timed":
            # Timed games don't auto-detect game over
            # User manually triggers end via UI
            return False, None

        # Standard game (11 or 9)
        target_score = int(self.victory_rules)

        # Check if either team has reached target score
        if self.score[0] >= target_score or self.score[1] >= target_score:
            # Check win-by-2 requirement
            score_diff = abs(self.score[0] - self.score[1])
            if score_diff >= 2:
                # Determine winner
                winner = 0 if self.score[0] > self.score[1] else 1
                return True, winner

        return False, None

    def get_score_string(self) -> str:
        """Get formatted score string from serving team's perspective.

        Singles:
            Returns "X-Y" where X is server's score, Y is receiver's score

        Doubles:
            Returns "X-Y-Z" where:
                - X is serving team's score
                - Y is receiving team's score
                - Z is server number (1 or 2)

        Returns:
            Score string formatted according to game type
        """
        if self.game_type == "singles":
            # Singles: server's score first, receiver's score second
            server_score = self.score[self.serving_team]
            receiver_team = 1 - self.serving_team
            receiver_score = self.score[receiver_team]
            return f"{server_score}-{receiver_score}"
        else:  # doubles
            # Doubles: serving team's score, receiving team's score, server number
            serving_score = self.score[self.serving_team]
            receiving_team = 1 - self.serving_team
            receiving_score = self.score[receiving_team]
            return f"{serving_score}-{receiving_score}-{self.server_number}"

    def get_server_info(self) -> ServerInfo:
        """Get current server information for UI display.

        In doubles, first_server_player_index tracks which player was designated
        as Server 1 when the possession started. This is fixed for the entire
        possession and only recalculated on side-out.

        Returns:
            ServerInfo containing:
                - serving_team: Index of serving team (0 or 1)
                - server_number: Server number for doubles (1 or 2), None for singles
                - player_name: Name of the current server
        """
        # Get the serving team's player names
        team_key = f"team{self.serving_team + 1}"
        team_players = self.player_names.get(team_key, [])

        if self.game_type == "singles":
            # Singles: only one player per team
            player_name = team_players[0] if team_players else "Unknown"
        else:  # doubles
            # Server 1 = first_server_player_index (set at side-out)
            # Server 2 = the other player (1 - first_server_player_index)
            if self.server_number == 1:
                player_index = self.first_server_player_index or 0
            else:  # server_number == 2
                player_index = 1 - (self.first_server_player_index or 0)

            player_name = team_players[player_index] if len(team_players) > player_index else "Unknown"

        return ServerInfo(
            serving_team=self.serving_team,
            server_number=self.server_number,
            player_name=player_name
        )

    def set_score(self, score_string: str) -> None:
        """Manually set the score (for Edit Score intervention).

        This method parses a score string and updates the internal state.
        Used when the user manually corrects an incorrect score.

        For doubles, this also recalculates first_server_player_index based
        on the serving team's new score, treating it as a new possession start.

        Args:
            score_string: "X-Y" for singles, "X-Y-Z" for doubles (from serving team's perspective)

        Raises:
            ValueError: If score_string format is invalid
        """
        parts = score_string.split("-")

        if self.game_type == "singles":
            if len(parts) != 2:
                raise ValueError(f"Singles score must be X-Y format, got: {score_string}")
            try:
                server_score = int(parts[0])
                receiver_score = int(parts[1])
            except ValueError:
                raise ValueError(f"Invalid score values in: {score_string}")

            # Update scores from serving team's perspective
            self.score[self.serving_team] = server_score
            receiver_team = 1 - self.serving_team
            self.score[receiver_team] = receiver_score

        else:  # doubles
            if len(parts) != 3:
                raise ValueError(f"Doubles score must be X-Y-Z format, got: {score_string}")
            try:
                serving_score = int(parts[0])
                receiving_score = int(parts[1])
                server_num = int(parts[2])
            except ValueError:
                raise ValueError(f"Invalid score values in: {score_string}")

            if server_num not in (1, 2):
                raise ValueError(f"Server number must be 1 or 2, got: {server_num}")

            # Update scores and server number
            self.score[self.serving_team] = serving_score
            receiving_team = 1 - self.serving_team
            self.score[receiving_team] = receiving_score
            self.server_number = server_num
            # Recalculate first_server based on serving team's new score
            self.first_server_player_index = 0 if serving_score % 2 == 0 else 1

    def force_side_out(self) -> None:
        """Force a side-out without scoring (for intervention).

        This method switches the serve to the other team without changing the score.
        Used when the user needs to manually correct serving errors.

        Singles:
            - Switch serving team

        Doubles:
            - Switch to other team's server 1
            - Recalculate first_server_player_index based on new serving team's score
        """
        # Switch serving team
        self.serving_team = 1 - self.serving_team

        # For doubles, reset to server 1 and recalculate first_server
        if self.game_type == "doubles":
            self.server_number = 1
            new_serving_score = self.score[self.serving_team]
            self.first_server_player_index = 0 if new_serving_score % 2 == 0 else 1

    def save_snapshot(self) -> ScoreSnapshot:
        """Save current state for undo functionality.

        Creates an immutable snapshot of the current score state that can be
        restored later via restore_snapshot().

        Returns:
            ScoreSnapshot containing current score, serving team, server number,
            and first_server_player_index
        """
        return ScoreSnapshot(
            score=tuple(self.score),  # Convert to tuple for immutability
            serving_team=self.serving_team,
            server_number=self.server_number,
            first_server_player_index=self.first_server_player_index
        )

    def restore_snapshot(self, snapshot: ScoreSnapshot) -> None:
        """Restore state from snapshot.

        Restores the score state to a previous snapshot, typically for undo operations.

        Args:
            snapshot: ScoreSnapshot to restore from
        """
        self.score = list(snapshot.score)  # Convert tuple back to list
        self.serving_team = snapshot.serving_team
        self.server_number = snapshot.server_number
        self.first_server_player_index = snapshot.first_server_player_index

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage.

        Returns:
            Dictionary containing all score state data
        """
        return {
            "game_type": self.game_type,
            "victory_rules": self.victory_rules,
            "player_names": self.player_names,
            "score": self.score,
            "serving_team": self.serving_team,
            "server_number": self.server_number,
            "first_server_player_index": self.first_server_player_index
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreState":
        """Create from dictionary.

        Args:
            data: Dictionary containing score state data

        Returns:
            ScoreState instance
        """
        instance = cls(
            game_type=data["game_type"],
            victory_rules=data["victory_rules"],
            player_names=data["player_names"]
        )
        instance.score = data["score"]
        instance.serving_team = data["serving_team"]
        instance.server_number = data.get("server_number")
        instance.first_server_player_index = data.get("first_server_player_index")
        return instance

    # Private helper methods

    def _handle_singles_receiver_wins(self) -> None:
        """Handle receiver winning in singles game.

        Singles side-out rules:
        - Receiver becomes the server
        - Scores remain unchanged
        - Serve switches to the other team
        """
        # Simple side-out: switch serving team
        self.serving_team = 1 - self.serving_team

    def _handle_doubles_receiver_wins(self) -> None:
        """Handle receiver winning in doubles game.

        Doubles side-out rules:
        - If server 1 loses: Switch to server 2 (same team)
        - If server 2 loses: Side-out to other team's server 1
        - Special case: At 0-0-2 (game start), first fault causes immediate side-out

        On side-out, first_server_player_index is recalculated based on the new
        serving team's score at the moment of side-out.
        """
        # Special case: Game start at 0-0-2
        # First fault causes immediate side-out (no server 2 attempt)
        if self.score == [0, 0] and self.server_number == 2:
            # Side-out to other team's server 1
            self.serving_team = 1 - self.serving_team
            self.server_number = 1
            # Calculate first_server for new serving team based on their score
            new_serving_score = self.score[self.serving_team]
            self.first_server_player_index = 0 if new_serving_score % 2 == 0 else 1
            return

        # Normal doubles rotation
        if self.server_number == 1:
            # Server 1 loses: switch to server 2 (same team)
            self.server_number = 2
        else:  # server_number == 2
            # Server 2 loses: side-out to other team's server 1
            self.serving_team = 1 - self.serving_team
            self.server_number = 1
            # Calculate first_server for new serving team based on their score
            new_serving_score = self.score[self.serving_team]
            self.first_server_player_index = 0 if new_serving_score % 2 == 0 else 1
