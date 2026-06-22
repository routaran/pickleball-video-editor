"""Batch-extract the cached raw-detection series for fused rally segmentation.

Runs pre-trained YOLOv8n + ByteTrack over each labelled video and caches the
**raw, pre-court-filter** geometry — every detection's foot-point (in
extracted-frame pixel space) and its track id, plus the court corners — as
``<out-dir>/<video-stem>.npz`` (v2 schema, see
:func:`ml.motion.features.save_feature_series`).  This is the heavy GPU pass; it
is run once so the cheap path (court filter + projection + features, plus the
court-dilation knob and fusion tuning) re-runs with no GPU.

Videos whose ``.training.json`` has no ``court_corners`` are skipped and listed
in the summary — fusion falls back to audio-only for those (see the deferred
corner-coverage decision in the plan).

Usage::

    python -m ml.tools.extract_motion_features --dir ~/Videos/pickleball
    python -m ml.tools.extract_motion_features game1.training.json --fps 5 --imgsz 1280
    python -m ml.tools.extract_motion_features --dir ~/Videos/pickleball --model yolov8s.pt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main"]


def _load_video_and_corners(
    json_path: Path,
) -> tuple[Path, list[tuple[int, int]]] | None:
    """Return ``(video_path, corners)`` or ``None`` when the file is unusable."""
    with json_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    if data.get("generated_by") == "auto_edit":
        return None

    video_block = data.get("video") or {}
    video_path = Path(video_block.get("path", ""))
    raw_corners = video_block.get("court_corners") or []
    if len(raw_corners) != 4:
        return None
    corners = [(int(c[0]), int(c[1])) for c in raw_corners]
    return video_path, corners


def _default_out_dir() -> Path:
    from ml.config import PathConfig  # noqa: PLC0415 — lazy so --help stays light

    return PathConfig().cache_dir / "motion"


def _extract_one(video_path: Path, corners: list[tuple[int, int]],
                 out_dir: Path, args: argparse.Namespace) -> int:
    """Extract + cache one video's raw-detection series. Returns 0 on success.

    Honours the ``--overwrite`` / cache-hit semantics of the batch path so the
    single-video (GUI) mode behaves identically.
    """
    out_path = out_dir / f"{video_path.stem}.npz"
    if out_path.exists() and not args.overwrite:
        print(f"[cache hit] {video_path.stem}.npz", file=sys.stderr)
        return 0

    from ml.motion.detector import MotionDetector  # noqa: PLC0415 — heavy, lazy
    from ml.motion.features import flatten_detections, save_feature_series  # noqa: PLC0415

    detector = MotionDetector(
        model_name=args.model,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        max_extract_dim=args.max_extract_dim,
        weights_dir=args.weights_dir,
    )
    try:
        print(f"[detect] {video_path.name} @ {args.fps} fps ...", file=sys.stderr)
        vd = detector.detect_video(video_path, corners, fps_out=args.fps)
        raw = flatten_detections(
            vd.frames,
            scaled_corners=vd.scaled_corners,
            extract_size=vd.extract_size,
            fps_out=args.fps,
            video_path=video_path,
        )
        save_feature_series(out_path, raw)
        print(f"[ok] {out_path.name} ({len(vd.frames)} frames)", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 — surface as a non-zero exit
        print(f"[FAIL] {video_path.name}: {exc}", file=sys.stderr)
        return 1


def _parse_corners_json(raw_json: str) -> list[tuple[int, int]] | None:
    """Parse a ``--corners-json`` value into four (x, y) tuples, or None if bad."""
    try:
        parsed = json.loads(raw_json)
        corners = [(int(p[0]), int(p[1])) for p in parsed]
    except (ValueError, TypeError, IndexError, KeyError):
        return None
    return corners if len(corners) == 4 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_motion_features",
        description=(
            "Run YOLOv8n person detection over labelled pickleball videos and "
            "cache per-frame on-court motion features for fused rally segmentation."
        ),
    )
    parser.add_argument("paths", metavar="PATH", nargs="*", type=Path,
                        help="One or more .training.json files.")
    parser.add_argument("--dir", dest="dirs", metavar="DIR", action="append",
                        type=Path, default=[],
                        help="Directory to glob for *.training.json (repeatable).")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Cache directory (default: ml/cache/motion).")
    parser.add_argument("--fps", type=float, default=5.0,
                        help="Detection sample rate, frames per second (default: 5).")
    parser.add_argument("--imgsz", type=int, default=1280,
                        help="YOLO inference image size (default: 1280).")
    parser.add_argument("--model", type=str, default="yolov8n.pt",
                        help="Ultralytics weights (default: yolov8n.pt).")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="Detection confidence threshold (default: 0.25).")
    parser.add_argument("--max-extract-dim", type=int, default=1280,
                        help="Longest side frames are extracted at (default: 1280).")
    parser.add_argument("--weights-dir", type=Path, default=None,
                        help="Cache dir for YOLO weights (default: ml/cache/weights/).")
    parser.add_argument("--device", type=str, default=None,
                        help="Torch device (default: ultralytics auto-select).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Recompute even if a cache file already exists.")
    parser.add_argument("--video", type=Path, default=None,
                        help="Single raw video file to process (use together with "
                             "--corners-json). Bypasses the .training.json scan; "
                             "used by the GUI's transparent one-click extraction.")
    parser.add_argument("--corners-json", type=str, default=None,
                        help="JSON array of four [x, y] court corners in source-"
                             "video pixel space, applied to --video. "
                             "e.g. '[[121,784],[1813,807],[1137,474],[790,472]]'.")
    args = parser.parse_args(argv)

    out_dir = (args.out_dir or _default_out_dir()).expanduser().resolve()

    # Single-video explicit-corners mode (used by the GUI's transparent
    # one-click extraction). --video and --corners-json must be given together.
    if args.video is not None or args.corners_json is not None:
        if args.video is None or args.corners_json is None:
            print("[extract_motion_features] ERROR: --video and --corners-json "
                  "must be supplied together.", file=sys.stderr)
            return 2
        corners = _parse_corners_json(args.corners_json)
        if corners is None:
            print("[extract_motion_features] ERROR: --corners-json must be a JSON "
                  "array of four [x, y] points.", file=sys.stderr)
            return 2
        video_path = args.video.expanduser().resolve()
        if not video_path.exists():
            print(f"[extract_motion_features] ERROR: video not found: {video_path}",
                  file=sys.stderr)
            return 2
        return _extract_one(video_path, corners, out_dir, args)

    # Collect candidate JSON paths.
    candidates: list[Path] = [p.expanduser().resolve() for p in (args.paths or [])]
    for d in (args.dirs or []):
        d = d.expanduser().resolve()
        if d.exists():
            candidates.extend(sorted(d.rglob("*.training.json")))
        else:
            print(f"[extract_motion_features] WARN: dir not found: {d}", file=sys.stderr)

    if not candidates:
        default_dir = (Path.home() / "Videos" / "pickleball").resolve()
        print(f"[extract_motion_features] No inputs; defaulting to {default_dir}",
              file=sys.stderr)
        candidates = sorted(default_dir.rglob("*.training.json"))

    # Deduplicate preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    if not unique:
        print("[extract_motion_features] No .training.json files found.", file=sys.stderr)
        return 1

    # Heavy imports only now that we know there is work to do.
    from ml.motion.detector import MotionDetector  # noqa: PLC0415
    from ml.motion.features import flatten_detections, save_feature_series  # noqa: PLC0415

    detector = MotionDetector(
        model_name=args.model,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        max_extract_dim=args.max_extract_dim,
        weights_dir=args.weights_dir,
    )

    n_done = 0
    skipped_no_corners: list[str] = []
    skipped_no_video: list[str] = []
    failed: list[str] = []

    for json_path in unique:
        loaded = _load_video_and_corners(json_path)
        if loaded is None:
            skipped_no_corners.append(json_path.name)
            print(f"[skip: no corners/auto_edit] {json_path.name}", file=sys.stderr)
            continue

        video_path, corners = loaded
        if not video_path.exists():
            skipped_no_video.append(json_path.name)
            print(f"[skip: video missing] {json_path.name} -> {video_path}", file=sys.stderr)
            continue

        out_path = out_dir / f"{video_path.stem}.npz"
        if out_path.exists() and not args.overwrite:
            print(f"[cache hit] {video_path.stem}.npz", file=sys.stderr)
            n_done += 1
            continue

        try:
            print(f"[detect] {video_path.name} @ {args.fps} fps ...", file=sys.stderr)
            vd = detector.detect_video(video_path, corners, fps_out=args.fps)
            raw = flatten_detections(
                vd.frames,
                scaled_corners=vd.scaled_corners,
                extract_size=vd.extract_size,
                fps_out=args.fps,
                video_path=video_path,
            )
            save_feature_series(out_path, raw)
            n_done += 1
            print(f"[ok] {out_path.name} ({len(vd.frames)} frames)", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — batch tool keeps going on failures
            failed.append(f"{json_path.name}: {exc}")
            print(f"[FAIL] {json_path.name}: {exc}", file=sys.stderr)

    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  motion features written/cached : {n_done}", file=sys.stderr)
    print(f"  skipped (no corners)           : {len(skipped_no_corners)}", file=sys.stderr)
    print(f"  skipped (video missing)        : {len(skipped_no_video)}", file=sys.stderr)
    print(f"  failed                         : {len(failed)}", file=sys.stderr)
    print(f"  cache dir                      : {out_dir}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    return 0 if n_done > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
