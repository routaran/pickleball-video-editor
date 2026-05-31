"""Post-export feature collection service.

Provides a single public entrypoint :func:`collect_features` that, given one
exported training JSON path, loads its :class:`~ml.examples.RallyExample`
records, resolves the configured extractors, and fills the
:class:`~ml.features.cache.FeatureCache` for every (example, extractor) pair
not already cached.

Design notes
------------
* Pure Python — no Qt, threading, or torch imports.  The caller owns threading.
* The public entrypoint :func:`collect_features` NEVER raises.  All failures
  are collected into :class:`CollectionSummary` so callers (including export
  pipelines) can proceed without guarding against exceptions.
* Extractor selection and cache location are injectable for tests.
* Version-aware cache lookups: stale records (version mismatch) are treated as
  misses and re-extracted automatically.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ml.config import FeatureCollectionConfig
from ml.examples import RallyExample, RallyExampleIndex, example_key
from ml.features.base import FeatureExtractor, FeatureRecord
from ml.features.cache import FeatureCache
from ml.features.registry import default_extractors, resolve_extractors


__all__ = [
    "CollectionSummary",
    "ExtractorSummary",
    "collect_features",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Summary types
# ---------------------------------------------------------------------------


@dataclass
class ExtractorSummary:
    """Per-extractor breakdown of a collection run.

    Attributes:
        name: Stable extractor identifier.
        computed: Number of examples extracted and written to cache.
        cache_hits: Number of examples satisfied from the existing cache.
        skipped: Number of examples whose extractor returned status="skipped".
        errors: Number of examples that produced an error record or raised
            an unexpected exception during extraction.
        error_details: List of human-readable error descriptions for each
            failed item.  Empty when ``errors == 0``.
    """

    name: str
    computed: int = 0
    cache_hits: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


@dataclass
class CollectionSummary:
    """Structured result of a single :func:`collect_features` call.

    Attributes:
        source_file: Absolute path to the training JSON that was processed.
        example_count: Number of eligible :class:`~ml.examples.RallyExample`
            records found in the file (0 on load failure).
        extractor_summaries: Per-extractor breakdown, keyed by extractor name.
        index_skip_counts: Skip-reason counts from
            :class:`~ml.examples.RallyExampleIndex` (e.g. ``"file:json_error"``).
        fatal_error: Non-empty string when loading failed catastrophically and
            no extraction was attempted.  Empty string on normal runs.
    """

    source_file: Path
    example_count: int = 0
    extractor_summaries: dict[str, ExtractorSummary] = field(default_factory=dict)
    index_skip_counts: dict[str, int] = field(default_factory=dict)
    fatal_error: str = ""

    # Convenience
    @property
    def total_computed(self) -> int:
        """Total number of (example, extractor) pairs newly written to cache."""
        return sum(s.computed for s in self.extractor_summaries.values())

    @property
    def total_cache_hits(self) -> int:
        """Total number of (example, extractor) pairs satisfied from cache."""
        return sum(s.cache_hits for s in self.extractor_summaries.values())

    @property
    def total_errors(self) -> int:
        """Total number of (example, extractor) pairs that produced an error."""
        return sum(s.errors for s in self.extractor_summaries.values())


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def collect_features(
    training_json_path: Path,
    *,
    extractor_names: list[str] | None = None,
    config: FeatureCollectionConfig | None = None,
    cache_root: Path | None = None,
) -> CollectionSummary:
    """Run feature extraction for all examples in one training JSON file.

    This is the primary service entrypoint.  It is safe to call from any
    context (export hook, CLI, test) because it catches all exceptions
    internally and records them in the returned :class:`CollectionSummary`.

    Parameters:
        training_json_path: Path to a schema-1.1 ``.training.json`` file.
            Does not need to exist — a missing file yields a summary with
            ``fatal_error`` set rather than raising.
        extractor_names: Explicit list of extractor names to run.  When
            ``None``, the default enabled set is derived from *config* via
            :func:`~ml.features.registry.default_extractors`.  Providing an
            explicit list ignores *config*'s ``metadata_enabled`` /
            ``audio_enabled`` flags.
        config: :class:`~ml.config.FeatureCollectionConfig` controlling the
            default extractor set.  Ignored when *extractor_names* is given.
            Defaults to a freshly constructed config when ``None``.
        cache_root: Root directory for the :class:`~ml.features.cache.FeatureCache`.
            Defaults to the project-wide default when ``None``.  Tests should
            pass ``tmp_path / "features"`` to avoid polluting the real cache.

    Returns:
        A :class:`CollectionSummary` describing all work done.  The function
        never raises; callers must inspect ``fatal_error`` and per-extractor
        ``errors`` to detect failures.
    """
    summary = CollectionSummary(source_file=training_json_path.resolve())

    # ------------------------------------------------------------------
    # Resolve extractors — failures here are fatal (bad extractor name)
    # ------------------------------------------------------------------
    try:
        extractors = _resolve_extractors(extractor_names, config)
    except Exception as exc:  # noqa: BLE001
        summary.fatal_error = f"Failed to resolve extractors: {exc}"
        _log.error("collect_features: %s", summary.fatal_error)
        return summary

    if not extractors:
        summary.fatal_error = "No extractors selected; nothing to do."
        _log.warning("collect_features: %s", summary.fatal_error)
        return summary

    # Initialise per-extractor summary entries.
    for ext in extractors:
        summary.extractor_summaries[ext.name] = ExtractorSummary(name=ext.name)

    # ------------------------------------------------------------------
    # Load examples — failure here is fatal for this file
    # ------------------------------------------------------------------
    try:
        index = RallyExampleIndex(files=[training_json_path])
    except Exception as exc:  # noqa: BLE001
        summary.fatal_error = (
            f"Failed to build RallyExampleIndex for "
            f"{training_json_path}: {exc}"
        )
        _log.error("collect_features: %s", summary.fatal_error)
        return summary

    summary.index_skip_counts = index.skip_counts
    examples = index.examples
    summary.example_count = len(examples)

    if not examples:
        _log.info(
            "collect_features: no eligible examples in %s (skip_counts=%s)",
            training_json_path,
            index.skip_counts,
        )
        return summary

    # ------------------------------------------------------------------
    # Build cache
    # ------------------------------------------------------------------
    cache = FeatureCache(root=cache_root)

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------
    for ext in extractors:
        ext_summary = summary.extractor_summaries[ext.name]
        _run_extractor(ext, examples, cache, ext_summary)

    _log.info(
        "collect_features: finished %s — %d examples, "
        "computed=%d, cache_hits=%d, errors=%d",
        training_json_path.name,
        summary.example_count,
        summary.total_computed,
        summary.total_cache_hits,
        summary.total_errors,
    )
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_extractors(
    extractor_names: list[str] | None,
    config: FeatureCollectionConfig | None,
) -> list[FeatureExtractor]:
    """Return the list of extractors to run, respecting explicit name override."""
    if extractor_names is not None:
        return resolve_extractors(extractor_names)
    return default_extractors(config)


def _run_extractor(
    extractor: FeatureExtractor,
    examples: list[RallyExample],
    cache: FeatureCache,
    ext_summary: ExtractorSummary,
) -> None:
    """Iterate over *examples* for one *extractor*, filling *cache* on miss.

    All per-item errors are collected into *ext_summary*; this function does
    not raise.
    """
    for example in examples:
        # Always use the canonical example_key as the cache key.  Extractors
        # that set their own key (e.g. the audio-end stub which uses str(example))
        # may produce values that are incorrect or too long for the filesystem.
        # We normalise to the hash key before every cache operation and
        # overwrite the record's key field before persisting.
        key = example_key(example)

        # Cache probe — version-aware.
        cached = cache.get(extractor.name, key, expected_version=extractor.version)
        if cached is not None:
            ext_summary.cache_hits += 1
            continue

        # Cache miss — extract.
        record = _extract_safe(extractor, example, key, ext_summary)
        if record is None:
            # _extract_safe already recorded the error.
            continue

        # Normalise the key on the returned record so the cache filename is
        # always the 16-char hex hash regardless of what the extractor set.
        if record.key != key:
            record = FeatureRecord(
                extractor_name=record.extractor_name,
                version=record.version,
                key=key,
                payload=record.payload,
                artifact_path=record.artifact_path,
                status=record.status,
                error=record.error,
            )

        if record.status == "skipped":
            ext_summary.skipped += 1
            # Still write to cache so downstream can distinguish not-computed
            # from stub/skipped.
            _put_safe(cache, record, extractor, key, ext_summary)
            continue

        if record.status == "error":
            ext_summary.errors += 1
            detail = record.error or "(no error message)"
            ext_summary.error_details.append(
                f"example key={key!r}: {detail}"
            )
            _log.warning(
                "collect_features[%s]: extractor error for key=%r: %s",
                extractor.name,
                key,
                detail,
            )
            # Do NOT cache error records — next run should retry.
            continue

        # status == "ok" (or anything else not "skipped"/"error")
        _put_safe(cache, record, extractor, key, ext_summary)
        ext_summary.computed += 1


def _extract_safe(
    extractor: FeatureExtractor,
    example: RallyExample,
    key: str,
    ext_summary: ExtractorSummary,
) -> FeatureRecord | None:
    """Call extractor.extract, catching any unexpected exception.

    Returns ``None`` (and records the error in *ext_summary*) if the call
    raises; otherwise returns the :class:`~ml.features.base.FeatureRecord`.
    """
    try:
        return extractor.extract(example)
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        ext_summary.errors += 1
        detail = f"example key={key!r}: unexpected exception\n{tb}"
        ext_summary.error_details.append(detail)
        _log.exception(
            "collect_features[%s]: unexpected exception for key=%r",
            extractor.name,
            key,
        )
        return None


def _put_safe(
    cache: FeatureCache,
    record: FeatureRecord,
    extractor: FeatureExtractor,
    key: str,
    ext_summary: ExtractorSummary,
) -> None:
    """Write *record* to *cache*, recording any write error in *ext_summary*."""
    try:
        cache.put(record)
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        # Downgrade to an error — the extraction succeeded but persistence failed.
        # We undo the computed increment if it was already applied; however this
        # helper is called before computed is incremented for "ok" records, so we
        # only need to undo for "skipped".
        if record.status == "skipped":
            ext_summary.skipped -= 1
        ext_summary.errors += 1
        detail = f"cache write failed for key={key!r}: {tb}"
        ext_summary.error_details.append(detail)
        _log.exception(
            "collect_features[%s]: cache.put failed for key=%r",
            extractor.name,
            key,
        )
