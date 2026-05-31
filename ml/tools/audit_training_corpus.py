"""Corpus health audit tool for .training.json label files.

Scans a directory tree of ``.training.json`` files and reports statistics
without modifying any file.  Intended both as an importable function and as
a standalone CLI.

Eligibility rules mirror ``ml/winner_dataset.py`` exactly:
- schema_version >= 1.1
- video.court_corners present and non-null
- generated_by != "auto_edit"

Per-rally skip reasons:
- is_post_game: True
- winning_team is None
- raw block is None

Public API
----------
audit_corpus(root_dir) -> CorpusReport
    Main entry point for programmatic use.

CLI usage::

    python -m ml.tools.audit_training_corpus /path/to/labels [--json]
    python -m ml.tools.audit_training_corpus --dir /path/to/labels [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "CorpusReport",
    "audit_corpus",
]


# ---------------------------------------------------------------------------
# Schema version helpers  (self-contained — does not import winner_dataset)
# ---------------------------------------------------------------------------

def _parse_version(version_str: str) -> tuple[int, ...]:
    """Convert a dotted version string like '1.1' to a comparable tuple.

    Only leading numeric components are kept; the first non-numeric component
    terminates parsing.

    Args:
        version_str: Version string in ``MAJOR[.MINOR[.PATCH]]`` format.

    Returns:
        Tuple of integers, e.g. ``(1, 1)``.
    """
    parts = version_str.strip().split(".")
    result: list[int] = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            break
    return tuple(result)


def _is_usable_training_file(data: dict[str, Any]) -> tuple[bool, str]:
    """Check file-level eligibility; return (eligible, reason).

    Eligibility criteria (all must hold):
    - schema_version >= 1.1
    - video.court_corners present and non-null
    - generated_by != "auto_edit"

    Args:
        data: Parsed training JSON dictionary.

    Returns:
        Tuple of (is_eligible, skip_reason).  skip_reason is an empty string
        when is_eligible is True.
    """
    schema_str = data.get("schema_version", "0")
    if _parse_version(schema_str) < (1, 1):
        return False, f"schema_version_too_old({schema_str})"

    video_block = data.get("video", {})
    corners = video_block.get("court_corners")
    if not corners:
        return False, "court_corners_missing"

    if data.get("generated_by") == "auto_edit":
        return False, "generated_by_auto_edit"

    return True, ""


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    """Load and parse a JSON file; return None on any error.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict or None if the file is unreadable or malformed.
    """
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RallySkipTally:
    """Counts of per-rally skip reasons encountered across the corpus.

    Attributes:
        is_post_game: Rallies skipped because ``is_post_game`` is True.
        winning_team_none: Rallies skipped because ``winning_team`` is None.
        raw_missing: Rallies skipped because the ``raw`` block is absent.
    """

    is_post_game: int = 0
    winning_team_none: int = 0
    raw_missing: int = 0

    @property
    def total(self) -> int:
        """Total number of skipped rallies."""
        return self.is_post_game + self.winning_team_none + self.raw_missing

    def to_dict(self) -> dict[str, int]:
        """Serialize to a plain dictionary."""
        return {
            "is_post_game": self.is_post_game,
            "winning_team_none": self.winning_team_none,
            "raw_missing": self.raw_missing,
            "total": self.total,
        }


@dataclass
class FileSkipTally:
    """Counts of file-level skip reasons.

    Attributes:
        schema_too_old: Files whose schema_version < 1.1.
        court_corners_missing: Files without video.court_corners.
        generated_by_auto_edit: Files where generated_by == "auto_edit".
        malformed_json: Files that could not be parsed.
    """

    schema_too_old: int = 0
    court_corners_missing: int = 0
    generated_by_auto_edit: int = 0
    malformed_json: int = 0

    @property
    def total(self) -> int:
        """Total number of skipped files."""
        return (
            self.schema_too_old
            + self.court_corners_missing
            + self.generated_by_auto_edit
            + self.malformed_json
        )

    def to_dict(self) -> dict[str, int]:
        """Serialize to a plain dictionary."""
        return {
            "schema_too_old": self.schema_too_old,
            "court_corners_missing": self.court_corners_missing,
            "generated_by_auto_edit": self.generated_by_auto_edit,
            "malformed_json": self.malformed_json,
            "total": self.total,
        }


@dataclass
class CorpusReport:
    """Full audit result for a directory of .training.json files.

    Attributes:
        root_dir: The directory that was scanned.
        total_files: Number of .training.json files discovered.
        schema_version_counts: Mapping of schema_version string to file count.
        eligible_file_count: Files that passed all file-level eligibility checks.
        file_skip_tally: Breakdown of why ineligible files were skipped.
        eligible_rally_count: Rallies from eligible files that are fully labeled.
        rally_skip_tally: Breakdown of why individual rallies were skipped.
        rallies_by_video: Mapping of video path string to eligible rally count.
        class_balance: Mapping of winning_team value (0 or 1) to rally count.
    """

    root_dir: Path
    total_files: int = 0
    schema_version_counts: dict[str, int] = field(default_factory=dict)
    eligible_file_count: int = 0
    file_skip_tally: FileSkipTally = field(default_factory=FileSkipTally)
    eligible_rally_count: int = 0
    rally_skip_tally: RallySkipTally = field(default_factory=RallySkipTally)
    rallies_by_video: dict[str, int] = field(default_factory=dict)
    class_balance: dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a JSON-serializable dictionary."""
        return {
            "root_dir": str(self.root_dir),
            "total_files": self.total_files,
            "schema_version_counts": self.schema_version_counts,
            "eligible_file_count": self.eligible_file_count,
            "skipped_file_count": self.file_skip_tally.total,
            "file_skip_reasons": self.file_skip_tally.to_dict(),
            "eligible_rally_count": self.eligible_rally_count,
            "skipped_rally_count": self.rally_skip_tally.total,
            "rally_skip_reasons": self.rally_skip_tally.to_dict(),
            "rallies_by_video": self.rallies_by_video,
            "class_balance": {str(k): v for k, v in self.class_balance.items()},
        }


