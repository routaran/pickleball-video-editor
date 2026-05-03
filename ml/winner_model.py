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
"""

import torch
import torch.nn as nn
import torchvision.models as tv_models

from pathlib import Path


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


def load_winner_classifier(
    checkpoint_path: Path,
    device: str = "cuda",
) -> WinnerClassifier:
    """Load a WinnerClassifier from a saved checkpoint dict.

    The checkpoint is expected to be a dict with at minimum the key
    ``"model_state_dict"``.  The optional keys ``"epoch"`` and
    ``"val_accuracy"`` are accepted but not used after loading.

    Args:
        checkpoint_path: Absolute or relative path to the ``.pt`` file.
        device: Target device string, e.g. ``"cuda"``, ``"cpu"``, or
                ``"cuda:1"``.  Defaults to ``"cuda"``; falls back to CPU
                automatically when CUDA is unavailable.

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

    model = WinnerClassifier()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    model.to(resolved_device)

    return model
