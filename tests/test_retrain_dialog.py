"""Tests for retrain_dialog pure helper functions.

Covers ``decide_default_apply`` and ``format_result_text`` — the two
module-level functions factored out of ``RetrainResultDialog`` so they are
trivially unit-testable without spawning a subprocess or creating a
QApplication.

No subprocess is launched and no Qt widget is instantiated; the test module
imports from ``src.ui.dialogs.retrain_dialog`` whose PyQt6 imports do NOT
require a display until a widget is actually constructed.

Run with::

    PYTHONPATH="$PWD" .venv/bin/python -m pytest tests/test_retrain_dialog.py -q
"""

from src.ui.dialogs.retrain_dialog import decide_default_apply, format_result_text


# ---------------------------------------------------------------------------
# decide_default_apply
# ---------------------------------------------------------------------------


class TestDecideDefaultApply:
    """Unit tests for the default-button selection logic."""

    def test_improvement_returns_true(self) -> None:
        """Apply is default when after_f1 > before_f1."""
        summary = {
            "after_loso_f1": 0.75,
            "before_loso_f1": 0.70,
            "delta": 0.05,
        }
        assert decide_default_apply(summary) is True

    def test_same_f1_returns_true(self) -> None:
        """Apply is default when after_f1 == before_f1 (at least not worse)."""
        summary = {
            "after_loso_f1": 0.70,
            "before_loso_f1": 0.70,
            "delta": 0.0,
        }
        assert decide_default_apply(summary) is True

    def test_regression_returns_false(self) -> None:
        """Keep is default when the candidate would regress F1."""
        summary = {
            "after_loso_f1": 0.65,
            "before_loso_f1": 0.72,
            "delta": -0.07,
        }
        assert decide_default_apply(summary) is False

    def test_no_baseline_key_present_returns_true(self) -> None:
        """Apply is default when before_loso_f1 key is absent (no prior baseline)."""
        summary = {"after_loso_f1": 0.68}
        assert decide_default_apply(summary) is True

    def test_before_is_explicit_none_returns_true(self) -> None:
        """Apply is default when before_loso_f1 is explicitly null/None."""
        summary = {"after_loso_f1": 0.68, "before_loso_f1": None}
        assert decide_default_apply(summary) is True

    def test_after_is_none_returns_false(self) -> None:
        """Keep is default when after_loso_f1 is None (cannot assess quality)."""
        summary = {"after_loso_f1": None, "before_loso_f1": 0.70}
        assert decide_default_apply(summary) is False

    def test_both_missing_returns_false(self) -> None:
        """Keep is default when neither F1 value is present."""
        assert decide_default_apply({}) is False

    def test_string_float_values_parsed(self) -> None:
        """String-typed float values (from JSON) are coerced correctly."""
        summary = {"after_loso_f1": "0.75", "before_loso_f1": "0.70"}
        assert decide_default_apply(summary) is True

    def test_slight_improvement_returns_true(self) -> None:
        """Even a tiny improvement triggers Apply as the default."""
        summary = {
            "after_loso_f1": 0.700001,
            "before_loso_f1": 0.700000,
        }
        assert decide_default_apply(summary) is True

    def test_slight_regression_returns_false(self) -> None:
        """Even a tiny regression triggers Keep as the default."""
        summary = {
            "after_loso_f1": 0.699999,
            "before_loso_f1": 0.700000,
        }
        assert decide_default_apply(summary) is False


# ---------------------------------------------------------------------------
# format_result_text
# ---------------------------------------------------------------------------


