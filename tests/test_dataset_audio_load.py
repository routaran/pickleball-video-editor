"""Tests for compute_mel_spectrogram using the soundfile-based load path.

Guards the fix in ml/dataset.py that replaces torchaudio.load() with
soundfile.read() to eliminate the torchcodec runtime dependency.

All tests run WITHOUT a real video file — a synthetic sine-wave WAV is
written to a pytest tmp_path directory using soundfile.

Test classes
------------
TestComputeMelSpectrogram  — tensor shape, dtype, and finite-value assertions
"""

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so both ml/ and src/ are importable.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Guards: skip entire module when required scientific packages are absent.
# ---------------------------------------------------------------------------

torch = pytest.importorskip("torch")
sf = pytest.importorskip("soundfile")
numpy = pytest.importorskip("numpy")


# ---------------------------------------------------------------------------
# Import modules under test.
# ---------------------------------------------------------------------------

from ml.config import AudioConfig  # noqa: E402
from ml.dataset import compute_mel_spectrogram  # noqa: E402


# ---------------------------------------------------------------------------
# Shared test parameters
# ---------------------------------------------------------------------------

_AUDIO_CONFIG = AudioConfig(
    sample_rate=16000,
    n_fft=400,
    hop_length=160,
    n_mels=64,
)


def _write_sine_wav(path: Path, sample_rate: int = 16000, duration: float = 1.0) -> None:
    """Write a mono float32 sine wave to path via soundfile.

    Args:
        path: Destination .wav file path.
        sample_rate: Samples per second (Hz).
        duration: Length of the tone in seconds.
    """
    num_samples = int(sample_rate * duration)
    t = numpy.linspace(0.0, duration, num_samples, endpoint=False, dtype=numpy.float32)
    tone = numpy.sin(2.0 * numpy.pi * 440.0 * t)  # 440 Hz A4, shape (num_samples,)
    sf.write(str(path), tone, sample_rate, subtype="FLOAT")


# ---------------------------------------------------------------------------
# TestComputeMelSpectrogram
# ---------------------------------------------------------------------------


class TestComputeMelSpectrogram:
    """Source-side tests for compute_mel_spectrogram with the soundfile fix."""

    def test_returns_torch_tensor(self, tmp_path: Path) -> None:
        """compute_mel_spectrogram must return a torch.Tensor instance.

        Verifies that the return value is not a numpy array or other type
        accidentally leaking through the soundfile conversion path.
        """
        wav_path = tmp_path / "tone.wav"
        _write_sine_wav(wav_path)

        result = compute_mel_spectrogram(wav_path, _AUDIO_CONFIG)

        assert isinstance(result, torch.Tensor), (
            f"Expected torch.Tensor, got {type(result).__name__}"
        )

    def test_output_shape_matches_n_mels(self, tmp_path: Path) -> None:
        """Output shape must be (n_mels, T) with T > 0.

        n_mels=64 is the first dimension.  T is the time dimension and must
        be at least 1 for any non-trivial audio input.
        """
        wav_path = tmp_path / "tone.wav"
        _write_sine_wav(wav_path)

        result = compute_mel_spectrogram(wav_path, _AUDIO_CONFIG)

        assert result.ndim == 2, (
            f"Expected 2-D tensor, got {result.ndim}-D with shape {tuple(result.shape)}"
        )

        n_mels_actual, time_frames = result.shape

        assert n_mels_actual == _AUDIO_CONFIG.n_mels, (
            f"Expected first dim {_AUDIO_CONFIG.n_mels} (n_mels), got {n_mels_actual}"
        )
        assert time_frames > 0, (
            f"Expected T > 0 time frames, got {time_frames}"
        )

    def test_all_values_are_finite(self, tmp_path: Path) -> None:
        """Every element in the output tensor must be finite (no NaN or Inf).

        A non-finite value indicates a broken log-mel computation or a
        degenerate waveform conversion (e.g., silence underflow, dtype mismatch).
        """
        wav_path = tmp_path / "tone.wav"
        _write_sine_wav(wav_path)

        result = compute_mel_spectrogram(wav_path, _AUDIO_CONFIG)

        assert torch.isfinite(result).all(), (
            "Output tensor contains NaN or Inf values — "
            f"finite count: {torch.isfinite(result).sum().item()} / {result.numel()}"
        )
