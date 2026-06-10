"""Neutral data layer for schema-1.1 rally examples.

Provides :class:`RallyExample`, a frozen dataclass that represents one rally
from a ``.training.json`` label file without imposing any ML framework
dependency (no torch, cv2, or numpy required).

This module is intentionally restricted to pure data + light parsing. Directory
scanning, index building, and cache-key logic are separate units that will be
appended or imported here by other agents.

Schema-1.1 layout (abbreviated)
---------------------------------
{
  "schema_version": "1.1",
  "generated_by": "manual",
  "video": {
    "path": "/absolute/path/to/video.mp4",
    "court_corners": [[x, y], [x, y], [x, y], [x, y]]
  },
  "rallies": [
    {
      "index": 0,
      "score_at_start": "0-0-2",   # doubles: "T1-T2-Server#"; singles: "T1-T2"
      "winner": "receiver",         # "server" | "receiver"
      "winning_team": 1,            # 0 or 1
      "is_post_game": false,
      "comment": null,
      "raw": {
        "start_seconds": 44.55,
        "end_seconds": 54.3
      }
    }
  ]
}
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["RallyExample", "RallyExampleIndex", "example_key"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RallyExample
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RallyExample:
    """Immutable representation of one rally from a schema-1.1 training file.

    All fields are derived directly from the JSON without ML-framework types.
    Downstream consumers (index, baselines, metadata extractor) read these
    fields; they do not modify them.

    Attributes:
        source_json_path: Absolute path to the ``.training.json`` file.
        video_path: Absolute path to the source video (from ``video.path``).
        rally_index: Zero-based position of this rally within the file.
        raw_start: Rally start timestamp in seconds (``raw.start_seconds``).
        raw_end: Rally end timestamp in seconds (``raw.end_seconds``).
        score_at_start: Score string at rally start, e.g. ``"0-0-2"`` (doubles)
            or ``"5-3"`` (singles).  Parsed into parts via :attr:`score_parts`.
        score_parts: Tuple of integer score components split from
            ``score_at_start``.  Doubles: ``(team1, team2, server_num)``.
            Singles: ``(server, receiver)``.
        server_num: For doubles, the current server number (1 or 2) derived
            from the third score part; ``None`` for singles.
        winner: Raw ``"server"`` or ``"receiver"`` string from the JSON.
        winning_team: Ground-truth integer label (0 or 1).
        court_corners: Four ``(x, y)`` pixel coordinates from ``video.court_corners``,
            stored as a tuple of tuples for hashability.
        schema_version: ``schema_version`` string from the file root.
        generated_by: ``generated_by`` string from the file root.
        is_post_game: Whether the rally is flagged as post-game.
    """

    source_json_path: Path
    video_path: Path
    rally_index: int
    raw_start: float
    raw_end: float
    score_at_start: str
    score_parts: tuple[int, ...]
    server_num: int | None
    winner: str
    winning_team: int
    court_corners: tuple[tuple[int, int], ...]
    schema_version: str
    generated_by: str
    is_post_game: bool
    serving_team: int | None = None
    """Absolute serving team index at rally start (0 or 1).

    Populated from ``score_snapshot_at_start.serving_team`` in the rally dict
    when that snapshot is present.  ``None`` for legacy files written before
    the snapshot block was added to the schema.

    Score strings like ``"5-3-2"`` are always perspective-relative
    (serving_score-receiving_score-server_num), so this field is required to
    convert ``score_parts`` into absolute team-indexed scores.
    """

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    @classmethod
    def from_rally_dict(
        cls,
        *,
        source_json_path: Path,
        video_path: Path,
        court_corners: tuple[tuple[int, int], ...],
        schema_version: str,
        generated_by: str,
        rally_dict: dict[str, Any],
    ) -> "RallyExample":
        """Construct a :class:`RallyExample` from file-level metadata and a rally dict.

        Performs light validation and coercion; does not raise — logs a warning
        and uses safe defaults for optional/nullable fields so callers can always
        obtain a usable object for well-formed data.

        Args:
            source_json_path: Path to the originating ``.training.json`` file.
            video_path: Resolved path to the video (from ``video.path``).
            court_corners: Pre-parsed court corners from ``video.court_corners``.
            schema_version: Top-level ``schema_version`` from the file.
            generated_by: Top-level ``generated_by`` from the file.
            rally_dict: One element from the ``rallies`` list.

        Returns:
            A frozen :class:`RallyExample` instance.
        """
        # -- raw timestamps --------------------------------------------------
        raw_block: dict[str, Any] = rally_dict.get("raw") or {}
        raw_start = float(raw_block.get("start_seconds", 0.0))
        raw_end = float(raw_block.get("end_seconds", 0.0))

        # -- score -----------------------------------------------------------
        score_at_start: str = rally_dict.get("score_at_start") or ""
        score_parts, server_num = _parse_score(score_at_start, source_json_path)

        # -- label fields ----------------------------------------------------
        winner: str = rally_dict.get("winner") or ""
        winning_team: int = int(rally_dict.get("winning_team") or 0)
        is_post_game: bool = bool(rally_dict.get("is_post_game", False))
        rally_index: int = int(rally_dict.get("index", 0))

        # -- serving_team from score snapshot --------------------------------
        # score_snapshot_at_start is a dict with keys: score, serving_team,
        # server_number, first_server_player_index.  It is only present in
        # files written after the snapshot block was added to the schema.
        snap = rally_dict.get("score_snapshot_at_start")
        serving_team: int | None = snap.get("serving_team") if isinstance(snap, dict) else None

        return cls(
            source_json_path=source_json_path,
            video_path=video_path,
            rally_index=rally_index,
            raw_start=raw_start,
            raw_end=raw_end,
            score_at_start=score_at_start,
            score_parts=score_parts,
            server_num=server_num,
            winner=winner,
            winning_team=winning_team,
            court_corners=court_corners,
            schema_version=schema_version,
            generated_by=generated_by,
            is_post_game=is_post_game,
            serving_team=serving_team,
        )

    @classmethod
    def from_json_file(cls, json_path: Path, rally_index: int) -> "RallyExample":
        """Convenience constructor: load one rally by index from a JSON file.

        Args:
            json_path: Path to a ``.training.json`` file.
            rally_index: Zero-based index of the rally to load.

        Returns:
            A frozen :class:`RallyExample` for the requested rally.

        Raises:
            FileNotFoundError: If *json_path* does not exist.
            KeyError: If *rally_index* is out of range.
            ValueError: If the file cannot be parsed as JSON.
        """
        if not json_path.exists():
            raise FileNotFoundError(json_path)

        with json_path.open(encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        schema_version: str = str(data.get("schema_version", ""))
        generated_by: str = str(data.get("generated_by", ""))

        video_block: dict[str, Any] = data.get("video") or {}
        video_path = Path(video_block.get("path", ""))

        raw_corners: list[list[int]] = video_block.get("court_corners") or []
        court_corners: tuple[tuple[int, int], ...] = tuple(
            (int(c[0]), int(c[1])) for c in raw_corners
        )

        rallies: list[dict[str, Any]] = data.get("rallies") or []
        if rally_index >= len(rallies):
            raise KeyError(
                f"rally_index {rally_index} out of range "
                f"(file has {len(rallies)} rallies): {json_path}"
            )

        return cls.from_rally_dict(
            source_json_path=json_path,
            video_path=video_path,
            court_corners=court_corners,
            schema_version=schema_version,
            generated_by=generated_by,
            rally_dict=rallies[rally_index],
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_score(
    score_at_start: str,
    source_path: Path,
) -> tuple[tuple[int, ...], int | None]:
    """Split a score string into integer parts and extract the server number.

    Doubles scores have three parts (``T1-T2-ServerNum``); singles have two
    (``T1-T2``).  Any other format logs a warning and returns empty parts.

    Args:
        score_at_start: Score string, e.g. ``"0-0-2"`` or ``"5-3"``.
        source_path: Used only for warning messages.

    Returns:
        A 2-tuple of:
        - ``score_parts``: integer tuple of all score components.
        - ``server_num``: third component as int (doubles) or ``None`` (singles).
    """
    if not score_at_start:
        return (), None

    raw_parts = score_at_start.strip().split("-")

    parsed: list[int] = []
    for part in raw_parts:
        if part.isdigit():
            parsed.append(int(part))
        else:
            logger.warning(
                "Non-numeric score component %r in %r from %s",
                part,
                score_at_start,
                source_path,
            )
            return (), None

    score_parts: tuple[int, ...] = tuple(parsed)

    if len(parsed) == 3:
        # Doubles: (serving_score, receiving_score, server_number)
        server_num: int | None = parsed[2]
    elif len(parsed) == 2:
        # Singles: (server_score, receiver_score)
        server_num = None
    else:
        logger.warning(
            "Unexpected score format %r in %s (expected 2 or 3 parts)",
            score_at_start,
            source_path,
        )
        return score_parts, None

    return score_parts, server_num


# ---------------------------------------------------------------------------
# Schema / eligibility helpers (mirrors winner_dataset._parse_version and
# winner_dataset._is_usable_training_file exactly so the index and the
# dataset agree on which files / rallies are eligible)
# ---------------------------------------------------------------------------

def _index_parse_version(version_str: str) -> tuple[int, ...]:
    """Convert a dotted version string to a comparable tuple of ints.

    Args:
        version_str: e.g. ``"1.1"`` or ``"2.0.1"``.

    Returns:
        Tuple of integers up to the first non-numeric component, e.g. ``(1, 1)``.
    """
    parts = version_str.strip().split(".")
    result: list[int] = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            break
    return tuple(result)


def _index_is_usable_file(data: dict[str, Any]) -> bool:
    """Return True when a training JSON satisfies all file-level eligibility criteria.

    Mirrors ``winner_dataset._is_usable_training_file`` exactly:

    - ``schema_version >= 1.1``
    - ``video.court_corners`` present and non-null
    - ``generated_by != "auto_edit"``

    Args:
        data: Parsed training JSON root dictionary.

    Returns:
        ``True`` if the file should be included; ``False`` otherwise.
    """
    schema_str = data.get("schema_version", "0")
    if _index_parse_version(schema_str) < (1, 1):
        return False

    video_block = data.get("video", {})
    corners = video_block.get("court_corners")
    if not corners:
        return False

    if data.get("generated_by") == "auto_edit":
        return False

    return True


def _index_is_usable_rally(rally: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(eligible, skip_reason)`` for a single rally dict.

    Mirrors the per-rally eligibility loop in ``WinnerDataset.__init__``:

    - Skips ``is_post_game == True``
    - Skips ``winning_team is None``
    - Skips ``raw is None``

    Args:
        rally: One element from the ``"rallies"`` list.

    Returns:
        A 2-tuple of:
        - ``eligible``: ``True`` if the rally passes all checks.
        - ``skip_reason``: Non-empty string describing the first failure;
          empty string when eligible.
    """
    if rally.get("is_post_game", False):
        return False, "post_game"
    if rally.get("winning_team") is None:
        return False, "winning_team_none"
    raw = rally.get("raw")
    if raw is None:
        return False, "raw_none"
    if raw.get("start_seconds") is None:
        return False, "raw_start_none"
    if raw.get("end_seconds") is None:
        return False, "raw_end_none"
    return True, ""


