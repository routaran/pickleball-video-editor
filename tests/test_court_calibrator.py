"""Tests for src/ui/widgets/court_calibrator.py.

A QApplication is created once per session via the module-level fixture so
that PyQt6 does not complain about widgets created without an application.

The tests do NOT require a display: the QT_QPA_PLATFORM environment variable
is set to "offscreen" before the QApplication is created, so the suite runs
in headless CI environments.

Test coverage:
- Initial widget state (Confirm disabled, step-1 prompt visible)
- 4 sequential click events advance the prompt and enable Confirm
- cornersCaptured signal carries 4 (x, y) tuples after Confirm
- Reset clears state and restores initial UI
- Coordinate translation from display pixels to original-image pixels
"""

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Force Qt into offscreen (headless) mode before any Qt import.
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ui.widgets.court_calibrator import CourtCalibratorWidget, _PROMPT_LABELS


# ---------------------------------------------------------------------------
# Session-scoped QApplication fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the singleton QApplication, creating it if necessary.

    Scoped to the session so we never create a second QApplication instance,
    which Qt forbids.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Per-test widget factory
# ---------------------------------------------------------------------------


def _make_widget(
    qapp: QApplication,
    source_width: int = 200,
    source_height: int = 200,
    label_width: int | None = None,
    label_height: int | None = None,
) -> CourtCalibratorWidget:
    """Create a CourtCalibratorWidget with a filled QPixmap.

    Args:
        qapp: Active QApplication (unused directly, but ensures Qt is live).
        source_width: Width of the source QPixmap in pixels.
        source_height: Height of the source QPixmap in pixels.
        label_width: If given, force the frame label to this width.
        label_height: If given, force the frame label to this height.

    Returns:
        An initialised, shown CourtCalibratorWidget.
    """
    px = QPixmap(source_width, source_height)
    px.fill()
    widget = CourtCalibratorWidget(px)
    if label_width is not None and label_height is not None:
        widget._frame_label.setFixedSize(label_width, label_height)
    widget.resize(800, 600)
    widget.show()
    qapp.processEvents()
    return widget


def _send_click(widget: CourtCalibratorWidget, x: int, y: int) -> None:
    """Synthesise a left-button MouseButtonPress event on _frame_label.

    The event is delivered through the widget's eventFilter, which is the
    same path real mouse clicks take.

    Args:
        widget: The calibrator widget to receive the click.
        x: Click x in _frame_label-local pixels.
        y: Click y in _frame_label-local pixels.
    """
    label = widget._frame_label
    pos = QPointF(x, y)
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.eventFilter(label, event)


