"""Tests for ml.features.audio_end — AudioEndFeatureExtractor stub.

Coverage
--------
* ``AudioEndFeatureExtractor`` satisfies the ``FeatureExtractor`` Protocol
  (``isinstance`` check passes at runtime).
* ``extract`` always returns a ``FeatureRecord`` with ``status="skipped"``,
  an empty payload, and ``artifact_path=None``.
* The returned record is JSON-serializable (round-trip lossless).
* Importing ``ml.features.audio_end`` does NOT load torch, librosa, scipy,
  torchaudio, cv2, decord, or numpy into ``sys.modules``.

Design constraints
------------------
* Torch-free: this test file itself imports none of the forbidden libraries.
* No I/O: all tests are pure in-memory.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = str(Path(__file__).parent.parent)

from ml.features import FeatureExtractor, FeatureRecord
from ml.features.audio_end import AudioEndFeatureExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_MODULES = frozenset(
    ["torch", "librosa", "scipy", "torchaudio", "cv2", "decord", "numpy"]
)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestAudioEndProtocolConformance:
    def test_isinstance_feature_extractor(self) -> None:
        extractor = AudioEndFeatureExtractor()
        assert isinstance(extractor, FeatureExtractor), (
            "AudioEndFeatureExtractor must satisfy the FeatureExtractor Protocol"
        )

    def test_name_attribute(self) -> None:
        extractor = AudioEndFeatureExtractor()
        assert extractor.name == "audio-end"

    def test_version_attribute(self) -> None:
        extractor = AudioEndFeatureExtractor()
        assert extractor.version == "0.0.0-stub"

    def test_extract_is_callable(self) -> None:
        extractor = AudioEndFeatureExtractor()
        assert callable(extractor.extract)


# ---------------------------------------------------------------------------
# extract() return value
# ---------------------------------------------------------------------------


class TestAudioEndExtract:
    def _extractor(self) -> AudioEndFeatureExtractor:
        return AudioEndFeatureExtractor()

    def test_returns_feature_record(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert isinstance(record, FeatureRecord)

    def test_status_is_skipped(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert record.status == "skipped", (
            f"Expected status='skipped', got {record.status!r}"
        )

    def test_payload_is_empty(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert record.payload == {}, (
            f"Stub must return empty payload, got {record.payload!r}"
        )

    def test_artifact_path_is_none(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert record.artifact_path is None

    def test_extractor_name_matches_name_attr(self) -> None:
        extractor = self._extractor()
        record = extractor.extract("clip_abc")
        assert record.extractor_name == extractor.name

    def test_version_matches_version_attr(self) -> None:
        extractor = self._extractor()
        record = extractor.extract("any_example")
        assert record.version == extractor.version

    def test_key_is_stringified_example(self) -> None:
        record = self._extractor().extract("my_clip_hash")
        assert record.key == "my_clip_hash"

    def test_none_example_does_not_raise(self) -> None:
        record = self._extractor().extract(None)
        assert record.status == "skipped"

    def test_dict_example_does_not_raise(self) -> None:
        record = self._extractor().extract({"path": "/tmp/clip.mp4", "fps": 30})
        assert record.status == "skipped"

    def test_error_field_contains_note(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert record.error is not None and len(record.error) > 0, (
            "Stub should populate error with a human-readable note"
        )

    def test_record_is_json_serializable(self) -> None:
        record = self._extractor().extract("clip_abc")
        assert record.is_json_serializable(), (
            "FeatureRecord produced by the stub must be JSON-serializable"
        )

    def test_record_round_trips_losslessly(self) -> None:
        record = self._extractor().extract("round_trip_key")
        restored = FeatureRecord.from_dict(record.to_dict())
        assert restored == record

    def test_successive_calls_return_independent_records(self) -> None:
        extractor = self._extractor()
        r1 = extractor.extract("key_one")
        r2 = extractor.extract("key_two")
        assert r1.key != r2.key
        assert r1.payload is not r2.payload


# ---------------------------------------------------------------------------
# Import isolation — no forbidden heavy dependencies
# ---------------------------------------------------------------------------


class TestAudioEndImportIsolation:
    def test_forbidden_modules_absent_from_sys_modules(self) -> None:
        """ml.features.audio_end must not pull heavy ML libs into sys.modules.

        Measured in a fresh subprocess so that heavy deps imported by other
        tests in the shared pytest process cannot produce false positives.
        """
        forbidden_list = sorted(_FORBIDDEN_MODULES)
        script = (
            "import sys, json\n"
            f"sys.path.insert(0, {_PROJECT_ROOT!r})\n"
            "import ml.features.audio_end\n"
            f"forbidden = {forbidden_list!r}\n"
            "leaked = [m for m in forbidden if m in sys.modules]\n"
            "if leaked:\n"
            "    print('LEAKED:' + ','.join(leaked))\n"
            "    sys.exit(1)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Importing ml.features.audio_end caused forbidden modules to load in a "
            f"clean subprocess: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )

    def test_audio_end_module_has_no_forbidden_attributes(self) -> None:
        """The module object itself must not carry any forbidden name as an attr."""
        import ml.features.audio_end as mod

        for forbidden in _FORBIDDEN_MODULES:
            assert not hasattr(mod, forbidden), (
                f"ml.features.audio_end unexpectedly exposes attribute {forbidden!r}"
            )
