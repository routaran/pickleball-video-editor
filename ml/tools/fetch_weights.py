"""Pre-download YOLO weights to the deterministic cache (``ml/cache/weights/``).

ultralytics otherwise auto-downloads weights into the current working directory
on first detection.  Run this once (in the ``.venv-motion`` env) so the weights
live in a fixed, reproducible location and the first batch run does no network
I/O mid-job.

Usage::

    python -m ml.tools.fetch_weights                 # yolov8n.pt (default)
    python -m ml.tools.fetch_weights yolov8s.pt      # larger variant
    python -m ml.tools.fetch_weights --weights-dir /some/dir yolov8n.pt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_weights",
        description="Pre-download YOLO weights to ml/cache/weights/ (deterministic).",
    )
    parser.add_argument(
        "model", nargs="?", default="yolov8n.pt",
        help="Weights filename to fetch (default: yolov8n.pt).",
    )
    parser.add_argument(
        "--weights-dir", type=Path, default=None,
        help="Override the cache directory (default: ml/cache/weights/).",
    )
    args = parser.parse_args(argv)

    from ml.motion.detector import ensure_weights  # noqa: PLC0415 — imports cv2

    path = ensure_weights(args.model, args.weights_dir)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