# ---------------------------------------------------------------------------
# Core audit function
# ---------------------------------------------------------------------------

def audit_corpus(root_dir: Path) -> CorpusReport:
    """Scan *root_dir* recursively for .training.json files and return a report.

    The function is read-only: no files are created, modified, or deleted.
    Eligibility rules replicate those in ``ml/winner_dataset.py`` exactly.

    Args:
        root_dir: Directory to search recursively for ``.training.json`` files.

    Returns:
        CorpusReport populated with all audit statistics.
    """
    report = CorpusReport(root_dir=root_dir)

    schema_version_counts: dict[str, int] = defaultdict(int)
    rallies_by_video: dict[str, int] = defaultdict(int)
    class_balance: dict[int, int] = defaultdict(int)

    json_paths = sorted(root_dir.rglob("*.training.json"))
    report.total_files = len(json_paths)

    for json_path in json_paths:
        data = _load_json_safe(json_path)
        if data is None:
            report.file_skip_tally.malformed_json += 1
            schema_version_counts["<malformed>"] += 1
            continue

        schema_str = data.get("schema_version", "0")
        schema_version_counts[schema_str] += 1

        eligible, reason = _is_usable_training_file(data)
        if not eligible:
            if reason.startswith("schema_version_too_old"):
                report.file_skip_tally.schema_too_old += 1
            elif reason == "court_corners_missing":
                report.file_skip_tally.court_corners_missing += 1
            elif reason == "generated_by_auto_edit":
                report.file_skip_tally.generated_by_auto_edit += 1
            continue

        report.eligible_file_count += 1

        video_block = data.get("video", {})
        video_path_str = str(video_block.get("path", "<unknown>"))

        for rally in data.get("rallies", []):
            if rally.get("is_post_game", False):
                report.rally_skip_tally.is_post_game += 1
                continue

            winning_team = rally.get("winning_team")
            if winning_team is None:
                report.rally_skip_tally.winning_team_none += 1
                continue

            raw = rally.get("raw")
            if raw is None:
                report.rally_skip_tally.raw_missing += 1
                continue

            # Rally is fully eligible.
            report.eligible_rally_count += 1
            rallies_by_video[video_path_str] += 1
            class_balance[int(winning_team)] += 1

    report.schema_version_counts = dict(schema_version_counts)
    report.rallies_by_video = dict(rallies_by_video)
    report.class_balance = dict(class_balance)

    return report


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------

