"""Tests for WinnerClassifier architecture and predict_winners inference.

All tests run WITHOUT a trained checkpoint and WITHOUT real video files.
torch is imported via pytest.importorskip so the suite degrades gracefully
in environments where it is not installed.

Test classes
------------
TestWinnerClassifierArchitecture  — forward-pass shape, softmax, gradients, param count
TestPredictWinners                 — inference pipeline via mocks
TestCheckpointMetadata             — E2: config round-trip, old-format back-compat, mismatch warning
"""

import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so both ml/ and src/ are importable.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Guard: skip entire module when torch is not importable.
# ---------------------------------------------------------------------------

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------------------
# Import the modules under test.
# ---------------------------------------------------------------------------

from ml.winner_model import WinnerClassifier, load_winner_classifier  # noqa: E402
from ml.predict_winner import predict_winners  # noqa: E402
from ml.config import WinnerModelConfig  # noqa: E402
from ml.train_winner import _config_to_dict  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_clip(batch: int = 2, frames: int = 20) -> "torch.Tensor":
    """Return a zero-filled (B, T, 3, 128, 256) float32 tensor."""
    return torch.zeros(batch, frames, 3, 128, 256)


# ---------------------------------------------------------------------------
# TestWinnerClassifierArchitecture
# ---------------------------------------------------------------------------


class TestWinnerClassifierArchitecture:
    """Structural tests for WinnerClassifier that need no checkpoint."""

    def test_forward_pass_output_shape(self) -> None:
        """Forward pass on a (2, 20, 3, 128, 256) input must yield shape (2, 2).

        Verifies that the backbone, temporal module, and classification head
        are wired together correctly end-to-end.
        """
        model = WinnerClassifier()
        x = _dummy_clip(batch=2, frames=20)
        out = model(x)

        assert out.shape == (2, 2), (
            f"Expected output shape (2, 2), got {tuple(out.shape)}"
        )

    def test_softmax_rows_sum_to_one(self) -> None:
        """Softmax probabilities across the class dimension must sum to 1.0.

        Checks all rows in a batch to confirm the head produces a proper
        probability distribution.
        """
        model = WinnerClassifier()
        x = _dummy_clip(batch=2, frames=20)
        out = model(x)

        probs = torch.softmax(out, dim=1)
        row_sums = probs.sum(dim=1)

        for i, s in enumerate(row_sums):
            s_val = float(s.detach())
            assert abs(s_val - 1.0) < 1e-5, (
                f"Row {i} softmax sum should be 1.0, got {s_val:.8f}"
            )

    def test_gradient_flows_through_all_submodules(self) -> None:
        """Backward pass must not raise and must produce gradients everywhere.

        Specifically exercises that the backbone, temporal Conv1d, and the
        linear head all have non-None .grad after .backward().
        """
        model = WinnerClassifier()
        x = _dummy_clip(batch=1, frames=20)

        out = model(x)
        out.sum().backward()

        # Spot-check one parameter from each major submodule.
        backbone_param = next(model.backbone.parameters())
        temporal_param = next(model.temporal.parameters())
        head_param = next(model.head.parameters())

        assert backbone_param.grad is not None, "No gradient in backbone"
        assert temporal_param.grad is not None, "No gradient in temporal module"
        assert head_param.grad is not None, "No gradient in classification head"

    def test_parameter_count_in_expected_range(self) -> None:
        """Total parameter count should be approximately 11.2 M.

        The range [10_000_000, 12_000_000] accommodates minor architecture
        variations while ensuring the ResNet-18 backbone is intact and not
        accidentally replaced with a much smaller or larger model.
        """
        model = WinnerClassifier()
        total_params = sum(p.numel() for p in model.parameters())

        assert 10_000_000 <= total_params <= 12_000_000, (
            f"Expected ~11.2 M parameters, got {total_params:,}"
        )


# ---------------------------------------------------------------------------
# TestPredictWinners
# ---------------------------------------------------------------------------


