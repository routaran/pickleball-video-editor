"""Frame picker dialog for selecting a video frame before court-corner calibration.

Provides a Qt dialog backed by decord for fast frame decoding. The user drags a
slider to scrub through the video; frames are extracted only on slider release to
avoid blocking the Qt event loop during a drag gesture.

Intended exclusively for use by ml/tools/calibrate_existing.py. It is co-located
here (rather than in src/ui/dialogs/) because decord is an ML-only dependency
installed via ``./configure --enable-ml``; placing it in the UI layer would pull
that transitive dep in for users who have not enabled ML.
"""

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles.colors import (
    BG_BORDER,
    BG_PRIMARY,
    BG_SECONDARY,
    BG_TERTIARY,
    PRIMARY_ACTION,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UNDO,
)

__all__ = ["FramePickerDialog"]

# Minimum dialog size so the preview is usable.
_MIN_PREVIEW_WIDTH = 640
_MIN_PREVIEW_HEIGHT = 360


class FramePickerDialog(QDialog):
    """A modal dialog that lets the user pick a single video frame via a slider.

    Frame extraction is backed by decord (``decord.VideoReader``). Frames are
    decoded on ``sliderReleased`` only — not on every ``valueChanged`` tick —
    to keep the Qt event loop responsive during drag gestures.

    Usage::

        picker = FramePickerDialog(video_path, parent=self)
        if picker.exec() == QDialog.DialogCode.Accepted:
            pixmap = picker.get_result()   # QPixmap, never None here
    """

    def __init__(self, video_path: Path, parent: QWidget | None = None) -> None:
        """Initialise the dialog and open the video with decord.

        Args:
            video_path: Absolute path to the video file. Must exist.
            parent:     Optional Qt parent widget.

        Raises:
            FileNotFoundError: If *video_path* does not exist. The caller is
                responsible for verifying the path before constructing this
                dialog; a missing file is a programmer error, not a recoverable
                runtime condition.
        """
        if not video_path.exists():
            raise FileNotFoundError(
                f"FramePickerDialog: video file not found: {video_path}"
            )

        super().__init__(parent)

        # Import here rather than at module level so that the rest of the
        # ml.tools package can be imported without decord present (e.g. in
        # unit tests that mock the module).
        import decord  # noqa: PLC0415

        decord.bridge.set_bridge("native")
        self._reader: decord.VideoReader = decord.VideoReader(str(video_path))
        self._frame_count: int = len(self._reader)
        self._current_pixmap: QPixmap | None = None
        self._accepted: bool = False

        self._build_ui()
        self._apply_styles()

        # Show the frame at approximately 5% into the video so the dialog
        # opens with something meaningful rather than a blank preview.
        initial_frame = max(0, int(self._frame_count * 0.05))
        self._slider.setValue(initial_frame)
        self._extract_and_show(initial_frame)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_result(self) -> QPixmap | None:
        """Return the selected frame pixmap if the dialog was accepted.

        Returns:
            The ``QPixmap`` for the frame the user confirmed, or ``None`` if
            the dialog was cancelled or no frame has been loaded yet.
        """
        if self._accepted:
            return self._current_pixmap
        return None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct widgets and wire signals."""
        self.setObjectName("framePickerDialog")
        self.setWindowTitle("Select Calibration Frame")
        self.setMinimumSize(_MIN_PREVIEW_WIDTH, _MIN_PREVIEW_HEIGHT + 120)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- Frame preview label -------------------------------------------
        self._preview_label = QLabel()
        self._preview_label.setObjectName("framePreview")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview_label.setMinimumSize(_MIN_PREVIEW_WIDTH, _MIN_PREVIEW_HEIGHT)
        self._preview_label.setText("Loading…")
        root.addWidget(self._preview_label, stretch=1)

        # --- Slider --------------------------------------------------------
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setObjectName("frameSlider")
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(0, self._frame_count - 1))
        self._slider.setSingleStep(1)
        self._slider.setPageStep(30)
        self._slider.sliderReleased.connect(self._on_slider_released)
        root.addWidget(self._slider)

        # --- Frame counter label -------------------------------------------
        self._counter_label = QLabel(f"Frame  0 / {self._frame_count}")
        self._counter_label.setObjectName("frameCounter")
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._counter_label)

        # --- Button row ----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("cancelButton")
        self._cancel_btn.clicked.connect(self.reject)

        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setObjectName("confirmButton")
        self._confirm_btn.setEnabled(False)   # enabled once first frame loads
        self._confirm_btn.clicked.connect(self._on_confirm)

        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._confirm_btn)
        root.addLayout(btn_row)

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet following the Court Green design system."""
        self.setStyleSheet(
            f"""
            QDialog#framePickerDialog {{
                background-color: {BG_PRIMARY};
            }}
            QLabel#framePreview {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: 4px;
                color: {TEXT_SECONDARY};
            }}
            QLabel#frameCounter {{
                color: {TEXT_SECONDARY};
                font-family: "JetBrains Mono", "Fira Code", monospace;
                font-size: 12px;
            }}
            QSlider#frameSlider::groove:horizontal {{
                height: 6px;
                background: {BG_TERTIARY};
                border-radius: 3px;
            }}
            QSlider#frameSlider::handle:horizontal {{
                background: {PRIMARY_ACTION};
                border: none;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider#frameSlider::sub-page:horizontal {{
                background: {PRIMARY_ACTION};
                border-radius: 3px;
            }}
            QPushButton#cancelButton {{
                background-color: transparent;
                border: 1px solid {UNDO};
                color: {UNDO};
                padding: 6px 18px;
                border-radius: 4px;
                font-size: 13px;
            }}
            QPushButton#cancelButton:hover {{
                background-color: {BG_TERTIARY};
            }}
            QPushButton#confirmButton {{
                background-color: {PRIMARY_ACTION};
                border: none;
                color: {BG_PRIMARY};
                padding: 6px 18px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#confirmButton:disabled {{
                background-color: {BG_TERTIARY};
                color: {TEXT_DISABLED};
                opacity: 0.4;
            }}
            QPushButton#confirmButton:hover:enabled {{
                background-color: {TEXT_PRIMARY};
            }}
            """
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_slider_released(self) -> None:
        """Extract and display the frame at the current slider position.

        Called only on ``sliderReleased`` — not on ``valueChanged`` — so that
        dragging the slider does not trigger a decode on every pixel of movement.
        """
        frame_index = self._slider.value()
        self._extract_and_show(frame_index)

    @pyqtSlot()
    def _on_confirm(self) -> None:
        """Accept the dialog, recording that the user confirmed the selection."""
        self._accepted = True
        self.accept()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_and_show(self, frame_index: int) -> None:
        """Decode *frame_index* with decord and display it in the preview label.

        Converts the decoded numpy array (H x W x 3, uint8, RGB) to a
        ``QPixmap`` via ``QImage.Format.Format_RGB888`` and scales it to fit
        the preview label while preserving the aspect ratio.

        Also updates the frame-counter label and enables the Confirm button
        on the first successful decode.

        Args:
            frame_index: Zero-based index of the frame to extract.
        """
        if frame_index < 0 or frame_index >= self._frame_count:
            return

        # decord returns (H, W, C) ndarray in RGB order when bridge="native".
        frame_array: np.ndarray = self._reader[frame_index].asnumpy()

        height, width, channels = frame_array.shape
        if channels != 3:
            # Unexpected channel count — skip rather than crash.
            return

        bytes_per_line = width * 3
        img = QImage(
            frame_array.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(img)

        # Scale to fit the label, keeping aspect ratio.
        scaled = pixmap.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

        self._current_pixmap = pixmap
        self._counter_label.setText(
            f"Frame  {frame_index} / {self._frame_count - 1}"
        )

        # Enable Confirm the first time a frame is successfully loaded.
        if not self._confirm_btn.isEnabled():
            self._confirm_btn.setEnabled(True)