# ---------------------------------------------------------------------------
# RallyExampleIndex
# ---------------------------------------------------------------------------

class RallyExampleIndex:
    """Directory index of schema-1.1 ``.training.json`` files.

    Scans one or more directories (or explicit file lists) for
    ``.training.json`` files, applies the same eligibility filters used by
    ``WinnerDataset``, and exposes:

    - :attr:`examples` — eligible :class:`RallyExample` records in
      deterministic order (sorted by source path, then rally index).
    - :attr:`skip_counts` — ``{reason: count}`` tally of skipped rallies and
      files.  File-level skips use reason strings prefixed with ``"file:"``
      (e.g. ``"file:schema_too_old"``, ``"file:no_court_corners"``,
      ``"file:auto_edit"``, ``"file:json_error"``, ``"file:not_found"``).
      Rally-level skips use plain reason strings from :func:`_index_is_usable_rally`.
    - :attr:`video_paths` — ``set[Path]`` of distinct video paths referenced
      by eligible examples.

    Callers can provide an *extra_file_filter* callable to impose additional
    eligibility constraints at the file level, and an *extra_rally_filter*
    callable at the rally level.  Both default to ``None`` (no extra filtering).

    Args:
        dirs: A single :class:`~pathlib.Path` or a list of paths.  Each path
            is searched **recursively** for ``*.training.json`` files.
        files: Explicit list of ``.training.json`` paths to include.  Combined
            with files found under *dirs*.
        extra_file_filter: Optional ``(data: dict) -> (bool, str)`` callable.
            Return ``(True, "")`` to accept or ``(False, reason)`` to reject.
        extra_rally_filter: Optional ``(rally_dict: dict) -> (bool, str)``
            callable with the same contract.

    Example::

        index = RallyExampleIndex(dirs=Path("~/Videos/pickleball").expanduser())
        print(len(index.examples), "eligible rallies")
        print(index.skip_counts)
        print(index.video_paths)
    """

    def __init__(
        self,
        dirs: Path | list[Path] | None = None,
        *,
        files: list[Path] | None = None,
        extra_file_filter: Any | None = None,
        extra_rally_filter: Any | None = None,
    ) -> None:
        # Normalise dirs argument
        if dirs is None:
            dir_list: list[Path] = []
        elif isinstance(dirs, Path):
            dir_list = [dirs]
        else:
            dir_list = list(dirs)

        # Collect candidate paths: recursive glob + explicit files list
        candidate_paths: list[Path] = []
        for d in dir_list:
            if d.exists():
                candidate_paths.extend(sorted(d.rglob("*.training.json")))
            else:
                logger.warning("RallyExampleIndex: directory not found: %s", d)

        if files:
            candidate_paths.extend(files)

        # Deduplicate while preserving order (sort for determinism)
        seen: set[Path] = set()
        unique_paths: list[Path] = []
        for p in sorted(candidate_paths):
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)

        skip_counter: Counter[str] = Counter()
        eligible: list[RallyExample] = []

        for json_path in unique_paths:
            if not json_path.exists():
                skip_counter["file:not_found"] += 1
                logger.warning("RallyExampleIndex: file not found: %s", json_path)
                continue

            # Parse JSON
            data = _index_load_json_safe(json_path, skip_counter)
            if data is None:
                continue

            # File-level eligibility
            file_skip_reason = _check_file_eligibility(
                data, extra_file_filter, skip_counter
            )
            if file_skip_reason:
                continue

            # Extract shared file-level fields
            schema_version: str = str(data.get("schema_version", ""))
            generated_by: str = str(data.get("generated_by", ""))
            video_block: dict[str, Any] = data.get("video") or {}
            video_path = Path(video_block.get("path", ""))
            raw_corners: list[list[int]] = video_block.get("court_corners") or []
            court_corners: tuple[tuple[int, int], ...] = tuple(
                (int(c[0]), int(c[1])) for c in raw_corners
            )

            rallies: list[dict[str, Any]] = data.get("rallies") or []
            for rally_dict in rallies:
                ok, reason = _index_is_usable_rally(rally_dict)
                if not ok:
                    skip_counter[reason] += 1
                    continue

                # Optional caller-supplied rally filter
                if extra_rally_filter is not None:
                    ok2, reason2 = extra_rally_filter(rally_dict)
                    if not ok2:
                        skip_counter[reason2 or "extra_rally_filter"] += 1
                        continue

                example = RallyExample.from_rally_dict(
                    source_json_path=json_path,
                    video_path=video_path,
                    court_corners=court_corners,
                    schema_version=schema_version,
                    generated_by=generated_by,
                    rally_dict=rally_dict,
                )
                eligible.append(example)

        self._examples: list[RallyExample] = eligible
        self._skip_counts: dict[str, int] = dict(skip_counter)
        self._video_paths: set[Path] = {ex.video_path for ex in eligible}

        logger.info(
            "RallyExampleIndex: %d eligible rallies from %d candidate file(s); "
            "skip_counts=%s",
            len(self._examples),
            len(unique_paths),
            self._skip_counts,
        )

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def examples(self) -> list[RallyExample]:
        """Eligible :class:`RallyExample` records in deterministic order."""
        return self._examples

    @property
    def skip_counts(self) -> dict[str, int]:
        """Mapping of skip reason to count of skipped items."""
        return dict(self._skip_counts)

    @property
    def video_paths(self) -> set[Path]:
        """Set of distinct video :class:`~pathlib.Path` values from eligible examples."""
        return set(self._video_paths)

    def __len__(self) -> int:
        return len(self._examples)

    def __repr__(self) -> str:
        return (
            f"RallyExampleIndex("
            f"eligible={len(self._examples)}, "
            f"videos={len(self._video_paths)}, "
            f"skip_counts={self._skip_counts!r})"
        )