class TestPredictWinners:
    """Inference pipeline tests using mocks for filesystem and video I/O."""

    # Shared dummy values used across tests.
    _VIDEO_PATH = Path("/fake/video.mp4")
    _CORNERS = [(0, 0), (256, 0), (256, 128), (0, 128)]
    _CHECKPOINT = Path("/fake/checkpoint.pt")

    # ------------------------------------------------------------------
    # Test 5 — empty intervals short-circuits before loading the model
    # ------------------------------------------------------------------

    def test_empty_intervals_returns_empty_list(self, tmp_path: Path) -> None:
        """predict_winners with [] rally_intervals returns [] immediately.

        torch.load must not be called because the early-return guard fires
        before any checkpoint I/O.
        """
        # Use a real path so the checkpoint existence check doesn't fire.
        fake_checkpoint = tmp_path / "model.pt"
        fake_checkpoint.write_bytes(b"placeholder")

        with patch("ml.predict_winner.torch.load") as mock_load:
            result = predict_winners(
                self._VIDEO_PATH,
                self._CORNERS,
                [],
                fake_checkpoint,
            )

        assert result == [], f"Expected [], got {result!r}"
        mock_load.assert_not_called()

    # ------------------------------------------------------------------
    # Test 6 — result length matches number of rally intervals
    # ------------------------------------------------------------------

    def test_returns_correct_length(self, tmp_path: Path) -> None:
        """predict_winners must return exactly one result per rally interval."""
        import numpy as np

        fake_checkpoint = tmp_path / "model.pt"
        fake_checkpoint.write_bytes(b"placeholder")

        fake_frames = np.zeros((20, 128, 256, 3), dtype=np.uint8)

        # A model stub that always predicts class 0 with high confidence.
        mock_model = MagicMock(spec=WinnerClassifier)
        mock_model.return_value = torch.tensor([[2.0, 1.0]])

        rally_intervals = [(0.0, 3.0), (5.0, 8.0), (10.0, 13.0)]
        fake_ckpt = {"model_state_dict": {}, "temperature": 1.0}

        with (
            patch("ml.predict_winner.torch.load", return_value=fake_ckpt),
            patch("ml.predict_winner.WinnerClassifier", return_value=mock_model),
            patch("ml.predict_winner.extract_clip", return_value=fake_frames),
            patch("ml.predict_winner.warp_clip_to_canonical", return_value=fake_frames),
            patch("ml.predict_winner.compute_homography", return_value=None),
        ):
            result = predict_winners(
                self._VIDEO_PATH,
                self._CORNERS,
                rally_intervals,
                fake_checkpoint,
            )

        assert len(result) == 3, (
            f"Expected 3 results for 3 rally intervals, got {len(result)}"
        )

    # ------------------------------------------------------------------
    # Test 7 — confidence values are valid probabilities in [0, 1]
    # ------------------------------------------------------------------

    def test_confidence_in_unit_interval(self, tmp_path: Path) -> None:
        """All returned confidence values must lie in [0.0, 1.0]."""
        import numpy as np

        fake_checkpoint = tmp_path / "model.pt"
        fake_checkpoint.write_bytes(b"placeholder")

        fake_frames = np.zeros((20, 128, 256, 3), dtype=np.uint8)

        mock_model = MagicMock(spec=WinnerClassifier)
        mock_model.return_value = torch.tensor([[2.0, 1.0]])

        rally_intervals = [(0.0, 3.0), (5.0, 8.0), (10.0, 13.0)]
        fake_ckpt = {"model_state_dict": {}, "temperature": 1.0}

        with (
            patch("ml.predict_winner.torch.load", return_value=fake_ckpt),
            patch("ml.predict_winner.WinnerClassifier", return_value=mock_model),
            patch("ml.predict_winner.extract_clip", return_value=fake_frames),
            patch("ml.predict_winner.warp_clip_to_canonical", return_value=fake_frames),
            patch("ml.predict_winner.compute_homography", return_value=None),
        ):
            result = predict_winners(
                self._VIDEO_PATH,
                self._CORNERS,
                rally_intervals,
                fake_checkpoint,
            )

        for i, (_, confidence) in enumerate(result):
            assert 0.0 <= confidence <= 1.0, (
                f"Rally {i}: confidence {confidence} is outside [0, 1]"
            )

    # ------------------------------------------------------------------
    # Test 8 — winning_team is always 0 or 1
    # ------------------------------------------------------------------

    def test_winning_team_is_zero_or_one(self, tmp_path: Path) -> None:
        """All returned winning_team values must be 0 or 1."""
        import numpy as np

        fake_checkpoint = tmp_path / "model.pt"
        fake_checkpoint.write_bytes(b"placeholder")

        fake_frames = np.zeros((20, 128, 256, 3), dtype=np.uint8)

        mock_model = MagicMock(spec=WinnerClassifier)
        mock_model.return_value = torch.tensor([[2.0, 1.0]])

        rally_intervals = [(0.0, 3.0), (5.0, 8.0), (10.0, 13.0)]
        fake_ckpt = {"model_state_dict": {}, "temperature": 1.0}

        with (
            patch("ml.predict_winner.torch.load", return_value=fake_ckpt),
            patch("ml.predict_winner.WinnerClassifier", return_value=mock_model),
            patch("ml.predict_winner.extract_clip", return_value=fake_frames),
            patch("ml.predict_winner.warp_clip_to_canonical", return_value=fake_frames),
            patch("ml.predict_winner.compute_homography", return_value=None),
        ):
            result = predict_winners(
                self._VIDEO_PATH,
                self._CORNERS,
                rally_intervals,
                fake_checkpoint,
            )

        for i, (winning_team, _) in enumerate(result):
            assert winning_team in (0, 1), (
                f"Rally {i}: winning_team={winning_team!r} must be 0 or 1"
            )

    # ------------------------------------------------------------------
    # Test 9 — missing checkpoint raises FileNotFoundError
    # ------------------------------------------------------------------

    def test_missing_checkpoint_raises_file_not_found_error(self) -> None:
        """predict_winners raises FileNotFoundError for a non-existent checkpoint.

        No mocks are applied to the checkpoint existence check so the real
        Path.exists() guard in predict_winners fires.
        """
        nonexistent = Path("/this/path/does/not/exist/model.pt")
        assert not nonexistent.exists(), "Precondition: path must not exist"

        with pytest.raises(FileNotFoundError):
            predict_winners(
                self._VIDEO_PATH,
                self._CORNERS,
                [(0.0, 3.0)],
                nonexistent,
            )


