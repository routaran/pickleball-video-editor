"""Training script for the rally winner classifier.

Usage:
    python -m ml.train_winner --root ~/Videos/pickleball/ --epochs 50

Scans *root* recursively for schema-1.1 .training.json files, builds
train/val splits via WinnerDataset, and trains WinnerClassifier with
differential learning rates (backbone vs temporal+head).

Saves the best checkpoint to ml/checkpoints/best_winner.pt when val
accuracy improves.  Early-stopping patience is 5 epochs.

Checkpoint metadata
-------------------
The saved ``.pt`` dict now includes a ``"config"`` sub-dict containing the
serialised ``WinnerModelConfig`` fields (including ``effective_clip_duration_s``)
so that loaders can detect config mismatches.  See :func:`_config_to_dict`.
"""

import argparse
import dataclasses
import random
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset

from ml.config import PathConfig, WinnerModelConfig
from ml.winner_dataset import WinnerDataset, load_winner_dataset
from ml.winner_model import WinnerClassifier


# ---------------------------------------------------------------------------
# Config serialisation (E2 — checkpoint metadata)
# ---------------------------------------------------------------------------


def _config_to_dict(cfg: WinnerModelConfig) -> dict:
    """Serialise *cfg* to a plain dict suitable for inclusion in a checkpoint.

    All dataclass fields are stored by name, with ``Path`` objects converted to
    strings so ``torch.save`` / ``torch.load`` round-trips cleanly.
    ``effective_clip_duration_s`` (the ablation-aware active clip window) is
    also captured so that the checkpoint is self-documenting regardless of
    whether an override was active at training time.

    Args:
        cfg: WinnerModelConfig instance used during this training run.

    Returns:
        Dict with one key per dataclass field, plus
        ``"effective_clip_duration_s"`` for the active clip window.
    """
    raw: dict = {}
    for f in dataclasses.fields(cfg):
        value = getattr(cfg, f.name)
        if isinstance(value, Path):
            value = str(value)
        raw[f.name] = value
    # Store the ablation-aware value explicitly so loaders see the actual window.
    raw["effective_clip_duration_s"] = cfg.effective_clip_duration_s
    return raw


# ---------------------------------------------------------------------------
# Per-video validation report (E1)
# ---------------------------------------------------------------------------


@torch.no_grad()
def _per_video_validate(
    model: WinnerClassifier,
    val_dataset: WinnerDataset,
    device: torch.device,
    batch_size: int = 8,
) -> list[dict]:
    """Compute per-video validation accuracy over *val_dataset*.

    Groups all rally records by their source video path, runs inference for
    each group, and returns one summary row per video.  This makes it easy to
    spot videos where the model is over- or under-fitting.

    Args:
        model: WinnerClassifier in eval mode (caller is responsible for mode).
        val_dataset: Validation split whose ``_records`` carry ``video_path``.
        device: Target compute device.
        batch_size: Clips to process in each forward pass.

    Returns:
        List of dicts, one per video, each containing:
        ``{"video": str, "n_total": int, "n_correct": int, "accuracy": float}``.
        Sorted by ``video`` key for stable output.
    """
    model.eval()

    # Group record indices by video path string.
    video_to_indices: dict[str, list[int]] = {}
    for idx, record in enumerate(val_dataset._records):
        key = str(record.video_path)
        if key not in video_to_indices:
            video_to_indices[key] = []
        video_to_indices[key].append(idx)

    report: list[dict] = []

    for video_key in sorted(video_to_indices.keys()):
        indices = video_to_indices[video_key]
        subset = Subset(val_dataset, indices)
        loader = DataLoader(
            subset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,  # avoid forking inside a worker context
        )

        n_total = 0
        n_correct = 0
        for clips, labels in loader:
            clips = clips.to(device)
            labels_list: list[int] = labels.tolist()
            logits = model(clips)
            preds: list[int] = logits.argmax(dim=1).cpu().tolist()
            for true_label, pred_label in zip(labels_list, preds):
                n_total += 1
                if true_label == pred_label:
                    n_correct += 1

        acc = n_correct / n_total if n_total > 0 else 0.0
        report.append(
            {
                "video": video_key,
                "n_total": n_total,
                "n_correct": n_correct,
                "accuracy": acc,
            }
        )

    return report


