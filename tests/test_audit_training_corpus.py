"""Tests for ml/tools/audit_training_corpus.py.

Builds tiny in-memory .training.json fixtures in a temp directory and asserts
that audit_corpus produces correct counts and skip-reason tallies.

All tests are torch-free; no import of torch occurs anywhere in this module.

Test classes
------------
TestParseVersion          — version string parsing edge cases
TestIsUsableTrainingFile  — file-level eligibility checks
TestAuditCorpus           — integration-style tests on temp-dir fixtures
TestCliJson               — --json flag produces valid JSON matching report
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so ml/ is importable.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.tools.audit_training_corpus import (  # noqa: E402
    CorpusReport,
    RallySkipTally,
    FileSkipTally,
    _is_usable_training_file,
    _parse_version,
    audit_corpus,
    main,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_training_json(
    schema_version: str = "1.1",
    court_corners: list[list[int]] | None = None,
    generated_by: str = "manual",
    video_path: str = "/fake/video.mp4",
    rallies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a minimal training JSON dict with sensible defaults.

    Args:
        schema_version: The schema_version field value.
        court_corners: If None, uses a default four-corner list.
                       Pass an empty list or a falsy value to omit.
        generated_by: Value for the top-level generated_by field.
        video_path: Synthetic path stored in video.path.
        rallies: List of rally dicts; defaults to an empty list.

    Returns:
        Dict that can be serialised to a .training.json file.
    """
    if court_corners is None:
        court_corners = [[0, 0], [640, 0], [640, 480], [0, 480]]

    video_block: dict[str, Any] = {"path": video_path}
    if court_corners:
        video_block["court_corners"] = court_corners

    return {
        "schema_version": schema_version,
        "generated_by": generated_by,
        "video": video_block,
        "rallies": rallies if rallies is not None else [],
    }


def _make_eligible_rally(
    index: int = 0,
    winning_team: int = 0,
    end_seconds: float = 10.0,
) -> dict[str, Any]:
    """Return a rally dict that passes all rally-level eligibility checks.

    Args:
        index: Rally index number.
        winning_team: 0 or 1.
        end_seconds: The raw.end_seconds timestamp value.

    Returns:
        Rally dict with is_post_game=False, winning_team set, raw block present.
    """
    return {
        "index": index,
        "is_post_game": False,
        "winning_team": winning_team,
        "raw": {
            "start_seconds": end_seconds - 5.0,
            "end_seconds": end_seconds,
        },
    }


def _write_training_json(directory: Path, name: str, data: dict[str, Any]) -> Path:
    """Serialise *data* as a .training.json file inside *directory*.

    Args:
        directory: Parent directory (must already exist).
        name: Base filename without extension.
        data: Dict to serialise.

    Returns:
        Path to the written file.
    """
    path = directory / f"{name}.training.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# TestParseVersion
# ---------------------------------------------------------------------------


class TestParseVersion:
    """Unit tests for the internal _parse_version helper."""

    def test_simple_two_part_version(self) -> None:
        assert _parse_version("1.1") == (1, 1)

    def test_single_component(self) -> None:
        assert _parse_version("2") == (2,)

    def test_three_part_version(self) -> None:
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_zero_version(self) -> None:
        assert _parse_version("0") == (0,)

    def test_non_numeric_component_stops_parsing(self) -> None:
        """A non-numeric component terminates parsing; leading parts are kept."""
        assert _parse_version("1.alpha.3") == (1,)

    def test_leading_whitespace_stripped(self) -> None:
        assert _parse_version("  1.1  ") == (1, 1)

    def test_comparison_old_lt_new(self) -> None:
        assert _parse_version("1.0") < _parse_version("1.1")

    def test_comparison_new_ge_min(self) -> None:
        assert _parse_version("1.1") >= (1, 1)

    def test_comparison_future_version(self) -> None:
        assert _parse_version("2.0") >= (1, 1)


# ---------------------------------------------------------------------------
# TestIsUsableTrainingFile
# ---------------------------------------------------------------------------


