"""CLI tool to retroactively add court_corners to existing .training.json files.

Usage:
    python -m ml.tools.calibrate_existing
    python -m ml.tools.calibrate_existing --root ~/Videos/pickleball/

For each .training.json that is missing court_corners, the tool:
1. Finds the source video referenced in the JSON.
2. Extracts a frame at ~5% into the video via ffmpeg (piped to memory).
3. Shows a Qt dialog with a CourtCalibratorWidget.
4. Saves the captured corners back to the JSON and bumps schema_version to "1.1".

Files that already have court_corners are skipped with a SKIP message.
"""

import argparse
import enum
import json
import subprocess
import sys
from pathlib import Path

from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout

from src.ui.widgets.court_calibrator import CourtCalibratorWidget
from ml.tools.frame_picker_dialog import FramePickerDialog


__all__ = ["main"]


class _Result(enum.Enum):
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


def _probe_duration(video_path: Path) -> float:
    """Return video duration in seconds using ffprobe, or 60.0 on failure.

    Uses LBYL: only tries to parse the output if the process succeeded and
    produced a non-empty, numeric-looking stdout line.

    Args:
        video_path: Path to the video file.

    Returns:
        Duration in seconds as a float.
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    raw = result.stdout.strip() if result.returncode == 0 else ""
    if raw and raw.replace(".", "", 1).isdigit():
        return float(raw)
    return 60.0


def _extract_frame_pixmap(video_path: Path, offset_s: float) -> QPixmap | None:
    """Extract a single frame from a video at offset_s using ffmpeg.

    Runs ffmpeg with output piped to stdout as raw PNG bytes; no temp file is
    written to disk.

    Args:
        video_path: Path to the video file.
        offset_s: Time offset in seconds for the extracted frame.

    Returns:
        QPixmap of the frame, or None if extraction failed.
    """
    result = subprocess.run(
        [
            "ffmpeg",
            "-ss", str(offset_s),
            "-i", str(video_path),
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    img = QImage.fromData(result.stdout)
    if img.isNull():
        return None
    return QPixmap.fromImage(img)


def _run_calibration_dialog(app: QApplication, pixmap: QPixmap, title: str) -> list[list[int]] | None:
    """Show a modal calibration dialog and return captured corners, or None.

    Blocks until the user confirms or closes the dialog.  Corners are returned
    as a list of four [x, y] pairs in original-image pixel coordinates, or None
    if the user dismissed the dialog without confirming.

    Args:
        app: The running QApplication instance (unused directly but must exist).
        pixmap: Frame pixmap to display inside the CourtCalibratorWidget.
        title: Window title for the dialog.

    Returns:
        List of four [x, y] corner coordinates, or None.
    """
    dialog = QDialog()
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(900, 600)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(8, 8, 8, 8)

    calibrator = CourtCalibratorWidget(pixmap, dialog)
    layout.addWidget(calibrator)

    captured: list[list[int]] = []

    def on_corners(corners: list) -> None:
        captured.clear()
        # corners is a list of (x, y) tuples; normalise to [[x,y], ...]
        captured.extend([list(pt) for pt in corners])
        dialog.accept()

    calibrator.cornersCaptured.connect(on_corners)
    dialog.exec()

    return captured if len(captured) == 4 else None


def _process_file(app: QApplication, json_path: Path, auto_frame: bool, force: bool = False) -> _Result:
    """Calibrate a single .training.json file.

    Checks for existing corners, acquires a frame (either automatically at 5%
    or via an interactive FramePickerDialog depending on *auto_frame*), shows
    the calibration dialog, and writes the result back to the JSON file.

    Args:
        app:        Running QApplication instance.
        json_path:  Path to the .training.json file to process.
        auto_frame: If True, extract the frame at 5% into the video without
                    showing the frame-picker dialog (back-compat for scripted
                    runs).  If False, open FramePickerDialog so the user can
                    choose an unobstructed frame interactively.

    Returns:
        _Result.UPDATED if corners were captured and saved.
        _Result.SKIPPED if corners were already present or the user dismissed.
        _Result.ERROR is never returned here; callers wrap this in try/except.
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    video_section = data.get("video", {})

    if video_section.get("court_corners") is not None and not force:
        print(f"SKIP: {json_path.name} (already has corners)")
        return _Result.SKIPPED

    video_path_str = video_section.get("path", "")
    video_path = Path(video_path_str)
    if not video_path.exists():
        print(f"WARN: video not found for {json_path.name}")
        return _Result.SKIPPED

    if auto_frame:
        duration = _probe_duration(video_path)
        offset_s = duration * 0.05
        pixmap = _extract_frame_pixmap(video_path, offset_s)
        if pixmap is None or pixmap.isNull():
            print(f"WARN: could not extract frame for {json_path.name}")
            return _Result.SKIPPED
    else:
        picker = FramePickerDialog(video_path)
        if picker.exec() != QDialog.DialogCode.Accepted:
            print(f"Skipped: {json_path}")
            return _Result.SKIPPED
        pixmap = picker.get_result()
        if pixmap is None or pixmap.isNull():
            print(f"WARN: frame picker returned no pixmap for {json_path.name}")
            return _Result.SKIPPED

    corners = _run_calibration_dialog(app, pixmap, f"Calibrate: {video_path.name}")
    if corners is None:
        # User closed the dialog without confirming — treat as skip, not error
        print(f"SKIP: {json_path.name} (dialog closed without confirming)")
        return _Result.SKIPPED

    data["video"]["court_corners"] = corners
    if data.get("schema_version") == "1.0":
        data["schema_version"] = "1.1"

    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"DONE: {json_path.name}")
    return _Result.UPDATED


def main() -> None:
    """Entry point: walk root, calibrate each uncalibrated .training.json."""
    parser = argparse.ArgumentParser(
        description="Add court_corners to existing .training.json files."
    )
    parser.add_argument(
        "--root",
        default=str(Path.home() / "Videos" / "pickleball"),
        help="Directory to search recursively for *.training.json files "
             "(default: ~/Videos/pickleball/)",
    )
    parser.add_argument(
        "--auto-frame",
        action="store_true",
        help="Skip the interactive frame picker; use the 5%%-into-video frame "
             "as today (back-compat for scripted runs).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-calibrate files that already have court_corners "
             "(overwrites existing corner data).",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"ERROR: --root directory does not exist: {root}")
        sys.exit(1)

    json_files = sorted(root.rglob("*.training.json"))
    if not json_files:
        print(f"No .training.json files found under {root}")
        return

    app = QApplication.instance() or QApplication(sys.argv)

    updated = 0
    skipped = 0
    for json_path in json_files:
        result = _Result.ERROR
        try:
            result = _process_file(app, json_path, args.auto_frame, args.force)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 — error boundary: log and continue
            print(f"ERROR: {json_path.name}: {exc}")
        if result is _Result.UPDATED:
            updated += 1
        elif result is _Result.SKIPPED:
            skipped += 1
        # ERROR: neither counter increments (file not updated, not intentionally skipped)

    print(f"\n{updated} files updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
