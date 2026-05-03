"""Training script for the rally winner classifier.

Usage:
    python -m ml.train_winner --root ~/Videos/pickleball/ --epochs 50

Scans *root* recursively for schema-1.1 .training.json files, builds
train/val splits via WinnerDataset, and trains WinnerClassifier with
differential learning rates (backbone vs temporal+head).

Saves the best checkpoint to ml/checkpoints/best_winner.pt when val
accuracy improves.  Early-stopping patience is 5 epochs.
"""

import argparse
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ml.config import PathConfig, WinnerModelConfig
from ml.winner_dataset import WinnerDataset, load_winner_dataset
from ml.winner_model import WinnerClassifier


# ---------------------------------------------------------------------------
# Class-weight helper
# ---------------------------------------------------------------------------


def _compute_class_weights(dataset: WinnerDataset) -> torch.Tensor:
    """Return balanced cross-entropy weights derived from *dataset* label counts.

    Uses the inverse-frequency formula:
        w_c = n_total / (2 * n_c)

    so that the two classes contribute equally to the loss regardless of how
    many samples exist per class.

    Args:
        dataset: Training split of WinnerDataset (already partitioned).

    Returns:
        Float tensor of shape (2,) with [w_team0, w_team1].
    """
    n_team0 = sum(1 for r in dataset._records if r.winning_team == 0)
    n_team1 = sum(1 for r in dataset._records if r.winning_team == 1)

    if n_team0 == 0 or n_team1 == 0:
        # Cannot compute meaningful weights — fall back to uniform.
        return torch.ones(2, dtype=torch.float32)

    n_total = n_team0 + n_team1
    w0 = n_total / (2 * n_team0)
    w1 = n_total / (2 * n_team1)
    return torch.tensor([w0, w1], dtype=torch.float32)


# ---------------------------------------------------------------------------
# Per-epoch passes
# ---------------------------------------------------------------------------


