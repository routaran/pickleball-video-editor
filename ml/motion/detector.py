"""YOLOv8n person detection + ByteTrack identity tracking over a video.

The detector streams frames from the system ffmpeg CLI (one subprocess, raw
``bgr24``), runs pre-trained YOLOv8n on the GPU, keeps only the "person" class,
and returns the **raw** foot-point of each detection (in extracted-frame pixel
space) together with a persistent ByteTrack ``track_id``.

It deliberately does **not** apply the court polygon filter or the court-plane
projection any more — those moved into the cheap, ultralytics-free path
(:mod:`ml.motion.court_apply`) so the court-dilation knob can be tuned offline
without re-running this GPU pass (see ``DILATION_TRACKING_SPEC.md``, Change 0).

Tracking (Change 2) is **stateful across frames**: ByteTrack carries track state
frame-to-frame via ``persist=True``, so frames are processed as a sequential
stream (one frame per ``track`` call) rather than in independent batches.
ByteTrack is appearance-free and deterministic, which the offline-reproducibility
invariant requires.  Track ids restart deterministically per video (the tracker
is reset at the start of each :meth:`MotionDetector.detect_video`).

Why ffmpeg streaming rather than ultralytics' built-in video reader: the project
forbids in-process video decoders in the GUI (decord/PyAV symbol interposition
segfaults mpv).  Even though detection runs in a separate offline process, we
keep the established ffmpeg-subprocess decode path for consistency and precise
control over the sample rate and scale.  Streaming also bounds memory — only one
frame is resident at a time, never the whole video.

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

from ml.motion.court_filter import foot_point
from ml.video_features import (
    CANONICAL_SIZE,
    _clean_ffmpeg_env,
    get_video_frame_size,
    resolve_extract_geometry,
)

__all__ = [
    "MotionDetector",
    "FrameDetections",
    "VideoDetections",
    "ensure_weights",
    "default_weights_dir",
]

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
    """Per-frame **raw** person detections for one sampled frame.

    Geometry is in *extracted-frame pixel space* and **pre-court-filter** — the
    court-polygon membership test and the court-plane projection are applied
    later in the cheap, ultralytics-free path (:mod:`ml.motion.court_apply`), so
    the dilation knob can be tuned without re-running the GPU pass.

    Attributes:
        index: Zero-based sampled-frame index.
        time_s: Frame timestamp in seconds (``index / fps_out``).
        foot_points: ``(k, 2)`` float32 foot-points (bottom-centre of each person
            box) in extracted-frame pixel coordinates.  Raw — not court-filtered.
        track_ids: ``(k,)`` int64 ByteTrack ids aligned with ``foot_points``
            (``-1`` where the tracker assigned no id this frame).
        n_raw: Number of raw person detections this frame (``== len(foot_points)``;
            kept as an explicit diagnostic field).
    """

    index: int
    time_s: float
    foot_points: np.ndarray
    track_ids: np.ndarray
    n_raw: int


@dataclass
class VideoDetections:
    """All sampled-frame detections for one video plus the geometry to project them.

    The court projection needs the corners in extracted-frame pixel space, so they
    travel alongside the per-frame detections (and into the ``.npz`` cache) rather
    than being applied here.

    Attributes:
        frames: One :class:`FrameDetections` per sampled frame, in time order.
        scaled_corners: ``(4, 2)`` float32 court corners in extracted-frame pixel
            space (what :class:`~ml.motion.court_filter.CourtModel` consumes).
        extract_size: ``(width, height)`` the frames were decoded at (provenance).
        fps_out: Detection sample rate (frames per second).
        video_path: Source video path (provenance).
    """

    frames: list[FrameDetections]
    scaled_corners: np.ndarray
    extract_size: tuple[int, int]
    fps_out: float
    video_path: str


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
        """Run YOLO on a batch and return per-frame person boxes (x1,y1,x2,y2).

        Stateless batched prediction (no tracking) — used by the overlay tool
        ``ml.tools.validate_detector``.  The cached extraction path uses
        :meth:`detect_video`, which tracks.
        """
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

    @staticmethod
    def _boxes_ids_from_result(
        res,
    ) -> tuple[list[tuple[float, float, float, float]], np.ndarray]:
        """Parse one ultralytics tracking ``Result`` into ``(boxes, track_ids)``.

        ``track_ids`` is an int64 ``(k,)`` array aligned with ``boxes``; entries
        are ``-1`` when the tracker assigned no id (or the ids do not align with
        the boxes, which should not happen but is guarded defensively).
        """
        boxes = getattr(res, "boxes", None)
        if boxes is None or boxes.xyxy is None or len(boxes) == 0:
            return [], np.zeros(0, dtype=np.int64)
        xyxy = boxes.xyxy.cpu().numpy()
        box_list = [(float(a), float(b), float(c), float(d)) for a, b, c, d in xyxy]
        if boxes.id is None:
            ids = np.full(len(box_list), -1, dtype=np.int64)
        else:
            ids = boxes.id.cpu().numpy().astype(np.int64).reshape(-1)
            if ids.shape[0] != len(box_list):
                ids = np.full(len(box_list), -1, dtype=np.int64)
        return box_list, ids

    def _reset_trackers(self) -> None:
        """Clear ByteTrack state so each video starts with fresh, deterministic ids.

        No-op before the first ``track`` call (the predictor / trackers do not
        exist yet); resets state (and the global id counter) for every subsequent
        video processed by the same detector instance.
        """
        predictor = getattr(self._model, "predictor", None)
        trackers = getattr(predictor, "trackers", None) if predictor is not None else None
        for tracker in trackers or []:
            tracker.reset()

    def _track_frame(
        self, frame: np.ndarray
    ) -> tuple[list[tuple[float, float, float, float]], np.ndarray]:
        """Track persons in a single frame (stateful across calls via persist)."""
        results = self._model.track(
            frame,
            imgsz=self.imgsz,
            conf=self.conf,
            classes=[_COCO_PERSON],
            device=self.device,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        return self._boxes_ids_from_result(results[0])

    def detect_video(
        self,
        video_path: str | Path,
        corners_native: list[tuple[int, int]],
        fps_out: float = 5.0,
    ) -> VideoDetections:
        """Detect + track persons across a whole video (raw, pre-court-filter).

        Frames are processed as a **sequential** stream so ByteTrack can carry
        track state frame-to-frame (``persist=True``); the tracker is reset first
        so ids restart deterministically for this video.  The court filter and
        court-plane projection are **not** applied here — see the module docstring
        and :mod:`ml.motion.court_apply`.

        Args:
            video_path: Path to the source video.
            corners_native: Four court corners in *native* video pixel coords
                (as stored in ``video.court_corners``).
            fps_out: Sampling rate for detection (frames per second).

        Returns:
            A :class:`VideoDetections` with one :class:`FrameDetections` per
            sampled frame (in time order), the extracted-frame court corners and
            extraction provenance.

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

        self._ensure()
        self._reset_trackers()  # fresh, deterministic track ids for this video

        frames_out: list[FrameDetections] = []
        for idx, frame in enumerate(
            _stream_bgr_frames(video_path, fps_out, extract_size)
        ):
            boxes, ids = self._track_frame(frame)
            feet = np.array(
                [foot_point(b) for b in boxes], dtype=np.float32
            ).reshape(-1, 2)
            frames_out.append(
                FrameDetections(
                    index=idx,
                    time_s=idx / fps_out,
                    foot_points=feet,
                    track_ids=np.asarray(ids, dtype=np.int64).reshape(-1),
                    n_raw=len(boxes),
                )
            )

        return VideoDetections(
            frames=frames_out,
            scaled_corners=np.asarray(scaled_corners, dtype=np.float32).reshape(4, 2),
            extract_size=(int(extract_size[0]), int(extract_size[1])),
            fps_out=float(fps_out),
            video_path=str(video_path),
        )
