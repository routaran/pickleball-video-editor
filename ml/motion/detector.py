"""YOLOv8n person detection over a video, filtered and projected to the court.

The detector streams frames from the system ffmpeg CLI (one subprocess, raw
``bgr24``), runs pre-trained YOLOv8n in batches on the GPU, keeps only the
"person" class, filters each detection's foot-point to the court polygon, and
projects the survivors onto the normalised court plane.

Why ffmpeg streaming rather than ultralytics' built-in video reader: the project
forbids in-process video decoders in the GUI (decord/PyAV symbol interposition
segfaults mpv).  Even though detection runs in a separate offline process, we
keep the established ffmpeg-subprocess decode path for consistency and precise
control over the sample rate and scale.  Streaming also bounds memory — only one
batch of frames is resident at a time, never the whole video.

``ultralytics`` is imported lazily so the rest of the package (and its unit
tests) import without the heavy dependency installed.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from ml.motion.court_filter import CourtModel, foot_point
from ml.video_features import (
    CANONICAL_SIZE,
    _clean_ffmpeg_env,
    get_video_frame_size,
    resolve_extract_geometry,
)

__all__ = ["MotionDetector", "FrameDetections", "ensure_weights", "default_weights_dir"]

_COCO_PERSON = 0  # ultralytics COCO index for "person" (0-based, unlike torchvision)


def default_weights_dir() -> Path:
    """Deterministic directory for cached YOLO weights (``ml/cache/weights/``)."""
    from ml.config import PathConfig  # noqa: PLC0415 — lazy, torch-free

    return PathConfig().cache_dir / "weights"


def ensure_weights(
    model_name: str | Path, weights_dir: str | Path | None = None
) -> Path:
    """Resolve YOLO weights to a deterministic local path, downloading if absent.

    ultralytics auto-downloads model assets into the *current working
    directory* by default, which is not reproducible (the file lands wherever
    the batch job happened to run).  This pins them under ``ml/cache/weights/``
    (or ``weights_dir``) so repeated runs, and runs from different CWDs, reuse
    the same checkpoint.

    Args:
        model_name: A weights filename (e.g. ``"yolov8n.pt"``) or a path to an
            existing checkpoint (used as-is).
        weights_dir: Destination directory for downloaded assets (default:
            :func:`default_weights_dir`).

    Returns:
        Absolute path to the local weights file.

    Raises:
        FileNotFoundError: If the asset could not be downloaded.
    """
    p = Path(model_name)
    if p.suffix == "":
        p = p.with_suffix(".pt")
    # An explicit path to an existing checkpoint wins — no download.
    if p.exists():
        return p.resolve()

    wdir = Path(weights_dir) if weights_dir is not None else default_weights_dir()
    target = wdir / p.name
    if target.exists():
        return target.resolve()

    wdir.mkdir(parents=True, exist_ok=True)
    # Use ultralytics' own resolver so the correct release URL for the installed
    # version is used, asking it to write to ``target``.  Some versions ignore
    # the requested directory and drop the file elsewhere (e.g. CWD) — relocate
    # it to ``target`` if that happens, so the result is always deterministic.
    from ultralytics.utils.downloads import attempt_download_asset  # noqa: PLC0415

    got = Path(attempt_download_asset(str(target)))
    if got.exists() and got.resolve() != target.resolve():
        shutil.move(str(got), str(target))
    if not target.exists():
        raise FileNotFoundError(
            f"Failed to download YOLO weights '{p.name}' to {target}"
        )
    return target.resolve()


@dataclass
class FrameDetections:
    """Per-frame on-court detections for one sampled frame.

    Attributes:
        index: Zero-based sampled-frame index.
        time_s: Frame timestamp in seconds (``index / fps_out``).
        court_points: ``(k, 2)`` normalised court-plane foot-points of the
            on-court persons (net at ``y = 0.5``).
        n_raw: Number of raw person detections before court filtering (useful
            for diagnostics: high n_raw with low on-court count means lots of
            spectators / adjacent-court players were correctly rejected).
    """

    index: int
    time_s: float
    court_points: np.ndarray
    n_raw: int


def _read_exact(stream, n: int) -> bytes:
    """Read exactly ``n`` bytes from a pipe, or fewer only at EOF."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _stream_bgr_frames(
    video_path: Path, fps_out: float, size: tuple[int, int]
) -> Iterator[np.ndarray]:
    """Yield ``(H, W, 3)`` uint8 BGR frames decoded by the system ffmpeg CLI."""
    width, height = size
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_out},scale={width}:{height}:flags=bilinear",
        "-pix_fmt",
        "bgr24",  # matches the BGR convention ultralytics assumes for ndarrays
        "-f",
        "rawvideo",
        "-",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_ffmpeg_env(),
    )
    frame_bytes = width * height * 3
    produced = 0
    try:
        while True:
            buf = _read_exact(proc.stdout, frame_bytes)
            if len(buf) < frame_bytes:
                break
            produced += 1
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        stderr = proc.stderr.read() if proc.stderr is not None else b""
        if proc.stderr is not None:
            proc.stderr.close()
        proc.wait()
        if produced == 0 and proc.returncode not in (0, None):
            msg = stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"ffmpeg produced no frames for {video_path} "
                f"(rc={proc.returncode}): {msg}"
            )