def _print_per_video_report(report: list[dict]) -> None:
    """Print the per-video validation report to stdout.

    Args:
        report: List of dicts as returned by :func:`_per_video_validate`.
    """
    if not report:
        print("       (no per-video data — val dataset is empty)")
        return

    print("\n--- Per-video validation ---")
    col_w = max(len(r["video"]) for r in report)
    header = f"  {'Video':<{col_w}}  {'Total':>6}  {'Correct':>7}  {'Acc':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in report:
        short = Path(row["video"]).name
        print(
            f"  {short:<{col_w}}  {row['n_total']:>6}  {row['n_correct']:>7}"
            f"  {row['accuracy']:>6.1%}"
        )
    print()


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


def _print_batch_sanity(clips: torch.Tensor, labels: torch.Tensor) -> None:
    """Print concise sanity stats for a sampled training batch."""
    label_counts = torch.bincount(labels.to(torch.int64), minlength=2)
    batch_n = int(label_counts.sum())
    n_team0 = int(label_counts[0].item())
    n_team1 = int(label_counts[1].item())
    p0 = n_team0 / batch_n if batch_n else 0.0
    p1 = n_team1 / batch_n if batch_n else 0.0

    print(
        f"       Batch sanity: intensity(min/mean/max)="
        f"{clips.min().item():.4f}/{clips.mean().item():.4f}/{clips.max().item():.4f} "
        f"| labels: team0={n_team0} ({p0:.1%}) "
        f"team1={n_team1} ({p1:.1%})"
    )


# ---------------------------------------------------------------------------
# Temperature scaling helpers
# ---------------------------------------------------------------------------


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor) -> float:
    """Fit a scalar temperature T on held-out logits via cross-entropy minimisation.

    Optimises ``log_T`` with LBFGS (50 iterations) so the procedure is fast and
    deterministic.  The resulting ``T = exp(log_T)`` is clamped to ``[0.05, 20]``
    to prevent degenerate solutions.

    A well-calibrated model returns T ≈ 1.  An overconfident model (softmax
    probabilities too extreme) returns T > 1.  An underconfident model returns
    T < 1.

    Args:
        logits: Raw (uncalibrated) model logits, shape ``(N, C)``.
        labels: Ground-truth integer class labels, shape ``(N,)``.

    Returns:
        Fitted temperature scalar as a Python float.  Returns ``1.0`` for empty
        inputs.
    """
    if logits.numel() == 0 or labels.numel() == 0:
        return 1.0

    logits = logits.float().detach()
    labels = labels.long().detach()

    log_t = torch.zeros(1, requires_grad=True)
    optimizer = torch.optim.LBFGS([log_t], lr=0.1, max_iter=50)

    def _closure() -> torch.Tensor:
        optimizer.zero_grad()
        t = log_t.exp().clamp(0.05, 20.0)
        loss = F.cross_entropy(logits / t, labels)
        loss.backward()
        return loss

    optimizer.step(_closure)

    fitted_t = float(log_t.exp().clamp(0.05, 20.0).item())
    return fitted_t


