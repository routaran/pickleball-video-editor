"""Tests for ml.dataset.prepare_video audio filtering and cache invalidation."""

import importlib
import json
import pickle
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy

# Guard against cross-test sys.modules contamination.
# Some test modules pre-install MagicMock stubs for torch-bearing modules,
# including ml.dataset itself. Evict those stubs before importing anything we
# need for these tests so we always resolve the real module or a test-local
# fallback.
for _evict_prefix in ("torch", "torchaudio", "soundfile", "ml.dataset"):
    for _key in list(sys.modules):
        if _key == _evict_prefix or _key.startswith(_evict_prefix + "."):
            if isinstance(sys.modules[_key], MagicMock):
                del sys.modules[_key]

_ml_package = sys.modules.get("ml")
if _ml_package is not None and isinstance(getattr(_ml_package, "dataset", None), MagicMock):
    delattr(_ml_package, "dataset")

try:
    import torch as _candidate_torch
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    _real_torch = None
    _tensor_capable_torch = None
else:  # pragma: no branch - simple capability checks
    _real_torch = (
        _candidate_torch
        if all(hasattr(_candidate_torch, attr) for attr in ("Tensor", "save", "load"))
        else None
    )
    _tensor_capable_torch = (
        _candidate_torch
        if all(hasattr(_candidate_torch, attr) for attr in ("Tensor", "tensor", "float32"))
        else None
    )

try:
    import soundfile as _real_soundfile
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    _real_soundfile = None

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class _FakeTensor:
    def __init__(self, values: list[float]) -> None:
        self.values = list(values)


class _FakeDataset:
    pass


class _FakeTorchModule(types.ModuleType):
    Tensor = _FakeTensor

    @staticmethod
    def save(obj: object, path: Path) -> None:
        with open(path, "wb") as fh:
            pickle.dump(obj, fh)

    @staticmethod
    def load(path: Path, **_kwargs: object) -> object:
        with open(path, "rb") as fh:
            return pickle.load(fh)


def _load_dataset_module():
    inserted_torch_stub = False
    inserted_torchaudio_stub = False
    inserted_soundfile_stub = False

    if _real_torch is None:
        fake_torch = _FakeTorchModule("torch")
        fake_torch_utils = types.ModuleType("torch.utils")
        fake_torch_utils_data = types.ModuleType("torch.utils.data")
        fake_torch_utils_data.Dataset = _FakeDataset
        fake_torch.utils = fake_torch_utils
        sys.modules["torch"] = fake_torch
        sys.modules["torch.utils"] = fake_torch_utils
        sys.modules["torch.utils.data"] = fake_torch_utils_data
        inserted_torch_stub = True
    if "torchaudio" not in sys.modules:
        sys.modules["torchaudio"] = types.ModuleType("torchaudio")
        inserted_torchaudio_stub = True
    if "soundfile" not in sys.modules:
        if _real_soundfile is not None:
            sys.modules["soundfile"] = _real_soundfile
        else:
            sys.modules["soundfile"] = types.ModuleType("soundfile")
            inserted_soundfile_stub = True

    module = importlib.import_module("ml.dataset")
    module = importlib.reload(module)

    if inserted_soundfile_stub:
        sys.modules.pop("soundfile", None)
    if inserted_torchaudio_stub:
        sys.modules.pop("torchaudio", None)
    if inserted_torch_stub:
        sys.modules.pop("torch", None)
        sys.modules.pop("torch.utils", None)
        sys.modules.pop("torch.utils.data", None)
    return module


from ml.config import AudioConfig  # noqa: E402

dataset = _load_dataset_module()
prepare_video = dataset.prepare_video

def _make_tensor(values: list[float]):
    if _tensor_capable_torch is not None:
        return _tensor_capable_torch.tensor(values, dtype=_tensor_capable_torch.float32)
    return _FakeTensor(values)


def _tensor_values(tensor: object) -> list[float]:
    if _tensor_capable_torch is not None and isinstance(tensor, _tensor_capable_torch.Tensor):
        return tensor.tolist()
    return tensor.values


def _training_data(video_path: Path, rallies: list[dict], generated_by: str = "manual") -> dict:
    return {
        "generated_by": generated_by,
        "video": {
            "path": str(video_path),
            "fps": 30.0,
            "duration_seconds": 12.0,
        },
        "rallies": rallies,
    }


def _write_training_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestPrepareVideoFiltering:
    def test_auto_edit_file_is_skipped(self, tmp_path: Path) -> None:
        video_path = tmp_path / "match.mp4"
        video_path.write_bytes(b"video")
        training_json = tmp_path / "match.training.json"
        _write_training_json(
            training_json,
            _training_data(
                video_path,
                rallies=[{"start": 1, "end": 10}],
                generated_by="auto_edit",
            ),
        )

        with (
            patch("ml.dataset.extract_audio") as mock_extract_audio,
            patch("ml.dataset.compute_mel_spectrogram") as mock_compute,
            patch("ml.dataset.build_labels_from_rallies") as mock_build_labels,
        ):
            result = prepare_video(training_json, AudioConfig(), tmp_path / "cache")

        assert result is None
        assert mock_extract_audio.call_count == 0
        assert mock_compute.call_count == 0
        assert mock_build_labels.call_count == 0


