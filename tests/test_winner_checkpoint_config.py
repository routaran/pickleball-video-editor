"""Tests for Phase 2 winner-checkpoint config loading.

Covers the single shared loader
:func:`ml.config.load_winner_config_from_checkpoint` and its use by
``ml.predict_winner.predict_winners``:

(a) v2.0 config-block round-trip,
(b) legacy checkpoint fallback to defaults with a one-time warning,
(c) the ``effective_clip_duration_s`` clip-window path at prediction time.

All tests run on CPU with mocked video I/O and a stub model so no GPU, real
video, or heavy checkpoint is required.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from ml.config import (
    CHECKPOINT_SCHEMA_VERSION,
    WinnerModelConfig,
    load_winner_config_from_checkpoint,
)


# ---------------------------------------------------------------------------
# (a) v2.0 round-trip load
# ---------------------------------------------------------------------------


class TestSharedLoaderV2RoundTrip:
    def test_full_config_block_round_trips_all_geometry(self) -> None:
        checkpoint: dict[str, Any] = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "model_state_dict": {},
            "config": {
                "checkpoint_path": "ml/checkpoints/winner_512x256.pt",
                "confidence_threshold": 0.8,
                "fps_out": 15,
                "clip_duration_s": 5.0,
                "canonical_width": 512,
                "canonical_height": 256,
                "device": "cuda",
                "clip_duration_override_s": None,
                "clip_extract_max_dim": 1080,
                "effective_clip_duration_s": 5.0,
            },
        }

        config = load_winner_config_from_checkpoint(checkpoint)

        assert config.canonical_width == 512
        assert config.canonical_height == 256
        assert config.fps_out == 15
        assert config.clip_duration_s == 5.0
        assert config.clip_extract_max_dim == 1080
        assert config.confidence_threshold == 0.8
        assert config.checkpoint_path == Path("ml/checkpoints/winner_512x256.pt")
        assert config.effective_clip_duration_s == 5.0

    def test_train_winner_serialised_config_round_trips(self) -> None:
        """A config serialised by the trainer reconstructs faithfully."""
        from ml.train_winner import _config_to_dict

        original = WinnerModelConfig(
            canonical_width=512,
            canonical_height=256,
            clip_duration_s=5.0,
            fps_out=15,
            clip_extract_max_dim=1080,
        )
        checkpoint = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "config": _config_to_dict(original),
        }

        loaded = load_winner_config_from_checkpoint(checkpoint)

        assert loaded.canonical_width == original.canonical_width
        assert loaded.canonical_height == original.canonical_height
        assert loaded.fps_out == original.fps_out
        assert loaded.clip_duration_s == original.clip_duration_s
        assert loaded.clip_extract_max_dim == original.clip_extract_max_dim
        assert (
            loaded.effective_clip_duration_s == original.effective_clip_duration_s
        )

    def test_unknown_forward_compatible_keys_are_ignored(self) -> None:
        """A newer checkpoint with extra config keys still loads on an old reader."""
        checkpoint = {
            "config": {
                "canonical_width": 256,
                "canonical_height": 128,
                "clip_duration_s": 2.5,
                # Keys this reader does not know about — must be dropped, not crash.
                "clip_window_policy": "clamp_to_rally_start_v1",
                "padding_policy": "repeat_first_frame_v1",
            }
        }

        config = load_winner_config_from_checkpoint(checkpoint)

        assert config.canonical_width == 256
        assert config.clip_duration_s == 2.5

    def test_v2_round_trip_emits_no_legacy_warning(
        self, recwarn: pytest.WarningsRecorder
    ) -> None:
        checkpoint = {
            "config": {"canonical_width": 256, "clip_duration_s": 2.5},
        }
        load_winner_config_from_checkpoint(checkpoint)
        legacy = [w for w in recwarn if "config block" in str(w.message)]
        assert legacy == []


# ---------------------------------------------------------------------------
# (b) legacy checkpoint fallback + warning
# ---------------------------------------------------------------------------


class TestSharedLoaderLegacyFallback:
    def test_missing_config_block_falls_back_to_defaults(self) -> None:
        checkpoint: dict[str, Any] = {"model_state_dict": {}}

        with pytest.warns(UserWarning, match="no v2.0 config block"):
            config = load_winner_config_from_checkpoint(checkpoint)

        assert config == WinnerModelConfig()

    def test_non_dict_config_block_falls_back_to_defaults(self) -> None:
        checkpoint: dict[str, Any] = {"config": "not-a-dict"}

        with pytest.warns(UserWarning, match="config block"):
            config = load_winner_config_from_checkpoint(checkpoint)

        assert config == WinnerModelConfig()

    def test_legacy_warning_includes_checkpoint_path(self) -> None:
        checkpoint: dict[str, Any] = {"model_state_dict": {}}

        with pytest.warns(UserWarning, match="legacy_winner.pt"):
            load_winner_config_from_checkpoint(
                checkpoint, checkpoint_path=Path("/models/legacy_winner.pt")
            )

    def test_warn_on_legacy_false_suppresses_warning(
        self, recwarn: pytest.WarningsRecorder
    ) -> None:
        checkpoint: dict[str, Any] = {"model_state_dict": {}}

        config = load_winner_config_from_checkpoint(checkpoint, warn_on_legacy=False)

        assert [w for w in recwarn if issubclass(w.category, UserWarning)] == []
        assert config == WinnerModelConfig()


# ---------------------------------------------------------------------------
# (c) effective_clip_duration_s path
# ---------------------------------------------------------------------------


class TestEffectiveClipDurationOverride:
    def test_persisted_effective_duration_becomes_override(self) -> None:
        """Saved effective duration > base duration is applied as an override."""
        checkpoint = {
            "config": {
                "clip_duration_s": 2.5,
                "effective_clip_duration_s": 5.0,
            }
        }

        config = load_winner_config_from_checkpoint(checkpoint)

        assert config.clip_duration_s == 2.5
        assert config.clip_duration_override_s == 5.0
        assert config.effective_clip_duration_s == 5.0

    def test_explicit_override_is_not_clobbered_by_effective_duration(self) -> None:
        checkpoint = {
            "config": {
                "clip_duration_s": 2.5,
                "clip_duration_override_s": 4.0,
                "effective_clip_duration_s": 4.0,
            }
        }

        config = load_winner_config_from_checkpoint(checkpoint)

        assert config.clip_duration_override_s == 4.0
        assert config.effective_clip_duration_s == 4.0


# ---------------------------------------------------------------------------
# (d) checkpoint schema-version mismatch warning
# ---------------------------------------------------------------------------


class TestSchemaVersionMismatchWarning:
    def test_future_schema_version_emits_exactly_one_user_warning(self) -> None:
        """A checkpoint written by a newer schema version triggers one UserWarning."""
        checkpoint: dict[str, Any] = {
            "checkpoint_schema_version": "3.0",
            "config": {"canonical_width": 256, "clip_duration_s": 2.5},
        }

        with pytest.warns(UserWarning, match="3.0") as record:
            load_winner_config_from_checkpoint(checkpoint)

        schema_warnings = [
            w for w in record if "schema version" in str(w.message).lower()
        ]
        assert len(schema_warnings) == 1

    def test_matching_schema_version_emits_no_schema_warning(
        self, recwarn: pytest.WarningsChecker
    ) -> None:
        """A checkpoint whose schema version matches the reader emits no warning."""
        checkpoint: dict[str, Any] = {
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "config": {"canonical_width": 256, "clip_duration_s": 2.5},
        }

        load_winner_config_from_checkpoint(checkpoint)

        schema_warnings = [
            w for w in recwarn if "schema version" in str(w.message).lower()
        ]
        assert schema_warnings == []


# ---------------------------------------------------------------------------
# predict_winners: auto-load config + use effective_clip_duration_s
# ---------------------------------------------------------------------------


_CHECKPOINT_5S: dict[str, Any] = {
    "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
    "model_state_dict": {},
    "temperature": 1.0,
    "config": {
        "clip_duration_s": 2.5,
        "effective_clip_duration_s": 5.0,
        "fps_out": 8,
        "canonical_width": 256,
        "canonical_height": 128,
        "device": "cpu",
        "clip_extract_max_dim": 640,
    },
}


class _StubModel:
    """Minimal stand-in for WinnerClassifier returning fixed logits."""

    def load_state_dict(self, _state: Any) -> None:
        return None

    def eval(self) -> "_StubModel":
        return self

    def to(self, _device: Any) -> "_StubModel":
        return self

    def __call__(self, _clip: torch.Tensor) -> torch.Tensor:
        # Always predict team 0 with a clear margin.
        return torch.tensor([[2.0, -2.0]])


def _patch_predict_winner_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch all video/model I/O in predict_winner and capture clip windows.

    Returns a dict that the test reads ``captured["clip_starts"]`` from.
    """
    import ml.predict_winner as pw

    captured: dict[str, Any] = {"clip_starts": [], "clip_ends": []}

    def fake_extract_clip(
        _video: Path,
        clip_start: float,
        clip_end: float,
        _fps: int,
        _extract_size: Any,
    ) -> np.ndarray:
        captured["clip_starts"].append(clip_start)
        captured["clip_ends"].append(clip_end)
        # (T, H, W, 3) uint8 — one frame is enough for the stub model.
        return np.zeros((1, 128, 256, 3), dtype=np.uint8)

    monkeypatch.setattr(pw, "extract_clip", fake_extract_clip)
    monkeypatch.setattr(
        pw, "get_video_frame_size", lambda _path: (256, 128)
    )
    monkeypatch.setattr(
        pw,
        "resolve_extract_geometry",
        lambda _size, corners, _canon, _maxdim: ((256, 128), corners),
    )
    monkeypatch.setattr(pw, "compute_homography", lambda _corners, _size: object())
    monkeypatch.setattr(
        pw,
        "warp_clip_to_canonical",
        lambda frames, _h, _size: frames,
    )
    monkeypatch.setattr(pw, "WinnerClassifier", _StubModel)
    monkeypatch.setattr(
        pw.torch, "load", lambda *args, **kwargs: dict(_CHECKPOINT_5S)
    )
    return captured