# ---------------------------------------------------------------------------
# RallyExampleIndex internal helpers
# ---------------------------------------------------------------------------

def _index_load_json_safe(
    path: Path,
    skip_counter: Counter[str],
) -> dict[str, Any] | None:
    """Load a JSON file, recording ``"file:json_error"`` on failure.

    Args:
        path: Path to a JSON file (already verified to exist).
        skip_counter: Mutable counter incremented on error.

    Returns:
        Parsed dictionary or ``None`` on decode error.
    """
    with path.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning("RallyExampleIndex: malformed JSON in %s: %s", path, exc)
            skip_counter["file:json_error"] += 1
            return None


def _check_file_eligibility(
    data: dict[str, Any],
    extra_file_filter: Any | None,
    skip_counter: Counter[str],
) -> str:
    """Apply file-level eligibility and return the first skip reason, or ``""``.

    Checks are applied in order:
    1. Built-in ``_index_is_usable_file`` (schema version, court corners, generated_by).
    2. Optional *extra_file_filter* callable.

    Args:
        data: Parsed training JSON root.
        extra_file_filter: Optional ``(data) -> (bool, str)`` callable.
        skip_counter: Mutable counter; incremented on rejection.

    Returns:
        The skip reason string if rejected, otherwise ``""``.
    """
    if not _index_is_usable_file(data):
        # Determine the specific file-level reason
        schema_str = data.get("schema_version", "0")
        if _index_parse_version(schema_str) < (1, 1):
            reason = "file:schema_too_old"
        elif data.get("generated_by") == "auto_edit":
            reason = "file:auto_edit"
        else:
            reason = "file:no_court_corners"
        skip_counter[reason] += 1
        return reason

    if extra_file_filter is not None:
        ok, reason = extra_file_filter(data)
        if not ok:
            skip_counter[reason or "file:extra_filter"] += 1
            return reason or "file:extra_filter"

    return ""


