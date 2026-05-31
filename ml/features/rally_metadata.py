"""Cheap, decode-free metadata feature extractor for rally examples.

Computes all features directly from :class:`~ml.examples.RallyExample` fields
without touching video or audio data.  This makes it the fastest extractor in
the pipeline — suitable for always-on use and as a baseline for ablations.

Design notes
------------
* Zero heavy imports: no torch, cv2, librosa, numpy, or scipy.
* Serving-team derivation follows the same score-string convention used by
  ``_backfill_game`` / ``ScoreState.get_score_string``: the first score part
  is always the *current server's* score and the second is the *receiver's*
  score (perspective-relative, not absolute team index).  The absolute serving
  team (0 or 1) cannot be recovered from a single example's score string
  without replaying the entire game, so we expose the server-relative scores
  rather than a misleading absolute team index.
* ``normalized_rally_index`` is the rally's position within its source file
  expressed as a float in [0.0, 1.0].  Because individual examples don't carry
  total-rally-count, we use the raw ``rally_index`` for the ordinal and emit
  ``rally_index`` separately; callers that need normalisation can divide by the
  dataset length.
* All payload values are JSON-primitive (bool, int, float, str, None).
"""

from __future__ import annotations

from typing import Any

from ml.examples import RallyExample, example_key
from ml.features.base import FeatureExtractor, FeatureRecord


__all__ = ["RallyMetadataExtractor"]


class RallyMetadataExtractor:
    """Metadata feature extractor that requires no video or audio decoding.

    Implements the :class:`~ml.features.base.FeatureExtractor` Protocol.
    Every feature is derived exclusively from :class:`~ml.examples.RallyExample`
    fields (timestamps, score string, labels, path metadata).

    Attributes:
        name: Stable extractor identifier written into every produced record.
        version: Semver string; bump when cached records must be invalidated.

    Payload keys (all JSON-primitive)
    ----------------------------------
    ``duration_s`` : float
        Rally duration in seconds: ``raw_end - raw_start``.
    ``raw_start`` : float
        Rally start timestamp in seconds.
    ``raw_end`` : float
        Rally end timestamp in seconds.
    ``score_at_start`` : str
        Raw score string from the example (e.g. ``"0-0-2"`` or ``"5-3"``).
    ``is_doubles`` : bool
        True when the score string has 3 parts (doubles format).
    ``is_singles`` : bool
        True when the score string has 2 parts (singles format).
    ``server_score`` : int | None
        Score of the serving team at rally start (first score part).
        ``None`` when the score string is absent or malformed.
    ``receiver_score`` : int | None
        Score of the receiving team at rally start (second score part).
        ``None`` when the score string is absent or malformed.
    ``score_margin`` : int | None
        ``server_score - receiver_score``.  Positive means the server leads.
        ``None`` when either score is unavailable.
    ``server_num`` : int | None
        Server number for doubles (1 or 2); ``None`` for singles or
        when unavailable.
    ``winner`` : str
        Raw winner label (``"server"`` or ``"receiver"``).
    ``winning_team`` : int
        Ground-truth team label (0 or 1).
    ``server_wins`` : bool
        True when ``winner == "server"``.
    ``rally_index`` : int
        Zero-based rally position within its source file.
    ``is_post_game`` : bool
        True when the rally is flagged as post-game footage.
    ``score_parts_count`` : int
        Number of hyphen-delimited components in ``score_at_start``
        (0 when the score string is absent, 2 for singles, 3 for doubles).
    ``schema_version`` : str
        Schema version string from the source training file.
    ``generated_by`` : str
        ``generated_by`` field from the source training file.
    """

    name: str = "rally-metadata"
    version: str = "1.0.0"

    def extract(self, example: Any) -> FeatureRecord:
        """Extract cheap metadata features from a :class:`~ml.examples.RallyExample`.

        Parameters:
            example: Expected to be a :class:`~ml.examples.RallyExample`.  If
                it is not, an error record is returned without raising.

        Returns:
            A :class:`~ml.features.base.FeatureRecord` with ``status="ok"``
            on success, or ``status="error"`` if ``example`` is not the
            expected type.
        """
        if not isinstance(example, RallyExample):
            return FeatureRecord(
                extractor_name=self.name,
                version=self.version,
                key="",
                payload={},
                status="error",
                error=(
                    f"RallyMetadataExtractor.extract expected RallyExample, "
                    f"got {type(example).__name__!r}"
                ),
            )

        key = example_key(example)
        payload = _build_payload(example)

        return FeatureRecord(
            extractor_name=self.name,
            version=self.version,
            key=key,
            payload=payload,
            artifact_path=None,
            status="ok",
            error=None,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_payload(example: RallyExample) -> dict[str, Any]:
    """Compute all metadata features from *example* without I/O.

    Args:
        example: A :class:`~ml.examples.RallyExample` to extract features from.

    Returns:
        A flat dictionary whose values are all JSON-primitive.
    """
    duration_s: float = round(example.raw_end - example.raw_start, 6)

    score_parts = example.score_parts
    parts_count: int = len(score_parts)

    is_doubles: bool = parts_count == 3
    is_singles: bool = parts_count == 2

    # Score-string values are server-perspective relative (see module docstring)
    server_score: int | None = score_parts[0] if parts_count >= 2 else None
    receiver_score: int | None = score_parts[1] if parts_count >= 2 else None

    score_margin: int | None = (
        server_score - receiver_score
        if server_score is not None and receiver_score is not None
        else None
    )

    # server_num comes from example directly (already parsed by RallyExample)
    server_num: int | None = example.server_num

    server_wins: bool = example.winner == "server"

    return {
        # Timing
        "duration_s": duration_s,
        "raw_start": round(example.raw_start, 6),
        "raw_end": round(example.raw_end, 6),
        # Score context
        "score_at_start": example.score_at_start,
        "is_doubles": is_doubles,
        "is_singles": is_singles,
        "score_parts_count": parts_count,
        "server_score": server_score,
        "receiver_score": receiver_score,
        "score_margin": score_margin,
        "server_num": server_num,
        # Labels
        "winner": example.winner,
        "winning_team": example.winning_team,
        "server_wins": server_wins,
        # Positional
        "rally_index": example.rally_index,
        "is_post_game": example.is_post_game,
        # Provenance
        "schema_version": example.schema_version,
        "generated_by": example.generated_by,
    }


# Sanity-check Protocol conformance at import time.
assert isinstance(RallyMetadataExtractor(), FeatureExtractor), (
    "RallyMetadataExtractor does not satisfy the FeatureExtractor Protocol"
)
