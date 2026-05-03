"""Dataset pipeline for rally detection training.

Handles:
1. Discovery of .training.json label files
2. Audio extraction from video files (via ffmpeg → WAV)
3. Mel spectrogram computation and caching
4. Sliding window dataset with binary labels (play vs dead time)
5. Train/val splitting by video (no data leakage)
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch
import torchaudio
from torch.utils.data import Dataset

from ml.config import AudioConfig, PathConfig


def find_training_files(search_dir: str | Path) -> list[Path]:
    """Recursively find all .training.json files under a directory.

    Args:
        search_dir: Directory to search

    Returns:
        Sorted list of paths to training JSON files
    """
    return sorted(Path(search_dir).rglob("*.training.json"))


def load_training_json(path: Path) -> dict[str, Any]:
    """Load and validate a training JSON file.

    Args:
        path: Path to .training.json file

    Returns:
        Parsed training data dictionary

    Raises:
        ValueError: If required fields are missing
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    required = ["video", "rallies"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required key '{key}' in {path}")

    return data


def extract_audio(video_path: str | Path, output_path: Path, sample_rate: int = 22050) -> Path:
    """Extract audio from video file as mono WAV using ffmpeg.

    Args:
        video_path: Path to source video file
        output_path: Path for output WAV file
        sample_rate: Target sample rate in Hz

    Returns:
        Path to extracted WAV file

    Raises:
        RuntimeError: If ffmpeg fails
    """
    video_path = Path(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        return output_path

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn",                      # no video
        "-ac", "1",                 # mono
        "-ar", str(sample_rate),    # resample
        "-f", "wav",
        "-y",                       # overwrite
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {video_path}: {result.stderr[:500]}")

    return output_path


def compute_mel_spectrogram(
    wav_path: Path,
    audio_config: AudioConfig,
) -> torch.Tensor:
    """Compute log-mel spectrogram from WAV file.

    Args:
        wav_path: Path to mono WAV file
        audio_config: Audio processing parameters

    Returns:
        Log-mel spectrogram tensor of shape (n_mels, time_frames)
    """
    data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data).T  # (frames, channels) -> (channels, frames)

    # Resample if needed
    if sr != audio_config.sample_rate:
        resampler = torchaudio.transforms.Resample(sr, audio_config.sample_rate)
        waveform = resampler(waveform)

    # Ensure mono
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    mel_transform = torchaudio.transforms.MelSpectrogram(
        sample_rate=audio_config.sample_rate,
        n_fft=audio_config.n_fft,
        hop_length=audio_config.hop_length,
        n_mels=audio_config.n_mels,
    )

    mel_spec = mel_transform(waveform)  # (1, n_mels, time)
    log_mel = torch.log(mel_spec + 1e-9)  # log scale

    return log_mel.squeeze(0)  # (n_mels, time)


def build_labels_from_rallies(
    rallies: list[dict[str, Any]],
    fps: float,
    total_duration: float,
    audio_config: AudioConfig,
) -> np.ndarray:
    """Create per-sample binary labels from rally timestamps.

    Each audio sample is labeled 1 (active play) if it falls within a rally's
    raw timestamps, 0 (dead time) otherwise.

    Args:
        rallies: Rally list from training JSON
        fps: Video FPS (for frame-to-seconds conversion)
        total_duration: Video duration in seconds
        audio_config: Audio processing parameters

    Returns:
        1D numpy array of binary labels, one per audio sample
    """
    total_samples = int(total_duration * audio_config.sample_rate)
    labels = np.zeros(total_samples, dtype=np.float32)

    for rally in rallies:
        if rally.get("is_post_game", False):
            continue

        # Prefer raw timestamps (ground truth); fall back to padded
        timestamps = rally.get("raw") or rally.get("padded")
        if timestamps is None:
            continue

        start_sec = timestamps["start_seconds"]
        end_sec = timestamps["end_seconds"]

        start_sample = int(start_sec * audio_config.sample_rate)
        end_sample = int(end_sec * audio_config.sample_rate)

        start_sample = max(0, start_sample)
        end_sample = min(total_samples, end_sample)

        labels[start_sample:end_sample] = 1.0

    return labels


class RallyDataset(Dataset):
    """PyTorch Dataset of mel spectrogram windows with binary labels.

    Each item is a (spectrogram_window, label) pair where:
    - spectrogram_window: (1, n_mels, time_frames) tensor
    - label: scalar 0.0 (dead time) or 1.0 (active play)

    The label is determined by the center of the audio window.
    """

    def __init__(
        self,
        spectrograms: list[torch.Tensor],
        labels_list: list[np.ndarray],
        audio_config: AudioConfig,
        hop_seconds: float | None = None,
    ) -> None:
        """Build the windowed dataset from multiple videos.

        Args:
            spectrograms: List of mel spectrograms, one per video
            labels_list: List of per-sample label arrays, one per video
            audio_config: Audio processing parameters
            hop_seconds: Window hop in seconds (default: audio_config.hop_seconds)
        """
        self.audio_config = audio_config
        self.window_mel_frames = audio_config.window_mel_frames
        hop_sec = hop_seconds or audio_config.hop_seconds
        self.hop_mel_frames = max(1, int(hop_sec * audio_config.sample_rate / audio_config.hop_length))

        # Build index: (video_idx, start_mel_frame) for each window
        self.windows: list[tuple[int, int]] = []
        self.spectrograms = spectrograms
        self.labels_list = labels_list

        for vid_idx, spec in enumerate(spectrograms):
            n_frames = spec.shape[1]
            start = 0
            while start + self.window_mel_frames <= n_frames:
                self.windows.append((vid_idx, start))
                start += self.hop_mel_frames

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        vid_idx, start_frame = self.windows[idx]

        # Extract spectrogram window
        spec = self.spectrograms[vid_idx]
        window = spec[:, start_frame:start_frame + self.window_mel_frames]
        window = window.unsqueeze(0)  # (1, n_mels, time_frames)

        # Label based on center of window
        center_frame = start_frame + self.window_mel_frames // 2
        center_sample = center_frame * self.audio_config.hop_length

        labels = self.labels_list[vid_idx]
        if center_sample < len(labels):
            label = float(labels[center_sample])
        else:
            label = 0.0

        return window, torch.tensor(label, dtype=torch.float32)


def prepare_video(
    training_json_path: Path,
    audio_config: AudioConfig,
    cache_dir: Path,
) -> tuple[torch.Tensor, np.ndarray, dict[str, Any]] | None:
    """Prepare one video: extract audio, compute spectrogram, build labels.

    Results are cached to disk for fast re-loading.

    Args:
        training_json_path: Path to .training.json file
        audio_config: Audio processing parameters
        cache_dir: Directory for caching extracted audio and spectrograms

    Returns:
        Tuple of (spectrogram, labels, training_data) or None if video missing
    """
    data = load_training_json(training_json_path)
    video_path = Path(data["video"]["path"])

    if not video_path.exists():
        print(f"  SKIP: video not found: {video_path}")
        return None

    video_id = video_path.stem
    wav_path = cache_dir / f"{video_id}.wav"
    spec_path = cache_dir / f"{video_id}_mel.pt"
    labels_path = cache_dir / f"{video_id}_labels.npy"

    # Extract audio
    extract_audio(video_path, wav_path, audio_config.sample_rate)

    # Compute or load cached spectrogram
    if spec_path.exists():
        spectrogram = torch.load(spec_path, weights_only=True)
    else:
        spectrogram = compute_mel_spectrogram(wav_path, audio_config)
        torch.save(spectrogram, spec_path)

    # Build or load cached labels
    if labels_path.exists():
        labels = np.load(labels_path)
    else:
        labels = build_labels_from_rallies(
            rallies=data["rallies"],
            fps=data["video"]["fps"],
            total_duration=data["video"]["duration_seconds"],
            audio_config=audio_config,
        )
        np.save(labels_path, labels)

    return spectrogram, labels, data


def prepare_all(
    search_dir: str | Path,
    audio_config: AudioConfig | None = None,
    paths: PathConfig | None = None,
) -> tuple[list[torch.Tensor], list[np.ndarray], list[str]]:
    """Prepare all videos found under search_dir.

    Args:
        search_dir: Directory to search for .training.json files
        audio_config: Audio processing config (uses defaults if None)
        paths: Path config (uses defaults if None)

    Returns:
        Tuple of (spectrograms, labels, video_ids) for all valid videos
    """
    audio_config = audio_config or AudioConfig()
    paths = paths or PathConfig()
    cache_dir = paths.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    training_files = find_training_files(search_dir)
    print(f"Found {len(training_files)} training files")

    spectrograms = []
    labels_list = []
    video_ids = []

    for i, tf in enumerate(training_files):
        print(f"  [{i+1}/{len(training_files)}] Processing {tf.name}...")
        result = prepare_video(tf, audio_config, cache_dir)
        if result is not None:
            spec, labels, data = result
            spectrograms.append(spec)
            labels_list.append(labels)
            video_ids.append(Path(data["video"]["path"]).stem)

    print(f"Prepared {len(spectrograms)} videos")
    return spectrograms, labels_list, video_ids