def _print_table(report: CorpusReport) -> None:
    """Print a formatted human-readable summary of *report* to stdout."""
    sep = "-" * 60

    print(sep)
    print(f"  Corpus audit: {report.root_dir}")
    print(sep)

    print(f"  Total .training.json files found : {report.total_files}")
    print()

    # Schema version breakdown
    print("  Schema version breakdown:")
    if report.schema_version_counts:
        for version, count in sorted(report.schema_version_counts.items()):
            print(f"    {version:<12}  {count:>5} file(s)")
    else:
        print("    (none)")
    print()

    # File eligibility
    skipped_files = report.file_skip_tally.total
    print(f"  Eligible files  : {report.eligible_file_count}")
    print(f"  Skipped files   : {skipped_files}")
    if skipped_files:
        ft = report.file_skip_tally
        if ft.schema_too_old:
            print(f"    schema_too_old           : {ft.schema_too_old}")
        if ft.court_corners_missing:
            print(f"    court_corners_missing    : {ft.court_corners_missing}")
        if ft.generated_by_auto_edit:
            print(f"    generated_by_auto_edit   : {ft.generated_by_auto_edit}")
        if ft.malformed_json:
            print(f"    malformed_json           : {ft.malformed_json}")
    print()

    # Rally eligibility
    skipped_rallies = report.rally_skip_tally.total
    total_rallies = report.eligible_rally_count + skipped_rallies
    print(f"  Total rallies seen (eligible files): {total_rallies}")
    print(f"  Eligible rallies                   : {report.eligible_rally_count}")
    print(f"  Skipped rallies                    : {skipped_rallies}")
    if skipped_rallies:
        rt = report.rally_skip_tally
        if rt.is_post_game:
            print(f"    is_post_game     : {rt.is_post_game}")
        if rt.winning_team_none:
            print(f"    winning_team_none: {rt.winning_team_none}")
        if rt.raw_missing:
            print(f"    raw_missing      : {rt.raw_missing}")
    print()

    # Class balance
    print("  Class balance (winning_team):")
    if report.class_balance:
        total_labeled = sum(report.class_balance.values())
        for team, count in sorted(report.class_balance.items()):
            pct = 100.0 * count / total_labeled if total_labeled else 0.0
            print(f"    team {team}: {count:>5} ({pct:.1f}%)")
    else:
        print("    (no labeled rallies)")
    print()

    # Per-video counts
    print("  Per-video eligible rally counts:")
    if report.rallies_by_video:
        for video_path, count in sorted(
            report.rallies_by_video.items(),
            key=lambda kv: (-kv[1], kv[0]),
        ):
            print(f"    {count:>4}  {video_path}")
    else:
        print("    (none)")
    print(sep)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_training_corpus",
        description=(
            "Scan a directory of .training.json files and report corpus health "
            "without modifying any file."
        ),
    )
    parser.add_argument(
        "dir",
        nargs="?",
        metavar="DIR",
        help="Directory to scan (positional shorthand for --dir).",
    )
    parser.add_argument(
        "--dir",
        dest="dir_flag",
        metavar="DIR",
        help="Directory to scan (explicit flag alternative).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON to stdout instead of the human table.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:] when None).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve directory: positional arg takes precedence over --dir flag.
    raw_dir: str | None = args.dir or args.dir_flag
    if not raw_dir:
        parser.error("A directory path is required (positional or --dir).")

    root_dir = Path(raw_dir)
    if not root_dir.is_dir():
        parser.error(f"Not a directory: {root_dir}")

    report = audit_corpus(root_dir)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_table(report)


if __name__ == "__main__":
    main(sys.argv[1:])
