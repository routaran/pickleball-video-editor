"""Winner prediction evaluation CLI.

Scans a directory of ``.training.json`` label files, performs a video-wise
train/val split, evaluates all heuristic baselines, and (when a checkpoint is
available) evaluates the trained :class:`~ml.winner_model.WinnerClassifier` as
well.  Prints a comparison table or emits JSON.

Usage examples::

    # Evaluate baselines only (no checkpoint):
    python -m ml.tools.evaluate_winner --dir ~/Videos/pickleball

    # Evaluate baselines + model checkpoint:
    python -m ml.tools.evaluate_winner \\
        --dir ~/Videos/pickleball \\
        --checkpoint ~/models/winner_best.pt

    # JSON output, custom val fraction:
    python -m ml.tools.evaluate_winner \\
        --dir ~/Videos/pickleball \\
        --val-fraction 0.25 \\
        --json

CLI flags
---------
--dir DIR               Root directory to scan for .training.json files.
                        May be supplied multiple times.  Defaults to
                        ~/Videos/pickleball.
--val-fraction FLOAT    Fraction of distinct videos held out for validation
                        (default 0.2).
--checkpoint PATH       Path to a .pt WinnerClassifier checkpoint.  When
                        omitted the tool attempts to find one automatically
                        in the winner training output directories.
--json                  Emit machine-readable JSON to stdout instead of the
                        human-readable table.
--calibration           Include calibration stats (ECE) for the model
                        evaluation (requires numpy; ignored for baselines).
--device DEVICE         PyTorch device string for model inference
                        (default: "cpu").
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys
from typing import Any


__all__ = ["main", "run_evaluation"]


# ---------------------------------------------------------------------------
# Default checkpoint discovery
# ---------------------------------------------------------------------------

def _default_checkpoint_search() -> Path | None:
    """Search expected WinnerClassifier checkpoint locations.

    Uses current training defaults first:

    - ``PathConfig().checkpoints_dir / "best_winner.pt"``
    - parent directories from ``WinnerModelConfig().checkpoint_path``
      (so we still honor a default that is a file path, not only a directory)
    - ``winner*.pt`` files under those directories

    and finally falls back to the legacy user-level models directory.

    Returns:
        Path to a checkpoint file or None if none is found.
    """
    from ml.config import PathConfig, WinnerModelConfig

    checkpoints_dir = PathConfig().checkpoints_dir
    default_cfg = WinnerModelConfig()

    explicit_candidates = [checkpoints_dir / "best_winner.pt", default_cfg.checkpoint_path]
    # Candidate path may be relative (as in config default), so check both
    # as provided and as resolved against the current working directory.
    explicit_candidates.append((Path.cwd() / default_cfg.checkpoint_path).resolve())

    for candidate in explicit_candidates:
        if candidate.exists():
            return candidate

    candidate_dirs: list[Path] = [checkpoints_dir, default_cfg.checkpoint_path.parent]
    candidate_dirs.append(
        Path.home() / ".local" / "share" / "pickleball-editor" / "models"
    )

    # Deduplicate without re-ordering.
    seen: set[str] = set()
    ordered_dirs: list[Path] = []
    for model_dir in candidate_dirs:
        model_dir_key = str(model_dir)
        if model_dir_key in seen:
            continue
        seen.add(model_dir_key)
        ordered_dirs.append(model_dir)

    for model_dir in ordered_dirs:
        if not model_dir.exists():
            continue

        explicit = model_dir / "best_winner.pt"
        if explicit.exists():
            return explicit

        candidates = sorted(model_dir.glob("winner*.pt"))
        if candidates:
            return candidates[-1]

    return None



def _load_checkpoint_temperature(checkpoint_path: Path) -> float:
    """Read the calibration temperature scalar from a checkpoint dict.

    Returns ``1.0`` (no-op) when the key is absent or the file cannot be
    loaded, so old checkpoints are handled transparently.

    Args:
        checkpoint_path: Path to the ``.pt`` checkpoint file.

    Returns:
        Temperature value as a Python float.
    """
    import torch as _torch

    try:
        ckpt = _torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if isinstance(ckpt, dict):
            return float(ckpt.get("temperature", 1.0))
    except Exception:
        pass
    return 1.0


def _read_game_config_from_source_json(
    source_json_path: Path,
) -> tuple[str, str]:
    """Read game_type and victory_rules from a ``.training.json`` file.

    Falls back to ``("doubles", "11")`` with a stderr warning when the file
    does not exist or cannot be parsed.

    Args:
        source_json_path: Path to the schema-1.1 training JSON file.

    Returns:
        Two-tuple of ``(game_type, victory_rules)`` strings.
    """
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
            game_block: dict = data.get("game", {})
            game_type = game_block.get("type", "doubles")
            victory_rules = str(game_block.get("victory_rules", "11"))
            return game_type, victory_rules
        except Exception as exc:
            print(
                f"[evaluate_winner] WARNING: cannot read game config from "
                f"{source_json_path}: {exc}; falling back to doubles/11",
                file=sys.stderr,
            )
    else:
        print(
            f"[evaluate_winner] WARNING: source JSON not found: {source_json_path};"
            " falling back to doubles/11",
            file=sys.stderr,
        )
    return "doubles", "11"


def _compute_game_level_metrics(
    val_examples: list,
    all_preds: list[int],
) -> "dict[str, Any] | None":
    """Group val examples by video and compute aggregate game-level metrics.

    Groups :class:`~ml.examples.RallyExample` items by ``video_path``, sorts
    within each group by ``rally_index``, reads game config from each video's
    ``source_json_path``, and calls :func:`~ml.evaluation.game_metrics.game_score_sequence_metrics`
    per video.

    Returns ``None`` when the prediction list length does not match the
    example list length (misaligned dataset filtering).

    Args:
        val_examples: Validation :class:`~ml.examples.RallyExample` list (pre-filtered).
        all_preds:    Per-example predictions in the same order as *val_examples*.

    Returns:
        Aggregated game-level metrics dict, or ``None`` on length mismatch.
    """
    if len(all_preds) != len(val_examples):
        print(
            f"[evaluate_winner] WARNING: prediction count ({len(all_preds)}) != "
            f"val example count ({len(val_examples)}) — skipping game-level metrics.",
            file=sys.stderr,
        )
        return None

    from ml.evaluation.game_metrics import aggregate_game_metrics, game_score_sequence_metrics

    # Group example indices by video path string.
    video_groups: dict[str, list[tuple[int, int]]] = {}
    for ex_idx, ex in enumerate(val_examples):
        key = str(ex.video_path)
        if key not in video_groups:
            video_groups[key] = []
        video_groups[key].append((ex.rally_index, ex_idx))

    per_game: list[dict[str, Any]] = []

    for video_key in sorted(video_groups.keys()):
        # Sort rallies within this video by rally_index for deterministic order.
        entries = sorted(video_groups[video_key], key=lambda t: t[0])

        predicted_teams: list[int] = [all_preds[ex_idx] for _, ex_idx in entries]
        ground_truth_teams: list[int] = [
            val_examples[ex_idx].winning_team for _, ex_idx in entries
        ]

        # Read game config from the source training JSON for this video.
        first_example = val_examples[entries[0][1]]
        game_type, victory_rules = _read_game_config_from_source_json(
            first_example.source_json_path
        )

        m = game_score_sequence_metrics(
            predicted_teams, ground_truth_teams, game_type, victory_rules
        )
        per_game.append(m)

    return aggregate_game_metrics(per_game)


def _load_checkpoint_config(checkpoint_path: Path) -> "WinnerModelConfig":
    """Load persisted WinnerModelConfig metadata from a checkpoint file.

    Thin wrapper that reads the ``.pt`` file and delegates reconstruction to
    the single shared loader :func:`ml.config.load_winner_config_from_checkpoint`
    so prediction, evaluation, and auto-edit all use identical geometry/legacy
    handling.  Falls back to the default ``WinnerModelConfig`` when the file
    cannot be loaded at all.
    """
    import torch as _torch

    from ml.config import WinnerModelConfig, load_winner_config_from_checkpoint

    try:
        checkpoint = _torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception:
        return WinnerModelConfig()

    if not isinstance(checkpoint, dict):
        return WinnerModelConfig()

    return load_winner_config_from_checkpoint(
        checkpoint, checkpoint_path=checkpoint_path
    )


def _load_checkpoint_schema_version(checkpoint_path: Path) -> str:
    """Read the checkpoint schema version string, or ``"legacy"`` when absent.

    Args:
        checkpoint_path: Path to the ``.pt`` checkpoint file.

    Returns:
        The stored ``"checkpoint_schema_version"`` string, or ``"legacy"`` for
        checkpoints written before the v2.0 schema (or that cannot be loaded).
    """
    import torch as _torch

    try:
        checkpoint = _torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception:
        return "legacy"

    if isinstance(checkpoint, dict):
        version = checkpoint.get("checkpoint_schema_version")
        if isinstance(version, str):
            return version
    return "legacy"


def _config_summary(config: "WinnerModelConfig") -> dict[str, Any]:
    """Build a JSON-serialisable summary of the geometry a model evaluated with.

    Reports the effective clip window (not just the stored default) so the
    output makes clip geometry mismatches obvious.

    Args:
        config: The :class:`~ml.config.WinnerModelConfig` reconstructed from the
            checkpoint.

    Returns:
        Dict of the geometry/timing fields that affect clip extraction.
    """
    return {
        "canonical_width": config.canonical_width,
        "canonical_height": config.canonical_height,
        "fps_out": config.fps_out,
        "clip_duration_s": config.clip_duration_s,
        "effective_clip_duration_s": config.effective_clip_duration_s,
        "clip_extract_max_dim": config.clip_extract_max_dim,
        "confidence_threshold": config.confidence_threshold,
        "device": config.device,
    }


# ---------------------------------------------------------------------------
# Baseline evaluation (torch-free)
# ---------------------------------------------------------------------------

def _run_baselines(
    train_examples: list,
    val_examples: list,
) -> list[dict[str, Any]]:
    """Fit and evaluate all built-in baselines.

    Args:
        train_examples: Training split :class:`~ml.examples.RallyExample` list.
        val_examples:   Validation split list.

    Returns:
        List of result dicts, one per baseline, each containing
        ``"name"``, ``"n_total"``, ``"n_correct"``, ``"n_wrong"``,
        ``"accuracy"``.
    """
    from ml.evaluation.baselines import make_baselines, evaluate_baseline

    results: list[dict[str, Any]] = []
    for baseline in make_baselines():
        # Only MajorityClassBaseline has a fit() method; others are stateless.
        if hasattr(baseline, "fit"):
            baseline.fit(train_examples)
        metrics = evaluate_baseline(baseline, val_examples)
        results.append({"name": baseline.name, **metrics})
    return results


# ---------------------------------------------------------------------------
# Model evaluation (lazy torch import)
# ---------------------------------------------------------------------------

def _run_model(
    val_examples: list,
    checkpoint_path: Path,
    device: str,
    include_calibration: bool,
) -> dict[str, Any] | None:
    """Load and evaluate the winner classifier on the val split.

    All torch imports are deferred inside this function so that the baseline
    path works even when torch is not installed.

    Args:
        val_examples:        Validation :class:`~ml.examples.RallyExample` list.
        checkpoint_path:     Path to the ``.pt`` checkpoint.
        device:              PyTorch device string (e.g. ``"cpu"``).
        include_calibration: Whether to compute ECE calibration stats.

    Returns:
        Dictionary with model evaluation metrics, or None if the model cannot
        be loaded (file missing, torch unavailable, etc.).
    """
    # --- lazy torch availability check ---
    try:
        import torch  # noqa: F401 (presence check only here)
    except ImportError:
        print(
            "[evaluate_winner] NOTE: torch is not installed — model evaluation skipped.",
            file=sys.stderr,
        )
        return None

    if not checkpoint_path.exists():
        print(
            f"[evaluate_winner] NOTE: checkpoint not found at {checkpoint_path}"
            " — model evaluation skipped.",
            file=sys.stderr,
        )
        return None

    # --- load temperature and model ---
    import torch as _torch
    from ml.winner_model import load_winner_classifier

    # Read calibration temperature from checkpoint (1.0 for old checkpoints).
    temperature: float = _load_checkpoint_temperature(checkpoint_path)

    checkpoint_config = _load_checkpoint_config(checkpoint_path)

    try:
        model = load_winner_classifier(
            checkpoint_path,
            device=device,
            config=checkpoint_config,
        )
    except Exception as exc:  # pragma: no cover — catch-all for load errors
        print(
            f"[evaluate_winner] WARNING: failed to load checkpoint: {exc}"
            " — model evaluation skipped.",
            file=sys.stderr,
        )
        return None

    # --- build dataset from val examples (no augmentation) ---
    from ml.winner_dataset import WinnerDataset

    # Use the exact validation examples already provided by run_evaluation to
    # avoid a second video-wise split/filter pass.
    dataset = WinnerDataset._from_rally_examples_no_split(
        records=val_examples,
        config=checkpoint_config,
        split="val",
        augment=False,
    )
    if len(dataset) == 0:
        print(
            "[evaluate_winner] NOTE: val dataset is empty"
            " — model evaluation skipped.",
            file=sys.stderr,
        )
        return None

    # --- inference loop ---
    from torch.utils.data import DataLoader

    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)

    model.eval()
    all_preds: list[int] = []
    all_labels: list[int] = []
    all_confidences: list[float] = []

    with _torch.no_grad():
        for clips, labels in loader:
            clips = clips.to(device)
            logits = model(clips)
            # Apply temperature scaling before softmax so reported confidences
            # are calibrated (matches the predict_winner.py inference path).
            probs = _torch.softmax(logits / temperature, dim=1)
            preds = logits.argmax(dim=1)  # argmax is scale-invariant

            for i in range(len(preds)):
                pred = int(preds[i].item())
                label = int(labels[i].item())
                conf = float(probs[i, pred].item())
                all_preds.append(pred)
                all_labels.append(label)
                all_confidences.append(conf)

    n_total = len(all_preds)
    n_correct = sum(1 for p, l in zip(all_preds, all_labels) if p == l)
    n_wrong = n_total - n_correct
    accuracy = n_correct / n_total if n_total > 0 else 0.0

    result: dict[str, Any] = {
        "name": "winner_classifier",
        "checkpoint": str(checkpoint_path),
        "checkpoint_schema_version": _load_checkpoint_schema_version(checkpoint_path),
        "config": _config_summary(checkpoint_config),
        "temperature": round(temperature, 4),
        "n_total": n_total,
        "n_correct": n_correct,
        "n_wrong": n_wrong,
        "accuracy": accuracy,
    }

    if include_calibration and n_total > 0:
        from ml.evaluation.confidence import calibration_stats

        correct_flags = [p == l for p, l in zip(all_preds, all_labels)]
        cal = calibration_stats(all_confidences, correct_flags)
        result["calibration"] = {
            "ece": round(cal.ece, 4),
            "n_samples": cal.n_samples,
        }

    # --- game-level metrics ---
    game_metrics = _compute_game_level_metrics(val_examples, all_preds)
    if game_metrics is not None:
        result["game_metrics"] = game_metrics

    return result


# ---------------------------------------------------------------------------
# Public entry point (importable)
# ---------------------------------------------------------------------------

def run_evaluation(
    dirs: list[Path],
    val_fraction: float = 0.2,
    checkpoint: Path | None = None,
    device: str = "cpu",
    include_calibration: bool = False,
) -> dict[str, Any]:
    """Run the full evaluation and return a result dictionary.

    This function is the importable core of the CLI.  It builds the
    :class:`~ml.examples.RallyExampleIndex`, splits examples, runs baselines,
    and optionally evaluates the model.

    Args:
        dirs:                Directory paths to scan for ``.training.json`` files.
        val_fraction:        Fraction of videos held out for validation.
        checkpoint:          Path to a winner classifier checkpoint, or None to
                             skip model evaluation.
        device:              PyTorch device string for model inference.
        include_calibration: Whether to include ECE calibration in the model
                             result dict.

    Returns:
        Dictionary with keys:

        - ``"n_eligible"``    — total eligible examples.
        - ``"n_train"``       — training set size.
        - ``"n_val"``         — validation set size.
        - ``"val_fraction"``  — the val_fraction used.
        - ``"baselines"``     — list of baseline result dicts.
        - ``"model"``         — model result dict or None.
        - ``"skip_counts"``   — skip reason tallies from the index.
    """
    from ml.examples import RallyExampleIndex
    from ml.evaluation.splits import video_wise_split

    index = RallyExampleIndex(dirs=dirs)
    all_examples = index.examples

    train_examples, val_examples = video_wise_split(
        all_examples, val_fraction=val_fraction
    )

    baseline_results = _run_baselines(train_examples, val_examples)

    model_result: dict[str, Any] | None = None
    if checkpoint is not None:
        model_result = _run_model(
            val_examples, checkpoint, device, include_calibration
        )
    else:
        # Attempt auto-discovery
        discovered = _default_checkpoint_search()
        if discovered is not None:
            print(
                f"[evaluate_winner] Auto-discovered checkpoint: {discovered}",
                file=sys.stderr,
            )
            model_result = _run_model(
                val_examples, discovered, device, include_calibration
            )
        else:
            print(
                "[evaluate_winner] No checkpoint provided or discovered"
                " — baselines only.",
                file=sys.stderr,
            )

    return {
        "n_eligible": len(all_examples),
        "n_train": len(train_examples),
        "n_val": len(val_examples),
        "val_fraction": val_fraction,
        "baselines": baseline_results,
        "model": model_result,
        "skip_counts": index.skip_counts,
    }


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _render_table(result: dict[str, Any]) -> str:
    """Render the evaluation result as a human-readable text table.

    Args:
        result: Dictionary returned by :func:`run_evaluation`.

    Returns:
        Multi-line string suitable for printing to stdout.
    """
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 60)
    lines.append("  Winner Prediction Evaluation")
    lines.append("=" * 60)
    lines.append(
        f"  Eligible examples : {result['n_eligible']}"
    )
    lines.append(
        f"  Train / Val       : {result['n_train']} / {result['n_val']}"
        f"  (val_fraction={result['val_fraction']:.2f})"
    )
    skip = result.get("skip_counts") or {}
    if skip:
        skip_str = ", ".join(f"{k}={v}" for k, v in sorted(skip.items()))
        lines.append(f"  Skip counts       : {skip_str}")
    lines.append("")

    # Column widths
    col_name = 24
    col_n = 7
    col_acc = 9

    header = (
        f"  {'Baseline/Model':<{col_name}}"
        f"{'N val':>{col_n}}"
        f"{'Correct':>{col_n}}"
        f"{'Wrong':>{col_n}}"
        f"{'Accuracy':>{col_acc}}"
    )
    lines.append(header)
    lines.append("  " + "-" * (col_name + col_n + col_n + col_n + col_acc))

    def _row(r: dict[str, Any]) -> str:
        name = r["name"]
        n_total = r.get("n_total", 0)
        n_correct = r.get("n_correct", 0)
        n_wrong = r.get("n_wrong", 0)
        acc = r.get("accuracy", 0.0)
        return (
            f"  {name:<{col_name}}"
            f"{n_total:>{col_n}}"
            f"{n_correct:>{col_n}}"
            f"{n_wrong:>{col_n}}"
            f"{acc:>{col_acc}.1%}"
        )

    for b in result["baselines"]:
        lines.append(_row(b))

    model = result.get("model")
    if model is not None:
        lines.append("  " + "-" * (col_name + col_n + col_n + col_n + col_acc))
        lines.append(_row(model))
        schema_version = model.get("checkpoint_schema_version")
        cfg = model.get("config")
        if cfg is not None:
            lines.append("")
            lines.append("  --- Checkpoint config ---")
            if schema_version is not None:
                lines.append(f"  Schema version    : {schema_version}")
            lines.append(
                f"  Canonical size    : {cfg['canonical_width']}x{cfg['canonical_height']}"
            )
            lines.append(f"  FPS out           : {cfg['fps_out']}")
            lines.append(
                f"  Eff. clip dur.    : {cfg['effective_clip_duration_s']:.2f} s"
                f"  (stored {cfg['clip_duration_s']:.2f} s)"
            )
            lines.append(f"  Extract max dim   : {cfg['clip_extract_max_dim']}")
            lines.append("")
        temp = model.get("temperature")
        if temp is not None:
            lines.append(
                f"  {'Temperature':<{col_name}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{temp:>{col_acc}.4f}"
            )
        cal = model.get("calibration")
        if cal is not None:
            lines.append(
                f"  {'ECE':<{col_name}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{cal['ece']:>{col_acc}.4f}"
            )
        gm = model.get("game_metrics")
        if gm is not None:
            lines.append("")
            lines.append("  --- Game-level ---")
            lines.append(f"  Games evaluated   : {gm['n_games']}")
            lines.append(
                f"  Exact sequence    : "
                f"{gm['pct_exact_sequence']:.1%}  ({int(round(gm['pct_exact_sequence'] * gm['n_games']))} / {gm['n_games']})"
            )
            mfd = gm.get("mean_first_divergence")
            if mfd is not None:
                lines.append(f"  Mean 1st diverge  : rally {mfd:.1f}")
            else:
                lines.append("  Mean 1st diverge  : n/a (all exact)")
            lines.append(
                f"  Mean rally acc    : {gm['mean_rally_winner_accuracy']:.1%}"
            )
    else:
        lines.append("")
        lines.append(
            "  [Model] Not evaluated (no checkpoint / torch unavailable)."
        )

    lines.append("=" * 60)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluate_winner",
        description=(
            "Evaluate heuristic baselines (and optionally a trained model) "
            "on the rally winner prediction task."
        ),
    )
    parser.add_argument(
        "--dir",
        dest="dirs",
        metavar="DIR",
        action="append",
        type=Path,
        help=(
            "Root directory to scan for .training.json files. "
            "May be supplied multiple times. "
            "Defaults to ~/Videos/pickleball."
        ),
    )
    parser.add_argument(
        "--val-fraction",
        type=float,
        default=0.2,
        metavar="FLOAT",
        help="Fraction of distinct videos held out for validation (default: 0.2).",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to a .pt WinnerClassifier checkpoint. "
            "When omitted the tool attempts auto-discovery from "
            "training defaults."
        ),
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit machine-readable JSON to stdout instead of the human-readable table.",
    )
    parser.add_argument(
        "--calibration",
        action="store_true",
        help="Include ECE calibration stats for the model evaluation.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        metavar="DEVICE",
        help="PyTorch device string for model inference (default: cpu).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the evaluate_winner CLI.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 on success).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Resolve directories
    dirs: list[Path]
    if args.dirs:
        dirs = [d.expanduser().resolve() for d in args.dirs]
    else:
        dirs = [(Path.home() / "Videos" / "pickleball").resolve()]

    result = run_evaluation(
        dirs=dirs,
        val_fraction=args.val_fraction,
        checkpoint=args.checkpoint,
        device=args.device,
        include_calibration=args.calibration,
    )

    if args.emit_json:
        print(json.dumps(result, indent=2))
    else:
        print(_render_table(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