@torch.no_grad()
def _collect_val_logits_labels(
    model: WinnerClassifier,
    loader: DataLoader,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Collect raw logits and ground-truth labels from a validation DataLoader.

    Unlike :func:`_validate`, this function returns the raw logits so that
    temperature scaling can be fitted on them.

    Args:
        model: WinnerClassifier set to eval mode by the caller.
        loader: DataLoader for the validation split.
        device: Target compute device.

    Returns:
        Tuple of ``(logits, labels)`` as CPU tensors concatenated across all
        batches.  Returns ``(empty (0,2), empty (0,))`` when the loader is
        empty.
    """
    model.eval()
    all_logits: list[torch.Tensor] = []
    all_labels: list[torch.Tensor] = []

    for clips, labels in loader:
        clips = clips.to(device)
        raw_logits = model(clips)  # (B, 2)
        all_logits.append(raw_logits.cpu())
        all_labels.append(labels.cpu())

    if not all_logits:
        return torch.empty(0, 2), torch.empty(0, dtype=torch.long)

    return torch.cat(all_logits, dim=0), torch.cat(all_labels, dim=0)


# ---------------------------------------------------------------------------
# Per-epoch passes
# ---------------------------------------------------------------------------


def _train_one_epoch(
    model: WinnerClassifier,
    loader: DataLoader,
    criterion: nn.CrossEntropyLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    log_batch_sanity: bool = False,
) -> float:
    """Run one full training pass over *loader*.

    Args:
        model: WinnerClassifier in train mode (set by caller).
        loader: DataLoader yielding (clip_tensor, winning_team) pairs.
        criterion: CrossEntropyLoss (with class weights already embedded).
        optimizer: Adam with two parameter groups.
        device: Target compute device.
        log_batch_sanity: If True, print statistics for the first batch only.

    Returns:
        Average cross-entropy loss over all batches in the epoch.
    """
    model.train()
    total_loss = 0.0
    n_samples = 0

    for batch_idx, (clips, labels) in enumerate(loader):
        clips = clips.to(device)
        labels = labels.to(device)

        if log_batch_sanity and batch_idx == 0:
            _print_batch_sanity(clips, labels)

        optimizer.zero_grad()
        logits = model(clips)  # (B, 2)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(labels)
        n_samples += len(labels)

    return total_loss / n_samples if n_samples > 0 else 0.0


def _train_one_epoch_accum(
    model: WinnerClassifier,
    loader: DataLoader,
    criterion: nn.CrossEntropyLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    grad_accum_steps: int = 1,
    scaler: "torch.cuda.amp.GradScaler | None" = None,
    log_batch_sanity: bool = False,
) -> float:
    """Run one full training pass with optional gradient accumulation and AMP.

    When *grad_accum_steps* > 1, the optimizer step is called only after every
    ``grad_accum_steps`` micro-batches (or at the end of the epoch).  The loss
    is divided by *grad_accum_steps* so accumulated gradients match the mean
    over the effective batch.

    Note: ResNet-18 BatchNorm stats are computed per micro-batch, so gradient
    accumulation does not fully replicate true large-batch BatchNorm training.

    Args:
        model: WinnerClassifier in train mode (set by caller).
        loader: DataLoader yielding (clip_tensor, winning_team) pairs.
        criterion: CrossEntropyLoss (with class weights already embedded).
        optimizer: Optimizer with one or more parameter groups.
        device: Target compute device.
        grad_accum_steps: Accumulate gradients over this many micro-batches.
        scaler: GradScaler for AMP, or None for standard (FP32) training.
        log_batch_sanity: If True, print statistics for the first batch only.

    Returns:
        Average cross-entropy loss over all batches in the epoch.
    """
    model.train()
    total_loss = 0.0
    n_samples = 0
    accum_steps = max(grad_accum_steps, 1)

    optimizer.zero_grad()

    for batch_idx, (clips, labels) in enumerate(loader):
        clips = clips.to(device)
        labels = labels.to(device)

        if log_batch_sanity and batch_idx == 0:
            _print_batch_sanity(clips, labels)

        if scaler is not None:
            with torch.cuda.amp.autocast():
                logits = model(clips)
                loss = criterion(logits, labels) / accum_steps
            scaler.scale(loss).backward()
        else:
            logits = model(clips)
            loss = criterion(logits, labels) / accum_steps
            loss.backward()

        # Undo the division for loss tracking so reported loss reflects
        # the actual per-sample cross-entropy, not the scaled value.
        total_loss += loss.item() * accum_steps * len(labels)
        n_samples += len(labels)

        is_last_batch = (batch_idx + 1) == len(loader)
        should_step = ((batch_idx + 1) % accum_steps == 0) or is_last_batch

        if should_step:
            if scaler is not None:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            optimizer.zero_grad()

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


def _seed_everything(seed: int) -> None:
    """Seed Python random, NumPy, and PyTorch for reproducibility.

    Does not guarantee perfect determinism: CUDA/cuDNN may remain
    nondeterministic depending on operations and hardware settings.

    Args:
        seed: Integer seed value.
    """
    random.seed(seed)
    try:
        import numpy as np  # noqa: PLC0415

        np.random.seed(seed)
    except ModuleNotFoundError:
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train_winner(
    root_dir: Path,
    epochs: int = 50,
    batch_size: int = 8,
    device_str: str = "cuda",
    *,
    model_config: WinnerModelConfig | None = None,
    checkpoint_out: Path | None = None,
    seed: int | None = None,
    grad_accum_steps: int = 1,
    num_workers: int = 4,
    amp: bool = False,
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
        model_config: WinnerModelConfig controlling clip geometry, fps, and
            extraction resolution.  When ``None`` the default config is used,
            preserving existing behaviour.
        checkpoint_out: Where to write the best checkpoint.  When ``None``
            the default ``PathConfig().checkpoints_dir / "best_winner.pt"``
            is used.  Parent directories are created as needed.
        seed: When not ``None``, seed Python random, NumPy, and PyTorch
            before training begins for reproducibility.
        grad_accum_steps: Accumulate gradients over this many micro-batches
            before calling optimizer.step().  Default 1 = standard training.
            Note: ResNet BatchNorm stats are computed per micro-batch, so
            gradient accumulation does not fully replicate true large-batch
            training.
        num_workers: Number of DataLoader worker processes.  Default 4.
        amp: Enable automatic mixed precision (AMP) with gradient scaling.
            Only active when the resolved device is CUDA; silently ignored on
            CPU with a warning.
    """
    # ---- Seed ----
    if seed is not None:
        _seed_everything(seed)

    # ---- Device ----
    if device_str.startswith("cuda") and not torch.cuda.is_available():
        print(f"Warning: CUDA requested but unavailable. Falling back to CPU.")
        device_str = "cpu"
    device = torch.device(device_str)
    print(f"Device: {device}")

    # ---- AMP setup ----
    use_amp = amp and device.type == "cuda"
    if amp and not use_amp:
        print("Warning: --amp requested but device is CPU; AMP disabled.")
    scaler: torch.cuda.amp.GradScaler | None = (
        torch.cuda.amp.GradScaler() if use_amp else None
    )

    # ---- Paths ----
    paths = PathConfig()
    if checkpoint_out is not None:
        checkpoint_path = checkpoint_out.expanduser().resolve()
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        checkpoint_path = paths.checkpoints_dir / "best_winner.pt"

    # ---- Config ----
    # E3: WinnerModelConfig.effective_clip_duration_s honours clip_duration_override_s
    # so ablation experiments automatically propagate to the dataset pipeline and
    # to the metadata saved in the checkpoint.
    model_cfg = model_config if model_config is not None else WinnerModelConfig()
    print("\n=== Loading datasets ===")
    print(
        f"Clip window: {model_cfg.effective_clip_duration_s:.2f}s "
        f"(clip_duration_s={model_cfg.clip_duration_s:.2f}s"
        + (
            f", override={model_cfg.clip_duration_override_s:.2f}s"
            if model_cfg.clip_duration_override_s is not None
            else ""
        )
        + ")"
    )
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
        num_workers=num_workers,
        pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
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

    effective_batch = batch_size * max(grad_accum_steps, 1)
    print(f"\nTraining settings:")
    print(f"  seed            : {seed}")
    print(f"  batch_size      : {batch_size}")
    print(f"  grad_accum_steps: {grad_accum_steps}")
    print(f"  effective_batch : {effective_batch}")
    print(f"  num_workers     : {num_workers}")
    print(f"  amp             : {use_amp}")
    print(f"  checkpoint_out  : {checkpoint_path}")

    print("\n=== Training ===")
    header = (
        f"{'Epoch':>5} | {'Train Loss':>10} | "
        f"{'Val Acc':>7} | "
        f"{'P0':>6} {'R0':>6} | {'P1':>6} {'R1':>6}"
    )
    print(header)
    print("-" * len(header))

    for epoch in range(1, epochs + 1):
        train_loss = _train_one_epoch_accum(
            model,
            train_loader,
            loss_fn,
            optimizer,
            device,
            grad_accum_steps=grad_accum_steps,
            scaler=scaler,
            log_batch_sanity=(epoch == 1),
        )
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

            # E2: embed WinnerModelConfig metadata so loaders can detect
            # config mismatches.  Stored under the "config" key so that
            # old-format checkpoints (without "config") remain distinguishable.
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_accuracy": best_val_acc,
                    "val_per_class_precision": precision,
                    "val_per_class_recall": recall,
                    "confusion_matrix": conf_matrix,
                    "config": _config_to_dict(model_cfg),
                },
                checkpoint_path,
            )

            print(f"       New best saved  (val_acc={best_val_acc:.1%})")
            print(
                f"       Confusion matrix: "
                f"[[{conf_matrix[0][0]}, {conf_matrix[0][1]}], "
                f"[{conf_matrix[1][0]}, {conf_matrix[1][1]}]]"
            )
            # E1: per-video breakdown at each new-best checkpoint so overfitting
            # to specific videos surfaces immediately in the training log.
            per_video_report = _per_video_validate(model, val_dataset, device, batch_size)
            _print_per_video_report(per_video_report)
        else:
            patience_counter += 1
            if patience_counter >= early_stop_patience:
                print(
                    f"\nEarly stopping after {epoch} epochs "
                    f"(patience={early_stop_patience})"
                )
                break

    # E1: per-video validation report — run once after training completes so
    # per-video overfitting is visible even when per-epoch output scrolls past.
    print("\n=== Per-video validation (final epoch) ===")
    per_video = _per_video_validate(model, val_dataset, device, batch_size)
    _print_per_video_report(per_video)

    # ---- Temperature scaling ----
    # Reload the best checkpoint weights, collect val logits, and fit a scalar
    # temperature T that minimises cross-entropy of logits/T on the val set.
    # The fitted T is stored back in the checkpoint so predict_winner can apply
    # it at inference time for calibrated confidence values.
    print("\n=== Temperature scaling ===")
    if best_val_acc > -1.0 and checkpoint_path.exists():
        best_ckpt: dict = torch.load(checkpoint_path, map_location=device, weights_only=True)
        model.load_state_dict(best_ckpt["model_state_dict"])
        model.eval()

        val_logits, val_labels = _collect_val_logits_labels(model, val_loader, device)

        if val_logits.numel() > 0:
            nll_before = float(F.cross_entropy(val_logits, val_labels).item())

            temperature = fit_temperature(val_logits, val_labels)

            nll_after = float(F.cross_entropy(val_logits / temperature, val_labels).item())
            print(f"Fitted temperature : {temperature:.4f}")
            print(f"Val NLL            : before={nll_before:.4f}  after={nll_after:.4f}")

            # Optional ECE reporting when calibration module is available.
            try:
                from ml.evaluation.confidence import calibration_stats  # noqa: PLC0415

                probs_before = torch.softmax(val_logits, dim=1)
                preds_before = probs_before.argmax(dim=1)
                confs_before = probs_before.max(dim=1).values.tolist()
                correct_flags = (preds_before == val_labels).tolist()
                cal_before = calibration_stats(confs_before, correct_flags)

                probs_after = torch.softmax(val_logits / temperature, dim=1)
                confs_after = probs_after.max(dim=1).values.tolist()
                cal_after = calibration_stats(confs_after, correct_flags)

                print(
                    f"Val ECE            : before={cal_before.ece:.4f}"
                    f"  after={cal_after.ece:.4f}"
                )
            except Exception:
                pass  # calibration reporting is best-effort

            best_ckpt["temperature"] = temperature
            torch.save(best_ckpt, checkpoint_path)
            print(f"Checkpoint re-saved with temperature={temperature:.4f}")
        else:
            print("Val set empty — storing temperature=1.0")
            best_ckpt["temperature"] = 1.0
            torch.save(best_ckpt, checkpoint_path)
    else:
        print("No best checkpoint available — skipping temperature scaling")

    print(f"Best checkpoint saved to: {checkpoint_path}")
    print(f"Best val accuracy: {best_val_acc:.1%}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _add_train_winner_args(parser: argparse.ArgumentParser) -> None:
    """Register all train-winner CLI arguments on *parser*.

    Shared between the standalone ``python -m ml.train_winner`` entry point and
    the ``python -m ml train-winner`` subcommand so both surfaces stay in sync.

    Args:
        parser: ArgumentParser (or sub-parser) to add arguments to.
    """
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
    # ---- Clip geometry ----
    parser.add_argument(
        "--canonical-width",
        type=int,
        default=None,
        help="Model input width in pixels after court homography warp (default: 256)",
    )
    parser.add_argument(
        "--canonical-height",
        type=int,
        default=None,
        help="Model input height in pixels after court homography warp (default: 128)",
    )
    parser.add_argument(
        "--clip-duration-s",
        type=float,
        default=None,
        help="Duration of the video clip fed to the model, in seconds (default: 2.5)",
    )
    parser.add_argument(
        "--fps-out",
        type=int,
        default=None,
        help="Frame sampling rate fed to the model in fps (default: 8)",
    )
    parser.add_argument(
        "--clip-extract-max-dim",
        type=int,
        default=None,
        help=(
            "Maximum long-side dimension for source frame extraction before warp "
            "(default: 640). Increasing this retains more far-side detail."
        ),
    )
    # ---- Checkpoint output ----
    parser.add_argument(
        "--checkpoint-out",
        type=str,
        default=None,
        help=(
            "Path to write the best checkpoint. ~ and relative paths are expanded. "
            "Parent directories are created as needed. "
            "Default: ml/checkpoints/best_winner.pt"
        ),
    )
    # ---- Reproducibility ----
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Integer seed for Python random, NumPy, and PyTorch. "
            "CUDA/cuDNN may remain nondeterministic. (default: no seeding)"
        ),
    )
    # ---- Optimization ----
    parser.add_argument(
        "--grad-accum-steps",
        type=int,
        default=1,
        help=(
            "Accumulate gradients over this many micro-batches before stepping the "
            "optimizer. Effective batch = batch-size * grad-accum-steps. "
            "ResNet BatchNorm caveats apply. (default: 1)"
        ),
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=4,
        help="DataLoader worker processes (default: 4)",
    )
    parser.add_argument(
        "--amp",
        action="store_true",
        default=False,
        help=(
            "Enable automatic mixed precision (AMP) with gradient scaling. "
            "Only active on CUDA; silently ignored on CPU."
        ),
    )
    # ---- Manifest placeholders (accepted but not yet used — Phase 3 owns these) ----
    parser.add_argument(
        "--train-manifest",
        type=str,
        default=None,
        help="Path to pinned train-split manifest JSON (Phase 3, not yet active).",
    )
    parser.add_argument(
        "--val-manifest",
        type=str,
        default=None,
        help="Path to pinned val-split manifest JSON (Phase 3, not yet active).",
    )
    parser.add_argument(
        "--test-manifest",
        type=str,
        default=None,
        help="Path to pinned test-split manifest JSON (Phase 3, not yet active).",
    )


