"""Tests for ml.features.base — FeatureRecord and FeatureExtractor.

Coverage
--------
* A minimal conforming class passes ``isinstance(obj, FeatureExtractor)``.
* A class missing required members fails ``isinstance``.
* ``FeatureRecord.to_dict`` / ``from_dict`` round-trips without data loss.
* The round-tripped dict is JSON-serializable (``json.dumps`` does not raise).
* ``FeatureRecord.is_json_serializable()`` returns True for valid payloads.

Design constraints
------------------
* Torch-free: no torch, cv2, or numpy imports.
* No I/O: all tests are pure in-memory.
"""

import json
from typing import Any

import pytest

from ml.features import FeatureExtractor, FeatureRecord
from ml.features.base import FeatureRecord as FeatureRecordDirect


# ---------------------------------------------------------------------------
# Helpers — minimal conforming extractor
# ---------------------------------------------------------------------------


class _ConformingExtractor:
    """Trivial extractor that satisfies the FeatureExtractor Protocol."""

    name: str = "test_extractor"
    version: str = "1.0.0"

    def extract(self, example: Any) -> FeatureRecord:
        return FeatureRecord(
            extractor_name=self.name,
            version=self.version,
            key=str(example),
            payload={"value": 42},
        )


class _MissingExtractMethod:
    """Has name and version but no extract() — should not conform."""

    name: str = "broken"
    version: str = "0.0.0"


class _MissingNameAttr:
    """Has extract() but no name attribute — should not conform."""

    version: str = "0.0.0"

    def extract(self, example: Any) -> FeatureRecord:  # pragma: no cover
        ...


class _NoProtocolMembers:
    """Completely unrelated class — must not conform."""

    pass


# ---------------------------------------------------------------------------
# isinstance conformance checks
# ---------------------------------------------------------------------------


class TestFeatureExtractorProtocol:
    def test_conforming_class_passes_isinstance(self) -> None:
        obj = _ConformingExtractor()
        assert isinstance(obj, FeatureExtractor), (
            "A class with name, version, and extract() must satisfy the Protocol"
        )

    def test_missing_extract_method_fails_isinstance(self) -> None:
        obj = _MissingExtractMethod()
        assert not isinstance(obj, FeatureExtractor), (
            "An object without extract() must not satisfy the Protocol"
        )

    def test_missing_name_attribute_fails_isinstance(self) -> None:
        obj = _MissingNameAttr()
        assert not isinstance(obj, FeatureExtractor), (
            "An object without name must not satisfy the Protocol"
        )

    def test_unrelated_class_fails_isinstance(self) -> None:
        obj = _NoProtocolMembers()
        assert not isinstance(obj, FeatureExtractor), (
            "An unrelated class must not satisfy the Protocol"
        )

    def test_extract_returns_feature_record(self) -> None:
        extractor = _ConformingExtractor()
        record = extractor.extract("clip_abc")
        assert isinstance(record, FeatureRecord)
        assert record.extractor_name == "test_extractor"
        assert record.key == "clip_abc"


# ---------------------------------------------------------------------------
# FeatureRecord round-trip and JSON-serializability
# ---------------------------------------------------------------------------


class TestFeatureRecordRoundTrip:
    def _make_record(self, **overrides: Any) -> FeatureRecord:
        defaults: dict[str, Any] = {
            "extractor_name": "meta_extractor",
            "version": "2.1.0",
            "key": "video_hash_deadbeef",
            "payload": {"duration_s": 3.75, "fps": 30, "label": "rally", "tags": ["hit", "bounce"]},
            "artifact_path": None,
            "status": "ok",
            "error": None,
        }
        defaults.update(overrides)
        return FeatureRecord(**defaults)

    def test_to_dict_contains_all_fields(self) -> None:
        record = self._make_record()
        d = record.to_dict()
        assert set(d.keys()) == {
            "extractor_name", "version", "key", "payload",
            "artifact_path", "status", "error",
        }

    def test_from_dict_restores_all_fields(self) -> None:
        original = self._make_record()
        restored = FeatureRecord.from_dict(original.to_dict())
        assert restored.extractor_name == original.extractor_name
        assert restored.version == original.version
        assert restored.key == original.key
        assert restored.payload == original.payload
        assert restored.artifact_path == original.artifact_path
        assert restored.status == original.status
        assert restored.error == original.error

    def test_round_trip_is_lossless(self) -> None:
        original = self._make_record()
        assert FeatureRecord.from_dict(original.to_dict()) == original

    def test_json_dumps_does_not_raise(self) -> None:
        record = self._make_record()
        serialized = json.dumps(record.to_dict())
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_json_loads_restores_record(self) -> None:
        original = self._make_record()
        serialized = json.dumps(original.to_dict())
        loaded = json.loads(serialized)
        restored = FeatureRecord.from_dict(loaded)
        assert restored == original

    def test_is_json_serializable_returns_true_for_valid_payload(self) -> None:
        record = self._make_record()
        assert record.is_json_serializable() is True

    def test_artifact_path_survives_round_trip(self) -> None:
        record = self._make_record(artifact_path="/tmp/features/clip_abc.npy")
        restored = FeatureRecord.from_dict(record.to_dict())
        assert restored.artifact_path == "/tmp/features/clip_abc.npy"

    def test_error_status_survives_round_trip(self) -> None:
        record = self._make_record(status="error", error="audio track missing")
        restored = FeatureRecord.from_dict(record.to_dict())
        assert restored.status == "error"
        assert restored.error == "audio track missing"

    def test_skipped_status_survives_round_trip(self) -> None:
        record = self._make_record(status="skipped", payload={})
        restored = FeatureRecord.from_dict(record.to_dict())
        assert restored.status == "skipped"

    def test_from_dict_uses_defaults_for_optional_fields(self) -> None:
        minimal: dict[str, Any] = {
            "extractor_name": "x",
            "version": "1.0.0",
            "key": "k",
        }
        record = FeatureRecord.from_dict(minimal)
        assert record.payload == {}
        assert record.artifact_path is None
        assert record.status == "ok"
        assert record.error is None

    def test_import_from_package_equals_direct_import(self) -> None:
        """Ensure __init__.py re-exports the same class object."""
        assert FeatureRecord is FeatureRecordDirect
