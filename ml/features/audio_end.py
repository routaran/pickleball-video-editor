"""No-op stub for the audio-end feature extractor.

This module satisfies the ``FeatureExtractor`` Protocol with a sentinel
implementation that decodes no audio and imports no heavy dependencies.
Its sole purpose is to hold the public surface steady so that a real
audio extractor can drop in later by replacing only this file's body
(plus declaring whatever audio library it needs).

Design constraints
------------------
* Zero new imports: no librosa, scipy, torchaudio, torch, cv2, decord, or
  numpy — not even under a lazy guard.
* Self-contained: does not import ml.dataset or ml.video_features to avoid
  pulling in their transitive dependencies.
* Protocol-conformant: ``isinstance(AudioEndFeatureExtractor(), FeatureExtractor)``
  is True at runtime.
* Never raises: ``extract`` always returns a ``FeatureRecord``; callers rely on
  the ``status`` field for failure detection.
"""

from __future__ import annotations

from typing import Any

from ml.features.base import FeatureExtractor, FeatureRecord


__all__ = ["AudioEndFeatureExtractor"]

_STUB_NOTE = "audio-end extraction not yet implemented; stub returns skipped"


class AudioEndFeatureExtractor:
    """Protocol-conformant no-op stub for end-of-rally audio features.

    When a real implementation is ready, replace the body of ``extract``
    and add the appropriate audio library to the project dependencies.
    The ``name`` and ``version`` attributes are the only parts of the
    public surface that must remain stable across that swap.

    Attributes:
        name: Stable extractor identifier written into every produced record.
        version: Semver string; bump when cached records must be invalidated.
    """

    name: str = "audio-end"
    version: str = "0.0.0-stub"

    def extract(self, example: Any) -> FeatureRecord:
        """Return a sentinel ``FeatureRecord`` without touching any audio data.

        Parameters:
            example: Accepted for interface compatibility; ignored entirely.

        Returns:
            A ``FeatureRecord`` with ``status="skipped"``, an empty
            ``payload``, and ``artifact_path=None``.  The ``error`` field
            carries a short human-readable note explaining the skip.
        """
        key = str(example) if example is not None else ""
        return FeatureRecord(
            extractor_name=self.name,
            version=self.version,
            key=key,
            payload={},
            artifact_path=None,
            status="skipped",
            error=_STUB_NOTE,
        )


# Sanity-check Protocol conformance at import time so misconfigurations are
# caught early rather than silently at pipeline registration.
assert isinstance(AudioEndFeatureExtractor(), FeatureExtractor), (
    "AudioEndFeatureExtractor does not satisfy the FeatureExtractor Protocol"
)