class TestIsUsableTrainingFile:
    """Unit tests for the file-level eligibility check."""

    def test_fully_eligible_file(self) -> None:
        data = _make_training_json(schema_version="1.1")
        eligible, reason = _is_usable_training_file(data)
        assert eligible is True
        assert reason == ""

    def test_schema_too_old_rejected(self) -> None:
        data = _make_training_json(schema_version="1.0")
        eligible, reason = _is_usable_training_file(data)
        assert eligible is False
        assert "schema_version_too_old" in reason

    def test_schema_zero_rejected(self) -> None:
        data = _make_training_json(schema_version="0")
        eligible, reason = _is_usable_training_file(data)
        assert eligible is False

    def test_missing_court_corners_rejected(self) -> None:
        data = _make_training_json()
        # Remove court_corners from video block
        del data["video"]["court_corners"]
        eligible, reason = _is_usable_training_file(data)
        assert eligible is False
        assert reason == "court_corners_missing"

    def test_empty_court_corners_rejected(self) -> None:
        data = _make_training_json()
        data["video"]["court_corners"] = []
        eligible, reason = _is_usable_training_file(data)
        assert eligible is False
        assert reason == "court_corners_missing"

    def test_auto_edit_rejected(self) -> None:
        data = _make_training_json(generated_by="auto_edit")
        eligible, reason = _is_usable_training_file(data)
        assert eligible is False
        assert reason == "generated_by_auto_edit"

    def test_schema_version_11_exactly_accepted(self) -> None:
        data = _make_training_json(schema_version="1.1")
        eligible, _ = _is_usable_training_file(data)
        assert eligible is True

    def test_schema_version_12_accepted(self) -> None:
        data = _make_training_json(schema_version="1.2")
        eligible, _ = _is_usable_training_file(data)
        assert eligible is True

    def test_schema_version_20_accepted(self) -> None:
        data = _make_training_json(schema_version="2.0")
        eligible, _ = _is_usable_training_file(data)
        assert eligible is True


# ---------------------------------------------------------------------------
# TestAuditCorpus
# ---------------------------------------------------------------------------


