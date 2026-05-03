"""CLI tool to produce setup.json + corners.json for a single uncut video.

Usage:
    python -m ml.tools.calibrate_video \\
        --video /path/to/match.mp4 \\
        --game-type doubles --victory-rule 11 \\
        --team1-players "Alice,Bob" \\
        --team2-players "Carol,Dave"

Writes two files into ``--out-dir`` (defaults to the video's parent directory):

  - ``setup.json``    = {"game_type", "victory_rule", "team1_players",
                         "team2_players"} — accepted by ``rally-trainer
                         auto-edit --setup``.
  - ``corners.json``  = [[x, y], [x, y], [x, y], [x, y]] in original-image
                         pixel coordinates — accepted by
                         ``rally-trainer auto-edit --corners``.

The corner step opens the same FramePickerDialog + CourtCalibratorWidget
used by ``calibrate_existing``, so the UX is identical.
"""

import argparse
import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog

from ml.tools.calibrate_existing import (
    _extract_frame_pixmap,
    _probe_duration,
    _run_calibration_dialog,
)
from ml.tools.frame_picker_dialog import FramePickerDialog


__all__ = ["main"]


_GAME_TYPES = ("doubles", "singles", "highlights")
_VICTORY_RULES = ("11", "9", "timed")


def _split_players(raw: str) -> list[str]:
    """Split a comma-separated player string into a clean list."""
    return [p.strip() for p in raw.split(",") if p.strip()]


def main() -> None:
    """Entry point: produce setup.json and corners.json for one video."""
    parser = argparse.ArgumentParser(
        description="Produce setup.json + corners.json for an uncut video so "
                    "it can be fed to `rally-trainer auto-edit`."
    )
    parser.add_argument("--video", required=True, help="Path to the source video.")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write setup.json and corners.json into "
             "(default: same directory as --video).",
    )
    parser.add_argument(
        "--game-type",
        choices=_GAME_TYPES,
        default="doubles",
        help="Game type (default: doubles).",
    )
    parser.add_argument(
        "--victory-rule",
        choices=_VICTORY_RULES,
        default="11",
        help="Victory condition (default: 11).",
    )
    parser.add_argument(
        "--team1-players",
        default="",
        help='Comma-separated names for team 1, e.g. "Alice,Bob". '
             "Required unless --game-type=highlights.",
    )
    parser.add_argument(
        "--team2-players",
        default="",
        help='Comma-separated names for team 2, e.g. "Carol,Dave". '
             "Required unless --game-type=highlights.",
    )
    parser.add_argument(
        "--auto-frame",
        action="store_true",
        help="Skip the interactive frame picker; calibrate against the "
             "5%%-into-video frame.",
    )
    args = parser.parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        print(f"ERROR: video not found: {video_path}")
        sys.exit(1)

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else video_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    team1 = _split_players(args.team1_players)
    team2 = _split_players(args.team2_players)
    if args.game_type != "highlights" and (not team1 or not team2):
        print("ERROR: --team1-players and --team2-players are required "
              "unless --game-type=highlights.")
        sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)

    if args.auto_frame:
        duration = _probe_duration(video_path)
        pixmap = _extract_frame_pixmap(video_path, duration * 0.05)
        if pixmap is None or pixmap.isNull():
            print(f"ERROR: could not extract auto-frame from {video_path.name}")
            sys.exit(1)
    else:
        picker = FramePickerDialog(video_path)
        if picker.exec() != QDialog.DialogCode.Accepted:
            print("Aborted: frame picker dismissed.")
            sys.exit(1)
        pixmap = picker.get_result()
        if pixmap is None or pixmap.isNull():
            print("ERROR: frame picker returned no pixmap.")
            sys.exit(1)

    corners = _run_calibration_dialog(app, pixmap, f"Calibrate: {video_path.name}")
    if corners is None:
        print("Aborted: calibration dialog closed without confirming.")
        sys.exit(1)

    setup_path = out_dir / "setup.json"
    corners_path = out_dir / "corners.json"

    setup_payload: dict[str, object] = {
        "game_type": args.game_type,
        "victory_rule": args.victory_rule,
        "team1_players": team1,
        "team2_players": team2,
    }
    setup_path.write_text(
        json.dumps(setup_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    corners_path.write_text(
        json.dumps(corners, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {setup_path}")
    print(f"Wrote {corners_path}")
    print()
    print("Next step:")
    print(
        f"  .venv/bin/python -m ml auto-edit \\\n"
        f"    --video {video_path} \\\n"
        f"    --setup {setup_path} \\\n"
        f"    --corners {corners_path} \\\n"
        f"    --out {out_dir} \\\n"
        f"    --checkpoint ml/checkpoints/best_winner.pt"
    )


if __name__ == "__main__":
    main()