def _build_model_config_from_args(args: argparse.Namespace) -> WinnerModelConfig:
    """Construct a WinnerModelConfig from parsed CLI args.

    Only fields that were explicitly provided (non-None) override the defaults
    so omitting a flag preserves current behaviour exactly.

    Args:
        args: Parsed namespace from a parser that used :func:`_add_train_winner_args`.

    Returns:
        WinnerModelConfig with caller-supplied overrides applied.
    """
    cfg = WinnerModelConfig()
    if args.canonical_width is not None:
        cfg = WinnerModelConfig(
            checkpoint_path=cfg.checkpoint_path,
            confidence_threshold=cfg.confidence_threshold,
            fps_out=cfg.fps_out,
            clip_duration_s=cfg.clip_duration_s,
            canonical_width=args.canonical_width,
            canonical_height=cfg.canonical_height,
            device=cfg.device,
            clip_duration_override_s=cfg.clip_duration_override_s,
            clip_extract_max_dim=cfg.clip_extract_max_dim,
        )
    if args.canonical_height is not None:
        cfg = WinnerModelConfig(
            checkpoint_path=cfg.checkpoint_path,
            confidence_threshold=cfg.confidence_threshold,
            fps_out=cfg.fps_out,
            clip_duration_s=cfg.clip_duration_s,
            canonical_width=cfg.canonical_width,
            canonical_height=args.canonical_height,
            device=cfg.device,
            clip_duration_override_s=cfg.clip_duration_override_s,
            clip_extract_max_dim=cfg.clip_extract_max_dim,
        )
    if args.clip_duration_s is not None:
        cfg = WinnerModelConfig(
            checkpoint_path=cfg.checkpoint_path,
            confidence_threshold=cfg.confidence_threshold,
            fps_out=cfg.fps_out,
            clip_duration_s=args.clip_duration_s,
            canonical_width=cfg.canonical_width,
            canonical_height=cfg.canonical_height,
            device=cfg.device,
            clip_duration_override_s=cfg.clip_duration_override_s,
            clip_extract_max_dim=cfg.clip_extract_max_dim,
        )
    if args.fps_out is not None:
        cfg = WinnerModelConfig(
            checkpoint_path=cfg.checkpoint_path,
            confidence_threshold=cfg.confidence_threshold,
            fps_out=args.fps_out,
            clip_duration_s=cfg.clip_duration_s,
            canonical_width=cfg.canonical_width,
            canonical_height=cfg.canonical_height,
            device=cfg.device,
            clip_duration_override_s=cfg.clip_duration_override_s,
            clip_extract_max_dim=cfg.clip_extract_max_dim,
        )
    if args.clip_extract_max_dim is not None:
        cfg = WinnerModelConfig(
            checkpoint_path=cfg.checkpoint_path,
            confidence_threshold=cfg.confidence_threshold,
            fps_out=cfg.fps_out,
            clip_duration_s=cfg.clip_duration_s,
            canonical_width=cfg.canonical_width,
            canonical_height=cfg.canonical_height,
            device=cfg.device,
            clip_duration_override_s=cfg.clip_duration_override_s,
            clip_extract_max_dim=args.clip_extract_max_dim,
        )
    return cfg


def main() -> None:
    """Parse CLI arguments and invoke train_winner()."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.train_winner",
        description="Train the rally winner classifier (WinnerClassifier).",
    )
    _add_train_winner_args(parser)
    args = parser.parse_args()

    root_dir = Path(args.root).expanduser().resolve()
    if not root_dir.exists():
        print(f"Error: root directory does not exist: {root_dir}")
        sys.exit(1)

    model_cfg = _build_model_config_from_args(args)

    checkpoint_out: Path | None = None
    if args.checkpoint_out is not None:
        checkpoint_out = Path(args.checkpoint_out)

    train_winner(
        root_dir=root_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        device_str=args.device,
        model_config=model_cfg,
        checkpoint_out=checkpoint_out,
        seed=args.seed,
        grad_accum_steps=args.grad_accum_steps,
        num_workers=args.num_workers,
        amp=args.amp,
    )


if __name__ == "__main__":
    main()