class TestPredictWinnersUsesCheckpointGeometry:
    def test_predict_uses_effective_clip_duration_from_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With config=None, the 5.0s effective window (not 2.5s) is used."""
        from ml.predict_winner import predict_winners

        captured = _patch_predict_winner_io(monkeypatch)

        checkpoint_path = tmp_path / "winner.pt"
        checkpoint_path.write_bytes(b"stub")
        corners = [(0, 0), (100, 0), (100, 75), (0, 75)]

        results = predict_winners(
            video_path=tmp_path / "video.mp4",
            corners=corners,
            rally_intervals=[(100.0, 120.0)],
            checkpoint_path=checkpoint_path,
            config=None,  # force auto-load from checkpoint metadata
        )

        # end_s - effective_clip_duration_s = 120.0 - 5.0 = 115.0
        # (NOT 120.0 - 2.5 = 117.5, which the old clip_duration_s bug produced).
        assert captured["clip_starts"] == [115.0]
        assert captured["clip_ends"] == [120.0]
        assert results == [(0, pytest.approx(probs_team0(), abs=1e-4))]

    def test_explicit_config_override_uses_its_effective_duration(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An explicit config wins over checkpoint metadata for the clip window."""
        from ml.predict_winner import predict_winners

        captured = _patch_predict_winner_io(monkeypatch)

        checkpoint_path = tmp_path / "winner.pt"
        checkpoint_path.write_bytes(b"stub")
        corners = [(0, 0), (100, 0), (100, 75), (0, 75)]

        explicit = WinnerModelConfig(
            device="cpu", clip_duration_s=2.5, clip_duration_override_s=3.0
        )

        predict_winners(
            video_path=tmp_path / "video.mp4",
            corners=corners,
            rally_intervals=[(100.0, 120.0)],
            checkpoint_path=checkpoint_path,
            config=explicit,
        )

        # Explicit override (3.0s): 120.0 - 3.0 = 117.0.
        assert captured["clip_starts"] == [117.0]


def probs_team0() -> float:
    """Softmax max for logits [2.0, -2.0] at temperature 1.0."""
    return float(torch.softmax(torch.tensor([[2.0, -2.0]]), dim=1).max().item())