class TestAuditCorpus:
    """Integration-level tests that write real fixture files to a tmp_path."""

    # ------------------------------------------------------------------
    # Test: empty directory
    # ------------------------------------------------------------------

    def test_empty_directory_returns_zero_counts(self, tmp_path: Path) -> None:
        report = audit_corpus(tmp_path)
        assert report.total_files == 0
        assert report.eligible_file_count == 0
        assert report.eligible_rally_count == 0
        assert report.file_skip_tally.total == 0
        assert report.rally_skip_tally.total == 0

    # ------------------------------------------------------------------
    # Test: old-schema file is counted but skipped
    # ------------------------------------------------------------------

    def test_old_schema_file_counted_and_skipped(self, tmp_path: Path) -> None:
        data = _make_training_json(schema_version="1.0")
        _write_training_json(tmp_path, "old_schema", data)

        report = audit_corpus(tmp_path)
        assert report.total_files == 1
        assert report.eligible_file_count == 0
        assert report.file_skip_tally.schema_too_old == 1
        assert report.schema_version_counts.get("1.0", 0) == 1

    # ------------------------------------------------------------------
    # Test: auto_edit file is skipped
    # ------------------------------------------------------------------

    def test_auto_edit_file_skipped(self, tmp_path: Path) -> None:
        data = _make_training_json(generated_by="auto_edit")
        _write_training_json(tmp_path, "auto_edit_file", data)

        report = audit_corpus(tmp_path)
        assert report.total_files == 1
        assert report.eligible_file_count == 0
        assert report.file_skip_tally.generated_by_auto_edit == 1

    # ------------------------------------------------------------------
    # Test: missing court_corners skipped
    # ------------------------------------------------------------------

    def test_missing_court_corners_skipped(self, tmp_path: Path) -> None:
        data = _make_training_json()
        del data["video"]["court_corners"]
        _write_training_json(tmp_path, "no_corners", data)

        report = audit_corpus(tmp_path)
        assert report.file_skip_tally.court_corners_missing == 1

    # ------------------------------------------------------------------
    # Test: malformed JSON counted under malformed_json
    # ------------------------------------------------------------------

    def test_malformed_json_counted(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "broken.training.json"
        bad_file.write_text("{this is not valid json", encoding="utf-8")

        report = audit_corpus(tmp_path)
        assert report.total_files == 1
        assert report.file_skip_tally.malformed_json == 1
        assert report.eligible_file_count == 0

    # ------------------------------------------------------------------
    # Test: eligible file with all eligible rallies
    # ------------------------------------------------------------------

    def test_eligible_file_with_two_rallies(self, tmp_path: Path) -> None:
        rallies = [
            _make_eligible_rally(index=0, winning_team=0, end_seconds=10.0),
            _make_eligible_rally(index=1, winning_team=1, end_seconds=20.0),
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "game1", data)

        report = audit_corpus(tmp_path)
        assert report.total_files == 1
        assert report.eligible_file_count == 1
        assert report.eligible_rally_count == 2
        assert report.rally_skip_tally.total == 0
        assert report.class_balance.get(0, 0) == 1
        assert report.class_balance.get(1, 0) == 1

    # ------------------------------------------------------------------
    # Test: is_post_game rally skipped
    # ------------------------------------------------------------------

    def test_post_game_rally_skipped(self, tmp_path: Path) -> None:
        rallies = [
            _make_eligible_rally(index=0, winning_team=0),
            {
                "index": 1,
                "is_post_game": True,
                "winning_team": 0,
                "raw": {"start_seconds": 20.0, "end_seconds": 25.0},
            },
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "with_postgame", data)

        report = audit_corpus(tmp_path)
        assert report.eligible_rally_count == 1
        assert report.rally_skip_tally.is_post_game == 1
        assert report.rally_skip_tally.total == 1

    # ------------------------------------------------------------------
    # Test: winning_team=None rally skipped
    # ------------------------------------------------------------------

    def test_winning_team_none_rally_skipped(self, tmp_path: Path) -> None:
        rallies = [
            _make_eligible_rally(index=0, winning_team=0),
            {
                "index": 1,
                "is_post_game": False,
                "winning_team": None,
                "raw": {"start_seconds": 20.0, "end_seconds": 25.0},
            },
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "with_null_winner", data)

        report = audit_corpus(tmp_path)
        assert report.eligible_rally_count == 1
        assert report.rally_skip_tally.winning_team_none == 1

    # ------------------------------------------------------------------
    # Test: missing raw block skipped
    # ------------------------------------------------------------------

    def test_missing_raw_rally_skipped(self, tmp_path: Path) -> None:
        rallies = [
            _make_eligible_rally(index=0, winning_team=1),
            {
                "index": 1,
                "is_post_game": False,
                "winning_team": 1,
                # no 'raw' key
            },
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "missing_raw", data)

        report = audit_corpus(tmp_path)
        assert report.eligible_rally_count == 1
        assert report.rally_skip_tally.raw_missing == 1

    # ------------------------------------------------------------------
    # Test: multiple files, mixed schemas
    # ------------------------------------------------------------------

    def test_multiple_files_mixed_schemas(self, tmp_path: Path) -> None:
        # One old-schema file
        _write_training_json(tmp_path, "old", _make_training_json(schema_version="1.0"))

        # Two eligible files with rallies
        rallies_a = [_make_eligible_rally(index=i, winning_team=i % 2) for i in range(3)]
        _write_training_json(
            tmp_path, "game_a", _make_training_json(rallies=rallies_a, video_path="/v/a.mp4")
        )

        rallies_b = [_make_eligible_rally(index=i, winning_team=0) for i in range(2)]
        _write_training_json(
            tmp_path, "game_b", _make_training_json(rallies=rallies_b, video_path="/v/b.mp4")
        )

        report = audit_corpus(tmp_path)

        assert report.total_files == 3
        assert report.eligible_file_count == 2
        assert report.file_skip_tally.schema_too_old == 1
        assert report.eligible_rally_count == 5  # 3 + 2
        assert report.schema_version_counts.get("1.0", 0) == 1
        assert report.schema_version_counts.get("1.1", 0) == 2

    # ------------------------------------------------------------------
    # Test: class_balance counts correctly
    # ------------------------------------------------------------------

    def test_class_balance_accumulates_across_files(self, tmp_path: Path) -> None:
        rallies1 = [
            _make_eligible_rally(winning_team=0),
            _make_eligible_rally(winning_team=0, end_seconds=20.0),
        ]
        rallies2 = [
            _make_eligible_rally(winning_team=1),
        ]
        _write_training_json(
            tmp_path, "f1", _make_training_json(rallies=rallies1, video_path="/v/v1.mp4")
        )
        _write_training_json(
            tmp_path, "f2", _make_training_json(rallies=rallies2, video_path="/v/v2.mp4")
        )

        report = audit_corpus(tmp_path)
        assert report.class_balance[0] == 2
        assert report.class_balance[1] == 1

    # ------------------------------------------------------------------
    # Test: per-video rally counts
    # ------------------------------------------------------------------

    def test_rallies_by_video(self, tmp_path: Path) -> None:
        rallies = [_make_eligible_rally(index=i, end_seconds=float(i * 10 + 10)) for i in range(4)]
        _write_training_json(
            tmp_path,
            "game",
            _make_training_json(rallies=rallies, video_path="/videos/match.mp4"),
        )

        report = audit_corpus(tmp_path)
        assert report.rallies_by_video.get("/videos/match.mp4", 0) == 4

    # ------------------------------------------------------------------
    # Test: recursive directory scan discovers nested files
    # ------------------------------------------------------------------

    def test_recursive_scan_finds_nested_files(self, tmp_path: Path) -> None:
        sub = tmp_path / "session1" / "game2"
        sub.mkdir(parents=True)

        rallies = [_make_eligible_rally(winning_team=0)]
        data = _make_training_json(rallies=rallies)
        _write_training_json(sub, "nested_game", data)

        report = audit_corpus(tmp_path)
        assert report.total_files == 1
        assert report.eligible_file_count == 1
        assert report.eligible_rally_count == 1

    # ------------------------------------------------------------------
    # Test: all-skipped rallies gives zero eligible_rally_count
    # ------------------------------------------------------------------

    def test_all_skipped_rallies_gives_zero_eligible(self, tmp_path: Path) -> None:
        rallies = [
            {"index": 0, "is_post_game": True, "winning_team": 0,
             "raw": {"start_seconds": 0.0, "end_seconds": 5.0}},
            {"index": 1, "is_post_game": False, "winning_team": None,
             "raw": {"start_seconds": 5.0, "end_seconds": 10.0}},
            {"index": 2, "is_post_game": False, "winning_team": 1},
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "all_bad_rallies", data)

        report = audit_corpus(tmp_path)
        assert report.eligible_rally_count == 0
        assert report.rally_skip_tally.is_post_game == 1
        assert report.rally_skip_tally.winning_team_none == 1
        assert report.rally_skip_tally.raw_missing == 1
        assert report.rally_skip_tally.total == 3

    # ------------------------------------------------------------------
    # Test: to_dict serialises without errors
    # ------------------------------------------------------------------

    def test_to_dict_is_json_serialisable(self, tmp_path: Path) -> None:
        rallies = [_make_eligible_rally(winning_team=0)]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "game", data)

        report = audit_corpus(tmp_path)
        d = report.to_dict()
        # Should not raise
        serialised = json.dumps(d)
        parsed = json.loads(serialised)
        assert parsed["total_files"] == 1
        assert parsed["eligible_rally_count"] == 1


