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

Cooperative cancellation
------------------------
Pass a ``cancel_check`` callable (no arguments, returns bool) to auto_edit().
If it returns True at any stage boundary the function raises AutoEditCancelled
and NO output files are written.  The check is performed:

  - After Stage 1 (audio detection complete, before Stage 2)
  - After Stage 2 (winner prediction complete, before Stage 3)
  - Before Stage 4 (score simulation complete; last chance to cancel before
    any file I/O)

Raising AutoEditCancelled from cancel_check itself is also safe.
"""

import logging
import torch
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ml.config import PathConfig, WinnerModelConfig
from ml.predict import predict_video
from ml.predict_winner import predict_winners
from src.core.models import GameCompletionInfo, ScoreSnapshot, SessionState
from src.core.rally_manager import RallyManager
from src.core.score_state import ScoreState
from src.output.kdenlive_generator import KdenliveGenerator
from src.output.training_data_generator import TrainingDataGenerator
from src.video.probe import probe_video


__all__ = ["AutoEditSetup", "AutoEditResult", "AutoEditCancelled", "auto_edit"]

logger = logging.getLogger(__name__)

# Rallies whose padded duration is below this threshold are flagged for human
# review regardless of winner-prediction confidence.  Aces, faults, and net
# errors are legitimate sub-3s score-advancing rallies, but they are also more
# prone to mis-detection, so a reviewer should verify them.
SHORT_RALLY_REVIEW_SECONDS = 3.0


class AutoEditCancelled(RuntimeError):
    """Raised when the caller's cancel_check() returns True.

    Guaranteed to be raised BEFORE any output files are written to disk,
    so a cancelled run leaves the output directory clean.
    """


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
        predicted_rally_count: Number of rallies the audio model detected
            (alias for n_detected; kept for backward compatibility).
        low_confidence_rally_indices: Zero-based indices of every scored
            (non-post-game) rally.  The winner model is near-chance on unseen
            videos, so all scored rallies are flagged for human winner review
            (post-game rallies are excluded).  Field name retained for
            backward compatibility.
        simulated_final_score: Tuple (team1_score, team2_score) extracted
            from the last pre-post-game ScoreSnapshot, or None when no
            rallies were scored.
        session_state: Fully-populated SessionState built directly from the
            in-memory ScoreState and RallyManager.  Callers can hand this
            straight to MainWindow without round-tripping through the training
            JSON, which previously lost current_score/serving_team/etc.
        n_detected: Total rally intervals output by Stage 1 (audio model).
        n_scored: Rallies that advanced the score (pre-game-over).
        n_post_game: Rallies appended after game-over with frozen score.
        fusion_unavailable_reason: Human-readable explanation set only when
            motion fusion was expected (court corners present) but could not be
            applied — e.g. the ``.venv-motion`` environment was missing or the
            GPU extraction failed — so Stage 1 fell back to audio-only.  ``None``
            when fusion was applied or was never applicable.  The GUI surfaces
            this once as an informational notice.
    """

    kdenlive_path: Path
    ass_path: Path
    training_json_path: Path
    predicted_rally_count: int
    low_confidence_rally_indices: list[int]
    simulated_final_score: tuple[int, int] | None
    session_state: SessionState
    n_detected: int = 0
    n_scored: int = 0
    n_post_game: int = 0
    fusion_unavailable_reason: str | None = None


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


