"""Unified CLI entry point for the rally detection ML pipeline.

Usage:
    python -m ml train --data-dir ~/Videos/pickleball/
    python -m ml predict --video /path/to/new_game.mp4
    python -m ml auto-edit --video /path/to/game.mp4 --setup /path/to/setup.json \\
        --corners /path/to/corners.json --out /path/to/output/ \\
        --checkpoint /path/to/best_winner.pt
    python -m ml auto-edit --from-training /path/to/game.training.json \\
        --out /path/to/output/ --checkpoint /path/to/best_winner.pt
    python -m ml train-winner --root ~/Videos/pickleball/ --epochs 50

This module dispatches to the train, predict, auto-edit, and train-winner
subcommands, providing a single executable for the entire ML pipeline.
"""

import argparse
import json
import sys
from pathlib import Path


def _load_setup_from_file(setup_path: Path) -> "AutoEditSetup":
    """Load AutoEditSetup from a setup JSON file.

    Expected format:
        {"game_type": "doubles", "victory_rule": "11",
         "team1_players": ["A", "B"], "team2_players": ["C", "D"]}

    Args:
        setup_path: Path to the setup JSON file.

    Returns:
        Populated AutoEditSetup instance.
    """
    from ml.auto_edit import AutoEditSetup

    raw = json.loads(setup_path.read_text(encoding="utf-8"))
    return AutoEditSetup(
        game_type=raw.get("game_type", "doubles"),
        victory_rule=raw.get("victory_rule", "11"),
        team1_players=raw.get("team1_players", []),
        team2_players=raw.get("team2_players", []),
    )


def _load_corners_from_file(corners_path: Path) -> list[tuple[int, int]]:
    """Load court corners from a corners JSON file.

    Expected format: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]

    Args:
        corners_path: Path to the corners JSON file.

    Returns:
        List of four (x, y) integer tuples.
    """
    raw: list[list[int]] = json.loads(corners_path.read_text(encoding="utf-8"))
    return [(int(pt[0]), int(pt[1])) for pt in raw]


def _load_setup_and_corners_from_training(
    training_path: Path,
) -> "tuple[AutoEditSetup, list[tuple[int, int]], Path]":
    """Extract AutoEditSetup, corners, and video_path from a training JSON file.

    Uses the ``game`` block for setup fields and ``video.court_corners`` for
    corners.

    Args:
        training_path: Path to a .training.json file produced by
            TrainingDataGenerator.

    Returns:
        Three-tuple of (AutoEditSetup, corners, video_path).
    """
    from ml.auto_edit import AutoEditSetup

    data = json.loads(training_path.read_text(encoding="utf-8"))

    game_block: dict = data.get("game", {})
    video_block: dict = data.get("video", {})

    raw_corners: list[list[int]] = video_block.get("court_corners", [])
    corners_as_lists = raw_corners if raw_corners else None

    setup = AutoEditSetup(
        game_type=game_block.get("type", "doubles"),
        victory_rule=game_block.get("victory_rules", "11"),
        team1_players=game_block.get("team1_players", []),
        team2_players=game_block.get("team2_players", []),
        court_corners=corners_as_lists,
    )

    corners: list[tuple[int, int]] = [(int(pt[0]), int(pt[1])) for pt in raw_corners]
    video_path = Path(video_block.get("path", ""))

    return setup, corners, video_path


