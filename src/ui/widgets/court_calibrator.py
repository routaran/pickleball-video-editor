"""Court calibrator widget for annotating court corners on a video frame.

The user clicks 4 court corners in a fixed order on a displayed video frame.
Captured points are emitted in original image pixel coordinates (not display
coordinates) so they can be used directly with compute_homography().

Click order:
    1. Team 1's baseline-left corner
    2. Team 1's baseline-right corner
    3. Team 2's baseline-right corner
    4. Team 2's baseline-left corner
"""

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPixmap, QPolygon
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.ui.styles.colors import (
    BG_BORDER,
    BG_PRIMARY,
    BG_TERTIARY,
    BORDER_COLOR,
    PRIMARY_ACTION,
    RECEIVER_WINS,
    TEXT_ACCENT,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UNDO,
)
from src.ui.styles.fonts import (
    RADIUS_MD,
    SPACE_MD,
    SPACE_SM,
    Fonts,
    WEIGHT_SEMIBOLD,
    SIZE_STATE_LABELS,
    SIZE_SECONDARY,
)


__all__ = ["CourtCalibratorWidget"]


# Prompt text shown above the image for each click step.
# Rich-text so team names can be rendered bold.
_PROMPT_LABELS: list[str] = [
    "Click <b>Team 1's</b> baseline-left corner",
    "Click <b>Team 1's</b> baseline-right corner",
    "Click <b>Team 2's</b> baseline-right corner",
    "Click <b>Team 2's</b> baseline-left corner",
]

# Team 1 markers use green; Team 2 markers use orange.
_TEAM1_COLOR = QColor(TEXT_ACCENT)    # #3DDC84
_TEAM2_COLOR = QColor(RECEIVER_WINS)  # #FFB300

_DOT_COLORS: list[QColor] = [
    _TEAM1_COLOR,
    _TEAM1_COLOR,
    _TEAM2_COLOR,
    _TEAM2_COLOR,
]

_DOT_RADIUS = 10    # Circle marker radius in display pixels
_LINE_WIDTH = 2     # Polygon edge stroke width in display pixels


