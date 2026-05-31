"""Tests for RallyExample and RallyExampleIndex.

All tests are torch-free and use temporary .training.json fixtures written
to a tmp_path directory provided by pytest.

Test classes
------------
TestRallyExampleConstruction  — basic from_rally_dict / from_json_file usage
TestRallyExampleIndex         — eligible vs skipped counts, skip reasons,
                                distinct video paths, extra filter hooks
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so ml/ is importable.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.examples import RallyExample, RallyExampleIndex  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_CORNERS = [[10, 20], [310, 20], [310, 220], [10, 220]]

_GOOD_FILE_TEMPLATE: dict = {
    "schema_version": "1.1",
    "generated_by": "manual",
    "video": {
        "path": "/fake/video.mp4",
        "court_corners": _CORNERS,
    },
    "rallies": [
        {
            "index": 0,
            "score_at_start": "0-0-2",
            "winner": "server",
            "winning_team": 0,
            "is_post_game": False,
            "comment": None,
            "raw": {"start_seconds": 10.0, "end_seconds": 20.5},
        },
        {
            "index": 1,
            "score_at_start": "1-0-1",
            "winner": "receiver",
            "winning_team": 1,
            "is_post_game": False,
            "comment": None,
            "raw": {"start_seconds": 30.0, "end_seconds": 40.0},
        },
    ],
}


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_good_file(tmp_path: Path, name: str = "game.training.json") -> Path:
    p = tmp_path / name
    _write_json(p, _GOOD_FILE_TEMPLATE)
    return p


# ---------------------------------------------------------------------------
# TestRallyExampleConstruction
# ---------------------------------------------------------------------------


class TestRallyExampleConstruction:
    """Basic construction tests for RallyExample."""

    def test_from_rally_dict_fields(self, tmp_path: Path) -> None:
        """from_rally_dict produces correct field values."""
        json_path = _make_good_file(tmp_path)
        rally_dict = _GOOD_FILE_TEMPLATE["rallies"][0]
        corners: tuple[tuple[int, int], ...] = tuple(
            (int(c[0]), int(c[1])) for c in _CORNERS
        )

        ex = RallyExample.from_rally_dict(
            source_json_path=json_path,
            video_path=Path("/fake/video.mp4"),
            court_corners=corners,
            schema_version="1.1",
            generated_by="manual",
            rally_dict=rally_dict,
        )

        assert ex.rally_index == 0
        assert ex.raw_start == pytest.approx(10.0)
        assert ex.raw_end == pytest.approx(20.5)
        assert ex.score_at_start == "0-0-2"
        assert ex.score_parts == (0, 0, 2)
        assert ex.server_num == 2
        assert ex.winner == "server"
        assert ex.winning_team == 0
        assert ex.is_post_game is False
        assert ex.court_corners == corners
        assert ex.schema_version == "1.1"
        assert ex.generated_by == "manual"

    def test_from_json_file_singles(self, tmp_path: Path) -> None:
        """from_json_file works for a singles score (no server_num)."""
        data = {
            "schema_version": "1.1",
            "generated_by": "manual",
            "video": {
                "path": "/fake/singles.mp4",
                "court_corners": _CORNERS,
            },
            "rallies": [
                {
                    "index": 0,
                    "score_at_start": "5-3",
                    "winner": "receiver",
                    "winning_team": 1,
                    "is_post_game": False,
                    "comment": None,
                    "raw": {"start_seconds": 5.0, "end_seconds": 15.0},
                }
            ],
        }
        p = tmp_path / "singles.training.json"
        _write_json(p, data)

        ex = RallyExample.from_json_file(p, rally_index=0)

        assert ex.score_parts == (5, 3)
        assert ex.server_num is None
        assert ex.winning_team == 1

    def test_from_json_file_missing_raises(self, tmp_path: Path) -> None:
        """from_json_file raises FileNotFoundError for a missing file."""
        with pytest.raises(FileNotFoundError):
            RallyExample.from_json_file(tmp_path / "nonexistent.training.json", 0)

    def test_from_json_file_out_of_range_raises(self, tmp_path: Path) -> None:
        """from_json_file raises KeyError when rally_index is out of range."""
        p = _make_good_file(tmp_path)
        with pytest.raises(KeyError):
            RallyExample.from_json_file(p, rally_index=99)

    def test_example_is_frozen(self, tmp_path: Path) -> None:
        """RallyExample is immutable (frozen dataclass)."""
        p = _make_good_file(tmp_path)
        ex = RallyExample.from_json_file(p, 0)
        with pytest.raises((AttributeError, TypeError)):
            ex.rally_index = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestRallyExampleIndex
# ---------------------------------------------------------------------------


class TestRallyExampleIndex:
    """Tests for RallyExampleIndex directory scanning and eligibility."""

    def test_single_good_file(self, tmp_path: Path) -> None:
        """Index loads both eligible rallies from a single good file."""
        _make_good_file(tmp_path)
        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 2
        assert index.skip_counts == {}

    def test_distinct_video_paths(self, tmp_path: Path) -> None:
        """video_paths contains exactly the paths referenced by eligible examples."""
        _make_good_file(tmp_path)
        index = RallyExampleIndex(dirs=tmp_path)

        assert index.video_paths == {Path("/fake/video.mp4")}

    def test_two_files_two_videos(self, tmp_path: Path) -> None:
        """Two files with different video paths yield two distinct video_paths."""
        data_a = dict(_GOOD_FILE_TEMPLATE)
        data_a["video"] = {
            "path": "/fake/video_a.mp4",
            "court_corners": _CORNERS,
        }
        data_b = dict(_GOOD_FILE_TEMPLATE)
        data_b["video"] = {
            "path": "/fake/video_b.mp4",
            "court_corners": _CORNERS,
        }

        _write_json(tmp_path / "a.training.json", data_a)
        _write_json(tmp_path / "b.training.json", data_b)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.video_paths) == 2
        assert len(index.examples) == 4  # 2 rallies each

    def test_schema_too_old_skipped(self, tmp_path: Path) -> None:
        """Files with schema_version < 1.1 are skipped with file:schema_too_old."""
        old = dict(_GOOD_FILE_TEMPLATE)
        old["schema_version"] = "1.0"
        _write_json(tmp_path / "old.training.json", old)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("file:schema_too_old", 0) == 1

    def test_auto_edit_skipped(self, tmp_path: Path) -> None:
        """Files with generated_by='auto_edit' are skipped with file:auto_edit."""
        ae = dict(_GOOD_FILE_TEMPLATE)
        ae["generated_by"] = "auto_edit"
        _write_json(tmp_path / "auto.training.json", ae)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("file:auto_edit", 0) == 1

    def test_no_court_corners_skipped(self, tmp_path: Path) -> None:
        """Files lacking court_corners are skipped with file:no_court_corners."""
        nc = dict(_GOOD_FILE_TEMPLATE)
        nc["video"] = {"path": "/fake/v.mp4"}  # no court_corners key
        _write_json(tmp_path / "no_corners.training.json", nc)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("file:no_court_corners", 0) == 1

    def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        """Malformed JSON files are skipped with file:json_error."""
        bad = tmp_path / "bad.training.json"
        bad.write_text("{ not valid json }", encoding="utf-8")

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("file:json_error", 0) == 1

    def test_post_game_rally_skipped(self, tmp_path: Path) -> None:
        """Rallies with is_post_game=True are skipped with reason 'post_game'."""
        data = {
            "schema_version": "1.1",
            "generated_by": "manual",
            "video": {"path": "/fake/v.mp4", "court_corners": _CORNERS},
            "rallies": [
                {
                    "index": 0,
                    "score_at_start": "11-9-2",
                    "winner": "server",
                    "winning_team": 0,
                    "is_post_game": True,
                    "comment": None,
                    "raw": {"start_seconds": 5.0, "end_seconds": 10.0},
                },
                {
                    "index": 1,
                    "score_at_start": "0-0-2",
                    "winner": "receiver",
                    "winning_team": 1,
                    "is_post_game": False,
                    "comment": None,
                    "raw": {"start_seconds": 20.0, "end_seconds": 30.0},
                },
            ],
        }
        _write_json(tmp_path / "pg.training.json", data)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 1
        assert index.skip_counts.get("post_game", 0) == 1

    def test_winning_team_none_skipped(self, tmp_path: Path) -> None:
        """Rallies with winning_team=None are skipped with 'winning_team_none'."""
        data = {
            "schema_version": "1.1",
            "generated_by": "manual",
            "video": {"path": "/fake/v.mp4", "court_corners": _CORNERS},
            "rallies": [
                {
                    "index": 0,
                    "score_at_start": "0-0-2",
                    "winner": "server",
                    "winning_team": None,
                    "is_post_game": False,
                    "comment": None,
                    "raw": {"start_seconds": 5.0, "end_seconds": 10.0},
                }
            ],
        }
        _write_json(tmp_path / "wt_none.training.json", data)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("winning_team_none", 0) == 1

    def test_raw_none_skipped(self, tmp_path: Path) -> None:
        """Rallies with raw=None are skipped with 'raw_none'."""
        data = {
            "schema_version": "1.1",
            "generated_by": "manual",
            "video": {"path": "/fake/v.mp4", "court_corners": _CORNERS},
            "rallies": [
                {
                    "index": 0,
                    "score_at_start": "0-0-2",
                    "winner": "server",
                    "winning_team": 0,
                    "is_post_game": False,
                    "comment": None,
                    "raw": None,
                }
            ],
        }
        _write_json(tmp_path / "raw_none.training.json", data)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts.get("raw_none", 0) == 1

    def test_mixed_files_counts(self, tmp_path: Path) -> None:
        """Good and bad files are tallied correctly together."""
        _make_good_file(tmp_path, "good.training.json")

        old = dict(_GOOD_FILE_TEMPLATE)
        old["schema_version"] = "0.9"
        _write_json(tmp_path / "old.training.json", old)

        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 2
        assert index.skip_counts.get("file:schema_too_old", 0) == 1

    def test_explicit_files_parameter(self, tmp_path: Path) -> None:
        """The files= parameter accepts paths directly without scanning dirs."""
        p = _make_good_file(tmp_path)
        # Pass via files= only (dirs=None)
        index = RallyExampleIndex(files=[p])

        assert len(index.examples) == 2

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Scanning a directory with no .training.json files yields zero examples."""
        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index.examples) == 0
        assert index.skip_counts == {}

    def test_extra_rally_filter(self, tmp_path: Path) -> None:
        """extra_rally_filter can reject additional rallies with a custom reason."""
        _make_good_file(tmp_path)

        # Reject any rally where score_at_start starts with '0'
        def _filter(rally_dict: dict) -> tuple[bool, str]:
            if rally_dict.get("score_at_start", "").startswith("0"):
                return False, "score_starts_with_zero"
            return True, ""

        index = RallyExampleIndex(dirs=tmp_path, extra_rally_filter=_filter)

        # rally 0 has "0-0-2" -> rejected; rally 1 has "1-0-1" -> accepted
        assert len(index.examples) == 1
        assert index.skip_counts.get("score_starts_with_zero", 0) == 1

    def test_extra_file_filter(self, tmp_path: Path) -> None:
        """extra_file_filter can reject files with a custom reason."""
        _make_good_file(tmp_path)

        def _filter(data: dict) -> tuple[bool, str]:
            if data.get("generated_by") == "manual":
                return False, "file:manual_not_allowed"
            return True, ""

        index = RallyExampleIndex(dirs=tmp_path, extra_file_filter=_filter)

        assert len(index.examples) == 0
        assert index.skip_counts.get("file:manual_not_allowed", 0) == 1

    def test_len_equals_examples_count(self, tmp_path: Path) -> None:
        """__len__ matches len(index.examples)."""
        _make_good_file(tmp_path)
        index = RallyExampleIndex(dirs=tmp_path)

        assert len(index) == len(index.examples)

    def test_repr_contains_counts(self, tmp_path: Path) -> None:
        """__repr__ includes eligible count and video count."""
        _make_good_file(tmp_path)
        index = RallyExampleIndex(dirs=tmp_path)
        r = repr(index)

        assert "eligible=2" in r
        assert "videos=1" in r