class TestFormatResultText:
    """Unit tests for the result-summary text formatter."""

    def test_basic_with_baseline(self) -> None:
        """Shows eligible, skipped, before, after, and delta."""
        summary = {
            "eligible": 5,
            "skipped": [],
            "after_loso_f1": 0.74,
            "before_loso_f1": 0.60,
            "delta": 0.14,
        }
        text = format_result_text(summary)
        assert "Eligible sessions: 5" in text
        assert "Skipped sessions:  0" in text
        assert "before 0.6000" in text
        assert "after 0.7400" in text
        assert "+0.1400" in text

    def test_no_baseline_shows_note(self) -> None:
        """When before_loso_f1 is None, shows 'no prior baseline' note."""
        summary = {
            "eligible": 3,
            "skipped": [],
            "after_loso_f1": 0.68,
            "before_loso_f1": None,
        }
        text = format_result_text(summary)
        assert "no prior baseline" in text
        assert "0.6800" in text
        # The before→after arrow format should NOT appear
        assert "→" not in text

    def test_no_baseline_key_absent(self) -> None:
        """before_loso_f1 missing from dict also shows 'no prior baseline'."""
        summary = {
            "eligible": 2,
            "skipped": [],
            "after_loso_f1": 0.71,
        }
        text = format_result_text(summary)
        assert "no prior baseline" in text

    def test_skipped_sessions_listed(self) -> None:
        """Skipped sessions show filename and reason."""
        summary = {
            "eligible": 2,
            "skipped": [
                {"path": "/data/sessions/video1.mp4", "reason": "no labels"},
                {"path": "/data/sessions/video2.mp4", "reason": "corrupt cache"},
            ],
            "after_loso_f1": 0.71,
            "before_loso_f1": 0.70,
            "delta": 0.01,
        }
        text = format_result_text(summary)
        assert "Skipped sessions:  2" in text
        assert "video1.mp4" in text
        assert "no labels" in text
        assert "video2.mp4" in text
        assert "corrupt cache" in text

    def test_empty_summary(self) -> None:
        """Empty dict produces sane defaults and does not crash."""
        text = format_result_text({})
        assert "Eligible sessions: 0" in text
        assert "Skipped sessions:  0" in text

    def test_no_f1_data_omits_f1_line(self) -> None:
        """When after_loso_f1 is absent, the F1 line is omitted entirely."""
        summary = {"eligible": 4, "skipped": []}
        text = format_result_text(summary)
        assert "Eligible sessions: 4" in text
        assert "F1" not in text

    def test_negative_delta_shown_with_sign(self) -> None:
        """Negative delta is shown with a '-' sign."""
        summary = {
            "eligible": 5,
            "skipped": [],
            "after_loso_f1": 0.65,
            "before_loso_f1": 0.72,
            "delta": -0.07,
        }
        text = format_result_text(summary)
        assert "-0.0700" in text

    def test_f1_formatted_to_four_decimal_places(self) -> None:
        """F1 values are formatted to 4 decimal places."""
        summary = {
            "eligible": 1,
            "skipped": [],
            "after_loso_f1": 0.7,
            "before_loso_f1": 0.6,
            "delta": 0.1,
        }
        text = format_result_text(summary)
        # Should show "0.7000" not "0.7" or "0.70"
        assert "0.7000" in text
        assert "0.6000" in text

    def test_skipped_section_header_present(self) -> None:
        """A non-empty skipped list includes a 'Skipped sessions:' header."""
        summary = {
            "eligible": 1,
            "skipped": [{"path": "/a/b.mp4", "reason": "too short"}],
            "after_loso_f1": 0.7,
            "before_loso_f1": 0.65,
            "delta": 0.05,
        }
        text = format_result_text(summary)
        assert "Skipped sessions:" in text
        assert "b.mp4" in text
        assert "too short" in text

    def test_no_skipped_omits_skipped_details(self) -> None:
        """When skipped list is empty, no 'Skipped sessions:' header appears."""
        summary = {
            "eligible": 3,
            "skipped": [],
            "after_loso_f1": 0.7,
            "before_loso_f1": 0.65,
            "delta": 0.05,
        }
        text = format_result_text(summary)
        lines = text.split("\n")
        # The count line "Skipped sessions:  0" is present, but no section header
        # for the details block.
        detail_header_lines = [
            ln for ln in lines if ln.strip() == "Skipped sessions:"
        ]
        assert detail_header_lines == []