class CourtCalibratorWidget(QWidget):
    """Widget that guides the user through clicking 4 court corner points.

    Displays a scaled video frame and overlays numbered circle markers plus
    progressive polygon edges as the user works through the 4 clicks.  When
    the user confirms, ``cornersCaptured`` is emitted with coordinates in the
    original image's pixel space.

    Coordinate handling
    -------------------
    Only original-image pixel coordinates are persisted (``_original_points``).
    On every render pass the current label size is used to recompute the scaled
    pixmap dimensions and its letterbox/pillarbox offset, then each stored
    original-image point is projected back into display space.  This means the
    overlay is always correct regardless of widget resize events.

    Signals:
        cornersCaptured(list): Emitted when Confirm is clicked.  Payload is a
            list of 4 ``(x, y)`` tuples in original-image pixel coordinates,
            ordered: T1-left, T1-right, T2-right, T2-left.

    Example::

        calibrator = CourtCalibratorWidget(frame_pixmap)
        calibrator.cornersCaptured.connect(on_corners)
    """

    cornersCaptured = pyqtSignal(list)

    def __init__(self, frame_pixmap: QPixmap, parent: QWidget | None = None) -> None:
        """Initialise the calibrator with a source frame.

        Args:
            frame_pixmap: Frame image to display and click on.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("courtCalibrator")

        self._source_pixmap = frame_pixmap
        # Original-image pixel coordinates for each recorded click.
        self._original_points: list[tuple[int, int]] = []

        self._build_ui()
        self._apply_styles()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct all child widgets and lay them out."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        # Step counter e.g. "STEP 1 OF 4"
        self._step_label = QLabel("STEP 1 OF 4")
        self._step_label.setObjectName("stepLabel")
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._step_label)

        # Main instruction prompt (HTML-formatted for bold team names)
        self._prompt_label = QLabel()
        self._prompt_label.setObjectName("promptLabel")
        self._prompt_label.setTextFormat(Qt.TextFormat.RichText)
        self._prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prompt_label.setWordWrap(True)
        self._update_prompt(0)
        layout.addWidget(self._prompt_label)

        # Image display area — the QLabel the user clicks on
        self._frame_label = QLabel()
        self._frame_label.setObjectName("frameLabel")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setMinimumSize(640, 360)
        self._frame_label.setCursor(Qt.CursorShape.CrossCursor)
        self._frame_label.installEventFilter(self)
        layout.addWidget(self._frame_label, stretch=1)

        # Hint text below the image
        self._hint_label = QLabel("Click on the frame to mark each corner in order.")
        self._hint_label.setObjectName("hintLabel")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint_label)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_SM)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setObjectName("resetButton")
        self._reset_btn.setFont(Fonts.button_other())
        self._reset_btn.setMinimumHeight(36)

        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setObjectName("confirmButton")
        self._confirm_btn.setFont(Fonts.button_other())
        self._confirm_btn.setMinimumHeight(36)
        self._confirm_btn.setEnabled(False)

        btn_row.addStretch()
        btn_row.addWidget(self._reset_btn)
        btn_row.addWidget(self._confirm_btn)
        layout.addLayout(btn_row)

        self._reset_btn.clicked.connect(self._reset)
        self._confirm_btn.clicked.connect(self._confirm)

        # Render once so the image appears before any clicks
        self._render_frame()

    def _apply_styles(self) -> None:
        """Apply QSS stylesheet consistent with the Court Green theme."""
        self.setStyleSheet(f"""
            #courtCalibrator {{
                background-color: {BG_PRIMARY};
            }}

            #courtCalibrator QLabel#stepLabel {{
                color: {TEXT_SECONDARY};
                font-size: {SIZE_SECONDARY}px;
                font-weight: {WEIGHT_SEMIBOLD};
                letter-spacing: 1px;
            }}

            #courtCalibrator QLabel#promptLabel {{
                color: {TEXT_PRIMARY};
                font-size: {SIZE_STATE_LABELS}px;
                font-weight: {WEIGHT_SEMIBOLD};
                padding: 4px 8px;
            }}

            #courtCalibrator QLabel#hintLabel {{
                color: {TEXT_SECONDARY};
                font-size: {SIZE_SECONDARY}px;
            }}

            #courtCalibrator QLabel#frameLabel {{
                background-color: {BG_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
            }}

            #courtCalibrator QPushButton {{
                background-color: {BG_TERTIARY};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: {RADIUS_MD}px;
                padding: {SPACE_SM}px {SPACE_MD}px;
                min-width: 90px;
            }}

            #courtCalibrator QPushButton:hover:!disabled {{
                border-color: {TEXT_ACCENT};
                color: {TEXT_ACCENT};
            }}

            #courtCalibrator QPushButton:disabled {{
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
            }}

            #courtCalibrator QPushButton#resetButton {{
                border-color: {UNDO};
                color: {UNDO};
            }}

            #courtCalibrator QPushButton#resetButton:hover {{
                background-color: {UNDO};
                color: {BG_PRIMARY};
            }}

            #courtCalibrator QPushButton#confirmButton {{
                background-color: {PRIMARY_ACTION};
                color: {BG_PRIMARY};
                border: 2px solid {PRIMARY_ACTION};
                font-weight: {WEIGHT_SEMIBOLD};
            }}

            #courtCalibrator QPushButton#confirmButton:hover:!disabled {{
                background-color: {TEXT_ACCENT};
                border-color: {TEXT_ACCENT};
                color: {BG_PRIMARY};
            }}

            #courtCalibrator QPushButton#confirmButton:disabled {{
                background-color: {BG_TERTIARY};
                color: {TEXT_DISABLED};
                border-color: {BG_BORDER};
                border-width: 1px;
            }}
        """)

    # ------------------------------------------------------------------
    # Event filtering — intercept mouse clicks on the frame label
    # ------------------------------------------------------------------

    def eventFilter(self, obj: object, event: object) -> bool:  # type: ignore[override]
        if obj is self._frame_label and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    if len(self._original_points) < 4:
                        self._handle_click(event.pos())
                        return True
        return super().eventFilter(obj, event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Click handling and coordinate translation
    # ------------------------------------------------------------------

    def _handle_click(self, pos: QPoint) -> None:
        """Record a click, translating from label-local to original-image coordinates.

        The click position is in the QLabel's local coordinate system.  The
        pixmap is centred inside the label with letterbox/pillarbox padding, so
        we subtract the offset and validate that the click landed inside the
        pixmap region before computing the inverse scale to source coordinates.

        Args:
            pos: Click position in QLabel-local pixels.
        """
        label = self._frame_label
        scaled_px = self._scaled_pixmap(label)
        offset_x = (label.width() - scaled_px.width()) // 2
        offset_y = (label.height() - scaled_px.height()) // 2

        # Position relative to the top-left of the displayed pixmap
        rel_x = pos.x() - offset_x
        rel_y = pos.y() - offset_y

        # Ignore clicks that land in the letterbox/pillarbox region
        if rel_x < 0 or rel_y < 0 or rel_x >= scaled_px.width() or rel_y >= scaled_px.height():
            return

        # Map back to original image pixel coordinates
        scale_x = self._source_pixmap.width() / scaled_px.width()
        scale_y = self._source_pixmap.height() / scaled_px.height()
        orig_x = int(rel_x * scale_x)
        orig_y = int(rel_y * scale_y)

        self._original_points.append((orig_x, orig_y))

        n = len(self._original_points)
        if n < 4:
            self._step_label.setText(f"STEP {n + 1} OF 4")
            self._update_prompt(n)
        else:
            self._step_label.setText("ALL 4 CORNERS CAPTURED")
            self._prompt_label.setText(
                "All corners marked. Click <b>Confirm</b> to proceed or <b>Reset</b> to redo."
            )
            self._hint_label.setText("")
            self._confirm_btn.setEnabled(True)

        self._render_frame()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _scaled_pixmap(self, label: QLabel) -> QPixmap:
        """Return the source pixmap scaled to fit the label preserving aspect ratio.

        Args:
            label: The QLabel whose current size governs the scaling.

        Returns:
            Scaled QPixmap that fits within label's bounding box.
        """
        return self._source_pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _original_to_display(
        self,
        orig_x: int,
        orig_y: int,
        scaled_px: QPixmap,
    ) -> QPoint:
        """Project an original-image coordinate into the pixmap's display space.

        The returned point is relative to the top-left of the *pixmap*, not the
        label.  The caller must add the label offset when drawing on the label.
        For _render_frame we draw directly on a canvas copy of the scaled
        pixmap, so no additional offset is needed.

        Args:
            orig_x: X coordinate in original image pixels.
            orig_y: Y coordinate in original image pixels.
            scaled_px: The scaled pixmap (determines the scale factors).

        Returns:
            QPoint in pixmap-local display coordinates.
        """
        scale_x = scaled_px.width() / self._source_pixmap.width()
        scale_y = scaled_px.height() / self._source_pixmap.height()
        return QPoint(int(orig_x * scale_x), int(orig_y * scale_y))

    def _render_frame(self) -> None:
        """Composite the frame pixmap with the overlay and push to the label.

        Draws (in order):
        1. Semi-transparent filled polygon (only once all 4 points exist).
        2. Connecting lines between consecutive markers (2+ points).
        3. Dashed closing edge between point 4 and point 1 (4 points only).
        4. Numbered filled circle markers at each click position.

        All drawing coordinates are relative to the top-left of the scaled
        pixmap canvas, not the label.  Original-image coordinates are
        re-projected at every render so the overlay remains correct after
        widget resize events.
        """
        label = self._frame_label
        scaled_px = self._scaled_pixmap(label)
        canvas = QPixmap(scaled_px)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        n = len(self._original_points)

        # Project all stored original-image points into pixmap display space
        display_pts: list[QPoint] = [
            self._original_to_display(ox, oy, scaled_px)
            for ox, oy in self._original_points
        ]

        # --- Semi-transparent filled polygon (4 points only) ------------
        if n == 4:
            poly = QPolygon(display_pts)
            fill = QColor(TEXT_ACCENT)
            fill.setAlphaF(0.12)
            painter.setBrush(fill)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly)

        # --- Progressive connecting lines (2+ points) -------------------
        if n >= 2:
            for i in range(n - 1):
                edge_color = _DOT_COLORS[i]
                pen = QPen(edge_color, _LINE_WIDTH, Qt.PenStyle.SolidLine)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(display_pts[i], display_pts[i + 1])

            # Dashed closing edge (T2-left back to T1-left)
            if n == 4:
                close_color = QColor(TEXT_ACCENT)
                close_color.setAlphaF(0.55)
                pen = QPen(close_color, _LINE_WIDTH, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(display_pts[3], display_pts[0])

        # --- Numbered circle markers ------------------------------------
        marker_font = QFont("JetBrains Mono")
        marker_font.setPixelSize(_DOT_RADIUS + 3)
        marker_font.setBold(True)
        painter.setFont(marker_font)

        for i, pt in enumerate(display_pts):
            color = _DOT_COLORS[i]

            # Filled circle
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, _DOT_RADIUS, _DOT_RADIUS)

            # Number label centred inside the circle
            painter.setPen(QColor(BG_PRIMARY))
            label_text = str(i + 1)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label_text)
            text_h = fm.ascent()
            painter.drawText(
                pt.x() - text_w // 2,
                pt.y() + text_h // 2,
                label_text,
            )

        painter.end()
        self._frame_label.setPixmap(canvas)

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def _update_prompt(self, step: int) -> None:
        """Set the prompt label text for the given 0-based step index.

        Args:
            step: 0-based index into _PROMPT_LABELS (0–3).
        """
        if 0 <= step < len(_PROMPT_LABELS):
            self._prompt_label.setText(_PROMPT_LABELS[step])

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """Clear all recorded clicks and restore the initial prompt state."""
        self._original_points.clear()
        self._step_label.setText("STEP 1 OF 4")
        self._update_prompt(0)
        self._hint_label.setText("Click on the frame to mark each corner in order.")
        self._confirm_btn.setEnabled(False)
        self._render_frame()

    def _confirm(self) -> None:
        """Emit ``cornersCaptured`` with the 4 original-image coordinate tuples."""
        self.cornersCaptured.emit(list(self._original_points))

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        """Re-render the overlay whenever the widget is resized.

        Because display coordinates are recomputed from original-image
        coordinates on every render pass, no stored state needs to be
        invalidated — just triggering a fresh render is sufficient.
        """
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._render_frame()
