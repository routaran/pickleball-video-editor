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
                        under ~/.local/share/pickleball-editor/models/.
--json                  Emit machine-readable JSON to stdout instead of the
                        human-readable table.
--calibration           Include calibration stats (ECE) for the model
                        evaluation (requires numpy; ignored for baselines).
--device DEVICE         PyTorch device string for model inference
                        (default: "cpu").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


__all__ = ["main", "run_evaluation"]


# ---------------------------------------------------------------------------
# Default checkpoint discovery
# ---------------------------------------------------------------------------

def _default_checkpoint_search() -> Path | None:
    """Search the canonical model directory for a winner checkpoint.

    Looks in ``~/.local/share/pickleball-editor/models/`` for any file
    matching ``winner*.pt``, returning the lexicographically last one (which
    is typically the most recent epoch).

    Returns:
        Path to a checkpoint file or None if none is found.
    """
    model_dir = (
        Path.home() / ".local" / "share" / "pickleball-editor" / "models"
    )
    if not model_dir.exists():
        return None
    candidates = sorted(model_dir.glob("winner*.pt"))
    if not candidates:
        return None
    return candidates[-1]


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

    # --- load model ---
    import torch as _torch
    from ml.winner_model import load_winner_classifier
    from ml.config import WinnerModelConfig

    try:
        model = load_winner_classifier(checkpoint_path, device=device)
    except Exception as exc:  # pragma: no cover — catch-all for load errors
        print(
            f"[evaluate_winner] WARNING: failed to load checkpoint: {exc}"
            " — model evaluation skipped.",
            file=sys.stderr,
        )
        return None

    config = WinnerModelConfig()

    # --- build dataset from val examples (no augmentation) ---
    from ml.winner_dataset import WinnerDataset

    # WinnerDataset.from_rally_examples applies its own internal split logic
    # based on the examples it receives.  Since we pass only val_examples and
    # request split="val", the dataset returns all provided examples as the val
    # split.  However, the method re-runs the split logic internally, which
    # requires at least 1 video to land in the val bucket.
    #
    # To work around this cleanly: if there is only one distinct video in
    # val_examples the from_rally_examples call with split="val" will produce 0
    # records (n_val=0 when n_videos<2).  In that case we fall back to
    # split="train" to expose all records.
    distinct_videos = len({str(ex.video_path) for ex in val_examples})
    split_arg = "val" if distinct_videos >= 2 else "train"

    dataset = WinnerDataset.from_rally_examples(
        records=val_examples,
        config=config,
        split=split_arg,
        augment=False,
    )

    if len(dataset) == 0:
        print(
            "[evaluate_winner] NOTE: val dataset is empty after filtering"
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
            probs = _torch.softmax(logits, dim=1)
            preds = logits.argmax(dim=1)

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
        cal = model.get("calibration")
        if cal is not None:
            lines.append(
                f"  {'ECE':<{col_name}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{'':>{col_n}}"
                f"{cal['ece']:>{col_acc}.4f}"
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
            "When omitted the tool attempts auto-discovery under "
            "~/.local/share/pickleball-editor/models/."
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
