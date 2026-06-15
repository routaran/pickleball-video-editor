"""Sparse person detection for player-region suppression (torchvision, offline).

The Phase-1 audit showed the tracker locking onto players, not the ball.  This
provides per-frame player boxes so the detector/tracker can DOWN-WEIGHT (soft, not
hard — the ball often passes near bodies) candidates that sit inside a player.

Detection runs sparsely (every ``stride`` frames) on the GPU and each intervening
frame reuses the nearest detected frame's boxes — players move slowly relative to
60 fps, and a soft penalty tolerates the small lag.
"""

import numpy as np
import torch
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_320_FPN_Weights as _W,
    fasterrcnn_mobilenet_v3_large_320_fpn,
)

__all__ = ["PersonDetector", "point_in_boxes"]

_COCO_PERSON = 1


class PersonDetector:
    """Lazy-loaded Faster R-CNN MobileNetV3 person detector."""

    def __init__(self, device: str | None = None, score_thr: float = 0.5) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.score_thr = score_thr
        self._model = None

    def _ensure(self) -> None:
        if self._model is None:
            m = fasterrcnn_mobilenet_v3_large_320_fpn(weights=_W.DEFAULT)
            m.eval().to(self.device)
            self._model = m

    @torch.no_grad()
    def boxes_per_frame(
        self, frames: np.ndarray, stride: int = 6, batch: int = 16
    ) -> list[list[tuple[float, float, float, float]]]:
        """Return a person-box list for every frame in ``frames`` (T, H, W, 3) RGB.

        Boxes are (x1, y1, x2, y2) in pixel coords.  Detected on a strided subset;
        each frame is assigned the nearest detected frame's boxes.
        """
        self._ensure()
        t_count = len(frames)
        det_idx = list(range(0, t_count, stride))
        if det_idx and det_idx[-1] != t_count - 1:
            det_idx.append(t_count - 1)

        det_boxes: dict[int, list[tuple[float, float, float, float]]] = {}
        for s in range(0, len(det_idx), batch):
            chunk = det_idx[s:s + batch]
            tens = [
                torch.from_numpy(frames[i]).permute(2, 0, 1).float().div(255.0).to(self.device)
                for i in chunk
            ]
            outs = self._model(tens)
            for i, out in zip(chunk, outs):
                keep = (out["labels"] == _COCO_PERSON) & (out["scores"] >= self.score_thr)
                boxes = out["boxes"][keep].cpu().numpy()
                det_boxes[i] = [(float(a), float(b), float(c), float(d)) for a, b, c, d in boxes]

        det_sorted = sorted(det_boxes.keys())
        per_frame: list[list[tuple[float, float, float, float]]] = []
        for f in range(t_count):
            nearest = min(det_sorted, key=lambda d: abs(d - f))
            per_frame.append(det_boxes[nearest])
        return per_frame


def point_in_boxes(
    x: float, y: float, boxes: list[tuple[float, float, float, float]], shrink: float = 0.0
) -> bool:
    """True if (x, y) lies inside any box, optionally shrunk toward its center.

    ``shrink`` in [0,1): fraction trimmed off each side, so only the *core* body
    (not the wide margin where a ball may pass) counts as inside.
    """
    for x1, y1, x2, y2 in boxes:
        if shrink > 0:
            mx, my = (x2 - x1) * shrink * 0.5, (y2 - y1) * shrink * 0.5
            x1, y1, x2, y2 = x1 + mx, y1 + my, x2 - mx, y2 - my
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False