# ---------------------------------------------------------------------------
# example_key
# ---------------------------------------------------------------------------

def example_key(example: RallyExample, config: Any | None = None) -> str:
    """Return a stable, deterministic hex key for a :class:`RallyExample`.

    The key is a 16-character hex prefix of a SHA-256 digest computed over
    a canonical JSON-serialised record of the inputs listed below.  It is
    stable across Python invocations and changes when **any** of the following
    inputs change:

    **Always included:**

    - ``video_path`` — absolute path string of the source video.
    - ``raw_start`` — rally start timestamp in seconds (rounded to 6 d.p.).
    - ``raw_end`` — rally end timestamp in seconds (rounded to 6 d.p.).
    - ``rally_index`` — zero-based rally position within the source file.
    - ``court_corners`` — list of ``[x, y]`` integer pairs.

    **Included when** *config* **is a** :class:`~ml.config.WinnerModelConfig`:

    - ``clip_duration_s`` — ``config.effective_clip_duration_s`` (respects
      ``clip_duration_override_s``).
    - ``fps_out`` — ``config.fps_out``.

    When *config* is ``None`` the clip parameters are omitted from the hash
    so the key is pure-data.  Passing any other type for *config* logs a
    warning and behaves as ``None``.

    Args:
        example: The :class:`RallyExample` to key.
        config: Optional :class:`~ml.config.WinnerModelConfig`.  When provided,
            ``effective_clip_duration_s`` and ``fps_out`` are folded into the
            hash.

    Returns:
        A 16-character lowercase hex string (first 8 bytes of SHA-256).
    """
    payload: dict[str, Any] = {
        "video_path": str(example.video_path),
        "raw_start": round(example.raw_start, 6),
        "raw_end": round(example.raw_end, 6),
        "rally_index": example.rally_index,
        "court_corners": [[c[0], c[1]] for c in example.court_corners],
    }

    if config is not None:
        # Import is deferred so this module stays torch-free at import time.
        # We detect WinnerModelConfig by attribute presence (duck-typing) to
        # avoid a hard import of ml.config which may trigger torch imports in
        # some environments.
        clip_dur = getattr(config, "effective_clip_duration_s", None)
        fps_out = getattr(config, "fps_out", None)
        if clip_dur is not None and fps_out is not None:
            payload["clip_duration_s"] = round(float(clip_dur), 6)
            payload["fps_out"] = int(fps_out)
        else:
            logger.warning(
                "example_key: config type %r does not expose expected "
                "WinnerModelConfig attributes; clip parameters omitted from hash.",
                type(config).__name__,
            )

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]
