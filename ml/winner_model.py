"""WinnerClassifier — ResNet-18 backbone + temporal Conv1d head.

Predicts which player/team won a rally from a short video clip.

Architecture overview
---------------------
1. ResNet-18 backbone (pretrained ImageNet) with the final FC replaced by
   nn.Identity, producing a 512-d feature vector per frame.
2. A lightweight temporal module (Conv1d → ReLU → AdaptiveAvgPool1d) that
   aggregates per-frame features across the clip's T frames into a single
   128-d representation.
3. A linear classification head mapping 128 → 2 (server wins / receiver wins).

Input/output shapes
-------------------
    forward(clip)  where  clip : (B, T, 3, H, W)
    returns logits          :  (B, 2)

Total parameters: ~11.2 M (dominated by the ResNet-18 backbone).

Checkpoint compatibility
------------------------
Checkpoints saved WITHOUT a ``"config"`` key (pre-E2 format) load unchanged —
the model weights are applied and no warning is emitted.  Checkpoints saved
WITH a ``"config"`` key are compared against the requested
``WinnerModelConfig``; any field mismatch produces a ``UserWarning`` but does
NOT prevent loading.
"""

import dataclasses
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torch.nn as nn
import torchvision.models as tv_models

if TYPE_CHECKING:
    from ml.config import WinnerModelConfig


__all__ = [
    "WinnerClassifier",
    "load_winner_classifier",
]


