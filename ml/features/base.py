"""Base interfaces for the feature extractor plugin system.

Provides ``FeatureRecord`` (the data envelope returned by every extractor) and
``FeatureExtractor`` (the Protocol that all extractor implementations must
satisfy).  New extractors — audio, visual, metadata, etc. — drop in by
implementing the Protocol; no other module needs to change.

Design notes
------------
* ``FeatureExtractor`` is a ``typing.Protocol`` with ``@runtime_checkable``
  so callers can verify conformance via ``isinstance`` at pipeline load time.
  This diverges from the project-wide ABC convention intentionally: the ML
  plan requires isinstance-based extractor registration.
* ``payload`` must remain strictly JSON-serializable (scalars and lists of
  scalars only).  No numpy arrays, torch tensors, or arbitrary objects.
* ``artifact_path`` is reserved for future .npy sidecar files; it is stored
  as a plain string (not Path) to stay JSON-round-trippable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


__all__ = ["FeatureRecord", "FeatureExtractor"]


# ---------------------------------------------------------------------------
# FeatureRecord
# ---------------------------------------------------------------------------


@dataclass
class FeatureRecord:
    """Data envelope produced by one extractor for one example.

    Attributes:
        extractor_name: Stable identifier matching ``FeatureExtractor.name``.
        version: Semantic version string for the extractor that produced this
            record.  Used to detect stale cached records.
        key: Unique key for the example (e.g. a clip hash or file path).
        payload: JSON-serializable mapping of feature names to scalar or list
            values.  Must contain only ``bool``, ``int``, ``float``, ``str``,
            ``None``, or flat ``list``s of those types.
        artifact_path: Optional filesystem path to a companion binary artefact
            (e.g. a .npy file for large feature arrays).  Stored as a plain
            string so JSON round-trips are lossless.
        status: Outcome tag.  Conventionally ``"ok"``, ``"skipped"``, or
            ``"error"``.  Defaults to ``"ok"``.
        error: Human-readable error description when ``status == "error"``;
            ``None`` otherwise.
    """

    extractor_name: str
    version: str
    key: str
    payload: dict[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None
    status: str = "ok"
    error: str | None = None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-round-trippable dictionary."""
        return {
            "extractor_name": self.extractor_name,
            "version": self.version,
            "key": self.key,
            "payload": self.payload,
            "artifact_path": self.artifact_path,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureRecord":
        """Deserialize from a dictionary produced by ``to_dict``."""
        return cls(
            extractor_name=data["extractor_name"],
            version=data["version"],
            key=data["key"],
            payload=data.get("payload", {}),
            artifact_path=data.get("artifact_path"),
            status=data.get("status", "ok"),
            error=data.get("error"),
        )

    def is_json_serializable(self) -> bool:
        """Return True if this record can be losslessly round-tripped through JSON."""
        try:
            json.dumps(self.to_dict())
            return True
        except (TypeError, ValueError):
            return False


# ---------------------------------------------------------------------------
# FeatureExtractor Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class FeatureExtractor(Protocol):
    """Protocol that all feature extractor plugins must satisfy.

    Implementations may be class instances, dataclasses, or any object that
    exposes ``name``, ``version``, and ``extract``.  The ``@runtime_checkable``
    decorator enables ``isinstance(obj, FeatureExtractor)`` checks at pipeline
    registration time.

    Attributes:
        name: Stable, unique identifier for this extractor.  Should be a
            lowercase slug (e.g. ``"metadata_v1"``).  Must match the
            ``extractor_name`` written into every produced ``FeatureRecord``.
        version: Semantic version string (e.g. ``"1.0.0"``).  Bump on any
            change that would invalidate previously cached records.

    Methods:
        extract(example): Produce a ``FeatureRecord`` for the given example.
            The ``example`` type is intentionally untyped here; concrete
            extractors should narrow it in their own signatures.  The method
            must never raise — callers rely on the returned ``status`` field
            to detect failures.
    """

    name: str
    version: str

    def extract(self, example: Any) -> FeatureRecord:
        """Extract features from ``example`` and return a ``FeatureRecord``.

        Parameters:
            example: The input to process.  The concrete type depends on the
                extractor (e.g. a dict of clip metadata, a Path to an audio
                file, a numpy array of frames).

        Returns:
            A ``FeatureRecord`` with ``status="ok"`` on success,
            ``status="error"`` if extraction failed (with ``error`` populated),
            or ``status="skipped"`` for intentional no-ops.
        """
        ...
