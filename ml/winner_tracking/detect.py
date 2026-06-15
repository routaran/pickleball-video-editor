"""Full-resolution ball-candidate detection.

Per frame, generate a high-recall set of ball candidates from the union of:
- motion (3-frame temporal differencing — the ball moves, static distractors don't),
- color (optic-yellow HSV), and
- small-blob shape, scored by circularity and size.

A per-clip *static-yellow persistence* mask suppresses fixed yellow objects (court-edge
tape, net center strap) that fooled naive color thresholding.  Recall is favored over
precision: the tracker disambiguates the true ball from clutter across frames.

No person detector yet (deferred — see audit notes); limb false positives are handled
downstream by trajectory smoothness / speed gating.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from ml.winner_tracking.person import point_in_boxes

__all__ = ["Candidate", "DetectorConfig", "build_court_mask", "detect_candidates"]


@dataclass(slots=True)
class Candidate:
    """One ball candidate in one frame (image pixel coordinates)."""

    frame: int
    x: float
    y: float
    radius: float
    area: float
    color_score: float      # mean yellowness over the blob, [0,1]
    motion_score: float     # mean motion magnitude over the blob, [0,1]
    circularity: float      # area / (pi r^2), [0,1]
    score: float            # combined candidate quality used for NMS ranking
    in_player: float = 0.0  # 1.0 if centre lies inside a (shrunk) person box


@dataclass(slots=True)
class DetectorConfig:
    hsv_lo: tuple[int, int, int] = (20, 60, 110)
    hsv_hi: tuple[int, int, int] = (55, 255, 255)
    motion_thr: int = 18
    min_area: float = 2.0
    max_area: float = 1200.0
    court_margin_px: int = 70
    static_persistence: float = 0.55   # yellow in >55% of frames => fixed object
    max_candidates_per_frame: int = 40


def build_court_mask(
    corners: list[list[int]], height: int, width: int, margin_px: int
) -> np.ndarray:
    """Filled court polygon dilated by ``margin_px`` (uint8 0/255)."""
    poly = np.asarray(corners, dtype=np.int32)
    mask = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(poly), 255)
    if margin_px > 0:
        k = np.ones((margin_px, margin_px), np.uint8)
        mask = cv2.dilate(mask, k)
    return mask


def _static_yellow_mask(yellow_stack: np.ndarray, thr: float) -> np.ndarray:
    """Pixels that are yellow in more than ``thr`` fraction of frames (uint8 0/255)."""
    persistence = yellow_stack.mean(axis=0)  # (H, W) float in [0,1]
    return (persistence > thr).astype(np.uint8) * 255


def detect_candidates(
    frames: np.ndarray,           # (T, H, W, 3) uint8 RGB
    corners: list[list[int]],
    cfg: DetectorConfig | None = None,
    person_boxes: list[list[tuple[float, float, float, float]]] | None = None,
    player_shrink: float = 0.15,
) -> list[list[Candidate]]:
    """Return per-frame candidate lists (index 0..T-1; ends get empty lists).

    When ``person_boxes`` is given (one list per frame), each candidate is tagged
    ``in_player=1.0`` if its centre falls inside a player box shrunk by
    ``player_shrink`` (so only the core body counts).  Tagging is soft: candidates
    are kept (recall preserved); the tracker applies the penalty.
    """
    if cfg is None:
        cfg = DetectorConfig()
    t_count, height, width, _ = frames.shape
    court = build_court_mask(corners, height, width, cfg.court_margin_px)

    # Precompute grayscale + per-frame yellow masks.
    gray = np.empty((t_count, height, width), np.int16)
    yellow = np.empty((t_count, height, width), np.uint8)
    lo = np.array(cfg.hsv_lo, np.uint8)
    hi = np.array(cfg.hsv_hi, np.uint8)
    for i in range(t_count):
        bgr = cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR)
        gray[i] = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.int16)
        yellow[i] = (cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), lo, hi) > 0)

    static_mask = _static_yellow_mask(yellow, cfg.static_persistence)
    dynamic_ok = cv2.bitwise_and(court, cv2.bitwise_not(static_mask))  # allowed region

    out: list[list[Candidate]] = [[] for _ in range(t_count)]
    open_k = np.ones((2, 2), np.uint8)

    for i in range(1, t_count - 1):
        # 3-frame motion: min of forward/backward abs-diff suppresses one-sided ghosts.
        d = np.minimum(
            np.abs(gray[i] - gray[i - 1]), np.abs(gray[i] - gray[i + 1])
        ).astype(np.uint8)
        motion = cv2.bitwise_and((d > cfg.motion_thr).astype(np.uint8) * 255, dynamic_ok)
        ycol = cv2.bitwise_and(yellow[i] * 255, dynamic_ok)

        # Candidate sources: moving blobs OR yellow blobs (union -> high recall).
        comb = cv2.bitwise_or(motion, ycol)
        comb = cv2.morphologyEx(comb, cv2.MORPH_OPEN, open_k)

        contours, _ = cv2.findContours(comb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        d_norm = d.astype(np.float32) / 255.0
        ycol_i = yellow[i]
        frame_cands: list[Candidate] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < cfg.min_area or area > cfg.max_area:
                continue
            (cx, cy), r = cv2.minEnclosingCircle(c)
            if r < 1.0:
                continue
            circ = float(area / (np.pi * r * r + 1e-6))
            # Local feature scores via a small ROI mask around the blob (fast).
            bx, by, bw, bh = cv2.boundingRect(c)
            roi = np.zeros((bh, bw), np.uint8)
            cv2.drawContours(roi, [c], -1, 255, -1, offset=(-bx, -by))
            sel = roi > 0
            color_s = float(ycol_i[by:by + bh, bx:bx + bw][sel].mean())
            motion_s = float(d_norm[by:by + bh, bx:bx + bw][sel].mean())
            # Combined quality: prefer yellow, moving, compact, small blobs.
            score = (
                0.45 * color_s
                + 0.30 * motion_s
                + 0.15 * min(circ, 1.0)
                + 0.10 * (1.0 - min(area / cfg.max_area, 1.0))
            )
            in_player = 0.0
            if person_boxes is not None:
                in_player = float(point_in_boxes(cx, cy, person_boxes[i], player_shrink))
            frame_cands.append(
                Candidate(i, float(cx), float(cy), float(r), float(area),
                          color_s, motion_s, circ, float(score), in_player)
            )
        frame_cands.sort(key=lambda c: -c.score)
        out[i] = frame_cands[: cfg.max_candidates_per_frame]
    return out
