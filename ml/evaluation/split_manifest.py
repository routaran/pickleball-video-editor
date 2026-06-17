"""Pinned train/val/test split-manifest loading and leakage detection.

Experiments are only comparable over time if the train/val/test partition is
fixed.  The legacy positional split (sort video paths, reserve the last N for
val) silently changes membership whenever videos are added or removed under the
root.  This module replaces that with explicit manifest files grouped at the
safest available unit — a match/event/game — and refuses any partition where a
match appears in more than one split.

This module is torch-free (stdlib + :class:`~pathlib.Path` only).

Manifest schema (v1.0)
----------------------
::

    {
      "schema_version": "1.0",
      "split_name": "winner_approach_a_2026_06",
      "unit": "match",
      "entries": [
        {
          "id": "match_001",
          "video_path": "/absolute/path/to/video.mp4",
          "training_json_path": "/absolute/path/to/game.training.json",
          "notes": "held out for test"
        }
      ]
    }

The grouping key (the "match level") is, in priority order:

1. ``match_id`` when present on the entry,
2. otherwise ``id``,
3. otherwise ``str(video_path)``.

Public API
----------
SplitManifestEntry      -- one parsed manifest entry
SplitManifest           -- a parsed manifest (name, unit, entries)
load_split_manifest     -- parse a single manifest file
detect_split_leakage    -- raise SplitLeakageError if a match spans splits
load_split_manifests    -- parse train/val/test together with leakage detection
SplitManifestError      -- base error for malformed manifests
SplitLeakageError       -- raised when a match appears in multiple splits
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "SplitManifestEntry",
    "SplitManifest",
    "SplitManifestError",
    "SplitLeakageError",
    "load_split_manifest",
    "detect_split_leakage",
    "load_split_manifests",
]


SUPPORTED_SCHEMA_VERSION: str = "1.0"


class SplitManifestError(ValueError):
    """Raised when a split-manifest file is missing or malformed."""


class SplitLeakageError(SplitManifestError):
    """Raised when one match/game appears in more than one split."""


@dataclass(frozen=True)
class SplitManifestEntry:
    """One parsed entry from a split manifest.

    Attributes:
        match_key: Grouping key used for leakage detection.  Resolved from
            ``match_id`` / ``id`` / ``video_path`` (in that order).
        entry_id: The raw ``id`` field (or ``""`` when absent).
        video_path: Absolute path to the source video, as a :class:`Path`.
        training_json_path: Absolute path to the rally label JSON, or ``None``.
        notes: Free-text notes (``""`` when absent).
    """

    match_key: str
    entry_id: str
    video_path: Path
    training_json_path: Path | None
    notes: str


@dataclass(frozen=True)
class SplitManifest:
    """A parsed split manifest.

    Attributes:
        split_name: The manifest's ``split_name`` (``""`` when absent).
        unit: The grouping unit declared in the manifest (e.g. ``"match"``).
        schema_version: The manifest's ``schema_version`` string.
        entries: Parsed :class:`SplitManifestEntry` records in file order.
        source_path: Path the manifest was loaded from.
    """

    split_name: str
    unit: str
    schema_version: str
    entries: tuple[SplitManifestEntry, ...]
    source_path: Path

    @property
    def match_keys(self) -> set[str]:
        """Distinct match-level grouping keys referenced by this manifest."""
        return {entry.match_key for entry in self.entries}

    @property
    def video_paths(self) -> set[Path]:
        """Distinct video paths referenced by this manifest."""
        return {entry.video_path for entry in self.entries}


def _resolve_match_key(entry: dict[str, Any], video_path_str: str) -> str:
    """Return the match-level grouping key for *entry* (LBYL precedence).

    Priority: ``match_id`` -> ``id`` -> the video path string.  Each candidate
    is only used when it is a non-empty string, so a blank ``id`` falls through
    to the video path rather than collapsing every blank-id entry into one
    group.

    Args:
        entry: One raw manifest entry dict.
        video_path_str: The entry's resolved video path string (fallback key).

    Returns:
        A non-empty grouping key string.
    """
    match_id = entry.get("match_id")
    if isinstance(match_id, str) and match_id.strip():
        return match_id.strip()

    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id.strip():
        return entry_id.strip()

    return video_path_str


def load_split_manifest(path: Path) -> SplitManifest:
    """Parse a single split-manifest JSON file.

    Args:
        path: Path to the manifest file.

    Returns:
        A parsed :class:`SplitManifest`.

    Raises:
        SplitManifestError: If the file is missing, is not valid JSON, is not a
            JSON object, lacks an ``entries`` list, or contains an entry without
            a usable ``video_path``.
    """
    if not path.exists():
        raise SplitManifestError(f"Split manifest not found: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SplitManifestError(
            f"Split manifest is not valid JSON: {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SplitManifestError(
            f"Split manifest root must be a JSON object, got "
            f"{type(data).__name__}: {path}"
        )

    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise SplitManifestError(
            f"Split manifest '{path}' must contain an 'entries' list "
            f"(got {type(raw_entries).__name__})."
        )

    split_name = data.get("split_name")
    split_name_str = split_name if isinstance(split_name, str) else ""

    unit = data.get("unit")
    unit_str = unit if isinstance(unit, str) else "match"

    schema_version = data.get("schema_version")
    schema_version_str = (
        schema_version if isinstance(schema_version, str) else SUPPORTED_SCHEMA_VERSION
    )

    entries: list[SplitManifestEntry] = []
    for position, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise SplitManifestError(
                f"Split manifest '{path}' entry #{position} must be a JSON "
                f"object, got {type(raw_entry).__name__}."
            )

        video_path_value = raw_entry.get("video_path")
        if not isinstance(video_path_value, str) or not video_path_value.strip():
            raise SplitManifestError(
                f"Split manifest '{path}' entry #{position} is missing a "
                "non-empty 'video_path'."
            )
        video_path_str = video_path_value.strip()

        training_json_value = raw_entry.get("training_json_path")
        training_json_path: Path | None = None
        if isinstance(training_json_value, str) and training_json_value.strip():
            training_json_path = Path(training_json_value.strip())

        entry_id_value = raw_entry.get("id")
        entry_id = entry_id_value.strip() if isinstance(entry_id_value, str) else ""

        notes_value = raw_entry.get("notes")
        notes = notes_value if isinstance(notes_value, str) else ""

        entries.append(
            SplitManifestEntry(
                match_key=_resolve_match_key(raw_entry, video_path_str),
                entry_id=entry_id,
                video_path=Path(video_path_str),
                training_json_path=training_json_path,
                notes=notes,
            )
        )

    return SplitManifest(
        split_name=split_name_str,
        unit=unit_str,
        schema_version=schema_version_str,
        entries=tuple(entries),
        source_path=path,
    )


def detect_split_leakage(manifests: dict[str, SplitManifest]) -> None:
    """Raise :class:`SplitLeakageError` if a match appears in more than one split.

    Leakage is checked at the match level (``SplitManifestEntry.match_key``),
    which is the safest unit: even if two splits reference the same match via
    different video files, the shared match key flags the overlap.

    Args:
        manifests: Mapping of split name (e.g. ``"train"``) to its parsed
            :class:`SplitManifest`.

    Raises:
        SplitLeakageError: When any match key is present in two or more splits.
            The message lists each offending key and the splits it spans.
    """
    # match_key -> sorted list of split names that contain it.
    key_to_splits: dict[str, list[str]] = {}
    for split_name in sorted(manifests):
        manifest = manifests[split_name]
        for match_key in sorted(manifest.match_keys):
            key_to_splits.setdefault(match_key, []).append(split_name)

    offenders = {
        key: splits for key, splits in key_to_splits.items() if len(splits) > 1
    }
    if offenders:
        details = "; ".join(
            f"{key!r} in {sorted(splits)}" for key, splits in sorted(offenders.items())
        )
        raise SplitLeakageError(
            "Split manifests overlap — the following match(es) appear in more "
            f"than one split: {details}"
        )


def load_split_manifests(
    *,
    train: Path | None = None,
    val: Path | None = None,
    test: Path | None = None,
) -> dict[str, SplitManifest]:
    """Load the provided split manifests and verify no leakage between them.

    Only the splits whose path argument is not ``None`` are loaded, so a caller
    can pin just train/val (leaving test for a separate final-report step).

    Args:
        train: Path to the train manifest, or ``None`` to omit it.
        val: Path to the val manifest, or ``None`` to omit it.
        test: Path to the test manifest, or ``None`` to omit it.

    Returns:
        Mapping of split name to parsed :class:`SplitManifest`, containing only
        the splits that were supplied.  Empty when all three are ``None``.

    Raises:
        SplitManifestError: If any provided manifest is malformed.
        SplitLeakageError: If a match appears in more than one provided split.
    """
    provided: dict[str, Path] = {}
    if train is not None:
        provided["train"] = train
    if val is not None:
        provided["val"] = val
    if test is not None:
        provided["test"] = test

    manifests: dict[str, SplitManifest] = {
        name: load_split_manifest(path) for name, path in provided.items()
    }

    if len(manifests) > 1:
        detect_split_leakage(manifests)

    return manifests
