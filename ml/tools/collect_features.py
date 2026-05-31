"""Batch feature collection CLI for the ML pipeline.

Builds a :class:`~ml.examples.RallyExampleIndex` over one or more data
directories and, for each (example, extractor) pair, checks the
:class:`~ml.features.cache.FeatureCache` before running extraction.  Fully
idempotent: re-running with an identical corpus and cache dir is a no-op.

Count semantics
---------------
``computed``   — extraction ran and ``cache.put`` was called.
``cache_hit``  — a valid, version-matched record already existed; skipped.
``skipped``    — extractor returned ``status="skipped"`` (e.g. audio stub).
``errors``     — extractor returned ``status="error"`` or an unexpected
                 exception occurred.

Usage
-----
From the project root::

    python -m ml.tools.collect_features --dir /path/to/labels \\
        [--features rally-metadata,audio-end] \\
        [--cache-dir /path/to/cache]

All three flags are optional:

``--dir PATH``
    Directory (or comma-separated list of directories) to scan recursively
    for ``*.training.json`` files.  Defaults to the current working directory.

``--features name1,name2``
    Comma-separated extractor names.  Defaults to the enabled set from a
    default :class:`~ml.config.FeatureCollectionConfig` (metadata on, audio
    off).

``--cache-dir PATH``
    Root directory for the feature cache.  Defaults to the project cache root
    (``ml/cache/features``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ml.examples import RallyExampleIndex, example_key
from ml.features.base import FeatureExtractor, FeatureRecord
from ml.features.cache import FeatureCache
from ml.features.registry import default_extractors, resolve_extractors


__all__ = ["CollectionCounts", "collect_features"]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CollectionCounts:
    """Summary counts from a :func:`collect_features` run.

    Attributes:
        computed:  Number of records freshly extracted and written to cache.
        cache_hit: Number of records skipped because a version-matched cached
                   record already existed.
        skipped:   Number of records where the extractor returned
                   ``status="skipped"`` (no-op stubs).
        errors:    Number of records where extraction failed (``status="error"``
                   or an unexpected exception).
        total_examples: Total number of eligible examples in the index.
        total_pairs:    Total (example × extractor) pairs evaluated.
    """

    computed: int = 0
    cache_hit: int = 0
    skipped: int = 0
    errors: int = 0
    total_examples: int = 0
    total_pairs: int = 0

    def __str__(self) -> str:
        return (
            f"CollectionCounts("
            f"computed={self.computed}, "
            f"cache_hit={self.cache_hit}, "
            f"skipped={self.skipped}, "
            f"errors={self.errors}, "
            f"total_examples={self.total_examples}, "
            f"total_pairs={self.total_pairs})"
        )


# ---------------------------------------------------------------------------
# Core logic (importable by tests and services)
# ---------------------------------------------------------------------------


def collect_features(
    dirs: list[Path],
    extractors: list[FeatureExtractor],
    cache: FeatureCache,
) -> CollectionCounts:
    """Run batch feature collection over *dirs* with *extractors*.

    For each eligible example in the index built from *dirs*, and for each
    extractor in *extractors*, the function checks the cache first.  On a
    version-matched cache hit the record is counted and skipped.  Otherwise
    ``extractor.extract(example)`` is called and the result is written to
    cache (regardless of its ``status``).

    The training JSON files are opened read-only; no label file is modified.

    Parameters:
        dirs: Directories to scan recursively for ``*.training.json`` files.
        extractors: Extractor instances to run; obtain via
            :func:`~ml.features.registry.resolve_extractors` or
            :func:`~ml.features.registry.default_extractors`.
        cache: Cache instance to read from and write to.

    Returns:
        A :class:`CollectionCounts` summary of the run.
    """
    counts = CollectionCounts()

    index = RallyExampleIndex(dirs=dirs)
    examples = index.examples
    counts.total_examples = len(examples)
    counts.total_pairs = len(examples) * len(extractors)

    _log.info(
        "collect_features: %d examples × %d extractors = %d pairs",
        counts.total_examples,
        len(extractors),
        counts.total_pairs,
    )

    for example in examples:
        key = example_key(example)

        for extractor in extractors:
            cached = cache.get(extractor.name, key, expected_version=extractor.version)
            if cached is not None:
                counts.cache_hit += 1
                _log.debug("cache hit: %s / %s", extractor.name, key)
                continue

            # Run extraction — must never raise per Protocol contract, but we
            # guard defensively so one bad extractor cannot abort the whole run.
            record: FeatureRecord
            try:
                record = extractor.extract(example)
            except Exception as exc:  # noqa: BLE001 — defensive boundary only
                _log.error(
                    "Unexpected exception from %s.extract for key %s: %s",
                    extractor.name,
                    key,
                    exc,
                )
                counts.errors += 1
                continue

            # Normalise the key to the canonical hash so that stub extractors
            # (e.g. audio-end) that derive their key from str(example) don't
            # produce filesystem-unfriendly paths.  The cache lookup above
            # already uses the same canonical key, so they will match on the
            # next run.
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

            # Always persist the record so the next run is a cache hit.
            cache.put(record)

            if record.status == "skipped":
                counts.skipped += 1
                _log.debug("skipped: %s / %s — %s", extractor.name, key, record.error)
            elif record.status == "error":
                counts.errors += 1
                _log.warning(
                    "extraction error: %s / %s — %s", extractor.name, key, record.error
                )
            else:
                counts.computed += 1
                _log.debug("computed: %s / %s", extractor.name, key)

    _log.info("collect_features complete: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collect_features",
        description=(
            "Batch feature collection for the pickleball ML pipeline. "
            "Idempotent: re-running with the same corpus and cache is a no-op."
        ),
    )
    parser.add_argument(
        "--dir",
        dest="dirs",
        metavar="PATH",
        default=".",
        help=(
            "Directory (or comma-separated list) to scan recursively for "
            "*.training.json files.  Defaults to the current directory."
        ),
    )
    parser.add_argument(
        "--features",
        dest="features",
        metavar="name1,name2",
        default=None,
        help=(
            "Comma-separated extractor names to run.  Defaults to the enabled "
            "set from FeatureCollectionConfig (metadata on, audio off)."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        metavar="PATH",
        default=None,
        help=(
            "Root directory for the feature cache.  "
            "Defaults to the project cache root (ml/cache/features)."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI.

    Parameters:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 on success, non-zero on error).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Resolve directories
    raw_dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
    dirs = [Path(d) for d in raw_dirs]

    for d in dirs:
        if not d.exists():
            _log.warning("Directory does not exist: %s", d)

    # Resolve extractors
    if args.features is not None:
        names = [n.strip() for n in args.features.split(",") if n.strip()]
        try:
            extractors = resolve_extractors(names)
        except KeyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        extractors = default_extractors()

    # Resolve cache
    cache_root = Path(args.cache_dir) if args.cache_dir else None
    cache = FeatureCache(root=cache_root)

    counts = collect_features(dirs=dirs, extractors=extractors, cache=cache)

    # Report
    print(
        f"Done.\n"
        f"  computed  : {counts.computed}\n"
        f"  cache_hit : {counts.cache_hit}\n"
        f"  skipped   : {counts.skipped}\n"
        f"  errors    : {counts.errors}\n"
        f"  total     : {counts.total_pairs} pairs "
        f"({counts.total_examples} examples × {len(extractors)} extractors)"
    )

    return 0 if counts.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
