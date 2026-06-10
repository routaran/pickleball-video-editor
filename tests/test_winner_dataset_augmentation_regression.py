"""Focused regression tests for WinnerDataset augmentation semantics.

These tests are intentionally lightweight:
- no real video decoding
- no real torch dependency required
- deterministic augmentation via patched randomness

They must not leave fake torch / torchvision modules in ``sys.modules`` during
collection because later test modules import the real winner-model stack.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np


_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _build_lightweight_torch_stubs() -> dict[str, types.ModuleType]:
    """Return minimal torch / torchvision stubs needed by ml.winner_dataset."""

    class FakeTensor:
        def __init__(self, array: np.ndarray) -> None:
            self._array = np.array(array, copy=False)

        def permute(self, *dims: int) -> "FakeTensor":
            return FakeTensor(np.transpose(self._array, dims))

        def float(self) -> "FakeTensor":
            return FakeTensor(self._array.astype(np.float32, copy=False))

        def div(self, value: float) -> "FakeTensor":
            return FakeTensor(self._array / value)

        def numpy(self) -> np.ndarray:
            return np.array(self._array, copy=False)

    torch_stub = types.ModuleType("torch")
    torch_stub.Tensor = FakeTensor
    torch_stub.from_numpy = lambda array: FakeTensor(np.asarray(array))

    torch_utils = types.ModuleType("torch.utils")
    torch_utils_data = types.ModuleType("torch.utils.data")

    class Dataset:
        pass

    torch_utils_data.Dataset = Dataset
    torch_utils.data = torch_utils_data
    torch_stub.utils = torch_utils

    tv_stub = types.ModuleType("torchvision")
    tv_transforms = types.ModuleType("torchvision.transforms")
    tv_functional = types.ModuleType("torchvision.transforms.functional")
    tv_functional.adjust_brightness = lambda tensor, _factor: tensor
    tv_functional.adjust_contrast = lambda tensor, _factor: tensor
    tv_functional.adjust_saturation = lambda tensor, _factor: tensor
    tv_transforms.functional = tv_functional
    tv_stub.transforms = tv_transforms

    return {
        "torch": torch_stub,
        "torch.utils": torch_utils,
        "torch.utils.data": torch_utils_data,
        "torchvision": tv_stub,
        "torchvision.transforms": tv_transforms,
        "torchvision.transforms.functional": tv_functional,
    }


def _build_lightweight_cv2_stub() -> types.ModuleType:
    """Return a minimal cv2 stub for ml.video_features import-time needs."""

    cv2_stub = types.ModuleType("cv2")
    cv2_stub.getPerspectiveTransform = lambda _src, _dst: np.eye(3, dtype=np.float64)
    cv2_stub.warpPerspective = lambda frame, _M, dsize: np.zeros(
        (dsize[1], dsize[0], frame.shape[2]),
        dtype=frame.dtype,
    )
    cv2_stub.resize = lambda frame, dsize: np.zeros(
        (dsize[1], dsize[0], frame.shape[2]),
        dtype=frame.dtype,
    )
    return cv2_stub


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _load_winner_dataset_symbols() -> tuple[object, type, type, object, object]:
    """Import ml.winner_dataset with isolated optional-dependency stubs."""

    stubbed_modules: dict[str, types.ModuleType] = {}
    if not _module_available("torch"):
        stubbed_modules.update(_build_lightweight_torch_stubs())
    if not _module_available("cv2"):
        stubbed_modules["cv2"] = _build_lightweight_cv2_stub()

    previous_modules = {
        name: sys.modules.get(name)
        for name in (
            "torch",
            "torch.utils",
            "torch.utils.data",
            "torchvision",
            "torchvision.transforms",
            "torchvision.transforms.functional",
            "cv2",
            "ml.video_features",
            "ml.winner_dataset",
        )
    }

    try:
        for name in ("ml.video_features", "ml.winner_dataset"):
            sys.modules.pop(name, None)
        sys.modules.update(stubbed_modules)

        from ml.config import WinnerModelConfig

        winner_dataset = importlib.import_module("ml.winner_dataset")
        return (
            winner_dataset,
            WinnerModelConfig,
            winner_dataset.WinnerDataset,
            winner_dataset._RallyRecord,
            winner_dataset._horizontal_flip_frames,
        )
    finally:
        for name in (
            "ml.winner_dataset",
            "ml.video_features",
            *stubbed_modules.keys(),
        ):
            sys.modules.pop(name, None)
        for name, module in previous_modules.items():
            if module is not None:
                sys.modules[name] = module


def _tensor_to_numpy(tensor: object) -> np.ndarray:
    if hasattr(tensor, "detach"):
        return tensor.detach().cpu().numpy()  # type: ignore[no-any-return]
    return tensor.numpy()  # type: ignore[no-any-return]


class TestWinnerDatasetAugmentationRegression:
    """Regression tests for label semantics under image mirroring."""

    @staticmethod
    def _make_dataset(
        *,
        WinnerModelConfig: type,
        WinnerDataset: type,
        _RallyRecord: type,
        winning_team: int,
    ) -> object:
        ds = WinnerDataset.__new__(WinnerDataset)
        # fps_out=2, clip_duration_s=1.0 → T=2, J=max(1,round(0.2*2))=1
        # extended array is T+2J = 4 frames; nominal clip at [1:3]
        ds._config = WinnerModelConfig(fps_out=2, clip_duration_s=1.0, device="cpu")
        ds._split = "train"
        ds._do_augment = True
        ds._records = [
            _RallyRecord(
                video_path=Path("/fake/video.mp4"),
                end_seconds=12.5,
                corners=[(10, 20), (310, 20), (310, 220), (10, 220)],
                winning_team=winning_team,
            )
        ]
        return ds

    @staticmethod
    def _asymmetric_frames() -> np.ndarray:
        """Return the nominal 2-frame clip (T=2) used as the centered window."""
        frames = np.zeros((2, 4, 6, 3), dtype=np.uint8)
        frames[:, :, :2, 0] = 255
        frames[:, :, 4:, 1] = 128
        frames[:, 1:3, 2:4, 2] = 64
        return frames

    @staticmethod
    def _wrap_in_extended(nominal: np.ndarray, J: int = 1) -> np.ndarray:
        """Wrap *nominal* frames in a (T+2J, H, W, C) extended array.

        Nominal frames are placed at [J : J+T]; prefix and suffix padding
        frames are zero-filled.  With ``randint`` returning 0, __getitem__
        slices ``[J : J+T]`` which recovers *nominal* exactly, so expected
        arrays in tests remain identical to the pre-fix versions.
        """
        T, H, W, C = nominal.shape
        extended = np.zeros((T + 2 * J, H, W, C), dtype=nominal.dtype)
        extended[J : J + T] = nominal
        return extended

    def test_horizontal_flip_preserves_label_while_mirroring_pixels(self) -> None:
        """Horizontal mirroring should not change the winner label."""
        (
            winner_dataset_module,
            WinnerModelConfig,
            WinnerDataset,
            _RallyRecord,
            _horizontal_flip_frames,
        ) = _load_winner_dataset_symbols()
        ds = self._make_dataset(
            WinnerModelConfig=WinnerModelConfig,
            WinnerDataset=WinnerDataset,
            _RallyRecord=_RallyRecord,
            winning_team=1,
        )
        nominal = self._asymmetric_frames()
        # _fetch_clip_tensor returns the extended array (T+2J=4 frames).
        # With randint→0, __getitem__ slices [J:J+T]=[1:3] = nominal.
        extended = self._wrap_in_extended(nominal, J=1)
        expected = (
            np.transpose(_horizontal_flip_frames(nominal), (0, 3, 1, 2)).astype(np.float32)
            / 255.0
        )

        with (
            patch.object(winner_dataset_module, "_fetch_clip_tensor", return_value=extended),
            patch.object(
                winner_dataset_module,
                "_apply_color_jitter",
                side_effect=lambda clip, **_: clip,
            ),
            patch.object(winner_dataset_module.random, "randint", return_value=0),
            patch.object(winner_dataset_module.random, "random", return_value=0.0),
        ):
            clip_tensor, winning_team = ds[0]

        assert winning_team == 1
        np.testing.assert_allclose(_tensor_to_numpy(clip_tensor), expected)

    def test_no_flip_leaves_pixels_and_label_unchanged(self) -> None:
        """The non-flip branch should preserve both pixels and label."""
        (
            winner_dataset_module,
            WinnerModelConfig,
            WinnerDataset,
            _RallyRecord,
            _,
        ) = _load_winner_dataset_symbols()
        ds = self._make_dataset(
            WinnerModelConfig=WinnerModelConfig,
            WinnerDataset=WinnerDataset,
            _RallyRecord=_RallyRecord,
            winning_team=0,
        )
        nominal = self._asymmetric_frames()
        extended = self._wrap_in_extended(nominal, J=1)
        expected = np.transpose(nominal, (0, 3, 1, 2)).astype(np.float32) / 255.0

        with (
            patch.object(winner_dataset_module, "_fetch_clip_tensor", return_value=extended),
            patch.object(
                winner_dataset_module,
                "_apply_color_jitter",
                side_effect=lambda clip, **_: clip,
            ),
            patch.object(winner_dataset_module.random, "randint", return_value=0),
            patch.object(winner_dataset_module.random, "random", return_value=0.9),
        ):
            clip_tensor, winning_team = ds[0]

        assert winning_team == 0
        np.testing.assert_allclose(_tensor_to_numpy(clip_tensor), expected)

    def test_vertical_flip_swaps_label_while_mirroring_pixels(self) -> None:
        """Vertical mirroring must swap the winner label (teams differ along height).

        ``random.random`` is patched to 0.3 so that ``flip_random`` falls in
        ``[0.25, 0.5)`` — the vertical-flip branch.  The frames are constructed
        to be asymmetric along *both* the height axis (axis=1) and the width
        axis (axis=2), so that flipping the wrong axis would produce a pixel
        mismatch and a correct horizontal-only flip would also be detected.
        """
        (
            winner_dataset_module,
            WinnerModelConfig,
            WinnerDataset,
            _RallyRecord,
            _,
        ) = _load_winner_dataset_symbols()
        ds = self._make_dataset(
            WinnerModelConfig=WinnerModelConfig,
            WinnerDataset=WinnerDataset,
            _RallyRecord=_RallyRecord,
            winning_team=1,
        )

        # Build frames asymmetric along BOTH height (axis=1) and width (axis=2).
        # Width asymmetry: left columns have R=255, right columns have G=128.
        # Height asymmetry: only the top row (row 0) has B=200; all other rows
        # leave B=0.  A vertical flip turns row 0 into row 3, so the resulting
        # pixel layout differs from a horizontal flip or no-flip — a wrong-axis
        # operation cannot accidentally pass the assertion below.
        frames = np.zeros((2, 4, 6, 3), dtype=np.uint8)
        frames[:, :, :2, 0] = 255   # left columns, channel R — width asymmetry
        frames[:, :, 4:, 1] = 128   # right columns, channel G — width asymmetry
        frames[:, 0, :, 2] = 200    # top row only, channel B — height asymmetry

        expected = (
            np.transpose(
                np.ascontiguousarray(np.flip(frames, axis=1)),
                (0, 3, 1, 2),
            ).astype(np.float32)
            / 255.0
        )

        extended = self._wrap_in_extended(frames, J=1)

        with (
            patch.object(winner_dataset_module, "_fetch_clip_tensor", return_value=extended),
            patch.object(
                winner_dataset_module,
                "_apply_color_jitter",
                side_effect=lambda clip, **_: clip,
            ),
            patch.object(winner_dataset_module.random, "randint", return_value=0),
            patch.object(winner_dataset_module.random, "random", return_value=0.3),
        ):
            clip_tensor, returned_winning_team = ds[0]

        # Label must be flipped: winning_team was 1, vertical flip swaps it to 0.
        assert returned_winning_team == 1 - 1

        # Pixel content must match a top-bottom mirror.
        # A horizontal flip or no-flip would both fail here because the frames
        # are asymmetric along height (B channel differs between top and bottom).
        np.testing.assert_allclose(_tensor_to_numpy(clip_tensor), expected)
