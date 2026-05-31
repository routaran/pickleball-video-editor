"""Tests for ml.tools.collect_features and ml.features.registry.

Coverage
--------
* First run over a tiny fixture corpus computes metadata features and writes
  them to cache (computed > 0, cache_hit == 0).
* Second identical run is all cache-hits (computed == 0, cache_hit > 0).
* The audio-end stub yields skipped records; its count increments correctly.
* Error count is 0 for well-formed fixtures.
* total_pairs == total_examples × len(extractors).
* :func:`resolve_extractors` raises ``KeyError`` for unknown names.
* :func:`default_extractors` with default config returns only the metadata
  extractor (audio disabled by default).
* :func:`default_extractors` with audio_enabled returns both extractors.

Design constraints
------------------
* Torch-free: no torch, cv2, librosa, numpy, or scipy.
* All I/O is scoped to pytest's ``tmp_path`` fixture.
* Training JSON files are written to a temp dir; the real corpus is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ml.config import FeatureCollectionConfig
from ml.features.audio_end import AudioEndFeatureExtractor
from ml.features.cache import FeatureCache
from ml.features.rally_metadata import RallyMetadataExtractor
from ml.features.registry import default_extractors, resolve_extractors, REGISTRY
from ml.tools.collect_features import CollectionCounts, collect_features


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_COURT_CORNERS = [[100, 200], [540, 200], [540, 380], [100, 380]]


def _make_training_json(
    video_path: str = "/fake/video.mp4",
    rallies: list[dict[str, Any]] | None = None,
    schema_version: str = "1.1",
    generated_by: str = "manual",
) -> dict[str, Any]:
    """Return a schema-1.1-compatible training JSON dict."""
    if rallies is None:
        rallies = [
            {
                "index": 0,
                "score_at_start": "0-0-2",
                "winner": "server",
                "winning_team": 0,
                "is_post_game": False,
                "comment": None,
                "raw": {"start_seconds": 10.0, "end_seconds": 18.5},
            },
            {
                "index": 1,
                "score_at_start": "1-0-1",
                "winner": "receiver",
                "winning_team": 1,
                "is_post_game": False,
                "comment": None,
                "raw": {"start_seconds": 25.0, "end_seconds": 34.0},
            },
        ]
    return {
        "schema_version": schema_version,
        "generated_by": generated_by,
        "video": {
            "path": video_path,
            "court_corners": _COURT_CORNERS,
        },
        "rallies": rallies,
    }


def _write_corpus(tmp_path: Path, n_files: int = 1) -> Path:
    """Write *n_files* training JSON files under *tmp_path* and return the dir."""
    data_dir = tmp_path / "corpus"
    data_dir.mkdir()
    for i in range(n_files):
        payload = _make_training_json(video_path=f"/fake/video_{i}.mp4")
        (data_dir / f"game_{i:02d}.training.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return data_dir


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_known_names_present(self) -> None:
        assert "rally-metadata" in REGISTRY
        assert "audio-end" in REGISTRY

    def test_resolve_known_names(self) -> None:
        extractors = resolve_extractors(["rally-metadata"])
        assert len(extractors) == 1
        assert extractors[0].name == "rally-metadata"

    def test_resolve_multiple_names(self) -> None:
        extractors = resolve_extractors(["rally-metadata", "audio-end"])
        assert len(extractors) == 2
        assert extractors[0].name == "rally-metadata"
        assert extractors[1].name == "audio-end"

    def test_resolve_unknown_name_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            resolve_extractors(["nonexistent"])

    def test_default_extractors_metadata_only_by_default(self) -> None:
        """Default config: metadata on, audio off."""
        extractors = default_extractors()
        names = [e.name for e in extractors]
        assert "rally-metadata" in names
        assert "audio-end" not in names

    def test_default_extractors_audio_enabled(self) -> None:
        config = FeatureCollectionConfig(metadata_enabled=True, audio_enabled=True)
        extractors = default_extractors(config)
        names = [e.name for e in extractors]
        assert "rally-metadata" in names
        assert "audio-end" in names

    def test_default_extractors_metadata_disabled(self) -> None:
        config = FeatureCollectionConfig(metadata_enabled=False, audio_enabled=False)
        extractors = default_extractors(config)
        assert extractors == []

    def test_resolve_returns_protocol_conformant_instances(self) -> None:
        from ml.features.base import FeatureExtractor

        for extractor in resolve_extractors(["rally-metadata", "audio-end"]):
            assert isinstance(extractor, FeatureExtractor)


# ---------------------------------------------------------------------------
# collect_features — metadata extractor only
# ---------------------------------------------------------------------------


class TestCollectFeaturesMetadataOnly:
    def _metadata_extractor(self) -> list:
        return resolve_extractors(["rally-metadata"])

    def test_first_run_computes_records(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._metadata_extractor()

        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        # 1 file × 2 rallies × 1 extractor = 2 pairs
        assert counts.total_examples == 2
        assert counts.total_pairs == 2
        assert counts.computed == 2
        assert counts.cache_hit == 0
        assert counts.skipped == 0
        assert counts.errors == 0

    def test_second_run_is_all_cache_hits(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._metadata_extractor()

        # First run populates the cache
        collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        # Second run: everything is a cache hit
        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        assert counts.computed == 0
        assert counts.cache_hit == 2
        assert counts.skipped == 0
        assert counts.errors == 0

    def test_counts_scale_with_multiple_files(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=3)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._metadata_extractor()

        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        # 3 files × 2 rallies each × 1 extractor
        assert counts.total_examples == 6
        assert counts.computed == 6
        assert counts.cache_hit == 0

    def test_partial_cache_partial_compute(self, tmp_path: Path) -> None:
        """Populate cache for one example then add a second file; only the new
        examples should be computed."""
        data_dir = tmp_path / "corpus"
        data_dir.mkdir()
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._metadata_extractor()

        # Write first file and collect
        payload_a = _make_training_json(video_path="/fake/a.mp4")
        (data_dir / "game_a.training.json").write_text(
            json.dumps(payload_a), encoding="utf-8"
        )
        counts_a = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)
        assert counts_a.computed == 2

        # Add a second file without clearing the cache
        payload_b = _make_training_json(video_path="/fake/b.mp4")
        (data_dir / "game_b.training.json").write_text(
            json.dumps(payload_b), encoding="utf-8"
        )
        counts_b = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        # First file's 2 examples are cache-hits; second file's 2 are computed
        assert counts_b.computed == 2
        assert counts_b.cache_hit == 2
        assert counts_b.total_examples == 4


# ---------------------------------------------------------------------------
# collect_features — audio stub (skipped records)
# ---------------------------------------------------------------------------


class TestCollectFeaturesAudioStub:
    def _audio_extractor(self) -> list:
        return resolve_extractors(["audio-end"])

    def test_audio_stub_produces_skipped_records(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._audio_extractor()

        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        assert counts.total_examples == 2
        assert counts.total_pairs == 2
        assert counts.skipped == 2
        assert counts.computed == 0
        assert counts.errors == 0

    def test_audio_stub_second_run_is_cache_hit(self, tmp_path: Path) -> None:
        """Even skipped records are persisted; re-running is a cache hit."""
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._audio_extractor()

        collect_features(dirs=[data_dir], extractors=extractors, cache=cache)
        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        assert counts.cache_hit == 2
        assert counts.skipped == 0
        assert counts.computed == 0


# ---------------------------------------------------------------------------
# collect_features — both extractors together
# ---------------------------------------------------------------------------


class TestCollectFeaturesAllExtractors:
    def _all_extractors(self) -> list:
        return resolve_extractors(["rally-metadata", "audio-end"])

    def test_first_run_both_extractors(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._all_extractors()

        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        # 2 rallies × 2 extractors = 4 pairs
        assert counts.total_examples == 2
        assert counts.total_pairs == 4
        assert counts.computed == 2      # metadata: 2 ok records
        assert counts.skipped == 2      # audio-end: 2 skipped records
        assert counts.cache_hit == 0
        assert counts.errors == 0

    def test_second_run_all_cache_hits(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = self._all_extractors()

        collect_features(dirs=[data_dir], extractors=extractors, cache=cache)
        counts = collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        assert counts.cache_hit == 4
        assert counts.computed == 0
        assert counts.skipped == 0
        assert counts.errors == 0


# ---------------------------------------------------------------------------
# collect_features — edge cases
# ---------------------------------------------------------------------------


class TestCollectFeaturesEdgeCases:
    def test_empty_corpus_returns_zero_counts(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        cache = FeatureCache(root=tmp_path / "cache")
        extractors = resolve_extractors(["rally-metadata"])

        counts = collect_features(dirs=[empty_dir], extractors=extractors, cache=cache)

        assert counts.total_examples == 0
        assert counts.total_pairs == 0
        assert counts.computed == 0

    def test_no_extractors_returns_zero_counts(self, tmp_path: Path) -> None:
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache = FeatureCache(root=tmp_path / "cache")

        counts = collect_features(dirs=[data_dir], extractors=[], cache=cache)

        assert counts.total_examples == 2
        assert counts.total_pairs == 0
        assert counts.computed == 0

    def test_collection_counts_str(self) -> None:
        counts = CollectionCounts(computed=3, cache_hit=1, skipped=2, errors=0,
                                   total_examples=3, total_pairs=6)
        s = str(counts)
        assert "computed=3" in s
        assert "cache_hit=1" in s
        assert "skipped=2" in s

    def test_cache_records_are_valid_json(self, tmp_path: Path) -> None:
        """Verify that put records round-trip through JSON correctly."""
        data_dir = _write_corpus(tmp_path, n_files=1)
        cache_dir = tmp_path / "cache"
        cache = FeatureCache(root=cache_dir)
        extractors = resolve_extractors(["rally-metadata"])

        collect_features(dirs=[data_dir], extractors=extractors, cache=cache)

        sidecar_dir = cache_dir / "rally-metadata"
        assert sidecar_dir.exists()
        sidecars = list(sidecar_dir.glob("*.json"))
        assert len(sidecars) == 2

        for sidecar in sidecars:
            parsed = json.loads(sidecar.read_text(encoding="utf-8"))
            assert parsed["extractor_name"] == "rally-metadata"
            assert parsed["status"] == "ok"
            assert "duration_s" in parsed["payload"]
