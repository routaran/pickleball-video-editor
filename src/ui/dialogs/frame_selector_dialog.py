"""Frame Selector Dialog for the Pickleball Video Editor.

Modal dialog that lets the user scrub to any timestamp in the video and pick a
frame for court-corner calibration.  Frame extraction is backed by ffmpeg
(already a hard editor dependency) via ``src.video.frame_extract.extract_frame_at``.

Design constraints:
- Frames are extracted only on ``sliderReleased`` and on arrow-key seeks, NOT
  on every ``valueChanged`` tick.  This prevents an ffmpeg subprocess storm
  during drag gestures (~200–500 ms per extract × many events = unusable UI).
- A "Loading..." overlay is shown in the preview while ffmpeg runs so the user
  gets visible feedback even though extraction is synchronous on the main thread.
- The Confirm button starts disabled and enables only after the first successful
  frame extraction.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QPixmap
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
from src.ui.styles.components import ButtonStyles
from src.ui.styles.fonts import (
    Fonts,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    RADIUS_MD,
    RADIUS_LG,
)
from src.video.frame_extract import extract_frame_at

__all__ = ["FrameSelectorDialog"]

# Minimum dimensions for the frame preview area.
_MIN_PREVIEW_WIDTH = 640
_MIN_PREVIEW_HEIGHT = 360

# Slider precision: each unit = 0.01 s.
_SLIDER_SCALE = 100          # multiply seconds to get slider ticks
_SINGLE_STEP_S = 1.0         # Left / Right arrow keys
_PAGE_STEP_S = 10.0          # PageUp / PageDown keys


def _fmt_timestamp(seconds: float) -> str:
    """Format *seconds* as ``MM:SS.ss`` for the timestamp label.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Human-readable timestamp string, e.g. ``"01:23.45"``.
    """
    if seconds < 0:
        seconds = 0.0
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:05.2f}"


class FrameSelectorDialog(QDialog):
    """Modal dialog for choosing a video frame via a scrub slider.

    The user drags the slider (or uses arrow/page keys) to a timestamp; on
    releasing the slider a single ffmpeg call extracts the frame and updates the
    preview.  Clicking **Use This Frame** returns the chosen ``QPixmap`` via
    :meth:`get_result`.

    Example::

        selector = FrameSelectorDialog(
            video_path=Path("/path/to/video.mp4"),
            video_duration_s=duration,
            initial_offset_s=duration * 0.05,
            parent=self,
        )
        if selector.exec() == QDialog.DialogCode.Accepted:
            pixmap = selector.get_result()   # QPixmap, not None here

    Args:
        video_path: Absolute path to the video file.  Must exist.
        video_duration_s: Total video duration in seconds.  Must be > 0.
        initial_offset_s: Seek position shown when the dialog first opens.
            Defaults to ``video_duration_s * 0.05`` when ``None``.
        parent: Optional parent widget for modal anchoring.

    Raises:
        FileNotFoundError: If *video_path* does not exist.  Programmer error.
        ValueError: If *video_duration_s* is <= 0.  Programmer error.
    """

    def __init__(
        self,
        video_path: Path,
        video_duration_s: float,
        initial_offset_s: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        # LBYL guards — both are programmer errors, not recoverable runtime faults.
        if not video_path.exists():
            raise FileNotFoundError(
                f"FrameSelectorDialog: video file not found: {video_path}"
            )
        if video_duration_s <= 0:
            raise ValueError(
                f"FrameSelectorDialog: video_duration_s must be > 0, got {video_duration_s!r}"
            )

        super().__init__(parent)

        self._video_path = video_path
        self._duration_s = video_duration_s
        self._current_pixmap: QPixmap | None = None
        self._accepted_result: QPixmap | None = None

        # Resolve initial offset: default to 5% of duration.
        if initial_offset_s is None:
            initial_offset_s = video_duration_s * 0.05
        # Clamp to valid range.
        initial_offset_s = max(0.0, min(initial_offset_s, video_duration_s))
        self._initial_offset_s = initial_offset_s

        self._build_ui()
        self._apply_styles()
        self._connect_signals()

        # Populate preview immediately with the initial frame.
        self._seek_to(initial_offset_s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_result(self) -> QPixmap | None:
        """Return the chosen frame pixmap when the dialog was accepted.

        Returns:
            The ``QPixmap`` the user confirmed, or ``None`` if the dialog was
            cancelled or no frame was successfully extracted before acceptance.
        """
        return self._accepted_result

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct all widgets and assemble the layout."""
        self.setObjectName("frameSelectorDialog")
        self.setWindowTitle("Select Calibration Frame")
        self.setModal(True)
        self.setMinimumSize(_MIN_PREVIEW_WIDTH, _MIN_PREVIEW_HEIGHT + 140)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        root.setSpacing(SPACE_SM)

        # --- Title label --------------------------------------------------
        title = QLabel("Select Calibration Frame")
        title.setObjectName("dialogTitle")
        title.setFont(Fonts.dialog_title())
        root.addWidget(title)

        # --- Frame preview ------------------------------------------------
        self._preview_label = QLabel("Loading...")
        self._preview_label.setObjectName("framePreview")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview_label.setMinimumSize(_MIN_PREVIEW_WIDTH, _MIN_PREVIEW_HEIGHT)
        root.addWidget(self._preview_label, stretch=1)

        # --- Slider row ---------------------------------------------------
        slider_row = QHBoxLayout()
        slider_row.setSpacing(SPACE_SM)

        frame_lbl = QLabel("Frame:")
        frame_lbl.setObjectName("frameLabel")
        frame_lbl.setFont(Fonts.secondary())
        slider_row.addWidget(frame_lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setObjectName("frameSlider")
        max_tick = max(0, int(self._duration_s * _SLIDER_SCALE))
        self._slider.setMinimum(0)
        self._slider.setMaximum(max_tick)
        self._slider.setSingleStep(int(_SINGLE_STEP_S * _SLIDER_SCALE))
        self._slider.setPageStep(int(_PAGE_STEP_S * _SLIDER_SCALE))
        slider_row.addWidget(self._slider, stretch=1)

        self._timestamp_label = QLabel()
        self._timestamp_label.setObjectName("timestampLabel")
        self._timestamp_label.setFont(Fonts.display())
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._timestamp_label.setMinimumWidth(140)
        slider_row.addWidget(self._timestamp_label)

        root.addLayout(slider_row)

        # Set slider to initial position and update the timestamp label.
        initial_tick = int(self._initial_offset_s * _SLIDER_SCALE)
        self._slider.setValue(initial_tick)
        self._update_timestamp_label()

        # --- Button row ---------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_SM)

        hint_label = QLabel("← / →: \xb11s   PgUp/PgDn: \xb110s")
        hint_label.setObjectName("hintLabel")
        hint_label.setFont(Fonts.secondary())
        btn_row.addWidget(hint_label)

        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("cancelButton")
        self._cancel_btn.setFont(Fonts.button_other())
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setMinimumWidth(90)
        self._cancel_btn.setStyleSheet(ButtonStyles.outline(UNDO))
        btn_row.addWidget(self._cancel_btn)

        self._confirm_btn = QPushButton("Use This Frame")
        self._confirm_btn.setObjectName("confirmButton")
        self._confirm_btn.setFont(Fonts.button_other())
        self._confirm_btn.setFixedHeight(36)
        self._confirm_btn.setMinimumWidth(120)
        self._confirm_btn.setStyleSheet(ButtonStyles.primary())
        self._confirm_btn.setEnabled(False)  # enabled after first successful extract
        btn_row.addWidget(self._confirm_btn)

        root.addLayout(btn_row)

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet following the Court Green design system."""
        self.setStyleSheet(f"""
            QDialog#frameSelectorDialog {{
                background-color: {BG_PRIMARY};
            }}

            QLabel#dialogTitle {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
                border: none;
                padding-bottom: {SPACE_XS}px;
            }}

            QLabel#framePreview {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BG_BORDER};
                border-radius: {RADIUS_LG}px;
                color: {TEXT_SECONDARY};
            }}

            QLabel#frameLabel,
            QLabel#hintLabel {{
                color: {TEXT_SECONDARY};
                background-color: transparent;
                border: none;
            }}

            QLabel#timestampLabel {{
                color: {TEXT_PRIMARY};
                background-color: transparent;
                border: none;
                font-family: "JetBrains Mono", "Fira Code", monospace;
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

        """)

    def _connect_signals(self) -> None:
        """Wire widget signals to slots."""
        # valueChanged is cheap (label update only) — safe to connect for every tick.
        self._slider.valueChanged.connect(self._update_timestamp_label)
        # sliderReleased triggers ffmpeg extraction — one call per drag gesture.
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._cancel_btn.clicked.connect(self.reject)
        self._confirm_btn.clicked.connect(self._on_confirm)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _update_timestamp_label(self) -> None:
        """Refresh the timestamp label from the current slider position.

        This is cheap (no IO) so it can safely connect to ``valueChanged``.
        """
        offset_s = self._slider.value() / _SLIDER_SCALE
        total = _fmt_timestamp(self._duration_s)
        current = _fmt_timestamp(offset_s)
        self._timestamp_label.setText(f"{current} / {total}")

    @pyqtSlot()
    def _on_slider_released(self) -> None:
        """Extract and display the frame at the current slider position.

        Connected to ``sliderReleased`` only — never ``valueChanged`` — to
        avoid an ffmpeg subprocess on every drag pixel.
        """
        offset_s = self._slider.value() / _SLIDER_SCALE
        self._seek_to(offset_s)

    @pyqtSlot()
    def _on_confirm(self) -> None:
        """Record the current pixmap as the accepted result and close."""
        self._accepted_result = self._current_pixmap
        self.accept()

    # ------------------------------------------------------------------
    # Key navigation
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        """Handle keyboard navigation for frame stepping.

        - Left / Right: step ±1 second and extract.
        - PageUp / PageDown: step ±10 seconds and extract.
        - Enter / Return: accept if a frame has been loaded.
        - Escape: reject (cancel).

        All other keys are forwarded to the base class.

        Args:
            event: Key press event from Qt.
        """
        key = event.key()

        if key == Qt.Key.Key_Left:
            self._adjust_slider(-int(_SINGLE_STEP_S * _SLIDER_SCALE))
        elif key == Qt.Key.Key_Right:
            self._adjust_slider(int(_SINGLE_STEP_S * _SLIDER_SCALE))
        elif key == Qt.Key.Key_PageUp:
            self._adjust_slider(-int(_PAGE_STEP_S * _SLIDER_SCALE))
        elif key == Qt.Key.Key_PageDown:
            self._adjust_slider(int(_PAGE_STEP_S * _SLIDER_SCALE))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._current_pixmap is not None:
                self._on_confirm()
        elif key == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _adjust_slider(self, delta_ticks: int) -> None:
        """Move the slider by *delta_ticks* (clamped to valid range) then extract.

        Args:
            delta_ticks: Number of slider ticks to move (positive = forward).
        """
        new_value = self._slider.value() + delta_ticks
        new_value = max(self._slider.minimum(), min(new_value, self._slider.maximum()))
        self._slider.setValue(new_value)
        self._update_timestamp_label()
        offset_s = new_value / _SLIDER_SCALE
        self._seek_to(offset_s)

    def _seek_to(self, offset_s: float) -> None:
        """Run ffmpeg to extract the frame at *offset_s* and update the preview.

        Shows "Loading..." in the preview label while ffmpeg runs.  On success
        the preview is updated and the Confirm button is enabled.  On failure
        the preview reverts to a "Failed to load frame" message.

        Args:
            offset_s: Seek position in seconds.
        """
        self._preview_label.setText("Loading...")
        self._preview_label.setPixmap(QPixmap())  # clear any previous image

        # parent_widget=None → suppress modal error dialogs during slider scrubbing.
        pixmap = extract_frame_at(self._video_path, offset_s, parent_widget=None)

        if pixmap is None:
            self._preview_label.setText("Failed to load frame — seek to a different position.")
            return

        self._current_pixmap = pixmap

        # Scale to fill the preview label while preserving aspect ratio.
        scaled = pixmap.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

        # Enable Confirm on first successful load.
        if not self._confirm_btn.isEnabled():
            self._confirm_btn.setEnabled(True)
