"""Tests for ml.features.rally_metadata — RallyMetadataExtractor.

Coverage
--------
* ``RallyMetadataExtractor`` satisfies the ``FeatureExtractor`` Protocol
  (``isinstance`` check passes at runtime).
* ``extract`` returns a ``FeatureRecord`` with ``status="ok"`` and the
  expected payload field values on a variety of fixtures.
* No video or audio decoding occurs — all features come purely from
  ``RallyExample`` fields (no I/O whatsoever).
* The returned payload is strictly JSON-serializable.
* Importing ``ml.features.rally_metadata`` does NOT load torch, cv2,
  librosa, torchaudio, decord, or numpy into ``sys.modules``.

Design constraints
------------------
* Torch-free: this test file imports none of the forbidden libraries.
* No I/O: all tests are pure in-memory using synthetic RallyExample fixtures.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = str(Path(__file__).parent.parent)

from ml.examples import RallyExample, example_key
from ml.features import FeatureExtractor, FeatureRecord
from ml.features.rally_metadata import RallyMetadataExtractor


# ---------------------------------------------------------------------------
# Constants / forbidden modules
# ---------------------------------------------------------------------------

_FORBIDDEN_MODULES = frozenset(
    ["torch", "librosa", "torchaudio", "cv2", "decord", "numpy"]
)

# Shared synthetic court corners (four corners, pixel coords)
_CORNERS: tuple[tuple[int, int], ...] = (
    (100, 200),
    (540, 200),
    (540, 380),
    (100, 380),
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_example(
    *,
    raw_start: float = 10.0,
    raw_end: float = 20.0,
    score_at_start: str = "3-2-1",
    winner: str = "server",
    winning_team: int = 0,
    rally_index: int = 5,
    is_post_game: bool = False,
    schema_version: str = "1.1",
    generated_by: str = "manual",
) -> RallyExample:
    """Build a minimal synthetic :class:`RallyExample` for testing.

    Score string parsing follows RallyExample.from_rally_dict conventions:
    doubles = 3 parts, singles = 2 parts.
    """
    # Parse score_parts and server_num the same way RallyExample does
    parts = score_at_start.strip().split("-") if score_at_start else []
    parsed: list[int] = []
    for p in parts:
        if p.isdigit():
            parsed.append(int(p))

    score_parts: tuple[int, ...] = tuple(parsed) if len(parsed) in (2, 3) else ()
    server_num: int | None = parsed[2] if len(parsed) == 3 else None

    return RallyExample(
        source_json_path=Path("/fake/test.training.json"),
        video_path=Path("/fake/video.mp4"),
        rally_index=rally_index,
        raw_start=raw_start,
        raw_end=raw_end,
        score_at_start=score_at_start,
        score_parts=score_parts,
        server_num=server_num,
        winner=winner,
        winning_team=winning_team,
        court_corners=_CORNERS,
        schema_version=schema_version,
        generated_by=generated_by,
        is_post_game=is_post_game,
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestRallyMetadataProtocolConformance:
    def test_isinstance_feature_extractor(self) -> None:
        extractor = RallyMetadataExtractor()
        assert isinstance(extractor, FeatureExtractor), (
            "RallyMetadataExtractor must satisfy the FeatureExtractor Protocol"
        )

    def test_name_attribute(self) -> None:
        assert RallyMetadataExtractor().name == "rally-metadata"

    def test_version_is_semver_like(self) -> None:
        version = RallyMetadataExtractor().version
        parts = version.split(".")
        assert len(parts) == 3, f"version {version!r} must be semver X.Y.Z"
        assert all(p.isdigit() for p in parts), (
            f"version components must be digits, got {version!r}"
        )

    def test_extract_is_callable(self) -> None:
        assert callable(RallyMetadataExtractor().extract)


# ---------------------------------------------------------------------------
# extract() return type and envelope
# ---------------------------------------------------------------------------


class TestRallyMetadataExtractEnvelope:
    def _extractor(self) -> RallyMetadataExtractor:
        return RallyMetadataExtractor()

    def _example(self, **kwargs: Any) -> RallyExample:
        return _make_example(**kwargs)

    def test_returns_feature_record(self) -> None:
        record = self._extractor().extract(self._example())
        assert isinstance(record, FeatureRecord)

    def test_status_is_ok(self) -> None:
        record = self._extractor().extract(self._example())
        assert record.status == "ok", f"Expected status='ok', got {record.status!r}"

    def test_error_is_none_on_success(self) -> None:
        record = self._extractor().extract(self._example())
        assert record.error is None

    def test_extractor_name_matches_name_attr(self) -> None:
        extractor = self._extractor()
        record = extractor.extract(self._example())
        assert record.extractor_name == extractor.name

    def test_version_matches_version_attr(self) -> None:
        extractor = self._extractor()
        record = extractor.extract(self._example())
        assert record.version == extractor.version

    def test_artifact_path_is_none(self) -> None:
        record = self._extractor().extract(self._example())
        assert record.artifact_path is None

    def test_key_matches_example_key(self) -> None:
        example = self._example()
        record = self._extractor().extract(example)
        assert record.key == example_key(example)

    def test_error_record_on_wrong_type(self) -> None:
        """Non-RallyExample input must yield status='error', not raise."""
        record = self._extractor().extract({"not": "a_rally_example"})
        assert record.status == "error"
        assert record.error is not None

    def test_none_input_returns_error(self) -> None:
        record = self._extractor().extract(None)
        assert record.status == "error"


# ---------------------------------------------------------------------------
# Payload field values — doubles fixture
# ---------------------------------------------------------------------------


class TestRallyMetadataPayloadDoubles:
    """Verify all payload keys on a canonical doubles example."""

    _START = 44.55
    _END = 54.3

    def _record(self) -> FeatureRecord:
        example = _make_example(
            raw_start=self._START,
            raw_end=self._END,
            score_at_start="0-0-2",
            winner="receiver",
            winning_team=1,
            rally_index=0,
            is_post_game=False,
            schema_version="1.1",
            generated_by="manual",
        )
        return RallyMetadataExtractor().extract(example)

    def test_duration_s(self) -> None:
        p = self._record().payload
        expected = round(self._END - self._START, 6)
        assert p["duration_s"] == pytest.approx(expected, rel=1e-5)

    def test_raw_start(self) -> None:
        assert self._record().payload["raw_start"] == pytest.approx(self._START, rel=1e-5)

    def test_raw_end(self) -> None:
        assert self._record().payload["raw_end"] == pytest.approx(self._END, rel=1e-5)

    def test_score_at_start(self) -> None:
        assert self._record().payload["score_at_start"] == "0-0-2"

    def test_is_doubles_true(self) -> None:
        assert self._record().payload["is_doubles"] is True

    def test_is_singles_false(self) -> None:
        assert self._record().payload["is_singles"] is False

    def test_score_parts_count(self) -> None:
        assert self._record().payload["score_parts_count"] == 3

    def test_server_score(self) -> None:
        # "0-0-2": first part is serving team's score
        assert self._record().payload["server_score"] == 0

    def test_receiver_score(self) -> None:
        # "0-0-2": second part is receiving team's score
        assert self._record().payload["receiver_score"] == 0

    def test_score_margin(self) -> None:
        assert self._record().payload["score_margin"] == 0

    def test_server_num(self) -> None:
        # "0-0-2": third part is server number
        assert self._record().payload["server_num"] == 2

    def test_winner(self) -> None:
        assert self._record().payload["winner"] == "receiver"

    def test_winning_team(self) -> None:
        assert self._record().payload["winning_team"] == 1

    def test_server_wins_false(self) -> None:
        assert self._record().payload["server_wins"] is False

    def test_rally_index(self) -> None:
        assert self._record().payload["rally_index"] == 0

    def test_is_post_game_false(self) -> None:
        assert self._record().payload["is_post_game"] is False

    def test_schema_version(self) -> None:
        assert self._record().payload["schema_version"] == "1.1"

    def test_generated_by(self) -> None:
        assert self._record().payload["generated_by"] == "manual"


# ---------------------------------------------------------------------------
# Payload field values — singles fixture
# ---------------------------------------------------------------------------


class TestRallyMetadataPayloadSingles:
    """Verify payload keys on a singles example."""

    def _record(self) -> FeatureRecord:
        example = _make_example(
            raw_start=5.0,
            raw_end=12.5,
            score_at_start="5-3",
            winner="server",
            winning_team=0,
            rally_index=7,
            is_post_game=False,
        )
        return RallyMetadataExtractor().extract(example)

    def test_is_singles_true(self) -> None:
        assert self._record().payload["is_singles"] is True

    def test_is_doubles_false(self) -> None:
        assert self._record().payload["is_doubles"] is False

    def test_score_parts_count(self) -> None:
        assert self._record().payload["score_parts_count"] == 2

    def test_server_score(self) -> None:
        assert self._record().payload["server_score"] == 5

    def test_receiver_score(self) -> None:
        assert self._record().payload["receiver_score"] == 3

    def test_score_margin(self) -> None:
        assert self._record().payload["score_margin"] == 2

    def test_server_num_is_none(self) -> None:
        assert self._record().payload["server_num"] is None

    def test_server_wins_true(self) -> None:
        assert self._record().payload["server_wins"] is True

    def test_duration_s(self) -> None:
        p = self._record().payload
        assert p["duration_s"] == pytest.approx(7.5, rel=1e-5)

    def test_rally_index(self) -> None:
        assert self._record().payload["rally_index"] == 7


# ---------------------------------------------------------------------------
# Payload field values — edge cases
# ---------------------------------------------------------------------------


class TestRallyMetadataPayloadEdgeCases:
    def _extractor(self) -> RallyMetadataExtractor:
        return RallyMetadataExtractor()

    def test_server_leads_gives_positive_margin(self) -> None:
        example = _make_example(score_at_start="8-3-1", winner="server", winning_team=0)
        p = self._extractor().extract(example).payload
        assert p["score_margin"] == 5

    def test_receiver_leads_gives_negative_margin(self) -> None:
        example = _make_example(score_at_start="2-9-2", winner="receiver", winning_team=1)
        p = self._extractor().extract(example).payload
        assert p["score_margin"] == -7

    def test_post_game_flag_propagated(self) -> None:
        example = _make_example(is_post_game=True)
        p = self._extractor().extract(example).payload
        assert p["is_post_game"] is True

    def test_empty_score_string_gives_none_values(self) -> None:
        example = _make_example(score_at_start="")
        p = self._extractor().extract(example).payload
        assert p["score_parts_count"] == 0
        assert p["server_score"] is None
        assert p["receiver_score"] is None
        assert p["score_margin"] is None
        assert p["server_num"] is None

    def test_server_num_1(self) -> None:
        example = _make_example(score_at_start="4-3-1")
        p = self._extractor().extract(example).payload
        assert p["server_num"] == 1

    def test_server_num_2(self) -> None:
        example = _make_example(score_at_start="4-3-2")
        p = self._extractor().extract(example).payload
        assert p["server_num"] == 2

    def test_high_rally_index(self) -> None:
        example = _make_example(rally_index=99)
        p = self._extractor().extract(example).payload
        assert p["rally_index"] == 99

    def test_duration_zero_when_start_equals_end(self) -> None:
        example = _make_example(raw_start=30.0, raw_end=30.0)
        p = self._extractor().extract(example).payload
        assert p["duration_s"] == pytest.approx(0.0)

    def test_generated_by_propagated(self) -> None:
        example = _make_example(generated_by="auto_edit")
        p = self._extractor().extract(example).payload
        assert p["generated_by"] == "auto_edit"


# ---------------------------------------------------------------------------
# JSON serializability
# ---------------------------------------------------------------------------


class TestRallyMetadataJsonSerializable:
    def _extractor(self) -> RallyMetadataExtractor:
        return RallyMetadataExtractor()

    def test_payload_is_json_serializable_doubles(self) -> None:
        example = _make_example(score_at_start="3-2-1")
        record = self._extractor().extract(example)
        assert record.is_json_serializable(), (
            "FeatureRecord payload must be JSON-serializable (doubles)"
        )

    def test_payload_is_json_serializable_singles(self) -> None:
        example = _make_example(score_at_start="5-4")
        record = self._extractor().extract(example)
        assert record.is_json_serializable(), (
            "FeatureRecord payload must be JSON-serializable (singles)"
        )

    def test_payload_is_json_serializable_empty_score(self) -> None:
        example = _make_example(score_at_start="")
        record = self._extractor().extract(example)
        assert record.is_json_serializable()

    def test_full_record_round_trips_losslessly(self) -> None:
        example = _make_example(score_at_start="6-5-2", winner="receiver")
        record = self._extractor().extract(example)
        restored = FeatureRecord.from_dict(record.to_dict())
        assert restored == record

    def test_payload_values_are_primitives(self) -> None:
        """All payload values must be JSON-primitive types."""
        example = _make_example(score_at_start="3-2-1")
        payload = self._extractor().extract(example).payload
        allowed = (bool, int, float, str, type(None))
        for key, value in payload.items():
            assert isinstance(value, allowed), (
                f"Payload key {key!r} has non-primitive type {type(value).__name__!r}: "
                f"{value!r}"
            )

    def test_json_dumps_does_not_raise(self) -> None:
        example = _make_example(score_at_start="0-0-2")
        record = self._extractor().extract(example)
        dumped = json.dumps(record.to_dict())
        assert isinstance(dumped, str) and len(dumped) > 0


# ---------------------------------------------------------------------------
# No video/audio decoding
# ---------------------------------------------------------------------------


class TestRallyMetadataPureFromExample:
    """Verify that extraction performs no I/O and reads no media files."""

    def test_extract_works_with_nonexistent_video_path(self) -> None:
        """Must not attempt to open example.video_path during extract."""
        example = _make_example()
        # video_path = /fake/video.mp4 — does not exist on disk
        record = RallyMetadataExtractor().extract(example)
        assert record.status == "ok", (
            "extract should not fail due to non-existent video_path"
        )

    def test_extract_works_with_nonexistent_source_json_path(self) -> None:
        """Must not attempt to open example.source_json_path during extract."""
        example = _make_example()
        # source_json_path = /fake/test.training.json — does not exist
        record = RallyMetadataExtractor().extract(example)
        assert record.status == "ok"

    def test_successive_calls_return_independent_payloads(self) -> None:
        extractor = RallyMetadataExtractor()
        ex1 = _make_example(raw_start=1.0, raw_end=5.0, rally_index=0)
        ex2 = _make_example(raw_start=10.0, raw_end=20.0, rally_index=1)
        r1 = extractor.extract(ex1)
        r2 = extractor.extract(ex2)
        assert r1.payload["duration_s"] != r2.payload["duration_s"]
        assert r1.payload is not r2.payload


# ---------------------------------------------------------------------------
# Import isolation — no forbidden heavy dependencies
# ---------------------------------------------------------------------------


class TestRallyMetadataImportIsolation:
    def test_forbidden_modules_absent_from_sys_modules(self) -> None:
        """ml.features.rally_metadata must not pull heavy ML libs into sys.modules.

        Measured in a fresh subprocess so that heavy deps imported by other
        tests in the shared pytest process cannot produce false positives.
        """
        forbidden_list = sorted(_FORBIDDEN_MODULES)
        script = (
            "import sys\n"
            f"sys.path.insert(0, {_PROJECT_ROOT!r})\n"
            "import ml.features.rally_metadata\n"
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
            f"Importing ml.features.rally_metadata caused forbidden modules to load in a "
            f"clean subprocess: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )

    def test_module_has_no_forbidden_attributes(self) -> None:
        import ml.features.rally_metadata as mod

        for forbidden in _FORBIDDEN_MODULES:
            assert not hasattr(mod, forbidden), (
                f"ml.features.rally_metadata unexpectedly exposes attribute "
                f"{forbidden!r}"
            )