def _train_one_epoch(
    model: WinnerClassifier,
    loader: DataLoader,
    criterion: nn.CrossEntropyLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    """Run one full training pass over *loader*.

    Args:
        model: WinnerClassifier in train mode (set by caller).
        loader: DataLoader yielding (clip_tensor, winning_team) pairs.
        criterion: CrossEntropyLoss (with class weights already embedded).
        optimizer: Adam with two parameter groups.
        device: Target compute device.

    Returns:
        Average cross-entropy loss over all batches in the epoch.
    """
    model.train()
    total_loss = 0.0
    n_samples = 0

    for clips, labels in loader:
        clips = clips.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        logits = model(clips)  # (B, 2)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(labels)
        n_samples += len(labels)

    return total_loss / n_samples if n_samples > 0 else 0.0


@torch.no_grad()
def _validate(
    model: WinnerClassifier,
    loader: DataLoader,
    device: torch.device,
) -> tuple[float, list[float], list[float], list[list[int]]]:
    """Evaluate *model* on *loader* without gradient computation.

    Computes overall accuracy, per-class precision and recall, and the
    2x2 confusion matrix.

    Confusion matrix layout:
        [[TP_0, FP_0],   <- team 0 row: correct team-0 calls, team-0 mislabelled as team-1
         [FP_1, TP_1]]   <- team 1 row: team-1 mislabelled as team-0, correct team-1 calls

    Args:
        model: WinnerClassifier (set to eval mode by caller).
        loader: DataLoader for the validation split.
        device: Target compute device.

    Returns:
        Tuple of:
        - val_accuracy: Overall fraction of correct predictions.
        - precision: [precision_team0, precision_team1]
        - recall:    [recall_team0,    recall_team1]
        - confusion_matrix: 2x2 integer counts as nested lists.
    """
    model.eval()

    # Confusion matrix cells: conf[true][pred]
    conf: list[list[int]] = [[0, 0], [0, 0]]
    total = 0
    correct = 0

    for clips, labels in loader:
        clips = clips.to(device)
        labels_np = labels.tolist()

        logits = model(clips)  # (B, 2)
        preds = logits.argmax(dim=1).cpu().tolist()

        for true_label, pred_label in zip(labels_np, preds):
            conf[true_label][pred_label] += 1
            total += 1
            if true_label == pred_label:
                correct += 1

    val_accuracy = correct / total if total > 0 else 0.0

    # Per-class precision and recall
    precision: list[float] = []
    recall: list[float] = []
    for cls in range(2):
        tp = conf[cls][cls]
        fp = sum(conf[other][cls] for other in range(2) if other != cls)
        fn = sum(conf[cls][other] for other in range(2) if other != cls)

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision.append(p)
        recall.append(r)

    # Checkpoint format: [[TP_0, FP_0], [FP_1, TP_1]]
    checkpoint_conf = [
        [conf[0][0], conf[1][0]],   # [TP_0, FP_0  (team1 misclassified as team0)]
        [conf[0][1], conf[1][1]],   # [FP_1 (team0 misclassified as team1), TP_1]
    ]

    return val_accuracy, precision, recall, checkpoint_conf


# ---------------------------------------------------------------------------
# Main training function
# ---------------------------------------------------------------------------


def train_winner(
    root_dir: Path,
    epochs: int = 50,
    batch_size: int = 8,
    device_str: str = "cuda",
) -> None:
    """Train WinnerClassifier and save the best checkpoint.

    Loads train and val splits from *root_dir*, applies balanced class
    weights, trains with differential learning rates (backbone 1e-4,
    temporal+head 1e-3), and saves best checkpoint by val accuracy.

    Args:
        root_dir: Directory to scan recursively for .training.json files.
        epochs: Maximum number of training epochs.
        batch_size: Mini-batch size for both DataLoaders.
        device_str: PyTorch device string (e.g. "cuda", "cpu").
    """
    # ---- Device ----
    if device_str.startswith("cuda") and not torch.cuda.is_available():
        print(f"Warning: CUDA requested but unavailable. Falling back to CPU.")
        device_str = "cpu"
    device = torch.device(device_str)
    print(f"Device: {device}")

    # ---- Paths ----
    paths = PathConfig()
    checkpoint_path = paths.checkpoints_dir / "best_winner.pt"

    # ---- Data ----
    model_cfg = WinnerModelConfig()
    print("\n=== Loading datasets ===")
    train_dataset = load_winner_dataset(root_dir, model_cfg, split="train")
    val_dataset = load_winner_dataset(root_dir, model_cfg, split="val")

    if len(train_dataset) == 0:
        print("No training samples found. Verify .training.json files meet schema 1.1 requirements.")
        sys.exit(1)

    if len(val_dataset) == 0:
        print("No validation samples found. Need at least 2 videos for a train/val split.")
        sys.exit(1)

    # Label distribution
    n_team0 = sum(1 for r in train_dataset._records if r.winning_team == 0)
    n_team1 = sum(1 for r in train_dataset._records if r.winning_team == 1)
    print(f"Train samples: {len(train_dataset)} (team0={n_team0}, team1={n_team1})")
    print(f"Val   samples: {len(val_dataset)}")

    # ---- Class weights ----
    weights = _compute_class_weights(train_dataset)
    print(f"Class weights: team0={weights[0]:.3f}, team1={weights[1]:.3f}")

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=4,
        pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=(device.type == "cuda"),
    )

    # ---- Model ----
    model = WinnerClassifier().to(device)
    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Model parameters: {param_count:,}")

    # ---- Loss ----
    loss_fn = nn.CrossEntropyLoss(weight=weights.to(device))

    # ---- Optimizer: differential learning rates ----
    optimizer = torch.optim.Adam([
        {"params": model.backbone.parameters(), "lr": 1e-4},
        {
            "params": list(model.temporal.parameters()) + list(model.head.parameters()),
            "lr": 1e-3,
        },
    ])

    # ---- Training loop ----
    paths.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    best_val_acc: float = -1.0
    patience_counter = 0
    early_stop_patience = 5

    print("\n=== Training ===")
    header = (
        f"{'Epoch':>5} | {'Train Loss':>10} | "
        f"{'Val Acc':>7} | "
        f"{'P0':>6} {'R0':>6} | {'P1':>6} {'R1':>6}"
    )
    print(header)
    print("-" * len(header))

    for epoch in range(1, epochs + 1):
        train_loss = _train_one_epoch(model, train_loader, loss_fn, optimizer, device)
        val_acc, precision, recall, conf_matrix = _validate(model, val_loader, device)

        print(
            f"{epoch:5d} | {train_loss:10.4f} | "
            f"{val_acc:6.1%} | "
            f"{precision[0]:6.3f} {recall[0]:6.3f} | "
            f"{precision[1]:6.3f} {recall[1]:6.3f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0

            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_accuracy": best_val_acc,
                    "val_per_class_precision": precision,
                    "val_per_class_recall": recall,
                    "confusion_matrix": conf_matrix,
                },
                checkpoint_path,
            )

            print(f"       New best saved  (val_acc={best_val_acc:.1%})")
            print(
                f"       Confusion matrix: "
                f"[[{conf_matrix[0][0]}, {conf_matrix[0][1]}], "
                f"[{conf_matrix[1][0]}, {conf_matrix[1][1]}]]"
            )
        else:
            patience_counter += 1
            if patience_counter >= early_stop_patience:
                print(
                    f"\nEarly stopping after {epoch} epochs "
                    f"(patience={early_stop_patience})"
                )
                break

    print(f"\nBest checkpoint saved to: {checkpoint_path}")
    print(f"Best val accuracy: {best_val_acc:.1%}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and invoke train_winner()."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.train_winner",
        description="Train the rally winner classifier (WinnerClassifier).",
    )
    parser.add_argument(
        "--root",
        type=str,
        required=True,
        help="Root directory containing .training.json files (searched recursively)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Maximum number of training epochs (default: 50)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Mini-batch size (default: 8)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        help='Compute device, e.g. "cuda", "cuda:1", "cpu" (default: cuda)',
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