def _cmd_auto_edit(args: argparse.Namespace) -> None:
    """Execute the auto-edit subcommand.

    Resolves inputs from either --from-training or the explicit
    --video/--setup/--corners triple, validates all file paths, then calls
    auto_edit() and prints a clean summary.

    Args:
        args: Parsed argument namespace from argparse.
    """
    from ml.auto_edit import auto_edit

    # ------------------------------------------------------------------
    # Resolve video_path, setup, and corners.
    # ------------------------------------------------------------------
    if args.from_training is not None:
        training_path = Path(args.from_training)
        if not training_path.exists():
            print(
                f"Error: training JSON not found: {training_path}",
                file=sys.stderr,
            )
            raise SystemExit(1)

        setup, corners, video_path = _load_setup_and_corners_from_training(training_path)

        if not video_path or not video_path.exists():
            print(
                f"Error: video path from training JSON does not exist: {video_path}",
                file=sys.stderr,
            )
            raise SystemExit(1)

    else:
        missing = [
            name
            for name, value in [
                ("--video", args.video),
                ("--setup", args.setup),
                ("--corners", args.corners),
            ]
            if value is None
        ]
        if missing:
            print(
                f"Error: {', '.join(missing)} required when --from-training is not used.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        video_path = Path(args.video)
        setup_path = Path(args.setup)
        corners_path = Path(args.corners)

        if not video_path.exists():
            print(f"Error: video file not found: {video_path}", file=sys.stderr)
            raise SystemExit(1)
        if not setup_path.exists():
            print(f"Error: setup JSON not found: {setup_path}", file=sys.stderr)
            raise SystemExit(1)
        if not corners_path.exists():
            print(f"Error: corners JSON not found: {corners_path}", file=sys.stderr)
            raise SystemExit(1)

        setup = _load_setup_from_file(setup_path)
        corners = _load_corners_from_file(corners_path)

    # ------------------------------------------------------------------
    # Validate checkpoint.
    # ------------------------------------------------------------------
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"Error: checkpoint not found: {checkpoint_path}", file=sys.stderr)
        raise SystemExit(1)

    # ------------------------------------------------------------------
    # Prepare output directory.
    # ------------------------------------------------------------------
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Run the pipeline.
    # ------------------------------------------------------------------
    result = auto_edit(
        video_path=video_path,
        setup=setup,
        corners=corners,
        output_dir=output_dir,
        checkpoint_path=checkpoint_path,
        confidence_threshold=args.confidence_threshold,
    )

    # ------------------------------------------------------------------
    # Print summary.
    # ------------------------------------------------------------------
    if result.simulated_final_score is not None:
        score_str = (
            f"{result.simulated_final_score[0]}-{result.simulated_final_score[1]}"
        )
    else:
        score_str = "game did not complete"

    low_conf_indices = result.low_confidence_rally_indices
    low_conf_detail = f" (indices: {low_conf_indices})" if low_conf_indices else ""

    print("Auto-edit complete.")
    print(
        f"Rallies: {result.n_detected} detected / "
        f"{result.n_scored} scored / "
        f"{result.n_post_game} post-game"
    )
    print(f"Low-confidence rallies: {len(low_conf_indices)}{low_conf_detail}")
    print(f"Final score: {score_str}")
    print(f"Output: {result.kdenlive_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rally-trainer",
        description="Pickleball rally detection ML pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- train subcommand ---
    train_parser = subparsers.add_parser(
        "train",
        help="Train the rally detection model",
    )
    train_parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory containing .training.json files (searched recursively)",
    )
    train_parser.add_argument(
        "--epochs", type=int, default=None, help="Override number of epochs"
    )
    train_parser.add_argument(
        "--batch-size", type=int, default=None, help="Override batch size"
    )
    train_parser.add_argument(
        "--lr", type=float, default=None, help="Override learning rate"
    )

    # --- train-winner subcommand ---
    train_winner_parser = subparsers.add_parser(
        "train-winner",
        help="Train the rally winner classifier",
    )
    train_winner_parser.add_argument(
        "--root",
        type=str,
        required=True,
        help="Root directory containing .training.json files (searched recursively)",
    )
    train_winner_parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Maximum number of training epochs (default: 50)",
    )
    train_winner_parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Mini-batch size (default: 8)",
    )
    train_winner_parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        help='Compute device (default: cuda)',
    )

    # --- predict subcommand ---
    predict_parser = subparsers.add_parser(
        "predict",
        help="Detect rallies in a pickleball video",
    )
    predict_parser.add_argument(
        "--video", type=str, required=True, help="Path to video file"
    )
    predict_parser.add_argument(
        "--model", type=str, default=None,
        help="Path to model checkpoint (default: ml/checkpoints/best_model.pt)",
    )
    predict_parser.add_argument(
        "--threshold", type=float, default=None,
        help="Detection threshold (default: 0.5)",
    )
    predict_parser.add_argument(
        "--min-rally", type=float, default=None,
        help="Minimum rally duration in seconds (default: 3.0)",
    )
    predict_parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON path (default: print to stdout)",
    )

    # ------------------------------------------------------------------ #
    # auto-edit subcommand                                                 #
    # ------------------------------------------------------------------ #
    auto_edit_parser = subparsers.add_parser(
        "auto-edit",
        help="Run the full auto-edit pipeline from video to Kdenlive project",
    )
    # Source mode A: explicit video + setup + corners
    auto_edit_parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Path to the source video file",
    )
    auto_edit_parser.add_argument(
        "--setup",
        type=str,
        default=None,
        help=(
            'Path to setup JSON with GameConfig fields, e.g. '
            '{"game_type":"doubles","victory_rule":"11",'
            '"team1_players":["A","B"],"team2_players":["C","D"]}'
        ),
    )
    auto_edit_parser.add_argument(
        "--corners",
        type=str,
        default=None,
        help=(
            "Path to corners JSON — 4 [x,y] pairs, "
            "e.g. [[100,200],[800,200],[800,600],[100,600]]"
        ),
    )
    # Source mode B: derive everything from an existing training JSON
    auto_edit_parser.add_argument(
        "--from-training",
        type=str,
        default=None,
        help=(
            "Path to an existing .training.json file.  When supplied, --video, "
            "--setup, and --corners are read from that file instead."
        ),
    )
    # Shared required args
    auto_edit_parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output directory where all generated files will be written",
    )
    auto_edit_parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Path to the WinnerClassifier .pt checkpoint file",
    )
    auto_edit_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=None,
        help=(
            "Minimum softmax confidence to accept a winner prediction "
            "without flagging it as low-confidence "
            "(defaults to WinnerModelConfig.confidence_threshold (0.75))"
        ),
    )

    args = parser.parse_args()

    if args.command == "train":
        # Defer heavy imports until needed
        from ml.train import main as train_main

        # Rebuild sys.argv so train_main's own parser sees the right args
        argv = ["ml.train", "--data-dir", args.data_dir]
        if args.epochs is not None:
            argv += ["--epochs", str(args.epochs)]
        if args.batch_size is not None:
            argv += ["--batch-size", str(args.batch_size)]
        if args.lr is not None:
            argv += ["--lr", str(args.lr)]
        sys.argv = argv
        train_main()

    elif args.command == "train-winner":
        from ml.train_winner import train_winner

        root_dir = Path(args.root).expanduser().resolve()
        if not root_dir.exists():
            print(f"Error: root directory does not exist: {root_dir}")
            sys.exit(1)

        train_winner(
            root_dir=root_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device_str=args.device,
        )

    elif args.command == "predict":
        from ml.predict import main as predict_main

        argv = ["ml.predict", "--video", args.video]
        if args.model is not None:
            argv += ["--model", args.model]
        if args.threshold is not None:
            argv += ["--threshold", str(args.threshold)]
        if args.min_rally is not None:
            argv += ["--min-rally", str(args.min_rally)]
        if args.output is not None:
            argv += ["--output", args.output]
        sys.argv = argv
        predict_main()

    elif args.command == "auto-edit":
        _cmd_auto_edit(args)


if __name__ == "__main__":
    main()