def _validate_winner_checkpoint(checkpoint_path: Path) -> None:
    """Validate the Stage-2 winner checkpoint before any expensive computation.

    Checks existence, that the file can be loaded by torch, and that it
    contains the expected "model_state_dict" and "config" keys.

    Args:
        checkpoint_path: Path to the .pt checkpoint to validate.

    Raises:
        FileNotFoundError: If the checkpoint file does not exist.
        ValueError: If the file cannot be loaded or is missing required keys.
            The error message always includes the phrase
            "refusing to run Stage 1 audio detection against an unusable
            winner checkpoint" so callers can surface it to the user verbatim.
    """
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Winner checkpoint not found: {checkpoint_path} — "
            "refusing to run Stage 1 audio detection against an unusable "
            "winner checkpoint"
        )

    try:
        ckpt = torch.load(checkpoint_path, map_location="cpu")
    except Exception as exc:
        raise ValueError(
            f"Cannot load winner checkpoint {checkpoint_path}: {exc} — "
            "refusing to run Stage 1 audio detection against an unusable "
            "winner checkpoint"
        ) from exc

    missing: list[str] = [
        key for key in ("model_state_dict", "config") if key not in ckpt
    ]
    del ckpt

    if missing:
        raise ValueError(
            f"Winner checkpoint {checkpoint_path} is missing required "
            f"key(s) {missing} — refusing to run Stage 1 audio detection "
            "against an unusable winner checkpoint"
        )


def _motion_feature_path(video_path: Path) -> Path:
    """Path to the offline-extracted motion-feature cache for ``video_path``.

    Stage 1 applies motion fusion only when this ``.npz`` exists.  It is
    produced out-of-process by ``ml.tools.extract_motion_features`` in the
    isolated ``.venv-motion`` (YOLO/ByteTrack); the GUI process only ever reads
    it.  See ml/motion/DILATION_TRACKING_SPEC.md (Integration).
    """
    return PathConfig().cache_dir / "motion" / f"{video_path.stem}.npz"


