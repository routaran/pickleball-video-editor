"""Visual sanity check for YOLO person detection + court filtering (doc Step 1).

Samples a handful of frames from one labelled video, runs the detector, and
writes annotated JPGs so you can eyeball:

* whether players (including the small far-court pair on phone footage) are
  detected,
* whether spectators / adjacent-court players are correctly rejected by the
  court polygon,
* whether the dilated court polygon lines up with the real court.

Drawing legend: yellow = dilated court polygon, red box = raw detection,
green dot = on-court foot-point (kept), red dot = off-court foot-point (rejected).

Usage::

    python -m ml.tools.validate_detector game1.training.json --frames 12 --out /tmp/court_check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main"]


def _load_video_and_corners(json_path: Path) -> tuple[Path, list[tuple[int, int]]] | None:
    with json_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    video_block = data.get("video") or {}
    video_path = Path(video_block.get("path", ""))
    raw_corners = video_block.get("court_corners") or []
    if len(raw_corners) != 4:
        return None
    return video_path, [(int(c[0]), int(c[1])) for c in raw_corners]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_detector",
        description="Overlay YOLO detections + court polygon on sampled frames.",
    )
    parser.add_argument("json_path", type=Path, help="A .training.json with court_corners.")
    parser.add_argument("--frames", type=int, default=12, help="Frames to sample (default: 12).")
    parser.add_argument("--fps", type=float, default=2.0,
                        help="Sampling rate to walk the video at (default: 2).")
    parser.add_argument("--out", type=Path, default=Path("/tmp/court_check"),
                        help="Output directory for annotated JPGs.")
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--model", type=str, default="yolov8n.pt")
    parser.add_argument("--max-extract-dim", type=int, default=1280)
    parser.add_argument("--weights-dir", type=Path, default=None,
                        help="Cache dir for YOLO weights (default: ml/cache/weights/).")
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--dilation", type=float, default=None,
                        help="Court-polygon dilation for the on-court test "
                             "(default: CourtModel's built-in 0.12). Raise to "
                             "recover wide/baseline players; eyeball that the "
                             "adjacent court is still rejected.")
    args = parser.parse_args(argv)

    json_path = args.json_path.expanduser().resolve()
    if not json_path.exists():
        print(f"[validate_detector] ERROR: not found: {json_path}", file=sys.stderr)
        return 1

    loaded = _load_video_and_corners(json_path)
    if loaded is None:
        print(f"[validate_detector] ERROR: no 4 court_corners in {json_path.name}", file=sys.stderr)
        return 1
    video_path, corners = loaded
    if not video_path.exists():
        print(f"[validate_detector] ERROR: video missing: {video_path}", file=sys.stderr)
        return 1

    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    from ml.motion.court_filter import CourtModel, foot_point  # noqa: PLC0415
    from ml.motion.detector import MotionDetector, _stream_bgr_frames  # noqa: PLC0415
    from ml.video_features import (  # noqa: PLC0415
        CANONICAL_SIZE,
        get_video_frame_size,
        resolve_extract_geometry,
    )

    native = get_video_frame_size(video_path)
    extract_size, scaled_corners = resolve_extract_geometry(
        native, corners, CANONICAL_SIZE, args.max_extract_dim
    )
    court = (
        CourtModel(scaled_corners, CANONICAL_SIZE, dilation=args.dilation)
        if args.dilation is not None
        else CourtModel(scaled_corners, CANONICAL_SIZE)
    )
    poly = court.polygon.astype(np.int32).reshape(-1, 1, 2)

    detector = MotionDetector(
        model_name=args.model, conf=args.conf, imgsz=args.imgsz,
        device=args.device, max_extract_dim=args.max_extract_dim,
        weights_dir=args.weights_dir,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    saved = 0
    total_on = 0
    total_raw = 0

    # Walk the video at --fps, keep up to --frames evenly across what we read.
    frames_buf: list[np.ndarray] = []
    for frame in _stream_bgr_frames(video_path, args.fps, extract_size):
        frames_buf.append(frame)
        if len(frames_buf) >= args.frames * 8:  # cap memory; enough to subsample
            break

    if not frames_buf:
        print("[validate_detector] ERROR: ffmpeg produced no frames.", file=sys.stderr)
        return 1

    pick = np.linspace(0, len(frames_buf) - 1, min(args.frames, len(frames_buf))).astype(int)
    chosen = [frames_buf[i] for i in pick]
    boxes_per = detector.person_boxes(chosen)

    for n, (frame, boxes) in enumerate(zip(chosen, boxes_per)):
        img = frame.copy()
        cv2.polylines(img, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
        on_court = 0
        for b in boxes:
            x1, y1, x2, y2 = (int(v) for v in b)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
            fx, fy = foot_point(b)
            if court.on_court(fx, fy):
                on_court += 1
                cv2.circle(img, (int(fx), int(fy)), 5, (0, 255, 0), -1)
            else:
                cv2.circle(img, (int(fx), int(fy)), 5, (0, 0, 255), -1)
        cv2.putText(img, f"raw={len(boxes)} on_court={on_court}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        out_path = args.out / f"{video_path.stem}_{n:02d}.jpg"
        cv2.imwrite(str(out_path), img)
        saved += 1
        total_on += on_court
        total_raw += len(boxes)

    print(f"[validate_detector] wrote {saved} frames to {args.out}", file=sys.stderr)
    print(f"[validate_detector] mean raw={total_raw / saved:.1f} "
          f"on_court={total_on / saved:.1f} per frame "
          f"(expect ~4 on_court during rallies)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
