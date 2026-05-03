"""End-to-end auto-edit pipeline orchestrator for Pickleball Video Editor.

Runs the full pipeline from a raw video to finished output files without
any manual interaction:

  Stage 1 – Audio rally detection   (ml.predict.predict_video)
  Stage 2 – Winner prediction       (ml.predict_winner.predict_winners)
  Stage 3 – Score simulation        (ScoreState + RallyManager)
  Stage 4 – Output generation       (KdenliveGenerator + TrainingDataGenerator)

Public API
----------
auto_edit(video_path, setup, corners, output_dir, checkpoint_path, ...) -> AutoEditResult
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ml.config import WinnerModelConfig
from ml.predict import predict_video
from ml.predict_winner import predict_winners
from src.core.models import GameCompletionInfo, ScoreSnapshot, SessionState
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState
from src.output.kdenlive_generator import KdenliveGenerator
from src.output.training_data_generator import TrainingDataGenerator
from src.video.probe import probe_video


__all__ = ["AutoEditSetup", "AutoEditResult", "auto_edit"]

logger = logging.getLogger(__name__)


@dataclass
class AutoEditSetup:
    """Headless setup configuration consumed by the auto_edit() pipeline.

    This dataclass contains the subset of GameConfig fields that auto_edit()
    actually uses.  It deliberately has no PyQt6 dependency so the ML CLI
    can construct it without pulling in the Qt layer.

    Attributes:
        game_type: Type of game ("singles" or "doubles").
        victory_rule: Victory condition ("11", "9", or "timed").
        team1_players: Player names for Team 1.
        team2_players: Player names for Team 2.
        court_corners: Optional list of four [x, y] corner coordinates for
            the court in the source video frame.
    """

    game_type: str
    victory_rule: str
    team1_players: list[str] = field(default_factory=list)
    team2_players: list[str] = field(default_factory=list)
    court_corners: list[list[int]] | None = None


@dataclass
class AutoEditResult:
    """Result of a completed auto-edit pipeline run.

    Attributes:
        kdenlive_path: Path to the generated .kdenlive project file.
        ass_path: Path to the companion ASS subtitle file.
        training_json_path: Path to the .training.json labels file.
        predicted_rally_count: Number of rallies the audio model detected.
        low_confidence_rally_indices: Zero-based indices of rallies whose
            winner-prediction confidence fell below the threshold.
        simulated_final_score: Tuple (team1_score, team2_score) extracted
            from the last ScoreSnapshot, or None when no rallies were scored.
        session_state: Fully-populated SessionState built directly from the
            in-memory ScoreState and RallyManager.  Callers can hand this
            straight to MainWindow without round-tripping through the training
            JSON, which previously lost current_score/serving_team/etc.
    """

    kdenlive_path: Path
    ass_path: Path
    training_json_path: Path
    predicted_rally_count: int
    low_confidence_rally_indices: list[int]
    simulated_final_score: tuple[int, int] | None
    session_state: SessionState


def _build_player_names(setup: AutoEditSetup) -> dict[str, list[str]]:
    """Construct the player_names dict expected by ScoreState.

    Args:
        setup: AutoEditSetup with team1_players and team2_players.

    Returns:
        Dict with "team1" and "team2" keys containing player name lists.
        Falls back to placeholder names when the caller did not supply any,
        so ScoreState never receives an empty dict.
    """
    team1 = setup.team1_players if setup.team1_players else ["Team 1"]
    team2 = setup.team2_players if setup.team2_players else ["Team 2"]
    return {"team1": team1, "team2": team2}


def auto_edit(
    video_path: Path,
    setup: AutoEditSetup,
    corners: list[tuple[int, int]],
    output_dir: Path,
    checkpoint_path: Path,
    confidence_threshold: float = 0.75,
    winner_config: WinnerModelConfig | None = None,
) -> AutoEditResult:
    """Run the full auto-edit pipeline on a pickleball video.

    Executes four stages sequentially:
    1. Detect rally intervals from the audio track.
    2. Predict which team won each rally using the visual winner classifier.
    3. Simulate pickleball scoring through all detected rallies.
    4. Generate a Kdenlive project file, ASS subtitles, and training JSON.

    Args:
        video_path: Absolute path to the source video file.
        setup: AutoEditSetup containing game type, victory rule, and player names.
        corners: Four (x, y) pixel coordinates of the court corners in the
            original video frame, ordered top-left, top-right, bottom-right,
            bottom-left.  Required by the visual winner classifier.
        output_dir: Directory where all output files will be written.
        checkpoint_path: Path to the WinnerClassifier ``.pt`` checkpoint.
        confidence_threshold: Minimum softmax confidence to accept a winner
            prediction without flagging it as low-confidence.  Defaults to
            0.75.  Rallies below this threshold are included in
            AutoEditResult.low_confidence_rally_indices.
        winner_config: Optional WinnerModelConfig controlling clip duration,
            canonical resolution, device, etc.  Defaults are used when None.

    Returns:
        AutoEditResult with paths to all generated files and pipeline metadata.

    Raises:
        FileNotFoundError: If video_path does not exist or checkpoint_path is
            missing.
        ValueError: If corners does not contain exactly 4 points.
    """
    video_path = video_path.resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if len(corners) != 4:
        raise ValueError(
            f"corners must contain exactly 4 (x, y) points, got {len(corners)}"
        )

    if setup.game_type not in ("singles", "doubles"):
        raise ValueError("auto_edit does not support highlights mode")

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Stage 1: Audio rally detection
    # ------------------------------------------------------------------
    logger.info("Stage 1: detecting rallies in %s", video_path.name)

    raw_rallies: list[dict[str, float]] = predict_video(video_path)
    rally_intervals: list[tuple[float, float]] = [
        (r["start_seconds"], r["end_seconds"]) for r in raw_rallies
    ]

    predicted_rally_count = len(rally_intervals)
    logger.info("Stage 1 complete: %d rallies detected", predicted_rally_count)

    # ------------------------------------------------------------------
    # Stage 2: Winner prediction
    # ------------------------------------------------------------------
    logger.info("Stage 2: predicting winners for %d rallies", predicted_rally_count)

    winner_results: list[tuple[int, float]] = []
    if rally_intervals:
        winner_results = predict_winners(
            video_path=video_path,
            corners=corners,
            rally_intervals=rally_intervals,
            checkpoint_path=checkpoint_path,
            config=winner_config,
        )

    logger.info("Stage 2 complete")

    # ------------------------------------------------------------------
    # Stage 3: Score simulation
    # ------------------------------------------------------------------
    logger.info("Stage 3: simulating score for %s game", setup.game_type)

    video_info = probe_video(video_path)
    fps: float = video_info.fps

    player_names = _build_player_names(setup)
    score_state = ScoreState(
        game_type=setup.game_type,
        victory_rules=setup.victory_rule,
        player_names=player_names,
    )
    rally_manager = RallyManager(fps=fps)

    low_confidence_rally_indices: list[int] = []
    last_snapshot: ScoreSnapshot | None = None

    for idx, ((start_s, end_s), (winning_team, confidence)) in enumerate(
        zip(rally_intervals, winner_results)
    ):
        if confidence < confidence_threshold:
            low_confidence_rally_indices.append(idx)

        # Snapshot score state BEFORE this rally starts.
        snapshot_before = score_state.save_snapshot()
        score_at_start = score_state.get_score_string()

        rally_manager.start_rally(start_s, snapshot_before)

        # Determine winner from serving team perspective.
        if winning_team == score_state.serving_team:
            winner_str = "server"
            score_state.server_wins()
        else:
            winner_str = "receiver"
            score_state.receiver_wins()

        new_snapshot = score_state.save_snapshot()
        last_snapshot = new_snapshot

        rally_manager.end_rally(
            timestamp=end_s,
            winner=winner_str,
            score_at_start=score_at_start,
            score_snapshot=new_snapshot,
        )

        game_over, _winner_team = score_state.is_game_over()
        if game_over:
            logger.info("Game over at rally %d", idx)
            break

    # Extract final score from last snapshot.
    simulated_final_score: tuple[int, int] | None = None
    if last_snapshot is not None:
        simulated_final_score = (
            int(last_snapshot.score[0]),
            int(last_snapshot.score[1]),
        )

    logger.info(
        "Stage 3 complete: %d rallies scored, final score %s",
        rally_manager.get_rally_count(),
        simulated_final_score,
    )

    # ------------------------------------------------------------------
    # Stage 4: Output generation
    # ------------------------------------------------------------------
    logger.info("Stage 4: generating output files in %s", output_dir)

    resolution: tuple[int, int] = (video_info.width, video_info.height)
    segments = rally_manager.to_segments()

    # Build a stem for output files from the video name.
    stem = video_path.stem
    kdenlive_output_path = output_dir / f"{stem}_auto.kdenlive"

    # GameCompletionInfo: mark completed if game ended naturally.
    game_over, winner_team = score_state.is_game_over()
    game_completion: GameCompletionInfo | None = None
    if game_over and winner_team is not None and simulated_final_score is not None:
        winning_team_names = (
            setup.team1_players if winner_team == 0 else setup.team2_players
        )
        final_score_str = f"{simulated_final_score[0]}-{simulated_final_score[1]}"
        game_completion = GameCompletionInfo(
            is_completed=True,
            final_score=final_score_str,
            winning_team=winner_team,
            winning_team_names=winning_team_names,
        )

    generator = KdenliveGenerator(
        video_path=video_path,
        segments=segments,
        fps=fps,
        resolution=resolution,
        output_dir=output_dir,
        team1_players=setup.team1_players,
        team2_players=setup.team2_players,
        game_type=setup.game_type,
        game_completion=game_completion,
    )

    kdenlive_path, ass_path = generator.generate(output_path=kdenlive_output_path)
    logger.info("Kdenlive project written to %s", kdenlive_path)

    # Training data JSON.
    training_json_path = output_dir / f"{stem}_auto.training.json"

    # Convert corners from list[tuple[int,int]] to list[list[int]] for the schema.
    corners_for_json: list[list[int]] = [[x, y] for x, y in corners]

    TrainingDataGenerator.write(
        output_path=training_json_path,
        video_path=str(video_path),
        fps=fps,
        duration_seconds=video_info.duration,
        resolution=resolution,
        game_type=setup.game_type,
        victory_rules=setup.victory_rule,
        team1_players=setup.team1_players,
        team2_players=setup.team2_players,
        rallies=rally_manager.get_rallies(),
        game_completion=game_completion,
        court_corners=corners_for_json,
        generated_by="auto_edit",
    )
    logger.info("Training JSON written to %s", training_json_path)

    logger.info("Stage 4 complete")

    # ------------------------------------------------------------------
    # Build SessionState directly from in-memory objects.
    #
    # This avoids round-tripping through the training JSON (which only stores
    # the score string at rally-start and lacks the final ScoreState fields
    # current_score / serving_team / server_number / first_server_player_index).
    # MainWindow._init_core_components restores ScoreState from these fields, so
    # they must be populated correctly for review mode to show the right score.
    # ------------------------------------------------------------------
    corners_as_lists: list[list[int]] = [[x, y] for x, y in corners]

    session_state = SessionState(
        video_path=str(video_path),
        game_type=setup.game_type,
        victory_rules=setup.victory_rule,
        player_names=player_names,
        rallies=rally_manager.get_rallies(),
        current_score=list(score_state.score),
        serving_team=score_state.serving_team,
        server_number=score_state.server_number,
        first_server_player_index=score_state.first_server_player_index,
        game_completion=game_completion if game_completion is not None else GameCompletionInfo(),
        court_corners=corners_as_lists if corners_as_lists else None,
    )

    return AutoEditResult(
        kdenlive_path=kdenlive_path,
        ass_path=ass_path,
        training_json_path=training_json_path,
        predicted_rally_count=predicted_rally_count,
        low_confidence_rally_indices=low_confidence_rally_indices,
        simulated_final_score=simulated_final_score,
        session_state=session_state,
    )
