"""CNN model for rally detection from mel spectrograms."""

import torch
import torch.nn as nn

from ml.config import AudioConfig


class RallyDetector(nn.Module):
    """CNN binary classifier for pickleball rally detection.

    Takes a mel spectrogram window and outputs a probability that
    the center of the window contains active rally play.

    Architecture:
        3 convolutional blocks (Conv2d → BatchNorm → ReLU → MaxPool)
        followed by adaptive pooling and a 2-layer classifier head.

    Input shape: (batch, 1, n_mels, time_frames)
    Output shape: (batch, 1) — sigmoid probability
    """

    def __init__(self, audio_config: AudioConfig | None = None) -> None:
        super().__init__()
        cfg = audio_config or AudioConfig()

        self.features = nn.Sequential(
            # Block 1: (1, 128, T) → (32, 64, T/2)
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            # Block 2: (32, 64, T/2) → (64, 32, T/4)
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            # Block 3: (64, 32, T/4) → (128, 16, T/8)
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),

            # Pool to fixed size regardless of input dimensions
            nn.AdaptiveAvgPool2d((4, 4)),
        )

        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 4 * 4, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(128, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Mel spectrogram windows, shape (batch, 1, n_mels, time_frames)

        Returns:
            Raw logits, shape (batch, 1). Apply sigmoid for probabilities.
        """
        x = self.features(x)
        x = self.classifier(x)
        return x