class TestPrepareVideoCaching:
    def test_audio_config_change_invalidates_audio_and_label_cache(
        self, tmp_path: Path
    ) -> None:
        video_path = tmp_path / "match.mp4"
        video_path.write_bytes(b"video")
        training_json = tmp_path / "match.training.json"
        _write_training_json(
            training_json,
            _training_data(video_path, rallies=[{"start": 1, "end": 10}]),
        )
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        audio_calls: list[int] = []
        compute_calls: list[int] = []
        label_calls: list[int] = []

        def _fake_extract_audio(_video_path: Path, output_path: Path, sample_rate: int) -> Path:
            audio_calls.append(sample_rate)
            output_path.write_bytes(b"wav")
            return output_path

        def _fake_compute(_wav_path: Path, audio_config: AudioConfig):
            compute_calls.append(audio_config.sample_rate)
            return _make_tensor([float(audio_config.sample_rate)])

        def _fake_build_labels(**kwargs) -> numpy.ndarray:
            cfg = kwargs["audio_config"]
            label_calls.append(cfg.sample_rate)
            return numpy.full((4,), cfg.sample_rate, dtype=numpy.int64)

        cfg_a = AudioConfig(sample_rate=16000, n_mels=32, n_fft=400, hop_length=160)
        cfg_b = AudioConfig(sample_rate=22050, n_mels=32, n_fft=400, hop_length=160)

        with (
            patch("ml.dataset.extract_audio", side_effect=_fake_extract_audio),
            patch("ml.dataset.compute_mel_spectrogram", side_effect=_fake_compute),
            patch("ml.dataset.build_labels_from_rallies", side_effect=_fake_build_labels),
        ):
            first = prepare_video(training_json, cfg_a, cache_dir)
            second = prepare_video(training_json, cfg_b, cache_dir)

        assert first is not None
        assert second is not None
        assert audio_calls == [16000, 22050]
        assert compute_calls == [16000, 22050]
        assert label_calls == [16000, 22050]
        assert len(list(cache_dir.glob("*_mel.pt"))) == 2
        assert len(list(cache_dir.glob("*_labels.npy"))) == 2

    def test_label_content_change_reuses_audio_cache_and_rebuilds_labels(
        self, tmp_path: Path
    ) -> None:
        video_path = tmp_path / "match.mp4"
        video_path.write_bytes(b"video")
        training_json = tmp_path / "match.training.json"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cfg = AudioConfig(sample_rate=16000, n_mels=32, n_fft=400, hop_length=160)

        _write_training_json(
            training_json,
            _training_data(video_path, rallies=[{"start": 1, "end": 10}]),
        )

        audio_calls = 0
        compute_calls = 0
        build_calls = 0

        def _fake_extract_audio(_video_path: Path, output_path: Path, sample_rate: int) -> Path:
            nonlocal audio_calls
            audio_calls += 1
            output_path.write_bytes(str(sample_rate).encode("utf-8"))
            return output_path

        def _fake_compute(_wav_path: Path, _audio_config: AudioConfig):
            nonlocal compute_calls
            compute_calls += 1
            return _make_tensor([0.0, 1.0, 2.0])

        def _fake_build_labels(**kwargs) -> numpy.ndarray:
            nonlocal build_calls
            build_calls += 1
            rallies = kwargs["rallies"]
            return numpy.full((4,), len(rallies), dtype=numpy.int64)

        with (
            patch("ml.dataset.extract_audio", side_effect=_fake_extract_audio),
            patch("ml.dataset.compute_mel_spectrogram", side_effect=_fake_compute),
            patch("ml.dataset.build_labels_from_rallies", side_effect=_fake_build_labels),
        ):
            first = prepare_video(training_json, cfg, cache_dir)
            _write_training_json(
                training_json,
                _training_data(
                    video_path,
                    rallies=[
                        {"start": 1, "end": 10},
                        {"start": 20, "end": 30},
                    ],
                ),
            )
            second = prepare_video(training_json, cfg, cache_dir)

        assert first is not None
        assert second is not None
        first_spec, first_labels, _ = first
        second_spec, second_labels, _ = second
        assert audio_calls == 1
        assert compute_calls == 1
        assert build_calls == 2
        assert _tensor_values(first_spec) == _tensor_values(second_spec)
        assert not numpy.array_equal(first_labels, second_labels)
        assert len(list(cache_dir.glob("*_mel.pt"))) == 1
        assert len(list(cache_dir.glob("*_labels.npy"))) == 2
