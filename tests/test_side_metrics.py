"""Tests for Phase 5 side/event metrics (``ml.evaluation.side_metrics``).

Covers:
- team metrics with balanced and imbalanced labels,
- terminal-event-side metrics with near/far/unknown and partial coverage,
- winner-side diagnostics, always labelled non-decisive,
- malformed annotation / side-map rejection with a clear error,
- the human-readable evaluate_winner side block never conflates the two views.

This module is torch-free.
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.evaluation.side_metrics import (  # noqa: E402
    WINNER_SIDE_DISCLAIMER,
    SideMetricsError,
    TerminalEventAnnotation,
    compute_team_metrics,
    compute_terminal_event_side_metrics,
    compute_winner_side_diagnostics,
    load_side_map,
    load_terminal_event_annotations,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# compute_team_metrics
# ---------------------------------------------------------------------------


class TestComputeTeamMetrics:
    def test_perfect_predictions(self) -> None:
        labels = [0, 1, 0, 1]
        preds = [0, 1, 0, 1]
        m = compute_team_metrics(labels, preds)
        assert m["overall_accuracy"] == 1.0
        assert m["balanced_accuracy"] == 1.0
        assert m["team_0"]["accuracy"] == 1.0
        assert m["team_1"]["accuracy"] == 1.0

    def test_balanced_accuracy_handles_imbalance(self) -> None:
        # 9 team-0 (all correct), 1 team-1 (wrong). Overall acc=0.9 but balanced
        # accuracy must reflect the failed minority class.
        labels = [0] * 9 + [1]
        preds = [0] * 9 + [0]
        m = compute_team_metrics(labels, preds)
        assert m["overall_accuracy"] == pytest.approx(0.9)
        # team0 recall = 1.0, team1 recall = 0.0 → balanced = 0.5
        assert m["balanced_accuracy"] == pytest.approx(0.5)
        assert m["base_rate_team1"] == pytest.approx(0.1)

    def test_confusion_matrix_layout(self) -> None:
        labels = [0, 0, 1, 1]
        preds = [0, 1, 1, 1]
        m = compute_team_metrics(labels, preds)
        # conf[true][pred]: true0→{pred0:1, pred1:1}, true1→{pred0:0, pred1:2}
        assert m["confusion_matrix"] == [[1, 1], [0, 2]]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(SideMetricsError, match="same length"):
            compute_team_metrics([0, 1], [0])

    def test_empty_inputs(self) -> None:
        m = compute_team_metrics([], [])
        assert m["overall_accuracy"] is None
        assert m["balanced_accuracy"] is None


# ---------------------------------------------------------------------------
# terminal-event-side metrics
# ---------------------------------------------------------------------------


def _ann(video: str, idx: int, side: str) -> TerminalEventAnnotation:
    return TerminalEventAnnotation(video_path=video, rally_index=idx, terminal_event_side=side)


class TestTerminalEventSideMetrics:
    def test_near_far_unknown_buckets(self) -> None:
        keys = [("v.mp4", 0), ("v.mp4", 1), ("v.mp4", 2)]
        labels = [0, 1, 0]
        preds = [0, 0, 0]  # near correct, far wrong, unknown correct
        annotations = {
            ("v.mp4", 0): _ann("v.mp4", 0, "near"),
            ("v.mp4", 1): _ann("v.mp4", 1, "far"),
            ("v.mp4", 2): _ann("v.mp4", 2, "unknown"),
        }
        m = compute_terminal_event_side_metrics(labels, preds, keys, annotations)
        assert m["metric_kind"] == "terminal_event_side"
        assert m["near"]["accuracy"] == 1.0
        assert m["far"]["accuracy"] == 0.0
        assert m["unknown"]["accuracy"] == 1.0
        assert m["n_mapped"] == 3
        assert m["n_unmapped"] == 0

    def test_partial_annotation_coverage_counts_unmapped(self) -> None:
        keys = [("v.mp4", 0), ("v.mp4", 1)]
        labels = [0, 1]
        preds = [0, 1]
        annotations = {("v.mp4", 0): _ann("v.mp4", 0, "far")}  # rally 1 unmapped
        m = compute_terminal_event_side_metrics(labels, preds, keys, annotations)
        assert m["n_mapped"] == 1
        assert m["n_unmapped"] == 1
        assert m["far"]["n_total"] == 1
        assert m["near"]["n_total"] == 0
        assert m["near"]["accuracy"] is None

    def test_far_bucket_confusion_matrix(self) -> None:
        keys = [("v.mp4", 0), ("v.mp4", 1)]
        labels = [1, 1]
        preds = [0, 1]
        annotations = {
            ("v.mp4", 0): _ann("v.mp4", 0, "far"),
            ("v.mp4", 1): _ann("v.mp4", 1, "far"),
        }
        m = compute_terminal_event_side_metrics(labels, preds, keys, annotations)
        # both true=1; one predicted 0, one predicted 1.
        assert m["far"]["confusion_matrix"] == [[0, 0], [1, 1]]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(SideMetricsError, match="same length"):
            compute_terminal_event_side_metrics([0], [0], [], {})


# ---------------------------------------------------------------------------
# winner-side diagnostics (non-decisive)
# ---------------------------------------------------------------------------


class TestWinnerSideDiagnostics:
    def test_buckets_split_by_winning_team_side(self) -> None:
        keys = [("v.mp4", 0), ("v.mp4", 1)]
        labels = [0, 1]  # winning teams
        preds = [0, 1]
        # rally0: near team = 0 → winner (0) is near.
        # rally1: near team = 0 → winner (1) is far.
        side_map = {("v.mp4", 0): 0, ("v.mp4", 1): 0}
        m = compute_winner_side_diagnostics(labels, preds, keys, side_map)
        assert m["winner_near"]["n_total"] == 1
        assert m["winner_far"]["n_total"] == 1
        assert m["n_mapped"] == 2
        assert m["n_unmapped"] == 0

    def test_carries_non_decisive_disclaimer(self) -> None:
        m = compute_winner_side_diagnostics([0], [0], [("v.mp4", 0)], {("v.mp4", 0): 0})
        assert m["metric_kind"] == "winner_side_diagnostic"
        assert m["disclaimer"] == WINNER_SIDE_DISCLAIMER
        assert "Not a terminal-event-side metric" in m["disclaimer"]

    def test_unmapped_rallies_counted(self) -> None:
        keys = [("v.mp4", 0), ("v.mp4", 1)]
        labels = [0, 1]
        preds = [0, 1]
        side_map = {("v.mp4", 0): 0}  # rally 1 unmapped
        m = compute_winner_side_diagnostics(labels, preds, keys, side_map)
        assert m["n_mapped"] == 1
        assert m["n_unmapped"] == 1

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(SideMetricsError, match="same length"):
            compute_winner_side_diagnostics([0, 1], [0], [("v.mp4", 0)], {})


# ---------------------------------------------------------------------------
# annotation / side-map file loading
# ---------------------------------------------------------------------------


class TestLoadTerminalEventAnnotations:
    def test_parses_valid_file(self, tmp_path: Path) -> None:
        payload = {
            "schema_version": "1.0",
            "annotations": [
                {
                    "video_path": "/v.mp4",
                    "rally_index": 17,
                    "terminal_event_side": "far",
                    "terminal_event_team": 1,
                    "event_type": "losing_error",
                    "confidence": "high",
                }
            ],
        }
        result = load_terminal_event_annotations(_write_json(tmp_path / "a.json", payload))
        ann = result[("/v.mp4", 17)]
        assert ann.terminal_event_side == "far"
        assert ann.terminal_event_team == 1
        assert ann.event_type == "losing_error"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SideMetricsError, match="not found"):
            load_terminal_event_annotations(tmp_path / "missing.json")

    def test_invalid_side_raises(self, tmp_path: Path) -> None:
        payload = {
            "annotations": [
                {"video_path": "/v.mp4", "rally_index": 0, "terminal_event_side": "sideways"}
            ]
        }
        with pytest.raises(SideMetricsError, match="terminal_event_side"):
            load_terminal_event_annotations(_write_json(tmp_path / "a.json", payload))

    def test_missing_annotations_list_raises(self, tmp_path: Path) -> None:
        payload = {"schema_version": "1.0"}
        with pytest.raises(SideMetricsError, match="annotations"):
            load_terminal_event_annotations(_write_json(tmp_path / "a.json", payload))

    def test_missing_rally_index_raises(self, tmp_path: Path) -> None:
        payload = {
            "annotations": [{"video_path": "/v.mp4", "terminal_event_side": "near"}]
        }
        with pytest.raises(SideMetricsError, match="rally_index"):
            load_terminal_event_annotations(_write_json(tmp_path / "a.json", payload))

    def test_non_object_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(SideMetricsError, match="must be a JSON object"):
            load_terminal_event_annotations(path)


class TestLoadSideMap:
    def test_parses_per_rally_block(self, tmp_path: Path) -> None:
        payload = {
            "schema_version": "1.0",
            "rallies": [
                {"video_path": "/v.mp4", "rally_index": 3, "camera_near_team": 1},
            ],
        }
        result = load_side_map(_write_json(tmp_path / "s.json", payload))
        assert result == {("/v.mp4", 3): 1}

    def test_missing_rallies_returns_empty(self, tmp_path: Path) -> None:
        payload = {"schema_version": "1.0", "segments": []}
        result = load_side_map(_write_json(tmp_path / "s.json", payload))
        assert result == {}

    def test_invalid_near_team_raises(self, tmp_path: Path) -> None:
        payload = {
            "rallies": [{"video_path": "/v.mp4", "rally_index": 0, "camera_near_team": 2}]
        }
        with pytest.raises(SideMetricsError, match="camera_near_team"):
            load_side_map(_write_json(tmp_path / "s.json", payload))

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        path.write_text("{nope", encoding="utf-8")
        with pytest.raises(SideMetricsError, match="not valid JSON"):
            load_side_map(path)


# ---------------------------------------------------------------------------
# Human-readable evaluate_winner side block
# ---------------------------------------------------------------------------


class TestEvaluateWinnerSideRendering:
    def test_renders_both_sections_without_conflation(self) -> None:
        from ml.tools.evaluate_winner import _render_side_metrics_lines

        labels = [0, 1, 0, 1]
        preds = [0, 0, 0, 1]
        keys = [("v.mp4", i) for i in range(4)]
        annotations = {
            ("v.mp4", 0): _ann("v.mp4", 0, "near"),
            ("v.mp4", 1): _ann("v.mp4", 1, "far"),
        }
        side_map = {("v.mp4", 0): 0, ("v.mp4", 1): 0}

        sm = {
            "team": compute_team_metrics(labels, preds),
            "terminal_event_side": compute_terminal_event_side_metrics(
                labels, preds, keys, annotations
            ),
            "winner_side_diagnostic": compute_winner_side_diagnostics(
                labels, preds, keys, side_map
            ),
        }
        text = "\n".join(_render_side_metrics_lines(sm))

        # Primary and secondary sections are distinctly labelled.
        assert "PRIMARY far-side metric" in text
        assert "SECONDARY, non-decisive" in text
        # The non-decisive disclaimer is rendered verbatim.
        assert "Not a terminal-event-side metric" in text

    def test_team_only_block_renders(self) -> None:
        from ml.tools.evaluate_winner import _render_side_metrics_lines

        sm = {"team": compute_team_metrics([0, 1], [0, 1])}
        text = "\n".join(_render_side_metrics_lines(sm))
        assert "Team metrics" in text
        # No terminal-event/winner-side sections without their inputs.
        assert "PRIMARY far-side metric" not in text
        assert "SECONDARY" not in text


# ---------------------------------------------------------------------------
# All-unmapped warning in _compute_side_metrics
# ---------------------------------------------------------------------------


class TestAllUnmappedWarning:
    """When annotations are provided but NO example key matches, a loud
    warning must be emitted so operators notice the path-format mismatch.
    """

    def test_all_unmapped_emits_warning(self, tmp_path: Path, capsys) -> None:
        """Annotations use a relative path; dataset examples use absolute paths.

        Every example should land in n_unmapped, triggering the warning.
        """
        import types

        from ml.tools.evaluate_winner import _compute_side_metrics

        # Annotation file uses a relative path.
        ann_path = tmp_path / "annotations.json"
        ann_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "annotations": [
                        {
                            "video_path": "relative/game.mp4",  # relative key
                            "rally_index": 0,
                            "terminal_event_side": "far",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        # Dataset examples use absolute paths — mismatch is intentional.
        ex0 = types.SimpleNamespace(
            video_path=Path("/absolute/path/to/game.mp4"),
            rally_index=0,
        )
        ex1 = types.SimpleNamespace(
            video_path=Path("/absolute/path/to/game.mp4"),
            rally_index=1,
        )

        _compute_side_metrics(
            val_examples=[ex0, ex1],
            all_labels=[0, 1],
            all_preds=[0, 1],
            terminal_event_annotations=ann_path,
            side_map=None,
        )

        captured = capsys.readouterr()
        assert "WARNING" in captured.err, "Expected a WARNING on stderr"
        assert "unmapped" in captured.err.lower(), (
            "Warning should mention unmapped"
        )
        assert "n_unmapped == n_total" in captured.err or "ALL" in captured.err, (
            "Warning should make the all-unmapped condition explicit"
        )
        # The operator should see one dataset key and one annotation key so they
        # can diagnose the mismatch at a glance.
        assert "game.mp4" in captured.err, (
            "Warning should print an example path so the mismatch is visible"
        )

    def test_partial_unmapped_does_not_warn(self, tmp_path: Path, capsys) -> None:
        """When at least one example matches, no spurious warning is emitted."""
        import types

        from ml.tools.evaluate_winner import _compute_side_metrics

        ann_path = tmp_path / "annotations.json"
        ann_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "annotations": [
                        {
                            "video_path": "/absolute/path/to/game.mp4",
                            "rally_index": 0,
                            "terminal_event_side": "near",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        ex0 = types.SimpleNamespace(
            video_path=Path("/absolute/path/to/game.mp4"),
            rally_index=0,
        )
        ex1 = types.SimpleNamespace(
            video_path=Path("/absolute/path/to/game.mp4"),
            rally_index=1,  # unmapped, but not ALL
        )

        _compute_side_metrics(
            val_examples=[ex0, ex1],
            all_labels=[0, 1],
            all_preds=[0, 1],
            terminal_event_annotations=ann_path,
            side_map=None,
        )

        captured = capsys.readouterr()
        # Partial unmapping is expected and must NOT produce a noisy warning.
        assert "n_unmapped == n_total" not in captured.err
        assert "ALL" not in captured.err or "WARNING" not in captured.err