class MotionDetector:
    """Pre-trained YOLOv8n person detector with court filtering."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        conf: float = 0.25,
        imgsz: int = 1280,
        device: str | None = None,
        max_extract_dim: int = 1280,
        batch: int = 16,
        weights_dir: str | Path | None = None,
    ) -> None:
        """Configure the detector (model weights load lazily on first use).

        Args:
            model_name: Ultralytics weights name/path (``yolov8n.pt`` downloads
                on first use, into ``weights_dir``).  Bump to ``yolov8s.pt`` if
                far-court players are under-detected.
            conf: Confidence threshold for kept detections.
            imgsz: YOLO inference image size.  1280 (vs the 640 default) keeps
                small far-court players large enough to detect on phone footage.
            device: Torch device string; ``None`` lets ultralytics auto-select.
            max_extract_dim: Longest side the frames are extracted at; corners
                are scaled to match (see ``resolve_extract_geometry``).
            batch: Frames per YOLO forward pass.
            weights_dir: Directory to cache downloaded weights in (default:
                ``ml/cache/weights/`` via :func:`default_weights_dir`).
        """
        self.model_name = model_name
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.max_extract_dim = max_extract_dim
        self.batch = batch
        self.weights_dir = weights_dir
        self._model = None

    def _ensure(self) -> None:
        if self._model is None:
            from ultralytics import YOLO  # noqa: PLC0415 — heavy optional dep

            weights_path = ensure_weights(self.model_name, self.weights_dir)
            self._model = YOLO(str(weights_path))

    def person_boxes(
        self, frames: list[np.ndarray]
    ) -> list[list[tuple[float, float, float, float]]]:
        """Run YOLO on a batch and return per-frame person boxes (x1,y1,x2,y2)."""
        self._ensure()
        results = self._model.predict(
            frames,
            imgsz=self.imgsz,
            conf=self.conf,
            classes=[_COCO_PERSON],
            device=self.device,
            verbose=False,
        )
        per_frame: list[list[tuple[float, float, float, float]]] = []
        for res in results:
            boxes = res.boxes
            if boxes is None or boxes.xyxy is None or len(boxes) == 0:
                per_frame.append([])
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            per_frame.append(
                [(float(a), float(b), float(c), float(d)) for a, b, c, d in xyxy]
            )
        return per_frame

    def detect_video(
        self,
        video_path: str | Path,
        corners_native: list[tuple[int, int]],
        fps_out: float = 5.0,
    ) -> list[FrameDetections]:
        """Detect on-court persons across a whole video.

        Args:
            video_path: Path to the source video.
            corners_native: Four court corners in *native* video pixel coords
                (as stored in ``video.court_corners``).
            fps_out: Sampling rate for detection (frames per second).

        Returns:
            One :class:`FrameDetections` per sampled frame, in time order.

        Raises:
            ValueError: If ``corners_native`` is not four points.
        """
        video_path = Path(video_path)
        if corners_native is None or len(corners_native) != 4:
            raise ValueError(
                "detect_video requires exactly 4 court corners; "
                f"got {0 if corners_native is None else len(corners_native)}"
            )

        native = get_video_frame_size(video_path)
        extract_size, scaled_corners = resolve_extract_geometry(
            native, list(corners_native), CANONICAL_SIZE, self.max_extract_dim
        )
        court = CourtModel(scaled_corners, CANONICAL_SIZE)

        out: list[FrameDetections] = []
        batch_frames: list[np.ndarray] = []
        batch_idx: list[int] = []

        def _flush() -> None:
            if not batch_frames:
                return
            boxes_per = self.person_boxes(batch_frames)
            for idx, boxes in zip(batch_idx, boxes_per):
                feet = [foot_point(b) for b in boxes]
                on_court = court.filter_on_court(feet)
                court_pts = court.to_court_plane(on_court)
                out.append(
                    FrameDetections(
                        index=idx,
                        time_s=idx / fps_out,
                        court_points=court_pts,
                        n_raw=len(boxes),
                    )
                )
            batch_frames.clear()
            batch_idx.clear()

        for idx, frame in enumerate(_stream_bgr_frames(video_path, fps_out, extract_size)):
            batch_frames.append(frame)
            batch_idx.append(idx)
            if len(batch_frames) >= self.batch:
                _flush()
        _flush()

        return out
