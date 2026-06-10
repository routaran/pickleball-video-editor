"""Configuration and hyperparameters for the rally detection model."""

import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AudioConfig:
    """Audio processing parameters."""

    sample_rate: int = 22050
    n_mels: int = 128
    n_fft: int = 2048
    hop_length: int = 512
    window_seconds: float = 2.0
    hop_seconds: float = 0.5

    @property
    def window_samples(self) -> int:
        return int(self.window_seconds * self.sample_rate)

    @property
    def hop_samples(self) -> int:
        return int(self.hop_seconds * self.sample_rate)

    @property
    def window_mel_frames(self) -> int:
        """Number of mel spectrogram time frames per window."""
        return int(self.window_samples / self.hop_length) + 1


@dataclass
class TrainConfig:
    """Training hyperparameters."""

    batch_size: int = 64
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    epochs: int = 30
    val_fraction: float = 0.2
    early_stop_patience: int = 5
    num_workers: int = 4


@dataclass
class InferenceConfig:
    """Inference and post-processing parameters."""

    # Sliding window hop during inference (smaller = smoother but slower)
    hop_seconds: float = 0.25
    # Minimum probability to classify as "play"
    threshold: float = 0.5
    # Median filter kernel size (in prediction steps) for smoothing
    smooth_kernel: int = 5
    # Minimum rally duration in seconds (shorter segments are dropped).
    # Set to 1.5s so aces, faults, and net errors (legitimate sub-3s
    # score-advancing rallies) are not discarded before Stage 3.
    min_rally_seconds: float = 1.5
    # Merge rallies closer than this many seconds apart.
    # A 2s gap can fuse a scored rally with the very next quick serve;
    # tightening to 1s keeps independent short rallies separate.
    merge_gap_seconds: float = 1.0


@dataclass
class WinnerModelConfig:
    """Configuration for the WinnerClassifier inference pipeline.

    Attributes:
        checkpoint_path: Path to the saved ``.pt`` checkpoint produced by
            the winner-classifier training script.
        confidence_threshold: Minimum softmax probability required to accept
            a prediction; clips below this threshold are flagged as uncertain.
        fps_out: Frame rate used when sampling frames from a clip before
            passing them to the model.  Lower values are faster; 8 fps
            gives 20 frames for a 2.5-second clip.
        clip_duration_s: Duration (seconds) of the video segment fed to the
            model, anchored at the rally end timestamp.
        canonical_width: Width (pixels) each frame is resized to before the
            backbone.  Must match the resolution used during training.
        canonical_height: Height (pixels) each frame is resized to.
        device: PyTorch device string.  Falls back to CPU automatically when
            CUDA is unavailable.
        clip_duration_override_s: When set to a non-``None`` value, replaces
            ``clip_duration_s`` for the current run without changing the
            stored default.  Intended for clip-window ablation experiments.
            Use :py:meth:`effective_clip_duration_s` to read the active value.
    """

    checkpoint_path: Path = Path("ml/checkpoints/best_winner.pt")
    # Single source of truth for the "flag for human review" threshold.
    # All call-sites (auto_edit, CLI, progress dialog) default to None and
    # resolve to this value at runtime so there is exactly one place to change.
    confidence_threshold: float = 0.75
    fps_out: int = 8
    clip_duration_s: float = 2.5
    canonical_width: int = 256
    canonical_height: int = 128
    device: str = "cuda"
    clip_duration_override_s: float | None = None

    @property
    def effective_clip_duration_s(self) -> float:
        """Return the active clip duration for inference.

        Returns ``clip_duration_override_s`` when it is not ``None``,
        otherwise falls back to the ``clip_duration_s`` default.  Call-sites
        should use this property rather than reading ``clip_duration_s``
        directly so that ablation overrides are honoured transparently.
        """
        if self.clip_duration_override_s is not None:
            return self.clip_duration_override_s
        return self.clip_duration_s


@dataclass
class FeatureCollectionConfig:
    """Controls which feature extractors run during the data-collection pass.

    Attributes:
        metadata_enabled: Collect per-clip metadata (timestamps, labels,
            source video path).  Enabled by default because it is cheap and
            required for every downstream task.
        audio_enabled: Extract audio features (mel spectrograms, etc.).
            Disabled by default; the audio pipeline is not yet stable and
            adding it here makes it easy to opt-in without touching callers.
        features_subdir: Sub-directory under ``PathConfig.cache_dir`` where
            collected features are stored.  A future FeatureCache class will
            root itself here.
    """

    metadata_enabled: bool = True
    audio_enabled: bool = False
    features_subdir: str = "features"


def _default_data_root() -> Path:
    """Determine the data root for cache and checkpoints.

    When running from source: uses the project root (parent of ml/).
    When running as a PyInstaller bundle: uses the directory containing
    the executable, so cache/checkpoints live alongside the installed app.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — use the executable's directory
        return Path(sys.executable).parent
    # Running from source — ml/ is a subdirectory of the project root
    return Path(__file__).parent.parent


@dataclass
class PathConfig:
    """Project paths — all relative to the project root."""

    project_root: Path = field(default_factory=_default_data_root)

    @property
    def ml_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            # In a bundle, there's no ml/ subdirectory
            return self.project_root
        return self.project_root / "ml"

    @property
    def cache_dir(self) -> Path:
        return self.ml_dir / "cache"

    @property
    def checkpoints_dir(self) -> Path:
        return self.ml_dir / "checkpoints"

    @property
    def best_model_path(self) -> Path:
        return self.checkpoints_dir / "best_model.pt"
