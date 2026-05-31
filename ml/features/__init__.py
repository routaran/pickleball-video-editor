"""Feature extractor plugin system for the Pickleball ML pipeline.

This package defines the sole extension point for feature extraction.  New
extractors (audio, visual, metadata, etc.) drop in by implementing the
``FeatureExtractor`` Protocol and returning a ``FeatureRecord``; no other
module needs modification.

Public API
----------
``FeatureRecord``
    Data envelope produced by every extractor.  Carries the extractor identity,
    a JSON-serializable payload, an optional binary artefact path, and a status
    tag for no-op / failed extractors.

``FeatureExtractor``
    ``typing.Protocol`` (``@runtime_checkable``) that all extractor plugins
    must satisfy.  Use ``isinstance(obj, FeatureExtractor)`` at pipeline
    registration time to verify conformance.
"""

from ml.features.base import FeatureExtractor, FeatureRecord


__all__ = ["FeatureRecord", "FeatureExtractor"]
