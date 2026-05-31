"""Tests for ml.features.cache.FeatureCache.

Coverage
--------
* Miss on empty cache (no file present).
* Put then get round-trips the full FeatureRecord without data loss.
* Version invalidation: a stored record with a different version yields None
  when ``expected_version`` is supplied.
* Matching version passes through normally.
* Corrupt JSON entry yields None rather than raising.
* Partially-written / truncated JSON yields None rather than raising.
* Empty file yields None rather than raising.
* Non-object JSON (e.g. a bare list) yields None rather than raising.
* Missing required field in stored JSON yields None.
* Multiple extractors and keys are stored in separate subdirectories without
  collision.

Design constraints
------------------
* Torch-free: no torch imports.
* All I/O is scoped to pytest's ``tmp_path`` fixture.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from ml.features.base import FeatureRecord
from ml.features.cache import FeatureCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(**overrides: Any) -> FeatureRecord:
    """Return a minimal valid FeatureRecord, with optional field overrides."""
    defaults: dict[str, Any] = {
        "extractor_name": "test_extractor",
        "version": "1.0.0",
        "key": "clip_abc123",
        "payload": {"duration_s": 3.75, "fps": 30, "label": "rally"},
        "artifact_path": None,
        "status": "ok",
        "error": None,
    }
    defaults.update(overrides)
    return FeatureRecord(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeatureCacheMiss:
    def test_get_returns_none_when_no_file(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        result = cache.get("test_extractor", "nonexistent_key")
        assert result is None

    def test_get_returns_none_for_unknown_extractor(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        result = cache.get("unknown_extractor", "clip_abc")
        assert result is None


class TestFeatureCacheHit:
    def test_miss_then_hit(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record()

        assert cache.get(record.extractor_name, record.key) is None

        cache.put(record)

        result = cache.get(record.extractor_name, record.key)
        assert result is not None
        assert result == record

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record(
            payload={"score": 0.98, "frames": [1, 2, 3], "label": "rally"},
            artifact_path="/tmp/clip.npy",
            status="ok",
        )
        cache.put(record)
        restored = cache.get(record.extractor_name, record.key)

        assert restored is not None
        assert restored.extractor_name == record.extractor_name
        assert restored.version == record.version
        assert restored.key == record.key
        assert restored.payload == record.payload
        assert restored.artifact_path == record.artifact_path
        assert restored.status == record.status
        assert restored.error == record.error

    def test_put_creates_intermediate_directories(self, tmp_path: Path) -> None:
        root = tmp_path / "deeply" / "nested"
        cache = FeatureCache(root=root)
        record = _make_record()

        assert not root.exists()
        cache.put(record)
        assert root.exists()
        assert (root / record.extractor_name / f"{record.key}.json").exists()

    def test_put_overwrites_existing_entry(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        first = _make_record(payload={"value": 1})
        cache.put(first)

        second = _make_record(payload={"value": 2})
        cache.put(second)

        result = cache.get(second.extractor_name, second.key)
        assert result is not None
        assert result.payload == {"value": 2}


class TestVersionInvalidation:
    def test_mismatched_version_returns_none(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record(version="1.0.0")
        cache.put(record)

        result = cache.get(record.extractor_name, record.key, expected_version="2.0.0")
        assert result is None

    def test_matching_version_returns_record(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record(version="1.0.0")
        cache.put(record)

        result = cache.get(record.extractor_name, record.key, expected_version="1.0.0")
        assert result is not None
        assert result.version == "1.0.0"

    def test_no_expected_version_ignores_version_field(self, tmp_path: Path) -> None:
        """When expected_version is None, any stored version is accepted."""
        cache = FeatureCache(root=tmp_path)
        record = _make_record(version="99.0.0")
        cache.put(record)

        result = cache.get(record.extractor_name, record.key)
        assert result is not None
        assert result.version == "99.0.0"


class TestCorruptEntryHandling:
    def _sidecar_path(self, root: Path, extractor_name: str, key: str) -> Path:
        return root / extractor_name / f"{key}.json"

    def _write_sidecar(self, root: Path, extractor_name: str, key: str, content: str) -> None:
        path = self._sidecar_path(root, extractor_name, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        self._write_sidecar(tmp_path, "ext", "key1", "{not valid json")
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key1") is None

    def test_truncated_json_returns_none(self, tmp_path: Path) -> None:
        self._write_sidecar(tmp_path, "ext", "key2", '{"extractor_name": "ext", "ver')
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key2") is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        self._write_sidecar(tmp_path, "ext", "key3", "")
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key3") is None

    def test_bare_list_json_returns_none(self, tmp_path: Path) -> None:
        self._write_sidecar(tmp_path, "ext", "key4", "[1, 2, 3]")
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key4") is None

    def test_missing_required_field_returns_none(self, tmp_path: Path) -> None:
        incomplete = {"version": "1.0.0", "key": "k"}  # missing extractor_name
        self._write_sidecar(tmp_path, "ext", "key5", json.dumps(incomplete))
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key5") is None

    def test_missing_version_field_returns_none(self, tmp_path: Path) -> None:
        incomplete = {"extractor_name": "ext", "key": "k"}  # missing version
        self._write_sidecar(tmp_path, "ext", "key6", json.dumps(incomplete))
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key6") is None

    def test_missing_key_field_returns_none(self, tmp_path: Path) -> None:
        incomplete = {"extractor_name": "ext", "version": "1.0.0"}  # missing key
        self._write_sidecar(tmp_path, "ext", "key7", json.dumps(incomplete))
        cache = FeatureCache(root=tmp_path)
        assert cache.get("ext", "key7") is None

    def test_corrupt_entry_does_not_raise(self, tmp_path: Path) -> None:
        """Corrupt entries must never propagate an exception to the caller."""
        self._write_sidecar(tmp_path, "ext", "key8", "}{invalid")
        cache = FeatureCache(root=tmp_path)
        try:
            result = cache.get("ext", "key8")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"get() raised unexpectedly: {exc}")
        assert result is None


class TestMultiExtractorIsolation:
    def test_different_extractors_do_not_collide(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record_a = _make_record(extractor_name="extractor_a", payload={"x": 1})
        record_b = _make_record(extractor_name="extractor_b", payload={"x": 2})

        cache.put(record_a)
        cache.put(record_b)

        got_a = cache.get("extractor_a", record_a.key)
        got_b = cache.get("extractor_b", record_b.key)

        assert got_a is not None
        assert got_b is not None
        assert got_a.payload == {"x": 1}
        assert got_b.payload == {"x": 2}

    def test_different_keys_same_extractor_do_not_collide(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record_1 = _make_record(key="clip_001", payload={"val": 10})
        record_2 = _make_record(key="clip_002", payload={"val": 20})

        cache.put(record_1)
        cache.put(record_2)

        got_1 = cache.get(record_1.extractor_name, "clip_001")
        got_2 = cache.get(record_2.extractor_name, "clip_002")

        assert got_1 is not None
        assert got_2 is not None
        assert got_1.payload == {"val": 10}
        assert got_2.payload == {"val": 20}

    def test_cache_for_missing_key_in_populated_extractor(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        cache.put(_make_record(key="exists"))

        result = cache.get("test_extractor", "does_not_exist")
        assert result is None


class TestOnDiskLayout:
    def test_sidecar_file_is_valid_json(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record()
        cache.put(record)

        sidecar = tmp_path / record.extractor_name / f"{record.key}.json"
        assert sidecar.exists()
        parsed = json.loads(sidecar.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_sidecar_path_uses_extractor_subdirectory(self, tmp_path: Path) -> None:
        cache = FeatureCache(root=tmp_path)
        record = _make_record(extractor_name="audio_v2", key="hash_deadbeef")
        cache.put(record)

        expected = tmp_path / "audio_v2" / "hash_deadbeef.json"
        assert expected.exists()
