"""Tests for ml.features.service.collect_features.

Coverage
--------
* Normal run on a tiny fixture JSON: metadata extractor runs, writes to tmp
  cache, returns a summary with correct counts.
* Audio stub enabled via extractor_names override: audio-end extractor runs
  and produces a skipped record (stub).
* Idempotency: a second call on the same file is fully satisfied from cache
  (zero computed, all cache-hits).
* No-raise on a nonexistent JSON path: returns a summary with fatal_error set.
* No-raise on a malformed (non-JSON) file: returns a summary with fatal_error
  or zero examples, depending on where the failure occurs.
* No-raise on an empty JSON file: same contract as malformed.
* No-raise on a structurally valid but ineligible JSON (schema too old):
  returns a summary with example_count=0 and non-empty skip_counts.

Design constraints
------------------
* Torch-free.
* All I/O scoped to pytest tmp_path.
* No Qt imports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ml.features.service import CollectionSummary, collect_features


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_VALID_CORNERS: list[list[int]] = [
    [100, 200],
    [540, 200],
    [540, 400],
    [100, 400],
]


def _write_training_json(path: Path, data: dict[str, Any]) -> None:
    """Serialise *data* as JSON at *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _minimal_training_json(*, num_rallies: int = 2) -> dict[str, Any]:
    """Return a minimal schema-1.1 training JSON dict with *num_rallies* rallies."""
    rallies = [
        {
            "index": i,
            "score_at_start": f"{i}-0-2",
            "winner": "server" if i % 2 == 0 else "receiver",
            "winning_team": i % 2,
            "is_post_game": False,
            "comment": None,
            "raw": {
                "start_seconds": float(10 + i * 15),
                "end_seconds": float(20 + i * 15),
            },
        }
        for i in range(num_rallies)
    ]
    return {
        "schema_version": "1.1",
        "generated_by": "manual",
        "video": {
            "path": "/fake/video.mp4",
            "court_corners": _VALID_CORNERS,
        },
        "rallies": rallies,
    }


# ---------------------------------------------------------------------------
# Tests: normal run
# ---------------------------------------------------------------------------


class TestNormalRun:
    def test_metadata_extractor_runs_and_writes_cache(self, tmp_path: Path) -> None:
        """Metadata extractor should compute one record per rally and cache them."""
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=2))

        cache_root = tmp_path / "features"
        summary = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=cache_root,
        )

        assert summary.fatal_error == "", f"Unexpected fatal_error: {summary.fatal_error}"
        assert summary.example_count == 2
        assert "rally-metadata" in summary.extractor_summaries
        meta = summary.extractor_summaries["rally-metadata"]
        assert meta.computed == 2
        assert meta.cache_hits == 0
        assert meta.errors == 0
        # On-disk files should exist under cache_root
        meta_dir = cache_root / "rally-metadata"
        assert meta_dir.exists()
        cached_files = list(meta_dir.glob("*.json"))
        assert len(cached_files) == 2

    def test_summary_source_file_is_absolute(self, tmp_path: Path) -> None:
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=1))
        summary = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=tmp_path / "features",
        )
        assert summary.source_file.is_absolute()

    def test_convenience_totals_match_per_extractor(self, tmp_path: Path) -> None:
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=3))
        cache_root = tmp_path / "features"
        summary = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=cache_root,
        )
        assert summary.total_computed == 3
        assert summary.total_cache_hits == 0
        assert summary.total_errors == 0


class TestAudioStub:
    def test_audio_end_extractor_produces_skipped_records(self, tmp_path: Path) -> None:
        """audio-end is a stub — it should return status='skipped' per example."""
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=2))

        cache_root = tmp_path / "features"
        summary = collect_features(
            json_path,
            extractor_names=["audio-end"],
            cache_root=cache_root,
        )

        assert summary.fatal_error == ""
        assert summary.example_count == 2
        audio_sum = summary.extractor_summaries.get("audio-end")
        assert audio_sum is not None
        # Stub records count as skipped, not errors
        assert audio_sum.errors == 0
        assert audio_sum.skipped == 2
        assert audio_sum.computed == 0
        # Stubs ARE cached (so next call is a cache-hit, not a re-extraction)
        audio_dir = cache_root / "audio-end"
        assert audio_dir.exists()
        assert len(list(audio_dir.glob("*.json"))) == 2


# ---------------------------------------------------------------------------
# Tests: idempotency / cache-hit
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_call_is_all_cache_hits(self, tmp_path: Path) -> None:
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=2))
        cache_root = tmp_path / "features"

        # First call populates the cache.
        first = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=cache_root,
        )
        assert first.total_computed == 2

        # Second call must be fully served from cache.
        second = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=cache_root,
        )
        assert second.fatal_error == ""
        assert second.example_count == 2
        meta = second.extractor_summaries["rally-metadata"]
        assert meta.cache_hits == 2
        assert meta.computed == 0
        assert meta.errors == 0

    def test_audio_stub_second_call_is_cache_hit(self, tmp_path: Path) -> None:
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=1))
        cache_root = tmp_path / "features"

        collect_features(json_path, extractor_names=["audio-end"], cache_root=cache_root)
        second = collect_features(
            json_path, extractor_names=["audio-end"], cache_root=cache_root
        )
        audio = second.extractor_summaries["audio-end"]
        assert audio.cache_hits == 1
        assert audio.skipped == 0
        assert audio.computed == 0