# ---------------------------------------------------------------------------
# TestCliJson
# ---------------------------------------------------------------------------


class TestCliJson:
    """Tests for the --json CLI flag producing machine-readable output."""

    def test_json_flag_produces_valid_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        rallies = [_make_eligible_rally(winning_team=1)]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "game", data)

        main([str(tmp_path), "--json"])

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["total_files"] == 1
        assert parsed["eligible_file_count"] == 1
        assert parsed["eligible_rally_count"] == 1

    def test_json_output_matches_report(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """The JSON output must be equivalent to report.to_dict()."""
        rallies = [
            _make_eligible_rally(index=0, winning_team=0),
            _make_eligible_rally(index=1, winning_team=1, end_seconds=20.0),
        ]
        data = _make_training_json(rallies=rallies)
        _write_training_json(tmp_path, "g", data)

        main([str(tmp_path), "--json"])

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)

        report = audit_corpus(tmp_path)
        expected = report.to_dict()

        assert parsed["total_files"] == expected["total_files"]
        assert parsed["eligible_rally_count"] == expected["eligible_rally_count"]
        assert parsed["skipped_file_count"] == expected["skipped_file_count"]
        assert parsed["skipped_rally_count"] == expected["skipped_rally_count"]

    def test_human_table_output_without_json_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Without --json the output is a human-readable table, not JSON."""
        rallies = [_make_eligible_rally(winning_team=0)]
        _write_training_json(tmp_path, "g", _make_training_json(rallies=rallies))

        main([str(tmp_path)])

        captured = capsys.readouterr()
        # Should contain summary headings, not start with '{'
        assert "Corpus audit" in captured.out
        assert not captured.out.strip().startswith("{")

    def test_cli_missing_dir_exits(self) -> None:
        """main() must raise SystemExit when no directory is supplied."""
        with pytest.raises(SystemExit):
            main([])

    def test_cli_nonexistent_dir_exits(self) -> None:
        """main() must raise SystemExit for a path that is not a directory."""
        with pytest.raises(SystemExit):
            main(["/this/path/does/not/exist/at/all"])
