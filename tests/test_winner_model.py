"""Tests for WinnerClassifier architecture and predict_winners inference.

All tests run WITHOUT a trained checkpoint and WITHOUT real video files.
torch is imported via pytest.importorskip so the suite degrades gracefully
in environments where it is not installed.

Test classes
------------
TestWinnerClassifierArchitecture  — forward-pass shape, softmax, gradients, param count
TestPredictWinners                 — inference pipeline via mocks
"""

import sys
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

        The model must not be loaded (load_winner_classifier should not be
        called) because there is nothing to predict.
        """
        # Use a real path so the checkpoint existence check doesn't fire.
        fake_checkpoint = tmp_path / "model.pt"
        fake_checkpoint.write_bytes(b"placeholder")

        with patch("ml.predict_winner.load_winner_classifier") as mock_load:
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

        with (
            patch("ml.predict_winner.load_winner_classifier", return_value=mock_model),
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

        with (
            patch("ml.predict_winner.load_winner_classifier", return_value=mock_model),
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

        with (
            patch("ml.predict_winner.load_winner_classifier", return_value=mock_model),
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