# ---------------------------------------------------------------------------
# TestCheckpointMetadata — E2 config round-trip and mismatch warning
# ---------------------------------------------------------------------------


def _save_checkpoint(path: Path, include_config: bool, cfg: WinnerModelConfig | None = None) -> None:
    """Helper: save a minimal WinnerClassifier checkpoint to *path*.

    Args:
        path: Destination ``.pt`` file.
        include_config: When True, add a ``"config"`` key serialised via
                        :func:`_config_to_dict`.  When False, omit it to
                        simulate the old checkpoint format.
        cfg: WinnerModelConfig to serialise.  Defaults to a fresh instance.
    """
    model = WinnerClassifier()
    effective_cfg = cfg if cfg is not None else WinnerModelConfig()
    payload: dict = {
        "model_state_dict": model.state_dict(),
        "epoch": 1,
        "val_accuracy": 0.75,
    }
    if include_config:
        payload["config"] = _config_to_dict(effective_cfg)
    torch.save(payload, path)


class TestCheckpointMetadata:
    """Tests for E2: config metadata round-trip, back-compat, mismatch warning."""

    # ------------------------------------------------------------------
    # Test 10 — checkpoint WITH config metadata loads without warning
    # ------------------------------------------------------------------

    def test_checkpoint_with_config_loads_silently(self, tmp_path: Path) -> None:
        """A checkpoint saved with matching config must load without any warning.

        Saves a checkpoint using the default WinnerModelConfig, then loads it
        back requesting the same default config.  No UserWarning should fire.
        """
        ckpt = tmp_path / "with_config.pt"
        cfg = WinnerModelConfig()
        _save_checkpoint(ckpt, include_config=True, cfg=cfg)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = load_winner_classifier(ckpt, device="cpu", config=cfg)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 0, (
            f"Expected no UserWarning on matching config, got: "
            + "; ".join(str(w.message) for w in user_warnings)
        )
        assert isinstance(model, WinnerClassifier)

    # ------------------------------------------------------------------
    # Test 11 — OLD checkpoint (no config key) loads without warning
    # ------------------------------------------------------------------

    def test_old_checkpoint_without_config_loads_unchanged(self, tmp_path: Path) -> None:
        """An old-format checkpoint without a 'config' key must load cleanly.

        Simulates a pre-E2 checkpoint that has only 'model_state_dict'.
        The loader must not raise and must not emit a UserWarning so that
        existing inference pipelines are unaffected.
        """
        ckpt = tmp_path / "old_format.pt"
        _save_checkpoint(ckpt, include_config=False)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = load_winner_classifier(ckpt, device="cpu")

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 0, (
            f"Expected no UserWarning for old-format checkpoint, got: "
            + "; ".join(str(w.message) for w in user_warnings)
        )
        assert isinstance(model, WinnerClassifier)

    # ------------------------------------------------------------------
    # Test 12 — config mismatch produces UserWarning, does NOT raise
    # ------------------------------------------------------------------

    def test_config_mismatch_emits_warning_not_exception(self, tmp_path: Path) -> None:
        """A config mismatch must emit a UserWarning and still return the model.

        Saves a checkpoint with clip_duration_s=2.5, then loads it requesting
        clip_duration_s=5.0.  The loader must:
        - NOT raise any exception
        - emit at least one UserWarning mentioning the mismatched field
        - still return a valid WinnerClassifier
        """
        ckpt = tmp_path / "mismatch.pt"
        training_cfg = WinnerModelConfig(clip_duration_s=2.5)
        _save_checkpoint(ckpt, include_config=True, cfg=training_cfg)

        # Request a different clip_duration_s to trigger the mismatch.
        inference_cfg = WinnerModelConfig(clip_duration_s=5.0)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = load_winner_classifier(ckpt, device="cpu", config=inference_cfg)

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) >= 1, (
            "Expected at least one UserWarning for config mismatch, got none"
        )
        # The warning message should mention the differing field.
        combined_msg = " ".join(str(w.message) for w in user_warnings)
        assert "clip_duration_s" in combined_msg, (
            f"Warning did not mention 'clip_duration_s'. Got: {combined_msg!r}"
        )
        assert isinstance(model, WinnerClassifier), (
            "load_winner_classifier must still return a model despite mismatch"
        )