def auto_edit(
    video_path: Path,
    setup: AutoEditSetup,
    corners: list[tuple[int, int]],
    output_dir: Path,
    checkpoint_path: Path,
    confidence_threshold: float | None = None,
    winner_config: WinnerModelConfig | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> AutoEditResult:
    """Run the full auto-edit pipeline on a pickleball video.

    Executes four stages sequentially:
    1. Detect rally intervals from the audio track.
    2. Predict which team won each rally using the visual winner classifier.
    3. Simulate pickleball scoring through all detected rallies.
    4. Generate a Kdenlive project file, ASS subtitles, and training JSON.

    Cooperative cancellation: if ``cancel_check`` is provided, it is called
    at stage boundaries (after Stage 1, after Stage 2, and before Stage 4
    writes any file).  When it returns True, AutoEditCancelled is raised and
    no output files are written.

    Args:
        video_path: Absolute path to the source video file.
        setup: AutoEditSetup containing game type, victory rule, and player names.
        corners: Four (x, y) pixel coordinates of the court corners in the
            original video frame, ordered top-left, top-right, bottom-right,
            bottom-left.  Required by the visual winner classifier.
        output_dir: Directory where all output files will be written.
        checkpoint_path: Path to the WinnerClassifier ``.pt`` checkpoint.
        confidence_threshold: Minimum softmax confidence to accept a winner
            prediction without flagging it as low-confidence.  When ``None``
            (the default), the value is taken from ``winner_config`` if
            provided, otherwise from ``WinnerModelConfig.confidence_threshold``
            (the single source of truth, currently 0.75).  Rallies below the
            resolved threshold are included in
            AutoEditResult.low_confidence_rally_indices.
        winner_config: Optional WinnerModelConfig controlling clip duration,
            canonical resolution, device, etc.  Defaults are used when None.
        cancel_check: Optional zero-argument callable that returns True when
            the caller wants to abort the pipeline.  Checked after Stage 1,
            after Stage 2, and before Stage 4 file writes.  Raises
            AutoEditCancelled (no files written) when True is returned.
        progress_callback: Optional callable taking a human-readable phase
            string.  Invoked for sub-stages auto_edit drives internally (notably
            the on-demand motion-feature extraction in Stage 1a) so a GUI can
            update its progress label.  When None, progress is logged only.

    Returns:
        AutoEditResult with paths to all generated files and pipeline metadata.

    Raises:
        FileNotFoundError: If video_path does not exist, the Stage-1 audio
            checkpoint is missing, or checkpoint_path is missing.
        ValueError: If corners does not contain exactly 4 points, or if the
            winner checkpoint fails validation.
        AutoEditCancelled: If cancel_check() returns True at any stage boundary.
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

    # Resolve confidence threshold: explicit argument > winner_config > default.
    # WinnerModelConfig.confidence_threshold is the single source of truth.
    resolved_threshold: float
    if confidence_threshold is not None:
        resolved_threshold = confidence_threshold
    elif winner_config is not None:
        resolved_threshold = winner_config.confidence_threshold
    else:
        resolved_threshold = WinnerModelConfig().confidence_threshold

    # ------------------------------------------------------------------
    # Pre-validation: check both checkpoints BEFORE running Stage 1.
    # Stage 1 (audio extraction + inference) is expensive; validating
    # checkpoints upfront prevents wasting minutes only to fail at Stage 2.
    # ------------------------------------------------------------------

    # Stage-1 audio checkpoint: existence check only (predict_video loads it).
    audio_ckpt = PathConfig().best_model_path
    if not audio_ckpt.exists():
        raise FileNotFoundError(
            f"Stage-1 audio checkpoint not found: {audio_ckpt} — "
            "refusing to run Stage 1 audio detection against an unusable "
            "winner checkpoint"
        )

    # Stage-2 winner checkpoint: full load + key validation.
    _validate_winner_checkpoint(checkpoint_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Stage 1: Audio rally detection (+ optional motion fusion)
    # ------------------------------------------------------------------
    logger.info("Stage 1: detecting rallies in %s", video_path.name)

    # Motion fusion is used when a feature cache exists for this video; otherwise
    # we degrade gracefully to the tuned audio-only path.
    feature_path = _motion_feature_path(video_path)
    fusion_unavailable_reason: str | None = None

    # Stage 1a: build the motion-feature cache on demand (first run per video).
    # The detector (YOLO/ByteTrack + full OpenCV) MUST run out-of-process — the
    # GUI process can't import it without segfaulting mpv — so we shell out to
    # the isolated .venv-motion.  Any unavailability degrades to audio-only.
    if corners and not feature_path.exists():
        from ml.motion.extract_runner import (
            extract_features_subprocess,
            motion_venv_python,
        )

        if motion_venv_python() is None:
            fusion_unavailable_reason = (
                "Motion fusion was skipped because the .venv-motion environment "
                "was not found on this machine; rallies were detected from audio "
                "only."
            )
            logger.warning("Stage 1a: %s", fusion_unavailable_reason)
        else:
            logger.info("Stage 1a: extracting motion features for %s", video_path.name)
            if progress_callback is not None:
                progress_callback("Extracting motion features (GPU — first run for this video)…")
            extracted = extract_features_subprocess(
                video_path,
                corners,
                feature_path.parent,
                cancel_check=cancel_check,
                progress_cb=progress_callback,
            )
            if cancel_check is not None and cancel_check():
                raise AutoEditCancelled("Pipeline cancelled during motion extraction")
            if not extracted or not feature_path.exists():
                fusion_unavailable_reason = (
                    "Motion fusion was skipped because feature extraction did not "
                    "complete (no usable GPU or an extraction error); rallies were "
                    "detected from audio only."
                )
                logger.warning("Stage 1a: %s", fusion_unavailable_reason)

    raw_rallies: list[dict[str, float]]
    if corners and feature_path.exists():
        # Local import: pulls in only headless cv2 + numpy (ultralytics stays
        # offline), keeping the heavy detector out of the GUI process.  The
        # learned audio+visual combiner degrades to audio-only internally if its
        # checkpoint is missing, so this stays safe even without joint_combiner.json.
        from ml.motion.joint_fusion import predict_joint

        raw_rallies = predict_joint(
            video_path, corners=corners, feature_path=feature_path
        )
        logger.info("Stage 1: audio+visual fusion applied (cache: %s)", feature_path.name)
    else:
        raw_rallies = predict_video(video_path)
    rally_intervals: list[tuple[float, float]] = [
        (r["start_seconds"], r["end_seconds"]) for r in raw_rallies
    ]

    n_detected = len(rally_intervals)
    predicted_rally_count = n_detected
    logger.info("Stage 1 complete: %d rallies detected", n_detected)

    if cancel_check is not None and cancel_check():
        raise AutoEditCancelled("Pipeline cancelled after Stage 1")

    # ------------------------------------------------------------------
    # Stage 2: Winner prediction
    # ------------------------------------------------------------------
    logger.info("Stage 2: predicting winners for %d rallies", n_detected)

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

    if cancel_check is not None and cancel_check():
        raise AutoEditCancelled("Pipeline cancelled after Stage 2")

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
    last_scored_snapshot: ScoreSnapshot | None = None
    game_over_flag = False
    final_score_string: str = ""
    final_snapshot_for_post_game: ScoreSnapshot | None = None

    n_scored = 0
    n_post_game = 0
    n_low_or_short = 0  # informational: scored rallies also low-conf or short

    for idx, ((start_s, end_s), (winning_team, confidence)) in enumerate(
        zip(rally_intervals, winner_results, strict=True)
    ):
        if game_over_flag:
            # F7: post-game rally — frozen score, no score advancement.
            rally_manager.start_rally(start_s, final_snapshot_for_post_game)
            rally = rally_manager.end_rally(
                timestamp=end_s,
                winner="server",  # placeholder; score is frozen
                score_at_start=final_score_string,
                score_snapshot=final_snapshot_for_post_game,
            )
            rally.is_post_game = True
            rally.predicted_team = winning_team
            rally.prediction_confidence = confidence
            n_post_game += 1
            continue

        # --- Scored rally ---
        # The winner model is near-chance on unseen videos (see the winner-model
        # diagnosis), so EVERY scored rally is routed through human review rather
        # than trusted by confidence.  predicted_team / prediction_confidence
        # (stamped below) remain a non-authoritative pre-fill the reviewer
        # confirms or flips; a flip cascade-rescores downstream rallies.
        low_confidence_rally_indices.append(idx)

        # Informational only (no longer gates review): track rallies that are
        # additionally low-confidence or short, for the Stage-3 summary log.
        duration_s = end_s - start_s
        if confidence < resolved_threshold or duration_s < SHORT_RALLY_REVIEW_SECONDS:
            n_low_or_short += 1

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
        last_scored_snapshot = new_snapshot

        rally = rally_manager.end_rally(
            timestamp=end_s,
            winner=winner_str,
            score_at_start=score_at_start,
            score_snapshot=new_snapshot,
        )

        rally.predicted_team = winning_team
        rally.prediction_confidence = confidence

        n_scored += 1

        game_over, _winner_team = score_state.is_game_over()
        if game_over:
            logger.info("Game over at rally %d", idx)
            game_over_flag = True
            final_score_string = score_at_start  # score string before this rally
            # Use the post-rally snapshot so the post-game score reflects the
            # winning point being scored.
            final_snapshot_for_post_game = new_snapshot
            final_score_string = score_state.get_score_string()

    # Keep low_confidence list sorted and deduplicated.
    low_confidence_rally_indices = sorted(set(low_confidence_rally_indices))
    logger.info(
        "Stage 3: flagged all %d scored rallies for human winner review "
        "(%d also low-confidence or short)",
        n_scored,
        n_low_or_short,
    )

    # Extract final score from the last pre-post-game snapshot.
    simulated_final_score: tuple[int, int] | None = None
    if last_scored_snapshot is not None:
        simulated_final_score = (
            int(last_scored_snapshot.score[0]),
            int(last_scored_snapshot.score[1]),
        )

    logger.info(
        "Stage 3 complete: %d scored + %d post-game = %d total rallies, "
        "final score %s",
        n_scored,
        n_post_game,
        n_scored + n_post_game,
        simulated_final_score,
    )

    # ------------------------------------------------------------------
    # Cancellation check BEFORE Stage 4 writes any output file.
    # ------------------------------------------------------------------
    if cancel_check is not None and cancel_check():
        raise AutoEditCancelled("Pipeline cancelled before Stage 4 output")

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
        n_detected=n_detected,
        n_scored=n_scored,
        n_post_game=n_post_game,
        fusion_unavailable_reason=fusion_unavailable_reason,
    )
