"""Tests for Phase 3 pinned split-manifest loading and leakage detection.

Covers ``ml.evaluation.split_manifest``:
- parsing a manifest (fields, match-level grouping precedence),
- malformed-manifest rejection with a clear error,
- cross-split duplicate/leakage detection at the match level,
- the combined ``load_split_manifests`` helper (subset loading + leakage check).

This module is torch-free; it only exercises stdlib + pathlib code.
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.evaluation.split_manifest import (  # noqa: E402
    SplitLeakageError,
    SplitManifest,
    SplitManifestError,
    detect_split_leakage,
    load_split_manifest,
    load_split_manifests,
)


def _write_manifest(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest_payload(entries: list[dict], *, split_name: str = "s", unit: str = "match") -> dict:
    return {
        "schema_version": "1.0",
        "split_name": split_name,
        "unit": unit,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestLoadSplitManifest:
    def test_parses_basic_manifest(self, tmp_path: Path) -> None:
        payload = _manifest_payload(
            [
                {
                    "id": "match_001",
                    "video_path": "/videos/a.mp4",
                    "training_json_path": "/videos/a.training.json",
                    "notes": "held out for test",
                }
            ],
            split_name="winner_2026_06",
        )
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))

        assert isinstance(manifest, SplitManifest)
        assert manifest.split_name == "winner_2026_06"
        assert manifest.unit == "match"
        assert len(manifest.entries) == 1
        entry = manifest.entries[0]
        assert entry.entry_id == "match_001"
        assert entry.video_path == Path("/videos/a.mp4")
        assert entry.training_json_path == Path("/videos/a.training.json")
        assert entry.notes == "held out for test"

    def test_match_key_prefers_match_id(self, tmp_path: Path) -> None:
        payload = _manifest_payload(
            [
                {
                    "id": "entry_x",
                    "match_id": "MATCH_42",
                    "video_path": "/videos/a.mp4",
                }
            ]
        )
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.entries[0].match_key == "MATCH_42"

    def test_match_key_falls_back_to_id(self, tmp_path: Path) -> None:
        payload = _manifest_payload(
            [{"id": "match_007", "video_path": "/videos/a.mp4"}]
        )
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.entries[0].match_key == "match_007"

    def test_match_key_falls_back_to_video_path(self, tmp_path: Path) -> None:
        payload = _manifest_payload([{"video_path": "/videos/a.mp4"}])
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.entries[0].match_key == "/videos/a.mp4"

    def test_blank_id_does_not_collapse_entries(self, tmp_path: Path) -> None:
        """Two blank-id entries must not group together — they fall back to video path."""
        payload = _manifest_payload(
            [
                {"id": "", "video_path": "/videos/a.mp4"},
                {"id": "  ", "video_path": "/videos/b.mp4"},
            ]
        )
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.match_keys == {"/videos/a.mp4", "/videos/b.mp4"}

    def test_missing_training_json_path_is_none(self, tmp_path: Path) -> None:
        payload = _manifest_payload([{"id": "m1", "video_path": "/videos/a.mp4"}])
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.entries[0].training_json_path is None

    def test_video_paths_property(self, tmp_path: Path) -> None:
        payload = _manifest_payload(
            [
                {"id": "m1", "video_path": "/videos/a.mp4"},
                {"id": "m2", "video_path": "/videos/b.mp4"},
            ]
        )
        manifest = load_split_manifest(_write_manifest(tmp_path / "m.json", payload))
        assert manifest.video_paths == {Path("/videos/a.mp4"), Path("/videos/b.mp4")}


# ---------------------------------------------------------------------------
# Malformed-manifest rejection
# ---------------------------------------------------------------------------


class TestMalformedManifests:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SplitManifestError, match="not found"):
            load_split_manifest(tmp_path / "missing.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(SplitManifestError, match="not valid JSON"):
            load_split_manifest(path)

    def test_non_object_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "list.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(SplitManifestError, match="must be a JSON object"):
            load_split_manifest(path)

    def test_missing_entries_list_raises(self, tmp_path: Path) -> None:
        path = _write_manifest(tmp_path / "m.json", {"schema_version": "1.0"})
        with pytest.raises(SplitManifestError, match="entries"):
            load_split_manifest(path)

    def test_entry_without_video_path_raises(self, tmp_path: Path) -> None:
        payload = _manifest_payload([{"id": "m1"}])
        path = _write_manifest(tmp_path / "m.json", payload)
        with pytest.raises(SplitManifestError, match="video_path"):
            load_split_manifest(path)

    def test_non_object_entry_raises(self, tmp_path: Path) -> None:
        payload = _manifest_payload([])
        payload["entries"] = ["not-a-dict"]
        path = _write_manifest(tmp_path / "m.json", payload)
        with pytest.raises(SplitManifestError, match="must be a JSON object"):
            load_split_manifest(path)


# ---------------------------------------------------------------------------
# Leakage detection
# ---------------------------------------------------------------------------


class TestDetectSplitLeakage:
    def _manifest(self, tmp_path: Path, name: str, match_ids: list[str]) -> SplitManifest:
        payload = _manifest_payload(
            [
                {"id": mid, "video_path": f"/videos/{mid}.mp4"}
                for mid in match_ids
            ],
            split_name=name,
        )
        return load_split_manifest(_write_manifest(tmp_path / f"{name}.json", payload))

    def test_disjoint_splits_pass(self, tmp_path: Path) -> None:
        manifests = {
            "train": self._manifest(tmp_path, "train", ["m1", "m2"]),
            "val": self._manifest(tmp_path, "val", ["m3"]),
            "test": self._manifest(tmp_path, "test", ["m4"]),
        }
        # Should not raise.
        detect_split_leakage(manifests)

    def test_match_in_two_splits_raises(self, tmp_path: Path) -> None:
        manifests = {
            "train": self._manifest(tmp_path, "train", ["m1", "m2"]),
            "val": self._manifest(tmp_path, "val", ["m2", "m3"]),
        }
        with pytest.raises(SplitLeakageError, match="m2"):
            detect_split_leakage(manifests)

    def test_leakage_error_names_both_splits(self, tmp_path: Path) -> None:
        manifests = {
            "train": self._manifest(tmp_path, "train", ["m1"]),
            "test": self._manifest(tmp_path, "test", ["m1"]),
        }
        with pytest.raises(SplitLeakageError) as excinfo:
            detect_split_leakage(manifests)
        message = str(excinfo.value)
        assert "train" in message
        assert "test" in message

    def test_same_match_via_different_video_paths_is_caught(self, tmp_path: Path) -> None:
        """A shared match_id across different video files still flags leakage."""
        train_payload = _manifest_payload(
            [{"match_id": "MATCH_9", "video_path": "/videos/clip_a.mp4"}],
            split_name="train",
        )
        val_payload = _manifest_payload(
            [{"match_id": "MATCH_9", "video_path": "/videos/clip_b.mp4"}],
            split_name="val",
        )
        manifests = {
            "train": load_split_manifest(_write_manifest(tmp_path / "t.json", train_payload)),
            "val": load_split_manifest(_write_manifest(tmp_path / "v.json", val_payload)),
        }
        with pytest.raises(SplitLeakageError, match="MATCH_9"):
            detect_split_leakage(manifests)


# ---------------------------------------------------------------------------
# load_split_manifests (combined loader)
# ---------------------------------------------------------------------------


class TestLoadSplitManifests:
    def _write_split(self, tmp_path: Path, name: str, match_ids: list[str]) -> Path:
        payload = _manifest_payload(
            [{"id": mid, "video_path": f"/videos/{mid}.mp4"} for mid in match_ids],
            split_name=name,
        )
        return _write_manifest(tmp_path / f"{name}.json", payload)

    def test_loads_only_supplied_splits(self, tmp_path: Path) -> None:
        train_path = self._write_split(tmp_path, "train", ["m1", "m2"])
        val_path = self._write_split(tmp_path, "val", ["m3"])

        manifests = load_split_manifests(train=train_path, val=val_path)

        assert set(manifests) == {"train", "val"}

    def test_empty_when_no_paths(self) -> None:
        assert load_split_manifests() == {}

    def test_single_manifest_skips_leakage_check(self, tmp_path: Path) -> None:
        val_path = self._write_split(tmp_path, "val", ["m1"])
        manifests = load_split_manifests(val=val_path)
        assert set(manifests) == {"val"}

    def test_leakage_across_supplied_manifests_raises(self, tmp_path: Path) -> None:
        train_path = self._write_split(tmp_path, "train", ["m1", "m2"])
        test_path = self._write_split(tmp_path, "test", ["m2"])
        with pytest.raises(SplitLeakageError, match="m2"):
            load_split_manifests(train=train_path, test=test_path)
