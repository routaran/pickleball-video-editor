"""CLI tool to retroactively add winning_team labels to existing .training.json files.

Usage:
    python -m ml.tools.backfill_winner_labels
    python -m ml.tools.backfill_winner_labels --root ~/Videos/pickleball/

For each .training.json that is missing winning_team on its scored rallies, the tool:
1. Re-syncs ScoreState from the recorded score_at_start per rally (absorbs any
   lost Edit Score / Force Side-Out interventions whose history was not persisted).
2. Derives winning_team (0 = team1, 1 = team2) from the serving_team at the start
   of each rally combined with the rally's winner field.
3. Sets winning_team = null for post-game rallies (no score change, no team attribution).
4. Writes the result back to the same file and bumps schema_version to "1.1".

Files where every non-post-game rally already carries winning_team are skipped.
"""

import argparse
import enum
import json
import sys
from pathlib import Path

from src.core.score_state import ScoreState


__all__ = ["main"]


class _Result(enum.Enum):
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


def _already_labeled(data: dict) -> bool:
    """Return True if the file already has winning_team on all scored rallies.

    A file is considered already labeled when:
    - schema_version is "1.1", AND
    - every non-post-game rally has a "winning_team" key present.

    Both conditions must hold to be certain the file is complete.  If there are
    no non-post-game rallies at all, the file is trivially complete.

    Args:
        data: Parsed JSON dictionary from a .training.json file.

    Returns:
        True if no backfill work is needed for this file.
    """
    if data.get("schema_version") != "1.1":
        return False

    scored_rallies = [r for r in data.get("rallies", []) if not r.get("is_post_game")]
    if not scored_rallies:
        return True

    return all("winning_team" in r for r in scored_rallies)


def _backfill_game(game_section: dict, rallies: list[dict]) -> str | None:
    """Compute and assign winning_team for each rally in a single game.

    Re-syncs ScoreState from score_at_start on every rally, which absorbs the
    effects of any Edit Score or Force Side-Out interventions whose action
    history was not persisted in the JSON.

    Post-game rallies (is_post_game == true) receive winning_team = null because
    they represent footage captured after the game ended, not scored play.

    Args:
        game_section: The "game" dict from the training JSON.
        rallies: The "rallies" list from the training JSON (mutated in place).

    Returns:
        None on success, or an error message string if a score_at_start value
        could not be parsed (in which case the rallies list is left partially
        mutated — callers must discard it).
    """
    score = ScoreState(
        game_type=game_section["type"],
        victory_rules=game_section["victory_rules"],
        player_names={
            "team1": game_section["team1_players"],
            "team2": game_section["team2_players"],
        },
    )

    for rally in rallies:
        if rally.get("is_post_game"):
            rally["winning_team"] = None
            continue

        score_at_start = rally.get("score_at_start", "")
        if not score_at_start:
            return f"rally index {rally.get('index')}: missing score_at_start"

        # Validate the score string before calling set_score so we can produce
        # a clear error message rather than letting ValueError propagate raw.
        parts = score_at_start.split("-")
        expected_parts = 2 if game_section["type"] == "singles" else 3
        if len(parts) != expected_parts:
            return (
                f"rally index {rally.get('index')}: score_at_start "
                f"{score_at_start!r} has wrong part count for {game_section['type']}"
            )

        # Re-sync state — absorbs interventions
        score.set_score(score_at_start)

        serving = score.serving_team
        winner_field = rally.get("winner")

        if winner_field == "server":
            winning_team = serving
            score.server_wins()
        elif winner_field == "receiver":
            winning_team = 1 - serving
            score.receiver_wins()
        else:
            return (
                f"rally index {rally.get('index')}: unexpected winner value "
                f"{winner_field!r} (expected 'server' or 'receiver')"
            )

        rally["winning_team"] = winning_team

    return None


def _process_file(json_path: Path) -> _Result:
    """Backfill winning_team labels in a single .training.json file.

    Reads, validates, applies the backfill algorithm, and writes the result
    back to the same path.  Returns SKIPPED if the file is already labeled or
    has no rallies.  Never raises — unexpected errors are the caller's concern.

    Args:
        json_path: Path to the .training.json file to process.

    Returns:
        _Result.UPDATED if the file was rewritten with winning_team labels.
        _Result.SKIPPED if the file needed no changes.
    """
    raw_text = json_path.read_text(encoding="utf-8")
    data = json.loads(raw_text)

    if _already_labeled(data):
        print(f"SKIP: {json_path.name} (already has winning_team labels)")
        return _Result.SKIPPED

    game_section = data.get("game")
    if game_section is None:
        print(f"SKIP: {json_path.name} (no 'game' section)")
        return _Result.SKIPPED

    rallies = data.get("rallies")
    if not rallies:
        print(f"SKIP: {json_path.name} (no rallies)")
        return _Result.SKIPPED

    # Work on a copy of the rallies list so a mid-game error does not leave
    # partially mutated data that we would then accidentally write back.
    import copy
    rallies_copy = copy.deepcopy(rallies)

    error = _backfill_game(game_section, rallies_copy)
    if error is not None:
        print(f"WARN: {json_path.name}: {error} — skipping entire file")
        return _Result.SKIPPED

    # Commit the mutated copy back into the document
    data["rallies"] = rallies_copy
    data["schema_version"] = "1.1"

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"DONE: {json_path.name}")
    return _Result.UPDATED


def main() -> None:
    """Entry point: walk root, backfill each unlabeled .training.json."""
    parser = argparse.ArgumentParser(
        description="Add winning_team labels to existing .training.json files."
    )
    parser.add_argument(
        "--root",
        default=str(Path.home() / "Videos" / "pickleball"),
        help="Directory to search recursively for *.training.json files "
             "(default: ~/Videos/pickleball/)",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.exists():
        print(f"ERROR: --root directory does not exist: {root}")
        sys.exit(1)
    root = root.resolve()

    json_files = sorted(root.rglob("*.training.json"))
    if not json_files:
        print(f"No .training.json files found under {root}")
        return

    print(f"Found {len(json_files)} .training.json file(s) under {root}\n")

    updated = 0
    skipped = 0
    for json_path in json_files:
        result = _Result.ERROR
        try:
            result = _process_file(json_path)
        except Exception as exc:  # noqa: BLE001 — error boundary: log and continue
            print(f"ERROR: {json_path.name}: {exc}")
        if result is _Result.UPDATED:
            updated += 1
        elif result is _Result.SKIPPED:
            skipped += 1

    print(f"\n{updated} files updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
