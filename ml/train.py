"""Training script for the rally detection model.

Usage:
    python -m ml.train --data-dir ~/Videos/pickleball/

Finds all .training.json files under the data directory, prepares
spectrograms (cached), splits by video into train/val sets, and
trains the CNN classifier.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader

from ml.config import AudioConfig, TrainConfig, PathConfig
from ml.dataset import prepare_all, RallyDataset
from ml.model import RallyDetector


def compute_class_weight(labels_list: list[np.ndarray]) -> float:
    """Compute positive class weight for imbalanced binary labels.

    Returns the ratio of negative to positive samples, used as
    pos_weight in BCEWithLogitsLoss to handle class imbalance.

    Args:
        labels_list: List of per-sample label arrays

    Returns:
        Weight for the positive class (>1 means upweight positives)
    """
    total_pos = sum(labels.sum() for labels in labels_list)
    total_neg = sum(len(labels) - labels.sum() for labels in labels_list)

    if total_pos == 0:
        return 1.0

    return float(total_neg / total_pos)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    """Train for one epoch.

    Returns:
        Tuple of (average_loss, accuracy)
    """
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for windows, labels in loader:
        windows = windows.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        logits = model(windows).squeeze(1)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(labels)
        preds = (logits > 0).float()
        correct += (preds == labels).sum().item()
        total += len(labels)

    return total_loss / total, correct / total


@torch.no_grad()
def validate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float, float, float]:
    """Run validation.

    Returns:
        Tuple of (loss, accuracy, precision, recall)
    """
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    tp = 0
    fp = 0
    fn = 0

    for windows, labels in loader:
        windows = windows.to(device)
        labels = labels.to(device)

        logits = model(windows).squeeze(1)
        loss = criterion(logits, labels)

        total_loss += loss.item() * len(labels)
        preds = (logits > 0).float()
        correct += (preds == labels).sum().item()
        total += len(labels)

        tp += ((preds == 1) & (labels == 1)).sum().item()
        fp += ((preds == 1) & (labels == 0)).sum().item()
        fn += ((preds == 0) & (labels == 1)).sum().item()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return total_loss / total, correct / total, precision, recall


def main() -> None:
    parser = argparse.ArgumentParser(description="Train rally detection model")
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory containing .training.json files (searched recursively)",
    )
    parser.add_argument("--epochs", type=int, default=None, help="Override number of epochs")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--lr", type=float, default=None, help="Override learning rate")
    parser.add_argument(
        "--val-dir",
        type=str,
        default=None,
        help=(
            "Directory containing .training.json files to use as a fixed validation "
            "set instead of the internal train_test_split. When given, all files "
            "found under --data-dir are used for training."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Random seed for Python/NumPy/PyTorch and train_test_split. "
            "When omitted, the default seed of 42 is used for train_test_split "
            "but torch/numpy are not explicitly seeded."
        ),
    )
    args = parser.parse_args()

    audio_cfg = AudioConfig()
    train_cfg = TrainConfig()
    paths = PathConfig()

    if args.epochs is not None:
        train_cfg.epochs = args.epochs
    if args.batch_size is not None:
        train_cfg.batch_size = args.batch_size
    if args.lr is not None:
        train_cfg.learning_rate = args.lr

    # ------------------------------------------------------------------
    # Seed setup — must happen before any random operations.
    # ------------------------------------------------------------------
    _seed = args.seed if args.seed is not None else 42
    if args.seed is not None:
        import random as _random  # noqa: PLC0415 — intentional local import
        _random.seed(_seed)
        np.random.seed(_seed)
        torch.manual_seed(_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(_seed)
        print(f"Seed: {_seed} (explicit --seed)")
    else:
        print(f"Seed: {_seed} (default, torch/numpy not explicitly seeded)")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ------------------------------------------------------------------
    # Prepare data
    # ------------------------------------------------------------------
    print("\n=== Preparing data ===")
    spectrograms, labels_list, video_ids = prepare_all(
        args.data_dir, audio_cfg, paths
    )

    # ------------------------------------------------------------------
    # Train/val split
    # ------------------------------------------------------------------
    if args.val_dir is not None:
        # Fixed external validation set — use all of --data-dir for training.
        val_dir_path = Path(args.val_dir).expanduser().resolve()
        if not val_dir_path.exists():
            print(f"Error: --val-dir directory not found: {val_dir_path}", file=sys.stderr)
            sys.exit(1)

        print(f"\n=== Preparing fixed val set from {val_dir_path} ===")
        val_specs, val_labels, val_video_ids = prepare_all(val_dir_path, audio_cfg, paths)

        if len(val_specs) == 0:
            print("Error: --val-dir contains no usable training files", file=sys.stderr)
            sys.exit(1)

        if len(spectrograms) == 0:
            print("Error: --data-dir contains no usable training files", file=sys.stderr)
            sys.exit(1)

        train_specs = spectrograms
        train_labels = labels_list
        train_video_ids = video_ids

        print(f"\nVal source   : {val_dir_path}  (fixed, --val-dir)")
        print(f"Train videos ({len(train_video_ids)}): {train_video_ids}")
        print(f"Val videos   ({len(val_video_ids)}): {val_video_ids}")
    else:
        if len(spectrograms) < 2:
            print("Need at least 2 videos to create train/val split")
            sys.exit(1)

        # Split by video index (no data leakage between train and val)
        indices = list(range(len(spectrograms)))
        train_idx, val_idx = train_test_split(
            indices,
            test_size=train_cfg.val_fraction,
            random_state=_seed,
        )

        train_video_ids = [video_ids[i] for i in train_idx]
        val_video_ids = [video_ids[i] for i in val_idx]
        print(f"\nVal source   : internal train_test_split (seed={_seed})")
        print(f"Train videos ({len(train_idx)}): {train_video_ids}")
        print(f"Val videos   ({len(val_idx)}): {val_video_ids}")

        train_specs = [spectrograms[i] for i in train_idx]
        train_labels = [labels_list[i] for i in train_idx]
        val_specs = [spectrograms[i] for i in val_idx]
        val_labels = [labels_list[i] for i in val_idx]

    # Create datasets
    train_dataset = RallyDataset(train_specs, train_labels, audio_cfg)
    val_dataset = RallyDataset(val_specs, val_labels, audio_cfg)

    print(f"\nTrain windows: {len(train_dataset)}")
    print(f"Val windows: {len(val_dataset)}")

    # Class balance
    pos_weight_val = compute_class_weight(train_labels)
    print(f"Positive class weight: {pos_weight_val:.2f}")

    train_loader = DataLoader(
        train_dataset,
        batch_size=train_cfg.batch_size,
        shuffle=True,
        num_workers=train_cfg.num_workers,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=train_cfg.batch_size,
        shuffle=False,
        num_workers=train_cfg.num_workers,
        pin_memory=True,
    )

    # Model, loss, optimizer
    model = RallyDetector(audio_cfg).to(device)
    pos_weight = torch.tensor([pos_weight_val], device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=train_cfg.learning_rate,
        weight_decay=train_cfg.weight_decay,
    )

    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nModel parameters: {param_count:,}")

    # Training loop
    paths.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    patience_counter = 0

    print("\n=== Training ===")
    print(f"{'Epoch':>5} | {'Train Loss':>10} {'Train Acc':>9} | {'Val Loss':>8} {'Val Acc':>7} {'Prec':>6} {'Recall':>6}")
    print("-" * 72)

    for epoch in range(1, train_cfg.epochs + 1):
        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device
        )
        val_loss, val_acc, val_prec, val_recall = validate(
            model, val_loader, criterion, device
        )

        print(
            f"{epoch:5d} | {train_loss:10.4f} {train_acc:8.1%} | "
            f"{val_loss:8.4f} {val_acc:6.1%} {val_prec:6.3f} {val_recall:6.3f}"
        )

        # Checkpointing
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "val_loss": val_loss,
                    "val_acc": val_acc,
                    "val_precision": val_prec,
                    "val_recall": val_recall,
                    "audio_config": {
                        "sample_rate": audio_cfg.sample_rate,
                        "n_mels": audio_cfg.n_mels,
                        "n_fft": audio_cfg.n_fft,
                        "hop_length": audio_cfg.hop_length,
                        "window_seconds": audio_cfg.window_seconds,
                    },
                },
                paths.best_model_path,
            )
            print(f"       ↑ saved best model (val_loss={val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= train_cfg.early_stop_patience:
                print(f"\nEarly stopping after {epoch} epochs (patience={train_cfg.early_stop_patience})")
                break

    print(f"\nBest model saved to: {paths.best_model_path}")
    print(f"Best val loss: {best_val_loss:.4f}")


if __name__ == "__main__":
    main()