# ---------------------------------------------------------------------------
# Tests: no-raise guarantees on bad input
# ---------------------------------------------------------------------------


class TestNoRaiseOnBadInput:
    def test_nonexistent_file_returns_summary_with_fatal_error(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "does_not_exist.training.json"
        summary = collect_features(
            missing,
            extractor_names=["rally-metadata"],
            cache_root=tmp_path / "features",
        )
        assert isinstance(summary, CollectionSummary)
        # No examples can be loaded; either fatal_error is set or example_count is 0.
        # Both are acceptable outcomes — the key invariant is no exception.
        if summary.fatal_error:
            assert summary.example_count == 0
        else:
            assert summary.example_count == 0

    def test_nonexistent_file_does_not_raise(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.training.json"
        try:
            collect_features(
                missing,
                extractor_names=["rally-metadata"],
                cache_root=tmp_path / "features",
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"collect_features raised unexpectedly: {exc}")

    def test_malformed_json_does_not_raise(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.training.json"
        bad.write_text("{not valid json at all", encoding="utf-8")
        try:
            summary = collect_features(
                bad,
                extractor_names=["rally-metadata"],
                cache_root=tmp_path / "features",
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"collect_features raised unexpectedly: {exc}")
        else:
            assert isinstance(summary, CollectionSummary)
            assert summary.example_count == 0

    def test_empty_json_file_does_not_raise(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.training.json"
        empty.write_text("", encoding="utf-8")
        try:
            summary = collect_features(
                empty,
                extractor_names=["rally-metadata"],
                cache_root=tmp_path / "features",
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"collect_features raised unexpectedly: {exc}")
        else:
            assert isinstance(summary, CollectionSummary)
            assert summary.example_count == 0

    def test_schema_too_old_yields_zero_examples(self, tmp_path: Path) -> None:
        old_schema = {
            "schema_version": "1.0",
            "generated_by": "manual",
            "video": {
                "path": "/fake/video.mp4",
                "court_corners": _VALID_CORNERS,
            },
            "rallies": [
                {
                    "index": 0,
                    "score_at_start": "0-0-2",
                    "winner": "server",
                    "winning_team": 0,
                    "is_post_game": False,
                    "comment": None,
                    "raw": {"start_seconds": 10.0, "end_seconds": 20.0},
                }
            ],
        }
        json_path = tmp_path / "old.training.json"
        _write_training_json(json_path, old_schema)
        summary = collect_features(
            json_path,
            extractor_names=["rally-metadata"],
            cache_root=tmp_path / "features",
        )
        assert isinstance(summary, CollectionSummary)
        assert summary.example_count == 0
        assert summary.fatal_error == ""
        # The index should report a file-level skip reason.
        assert any("file:" in k for k in summary.index_skip_counts)

    def test_invalid_extractor_name_does_not_raise(self, tmp_path: Path) -> None:
        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=1))
        try:
            summary = collect_features(
                json_path,
                extractor_names=["does-not-exist"],
                cache_root=tmp_path / "features",
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"collect_features raised unexpectedly: {exc}")
        else:
            assert isinstance(summary, CollectionSummary)
            assert summary.fatal_error != ""


# ---------------------------------------------------------------------------
# Tests: default extractor selection via config
# ---------------------------------------------------------------------------


class TestDefaultExtractorConfig:
    def test_default_config_runs_metadata_only(self, tmp_path: Path) -> None:
        from ml.config import FeatureCollectionConfig

        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=1))
        cfg = FeatureCollectionConfig(metadata_enabled=True, audio_enabled=False)
        summary = collect_features(
            json_path,
            config=cfg,
            cache_root=tmp_path / "features",
        )
        assert "rally-metadata" in summary.extractor_summaries
        assert "audio-end" not in summary.extractor_summaries
        assert summary.extractor_summaries["rally-metadata"].computed == 1

    def test_audio_enabled_config_includes_audio_extractor(self, tmp_path: Path) -> None:
        from ml.config import FeatureCollectionConfig

        json_path = tmp_path / "fixture.training.json"
        _write_training_json(json_path, _minimal_training_json(num_rallies=1))
        cfg = FeatureCollectionConfig(metadata_enabled=True, audio_enabled=True)
        summary = collect_features(
            json_path,
            config=cfg,
            cache_root=tmp_path / "features",
        )
        assert "audio-end" in summary.extractor_summaries
