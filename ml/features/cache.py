"""Key-addressed feature cache for the ML feature extraction pipeline.

Materializes ``FeatureRecord`` objects as JSON sidecar files on disk under::

    <cache_dir> / "features" / <extractor_name> / <key>.json

Array-heavy payloads that require a companion binary artefact are stored as
``.npy`` files alongside the JSON sidecar; the ``artifact_path`` field of the
stored record points to that companion file.

Design notes
------------
* Corrupt-safe: any I/O error, JSON decode error, or missing required field
  during ``get`` yields ``None`` rather than raising.
* Version-aware: when ``expected_version`` is supplied to ``get``, a stored
  record whose ``version`` field does not match is treated as a miss so that
  stale cached records are transparently invalidated.
* Torch-free: numpy is the only non-stdlib binary dependency.
* The cache directory is injectable via the constructor so that tests can
  supply a temporary directory without mutating global state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ml.config import FeatureCollectionConfig, PathConfig
from ml.features.base import FeatureRecord


__all__ = ["FeatureCache"]

_log = logging.getLogger(__name__)


def _default_cache_root() -> Path:
    """Return the default feature cache root from project configuration."""
    paths = PathConfig()
    collection = FeatureCollectionConfig()
    return paths.cache_dir / collection.features_subdir


class FeatureCache:
    """Key-addressed on-disk cache for ``FeatureRecord`` sidecars.

    On-disk layout::

        <root>/
            <extractor_name>/
                <key>.json          # serialized FeatureRecord
                <key>.npy           # companion binary artefact (optional)

    Parameters:
        root: Root directory for the feature cache.  Defaults to
            ``PathConfig().cache_dir / FeatureCollectionConfig().features_subdir``.
            Tests should supply ``tmp_path / "features"`` (or similar) to
            avoid touching the real project cache.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path = root if root is not None else _default_cache_root()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        extractor_name: str,
        key: str,
        expected_version: str | None = None,
    ) -> FeatureRecord | None:
        """Return the cached ``FeatureRecord`` for the given extractor and key.

        Returns ``None`` on any of the following conditions:

        * The sidecar JSON file does not exist (cache miss).
        * The file is unreadable or contains malformed JSON (corrupt entry).
        * A required field is absent from the stored data (corrupt entry).
        * ``expected_version`` is given and does not match the stored version
          (stale entry — treated as a miss so the caller will re-extract).

        Parameters:
            extractor_name: Stable extractor identifier (used as subdirectory).
            key: Unique example key (used as filename stem).
            expected_version: When not ``None``, the stored record's ``version``
                must equal this value; otherwise the record is considered stale.

        Returns:
            The deserialized ``FeatureRecord``, or ``None`` on any miss/error.
        """
        sidecar = self._sidecar_path(extractor_name, key)
        if not sidecar.exists():
            return None

        raw: dict[str, Any]
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.debug("FeatureCache: corrupt sidecar %s — %s", sidecar, exc)
            return None

        if not isinstance(raw, dict):
            _log.debug("FeatureCache: sidecar %s is not a JSON object", sidecar)
            return None

        # Required fields check before constructing the record.
        for required in ("extractor_name", "version", "key"):
            if required not in raw:
                _log.debug(
                    "FeatureCache: sidecar %s missing required field %r",
                    sidecar,
                    required,
                )
                return None

        if expected_version is not None and raw["version"] != expected_version:
            _log.debug(
                "FeatureCache: stale record for %s/%s (stored=%r, expected=%r)",
                extractor_name,
                key,
                raw["version"],
                expected_version,
            )
            return None

        try:
            record = FeatureRecord.from_dict(raw)
        except (KeyError, TypeError, ValueError) as exc:
            _log.debug(
                "FeatureCache: could not deserialize %s — %s", sidecar, exc
            )
            return None

        return record

    def put(self, record: FeatureRecord) -> None:
        """Write ``record`` to its sidecar file, creating directories as needed.

        Parameters:
            record: The ``FeatureRecord`` to persist.  The ``extractor_name``
                and ``key`` fields determine the on-disk location.
        """
        sidecar = self._sidecar_path(record.extractor_name, record.key)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sidecar_path(self, extractor_name: str, key: str) -> Path:
        """Return the canonical sidecar path for the given extractor and key."""
        return self._root / extractor_name / f"{key}.json"
