"""Feature extractor registry for the ML pipeline.

This module is the single shared seam through which both the batch collection
CLI and any downstream service (e.g. post-export inference) obtain extractor
instances.  New extractors are registered here; callers query by name or ask
for the default enabled set from a ``FeatureCollectionConfig``.

Design notes
------------
* Registry is module-level (a plain dict) rather than a class singleton so
  it is importable without side effects and trivially testable.
* Extractor instances are created lazily at registration time — callers
  receive the same shared instance, which is safe because all Protocol-
  conformant extractors are stateless.
* No CLI specifics live here; the registry is a pure name→extractor mapping.
"""

from __future__ import annotations

from typing import Final

from ml.config import FeatureCollectionConfig
from ml.features.audio_end import AudioEndFeatureExtractor
from ml.features.base import FeatureExtractor
from ml.features.rally_metadata import RallyMetadataExtractor


__all__ = [
    "REGISTRY",
    "resolve_extractors",
    "default_extractors",
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Mapping from stable extractor name to a shared extractor instance.
#: Add new extractors here; the CLI and the post-export service both consume
#: this dict via :func:`resolve_extractors` and :func:`default_extractors`.
REGISTRY: Final[dict[str, FeatureExtractor]] = {
    RallyMetadataExtractor.name: RallyMetadataExtractor(),
    AudioEndFeatureExtractor.name: AudioEndFeatureExtractor(),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def resolve_extractors(names: list[str]) -> list[FeatureExtractor]:
    """Return extractor instances for the given list of names.

    Parameters:
        names: Ordered list of extractor name strings.  Each name must be a
            key in :data:`REGISTRY`.

    Returns:
        Ordered list of extractor instances corresponding to *names*.

    Raises:
        KeyError: If any name in *names* is not present in :data:`REGISTRY`.
            The error message includes the unrecognised name and a list of
            valid names to help callers produce actionable diagnostics.
    """
    result: list[FeatureExtractor] = []
    for name in names:
        if name not in REGISTRY:
            valid = sorted(REGISTRY.keys())
            raise KeyError(
                f"Unknown extractor {name!r}. "
                f"Registered extractors: {valid}"
            )
        result.append(REGISTRY[name])
    return result


def default_extractors(config: FeatureCollectionConfig | None = None) -> list[FeatureExtractor]:
    """Return the default set of enabled extractors from *config*.

    The default set is determined by :class:`~ml.config.FeatureCollectionConfig`
    flags:

    * ``metadata_enabled`` (default ``True``) — includes ``"rally-metadata"``.
    * ``audio_enabled`` (default ``False``) — includes ``"audio-end"`` when
      ``True``.  The audio extractor is a no-op stub that returns
      ``status="skipped"`` records; enabling it pre-populates the cache slot
      so downstream code can distinguish "not yet computed" from "stub".

    Parameters:
        config: Configuration controlling which extractors are active.
            Defaults to a freshly constructed :class:`FeatureCollectionConfig`
            (metadata on, audio off) when ``None``.

    Returns:
        Ordered list of enabled extractor instances.
    """
    if config is None:
        config = FeatureCollectionConfig()

    names: list[str] = []
    if config.metadata_enabled:
        names.append(RallyMetadataExtractor.name)
    if config.audio_enabled:
        names.append(AudioEndFeatureExtractor.name)

    return resolve_extractors(names)
