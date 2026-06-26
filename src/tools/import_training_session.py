"""Reconstruct a resumable app session from an exported ``.training.json``.

The app reloads previously-labelled games from **session files**
(``~/.local/share/pickleball-editor/sessions/{video_hash}.json``), surfaced in
the setup dialog's "Recent Sessions → Resume" flow.  Those session files are
not the same artefact as the ``.training.json`` ML export, and for the older
corpus they are gone — only the ``.training.json`` exports survive.

This tool rebuilds a :class:`~src.core.models.SessionState` from a
``.training.json`` and writes it back into the session directory, so the game
re-opens in the app with **all cuts / scores / winners / court corners intact**.
It deliberately does **not** reconstruct server identity (which physical player
served) — that field was never persisted and is exactly what the human labels
by hand afterwards (near/far starting-server orientation varies per game and
must be eyeballed).

Qt-free: imports only ``src.core`` data models.  Run headless::

    .venv/bin/python -m src.tools.import_training_session GAME.training.json
    .venv/bin/python -m src.tools.import_training_session GAME.training.json --video /path/to/video.mp4 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from src.core.models import GameCompletionInfo, Rally, SessionState
from src.core.score_state import ScoreState
from src.core.session_manager import SessionManager

__all__ = ["session_state_from_training", "import_training_json"]


def _rally_from_training(rally: dict[str, Any]) -> Rally:
    """Map one ``.training.json`` rally dict back to a :class:`Rally`.

    Padded frames are the editorial cut points (``start_frame``/``end_frame``);
    ``raw`` carries the unpadded user-marked timing.  ``winning_team`` is not
    stored on :class:`Rally` (it is re-derived at export), so it is ignored here.
    """
    padded = rally.get("padded") or {}
    raw = rally.get("raw") or {}
    # Restore any previously-labelled server (so re-opening a partially-labelled
    # game does not lose work).  Tolerant of absence — it is the field we add.
    server = rally.get("server") or {}
    pixel = server.get("pixel")
    return Rally(
        start_frame=int(padded.get("start_frame", 0)),
        end_frame=int(padded.get("end_frame", 0)),
        score_at_start=rally.get("score_at_start", "0-0"),
        winner=rally.get("winner", "server"),
        comment=rally.get("comment"),
        is_post_game=bool(rally.get("is_post_game", False)),
        raw_start_seconds=raw.get("start_seconds"),
        raw_end_seconds=raw.get("end_seconds"),
        raw_start_frame=raw.get("start_frame"),
        raw_end_frame=raw.get("end_frame"),
        server_team=server.get("team"),
        server_player_index=server.get("player_index"),
        server_pixel=tuple(pixel) if isinstance(pixel, (list, tuple)) else None,
    )


def _replay_final_state(
    game_type: str,
    victory_rules: str,
    team1: list[str],
    team2: list[str],
    rallies: list[Rally],
) -> tuple[list[int], int, int | None]:
    """Best-effort replay to recover (current_score, serving_team, server_number).

    Mirrors :meth:`TrainingDataGenerator.generate`'s cascade (set_score then
    server_wins/receiver_wins).  Only used to seed the resumed session's score
    display; per-rally ``score_at_start``/``winner`` come verbatim from the JSON,
    so an imperfect seed here never corrupts the labels.
    """
    if game_type not in ("singles", "doubles"):
        return [0, 0], 0, None
    state = ScoreState(
        game_type=game_type,
        victory_rules=victory_rules,
        player_names={"team1": team1, "team2": team2},
    )
    for rally in rallies:
        if rally.is_post_game:
            continue
        try:
            state.set_score(rally.score_at_start)
            if rally.winner == "server":
                state.server_wins()
            else:
                state.receiver_wins()
        except Exception:  # noqa: BLE001 — replay is best-effort; labels are authoritative
            break
    snap = state.save_snapshot()
    return list(snap.score), snap.serving_team, snap.server_number


def session_state_from_training(
    data: dict[str, Any], video_path: str | None = None
) -> SessionState:
    """Build a :class:`SessionState` from a parsed ``.training.json`` dict."""
    video = data.get("video", {})
    game = data.get("game", {})
    team1 = list(game.get("team1_players", []))
    team2 = list(game.get("team2_players", []))
    game_type = game.get("type", "doubles")
    victory_rules = game.get("victory_rules", "11")

    rallies = [_rally_from_training(r) for r in data.get("rallies", [])]
    current_score, serving_team, server_number = _replay_final_state(
        game_type, victory_rules, team1, team2, rallies
    )

    completion = game.get("completion")
    game_completion = (
        GameCompletionInfo.from_dict(completion)
        if isinstance(completion, dict)
        else GameCompletionInfo()
    )

    return SessionState(
        version="1.0",
        video_path=video_path or video.get("path", ""),
        video_hash="",  # filled by SessionManager.save()
        game_type=game_type,
        victory_rules=victory_rules,
        player_names={"team1": team1, "team2": team2},
        rallies=rallies,
        current_score=current_score,
        serving_team=serving_team,
        server_number=server_number,
        last_position=0.0,
        interventions=[],
        comments=[],
        game_completion=game_completion,
        court_corners=video.get("court_corners"),
    )


def import_training_json(
    json_path: Path,
    video_path: Path | None = None,
    session_manager: SessionManager | None = None,
    dry_run: bool = False,
) -> tuple[SessionState, Path | None]:
    """Reconstruct and (unless ``dry_run``) persist a session from a training JSON.

    Returns ``(session_state, written_path)``.  ``written_path`` is ``None`` on a
    dry run or if the video file is missing (the session is keyed by a hash of
    the video, so the video must exist to write a resumable file).
    """
    import json

    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    resolved_video = str(video_path) if video_path else data.get("video", {}).get("path", "")
    state = session_state_from_training(data, video_path=resolved_video)

    if dry_run:
        return state, None

    if not resolved_video or not Path(resolved_video).exists():
        print(
            f"WARNING: video not found at {resolved_video!r}; cannot write a "
            "resumable session (it is keyed by the video hash). Pass --video.",
            file=sys.stderr,
        )
        return state, None

    sm = session_manager or SessionManager()
    written = sm.save(state, resolved_video)
    return state, written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_json", type=Path, help="Path to a .training.json export")
    parser.add_argument(
        "--video", type=Path, default=None,
        help="Override the video path (default: video.path inside the JSON).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Reconstruct and report, but do not write the session file.",
    )
    args = parser.parse_args(argv)

    state, written = import_training_json(
        args.training_json, video_path=args.video, dry_run=args.dry_run
    )

    n_post = sum(1 for r in state.rallies if r.is_post_game)
    print(f"Reconstructed session from {args.training_json.name}")
    print(f"  game        : {state.game_type} / victory '{state.victory_rules}'")
    print(f"  teams       : {state.player_names.get('team1')} vs {state.player_names.get('team2')}")
    print(f"  rallies     : {len(state.rallies)} ({n_post} post-game)")
    print(f"  final score : {state.current_score} serving_team={state.serving_team} server#={state.server_number}")
    print(f"  court_corners: {'present' if state.court_corners else 'MISSING'}")
    print(f"  video       : {state.video_path}")
    if args.dry_run:
        print("  (dry run — no session written)")
    elif written is not None:
        print(f"  WROTE session: {written}")
    else:
        print("  NOT written (see warning above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