def _click_inside(widget: CourtCalibratorWidget, count: int = 1) -> None:
    """Click `count` times at distinct positions guaranteed to be inside the
    displayed pixmap region of the widget's frame label.

    The click positions are computed from the scaled-pixmap geometry so they
    always land inside the image regardless of label size.

    Args:
        widget: The calibrator widget to click on.
        count: Number of clicks to synthesise (up to 4).
    """
    label = widget._frame_label
    scaled = widget._scaled_pixmap(label)
    offset_x = (label.width() - scaled.width()) // 2
    offset_y = (label.height() - scaled.height()) // 2

    # Spread clicks across the image area so they are meaningfully distinct.
    step_x = max(1, scaled.width() // (count + 1))
    step_y = max(1, scaled.height() // (count + 1))

    for i in range(1, count + 1):
        cx = offset_x + step_x * i
        cy = offset_y + step_y * i
        # Clamp to valid region.
        cx = min(cx, offset_x + scaled.width() - 1)
        cy = min(cy, offset_y + scaled.height() - 1)
        _send_click(widget, cx, cy)


# ---------------------------------------------------------------------------
# Test 1 — Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    """Newly constructed widget must have the correct default state."""

    def test_confirm_button_disabled_initially(self, qapp: QApplication) -> None:
        """Confirm button must be disabled before any clicks."""
        w = _make_widget(qapp)
        assert not w._confirm_btn.isEnabled()

    def test_step_label_shows_step_1(self, qapp: QApplication) -> None:
        """Step label must read 'STEP 1 OF 4' before any clicks."""
        w = _make_widget(qapp)
        assert w._step_label.text() == "STEP 1 OF 4"

    def test_prompt_shows_first_instruction(self, qapp: QApplication) -> None:
        """Prompt must match the first entry in _PROMPT_LABELS."""
        w = _make_widget(qapp)
        assert _PROMPT_LABELS[0] in w._prompt_label.text()

    def test_no_recorded_points(self, qapp: QApplication) -> None:
        """_original_points must be empty before any clicks."""
        w = _make_widget(qapp)
        assert w._original_points == []


# ---------------------------------------------------------------------------
# Test 2 — 4 clicks advance the prompt and enable Confirm
# ---------------------------------------------------------------------------


class TestFourClicks:
    """Sequential clicks must advance the prompt and enable Confirm on click 4."""

    def test_confirm_enabled_after_four_clicks(self, qapp: QApplication) -> None:
        """Confirm button must become enabled exactly after the 4th click."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)
        assert w._confirm_btn.isEnabled()

    def test_confirm_not_enabled_after_three_clicks(self, qapp: QApplication) -> None:
        """Confirm must remain disabled after only 3 clicks."""
        w = _make_widget(qapp)
        _click_inside(w, count=3)
        assert not w._confirm_btn.isEnabled()

    def test_step_label_advances_with_each_click(self, qapp: QApplication) -> None:
        """Step label should advance from 'STEP 1 OF 4' to 'STEP 4 OF 4' then
        change to the all-captured message after the 4th click."""
        w = _make_widget(qapp)

        _click_inside(w, count=1)
        assert w._step_label.text() == "STEP 2 OF 4"

        _click_inside(w, count=1)
        assert w._step_label.text() == "STEP 3 OF 4"

        _click_inside(w, count=1)
        assert w._step_label.text() == "STEP 4 OF 4"

        _click_inside(w, count=1)
        # After all 4 corners are captured the label changes to the summary text.
        assert "4" in w._step_label.text() or "ALL" in w._step_label.text().upper()

    def test_prompt_advances_with_clicks(self, qapp: QApplication) -> None:
        """The prompt text must include the instruction for the next step after
        each click (steps 2, 3, 4)."""
        w = _make_widget(qapp)

        for step in range(1, 4):
            _click_inside(w, count=1)
            assert _PROMPT_LABELS[step] in w._prompt_label.text(), (
                f"After click {step}, expected prompt for step {step} "
                f"('{_PROMPT_LABELS[step]}'), got: '{w._prompt_label.text()}'"
            )

    def test_four_points_recorded(self, qapp: QApplication) -> None:
        """_original_points must hold exactly 4 entries after 4 clicks."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)
        assert len(w._original_points) == 4


# ---------------------------------------------------------------------------
# Test 3 — cornersCaptured signal
# ---------------------------------------------------------------------------


class TestCornersCapturedSignal:
    """Clicking Confirm must emit cornersCaptured with the 4 captured points."""

    def test_signal_emitted_on_confirm(self, qapp: QApplication) -> None:
        """cornersCaptured must fire exactly once when Confirm is clicked."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)

        emissions: list[list[tuple[int, int]]] = []
        w.cornersCaptured.connect(lambda pts: emissions.append(pts))

        w._confirm_btn.click()

        assert len(emissions) == 1, f"Expected 1 signal emission, got {len(emissions)}"

    def test_signal_payload_is_four_tuples(self, qapp: QApplication) -> None:
        """Emitted list must contain exactly 4 (x, y) tuples."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)

        captured: list[list[tuple[int, int]]] = []
        w.cornersCaptured.connect(lambda pts: captured.append(pts))
        w._confirm_btn.click()

        corners = captured[0]
        assert len(corners) == 4, f"Expected 4 corners, got {len(corners)}"
        for item in corners:
            assert len(item) == 2, f"Each corner should be (x, y), got {item}"
            x, y = item
            assert isinstance(x, int)
            assert isinstance(y, int)

    def test_signal_payload_matches_original_points(self, qapp: QApplication) -> None:
        """The emitted corners must be identical to _original_points."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)
        expected = list(w._original_points)

        captured: list[list[tuple[int, int]]] = []
        w.cornersCaptured.connect(lambda pts: captured.append(pts))
        w._confirm_btn.click()

        assert captured[0] == expected


# ---------------------------------------------------------------------------
# Test 4 — Reset
# ---------------------------------------------------------------------------


class TestReset:
    """Clicking Reset must clear all state and restore initial UI."""

    def test_reset_clears_recorded_clicks(self, qapp: QApplication) -> None:
        """_original_points must be empty after Reset."""
        w = _make_widget(qapp)
        _click_inside(w, count=2)
        assert len(w._original_points) == 2

        w._reset_btn.click()
        assert w._original_points == []

    def test_reset_disables_confirm(self, qapp: QApplication) -> None:
        """Confirm must be disabled after Reset regardless of prior state."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)
        assert w._confirm_btn.isEnabled()

        w._reset_btn.click()
        assert not w._confirm_btn.isEnabled()

    def test_reset_restores_step_label(self, qapp: QApplication) -> None:
        """Step label must return to 'STEP 1 OF 4' after Reset."""
        w = _make_widget(qapp)
        _click_inside(w, count=2)
        w._reset_btn.click()
        assert w._step_label.text() == "STEP 1 OF 4"

    def test_reset_restores_first_prompt(self, qapp: QApplication) -> None:
        """Prompt must return to the first instruction text after Reset."""
        w = _make_widget(qapp)
        _click_inside(w, count=2)
        w._reset_btn.click()
        assert _PROMPT_LABELS[0] in w._prompt_label.text()

    def test_reset_allows_fresh_four_clicks(self, qapp: QApplication) -> None:
        """After Reset, a new sequence of 4 clicks should re-enable Confirm."""
        w = _make_widget(qapp)
        _click_inside(w, count=4)
        w._reset_btn.click()

        _click_inside(w, count=4)
        assert w._confirm_btn.isEnabled()
        assert len(w._original_points) == 4


# ---------------------------------------------------------------------------
# Test 5 — Coordinate translation
# ---------------------------------------------------------------------------


class TestCoordinateTranslation:
    """Display-pixel clicks must map to the correct original-image coordinates."""

    def test_2x_scale_maps_display_to_original(self, qapp: QApplication) -> None:
        """Clicking at display position (50, 50) on a 100×100 display area that
        shows a 200×200 source image (2× scale factor) must yield original
        coordinates approximately (100, 100).

        Setup:
            source QPixmap: 200×200 pixels
            frame label fixed to: 100×100 pixels
            scaled pixmap fits exactly in the label: 100×100
            pillarbox/letterbox offset: (0, 0)
            click at label-local (50, 50) → original (50 * 2, 50 * 2) = (100, 100)
        """
        # Force the label to 100×100 so the 200×200 source is scaled 2:1.
        w = _make_widget(qapp, source_width=200, source_height=200,
                         label_width=100, label_height=100)

        label = w._frame_label
        scaled = w._scaled_pixmap(label)

        # Sanity: confirm the label is 100×100 and scaled pixmap fills it.
        assert label.width() == 100 and label.height() == 100, (
            f"Expected 100×100 label, got {label.width()}×{label.height()}"
        )
        assert scaled.width() == 100 and scaled.height() == 100, (
            f"Expected 100×100 scaled pixmap, got {scaled.width()}×{scaled.height()}"
        )

        # Compute the offset (should be 0, 0 when pixmap fills the label exactly).
        offset_x = (label.width() - scaled.width()) // 2
        offset_y = (label.height() - scaled.height()) // 2
        assert offset_x == 0 and offset_y == 0

        # Click at (50, 50) in label-local coordinates.
        _send_click(w, 50, 50)

        assert len(w._original_points) == 1, (
            "Click inside image should have been recorded"
        )
        orig_x, orig_y = w._original_points[0]
        assert abs(orig_x - 100) <= 1, (
            f"Expected orig_x ≈ 100 (2x scale), got {orig_x}"
        )
        assert abs(orig_y - 100) <= 1, (
            f"Expected orig_y ≈ 100 (2x scale), got {orig_y}"
        )

    def test_outside_image_click_ignored(self, qapp: QApplication) -> None:
        """A click that lands in the letterbox/pillarbox border must not be
        recorded (guard inside _handle_click).

        Setup:
            source QPixmap: 400×200 (2:1 wide)
            frame label: 300×300 (square)
            scaled pixmap: 300×150 (aspect-preserved), pillarbox above/below
            offset_y = (300 - 150) // 2 = 75
            click at (150, 10) → rel_y = 10 - 75 = -65 → rejected
        """
        w = _make_widget(qapp, source_width=400, source_height=200,
                         label_width=300, label_height=300)
        qapp.processEvents()

        label = w._frame_label
        scaled = w._scaled_pixmap(label)
        offset_y = (label.height() - scaled.height()) // 2

        # Verify our understanding of the geometry.
        assert offset_y > 0, (
            f"Expected pillarbox padding (offset_y > 0), got {offset_y}. "
            f"scaled={scaled.width()}×{scaled.height()}, "
            f"label={label.width()}×{label.height()}"
        )

        # Click in the letterbox region above the image.
        _send_click(w, label.width() // 2, offset_y // 2)

        assert w._original_points == [], (
            "Click in letterbox region must not be recorded"
        )