class WinnerClassifier(nn.Module):
    """ResNet-18 + temporal Conv1d classifier for rally winner prediction.

    The backbone processes each frame independently (batch over B*T),
    then the temporal module summarises across the time dimension.

    Args:
        None — all hyper-parameters are fixed to match the training spec.
    """

    def __init__(self) -> None:
        super().__init__()

        backbone = tv_models.resnet18(weights="DEFAULT")
        # Remove the classification head; output is now the 512-d avg-pool vector.
        backbone.fc = nn.Identity()  # type: ignore[assignment]
        self.backbone = backbone

        self.temporal = nn.Sequential(
            nn.Conv1d(512, 128, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool1d(1),
        )

        self.head = nn.Linear(128, 2)

    def forward(self, clip: torch.Tensor) -> torch.Tensor:
        """Run a forward pass on a batch of video clips.

        Args:
            clip: Tensor of shape (B, T, 3, H, W) — a batch of B clips, each
                  containing T RGB frames at spatial size H x W.

        Returns:
            Raw logits of shape (B, 2).  Apply softmax for probabilities or
            pass directly to nn.CrossEntropyLoss during training.
        """
        B, T, C, H, W = clip.shape

        # Flatten batch and time dimensions so the backbone processes every
        # frame as an independent image: (B*T, C, H, W) → (B*T, 512)
        x = self.backbone(clip.view(B * T, C, H, W))

        # Reshape back to (B, T, 512) then permute to (B, 512, T) for Conv1d
        x = x.view(B, T, 512).permute(0, 2, 1)

        # Temporal aggregation: (B, 512, T) → (B, 128, 1) → (B, 128)
        x = self.temporal(x).squeeze(-1)

        # Classification head: (B, 128) → (B, 2)
        return self.head(x)


def _warn_config_mismatch(
    saved: dict,
    requested_cfg: "WinnerModelConfig",
    checkpoint_path: Path,
) -> None:
    """Emit a UserWarning for each field that differs between *saved* and *requested_cfg*.

    Only fields present in the saved dict are compared; extra keys in *saved*
    that are not dataclass fields (e.g. ``"effective_clip_duration_s"``) are
    checked individually so the ablation value is also validated.

    Args:
        saved: The ``"config"`` sub-dict from the checkpoint.
        requested_cfg: The WinnerModelConfig the caller wants to use now.
        checkpoint_path: Used in the warning message for context.
    """
    mismatches: list[str] = []

    for f in dataclasses.fields(requested_cfg):
        if f.name not in saved:
            continue  # field added after checkpoint was saved — skip
        saved_value = saved[f.name]
        current_value = getattr(requested_cfg, f.name)
        # Normalise Path to str for comparison
        if isinstance(current_value, Path):
            current_value = str(current_value)
        if saved_value != current_value:
            mismatches.append(
                f"  {f.name}: saved={saved_value!r}, current={current_value!r}"
            )

    # Also check effective_clip_duration_s if present (ablation key)
    if "effective_clip_duration_s" in saved:
        saved_eff = saved["effective_clip_duration_s"]
        current_eff = requested_cfg.effective_clip_duration_s
        if saved_eff != current_eff:
            mismatches.append(
                f"  effective_clip_duration_s: saved={saved_eff!r}, current={current_eff!r}"
            )

    if mismatches:
        mismatch_str = "\n".join(mismatches)
        warnings.warn(
            f"WinnerModelConfig mismatch detected when loading checkpoint "
            f"'{checkpoint_path}'.\nThe following fields differ between the "
            f"checkpoint and the requested config (model weights are still "
            f"loaded):\n{mismatch_str}",
            UserWarning,
            stacklevel=3,
        )


def load_winner_classifier(
    checkpoint_path: Path,
    device: str = "cuda",
    config: "WinnerModelConfig | None" = None,
) -> WinnerClassifier:
    """Load a WinnerClassifier from a saved checkpoint dict.

    The checkpoint is expected to be a dict with at minimum the key
    ``"model_state_dict"``.  The optional keys ``"epoch"`` and
    ``"val_accuracy"`` are accepted but not used after loading.

    Config-mismatch detection (E2)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    If the checkpoint was saved with a ``"config"`` key (produced by the
    current training script), the saved config is compared against *config*
    (or a default ``WinnerModelConfig()`` when *config* is ``None``).
    Any field that differs triggers a ``UserWarning``.  The model is always
    loaded regardless of mismatches.

    Checkpoints WITHOUT a ``"config"`` key (old format) load unchanged —
    no warning is emitted.

    Args:
        checkpoint_path: Absolute or relative path to the ``.pt`` file.
        device: Target device string, e.g. ``"cuda"``, ``"cpu"``, or
                ``"cuda:1"``.  Defaults to ``"cuda"``; falls back to CPU
                automatically when CUDA is unavailable.
        config: Optional WinnerModelConfig to compare against the saved
                checkpoint metadata.  When ``None``, a default instance is
                used for the comparison.  Pass ``False`` to skip comparison
                entirely (not recommended).

    Returns:
        A WinnerClassifier in eval mode with weights loaded and moved to
        *device*.

    Raises:
        FileNotFoundError: If *checkpoint_path* does not exist.
        KeyError: If the checkpoint file lacks ``"model_state_dict"``.
    """
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Winner classifier checkpoint not found: {checkpoint_path}"
        )

    # Resolve the actual device — gracefully fall back to CPU when the
    # requested device is unavailable (e.g. no GPU on the current machine).
    resolved_device = device
    if device.startswith("cuda") and not torch.cuda.is_available():
        resolved_device = "cpu"

    checkpoint: dict = torch.load(
        checkpoint_path,
        map_location=resolved_device,
        weights_only=True,
    )

    if "model_state_dict" not in checkpoint:
        raise KeyError(
            f"Checkpoint at {checkpoint_path} is missing 'model_state_dict'. "
            f"Found keys: {list(checkpoint.keys())}"
        )

    # E2 (load side): compare saved config metadata against the requested config.
    # Old checkpoints that lack "config" silently pass through — back-compat.
    if "config" in checkpoint:
        # Import here to avoid a circular-import at module level; config is a
        # lightweight dataclass module with no ML dependencies.
        from ml.config import WinnerModelConfig as _WMC  # noqa: PLC0415

        effective_cfg: _WMC = config if config is not None else _WMC()
        _warn_config_mismatch(checkpoint["config"], effective_cfg, checkpoint_path)

    model = WinnerClassifier()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    model.to(resolved_device)

    return model
