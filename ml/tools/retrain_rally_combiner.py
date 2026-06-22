"""Human-in-the-loop combiner retraining CLI.

Discovers ``.training.json`` files in one or more directories, checks
combiner-eligibility (4 court corners + cached motion .npz), builds per-window
tables against the frozen audio CNN, and re-fits the logistic combiner on the
pooled corpus.  Honest performance is measured with leave-one-session-out (LOSO)
interval F1 before and after including any new corrections (A/B comparison).

The audio model (``best_model.pt``) is **not** retrained — only the tiny
logistic combiner weights change.

Usage::

    # Dry run — write joint_combiner.candidate.json and print validation JSON
    python -m ml.tools.retrain_rally_combiner --dir ~/Videos/pickleball

    # Apply the candidate to become the live combiner
    python -m ml.tools.retrain_rally_combiner --dir ~/Videos/pickleball --apply

    # Multiple search roots
    python -m ml.tools.retrain_rally_combiner --dir ~/Videos/pickleball --dir /mnt/nas/more

Protocol
--------
* ``--apply`` is absent (generate mode):

  a. Discover ``*.training.json`` under ``--dir``; exclude ``generated_by=="auto_edit"``.
  b. Check each file for eligibility: video file exists, exactly 4 court corners,
     and a cached motion .npz.  Ineligible files are reported in the ``skipped``
     list — never silently dropped.
  c. Build per-window tables (audio CNN inference + visual feature lookup).
  d. LOSO A/B: compare combiner F1 with vs without the new corrections.
  e. Fit candidate combiner on all eligible tables.
  f. Write ``joint_combiner.candidate.json`` and ``joint_combiner.candidate.manifest.json``
     next to the live combiner.
  g. Print exactly one JSON line to stdout; progress to stderr.

* ``--apply``:

  Back up ``joint_combiner.json`` → ``joint_combiner.json.bak``, then move
  the candidate and its manifest into place.

Exit codes: 0 = success, 1 = error (also prints ``{"status":"error",...}`` to stdout).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ml.config import PathConfig
from ml.motion.joint_dataset import build_window_table, motion_cache_path
from ml.motion.joint_fusion import (
    JointCombiner,
    combiner_feature_matrix,
    loso_interval_f1,
)
from ml.motion.visual_features import VISUAL_FEATURE_KEYS

__all__ = ["main"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _candidate_path(combiner_path: Path) -> Path:
    """Candidate combiner path: sibling of the live combiner."""
    return combiner_path.parent / "joint_combiner.candidate.json"


def _candidate_manifest_path(combiner_path: Path) -> Path:
    """Candidate manifest path: sibling of the live combiner."""
    return combiner_path.parent / "joint_combiner.candidate.manifest.json"


def _live_manifest_path(combiner_path: Path) -> Path:
    """Live manifest path: sibling of the live combiner."""
    return combiner_path.parent / "joint_combiner.manifest.json"


def _check_eligibility(jp: Path, data: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(eligible, reason)`` for one training json dict.

    Checks, in order:
    1. Video file exists.
    2. Exactly 4 court corners.
    3. Cached motion .npz present.

    ``generated_by=="auto_edit"`` must be handled by the caller (silent skip).
    """
    video_block = data.get("video") or {}
    video_path = Path(video_block.get("path", ""))
    corners = video_block.get("court_corners") or []

    if not video_path.exists():
        return False, "video missing"
    if len(corners) != 4:
        return False, "missing/!=4 corners"
    npz = motion_cache_path(video_path)
    if not npz.exists():
        return False, "missing motion .npz"
    return True, ""


def _gt_interval_count(data: dict[str, Any]) -> int:
    """Number of non-post-game rallies with a raw/padded timestamp block."""
    count = 0
    for r in data.get("rallies", []):
        if r.get("is_post_game"):
            continue
        ts = r.get("raw") or r.get("padded")
        if ts and ts.get("end_seconds", 0.0) > ts.get("start_seconds", 0.0):
            count += 1
    return count


def _discover_jsons(dirs: list[Path]) -> list[Path]:
    """Glob for ``*.training.json`` under all *dirs*, sorted and deduplicated."""
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        for jp in sorted(d.rglob("*.training.json")):
            if jp not in seen:
                seen.add(jp)
                out.append(jp)
    return out


def _read_manifest_cutoff(manifest_path: Path) -> float | None:
    """Return the ``created_at`` manifest timestamp as a UTC float, or None."""
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        created_at = data.get("created_at")
        if not created_at:
            return None
        dt = datetime.fromisoformat(created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _build_tables(
    eligible_jsons: list[Path],
    model_path: Path | None,
    *,
    stderr=None,
) -> list[dict]:
    """Build per-window tables for all eligible jsons.

    Each returned table has the ``"json"`` key set to the source path string,
    as required by :func:`loso_interval_f1`.  Tables that come back ``None``
    or empty from :func:`build_window_table` are skipped (logged to stderr).
    """
    if stderr is None:
        stderr = sys.stderr
    tables: list[dict] = []
    for jp in eligible_jsons:
        print(f"[build] {jp.name}", file=stderr)
        table = build_window_table(jp, model_path=model_path)
        if table is None or not table["t"].size:
            print(f"[warn]  {jp.name}: table build returned None/empty — skipping", file=stderr)
            continue
        table["json"] = str(jp)
        tables.append(table)
    return tables


def _fit_combiner(tables: list[dict]) -> JointCombiner:
    """Fit a combiner on the pooled feature matrix from *tables*."""
    Xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for t in tables:
        vis = {k: t[k] for k in VISUAL_FEATURE_KEYS}
        Xs.append(combiner_feature_matrix(t["p_audio"], vis, t["valid"]))
        ys.append(np.asarray(t["label"], dtype=np.float64))
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    return JointCombiner.fit(X, y)


# ---------------------------------------------------------------------------
# Generate mode
# ---------------------------------------------------------------------------


def _run_generate(args: argparse.Namespace) -> int:
    combiner_path: Path = args.combiner.resolve()
    model_path: Path = PathConfig().best_model_path
    stderr = sys.stderr

    print(f"[retrain] scanning dirs: {[str(d) for d in args.dir]}", file=stderr)

    # 1. Discover all training jsons
    all_jsons = _discover_jsons(args.dir)
    print(f"[retrain] found {len(all_jsons)} *.training.json files", file=stderr)

    # 2. Eligibility filtering
    skipped: list[dict[str, str]] = []
    eligible_jsons: list[Path] = []

    for jp in all_jsons:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"path": str(jp), "reason": f"malformed json: {exc}"})
            continue

        # Silent exclusion — auto_edit files are never counted as eligible or skipped
        if data.get("generated_by") == "auto_edit":
            continue

        ok, reason = _check_eligibility(jp, data)
        if ok:
            eligible_jsons.append(jp)
        else:
            skipped.append({"path": str(jp), "reason": reason})

    n_eligible = len(eligible_jsons)
    print(
        f"[retrain] eligible: {n_eligible}  skipped: {len(skipped)}",
        file=stderr,
    )
    for sk in skipped:
        print(f"  [skip] {Path(sk['path']).name}: {sk['reason']}", file=stderr)

    if not eligible_jsons:
        msg = "No combiner-eligible videos found (need 4 court corners + motion .npz)."
        print(json.dumps({"status": "error", "message": msg}))
        return 1

    # 3. Build per-window tables (runs the frozen audio CNN)
    print(f"[retrain] building window tables for {n_eligible} videos …", file=stderr)
    tables = _build_tables(eligible_jsons, model_path, stderr=stderr)

    if not tables:
        msg = "All build_window_table calls returned None/empty.  Is the audio model loaded?"
        print(json.dumps({"status": "error", "message": msg}))
        return 1

    print(f"[retrain] built {len(tables)} tables", file=stderr)

    # 4. LOSO A/B validation
    live_manifest_path = _live_manifest_path(combiner_path)
    cutoff_ts = _read_manifest_cutoff(live_manifest_path)

    before_loso_f1: float | None = None
    delta: float | None = None

    if cutoff_ts is not None:
        new_paths = {str(jp) for jp in eligible_jsons if jp.stat().st_mtime > cutoff_ts}
        if new_paths:
            print(
                f"[retrain] manifest found — {len(new_paths)} new correction(s) vs prior run; "
                "computing A/B LOSO …",
                file=stderr,
            )
            tables_old = [t for t in tables if t["json"] not in new_paths]
            print(
                f"[retrain] LOSO before ({len(tables_old)} old tables) …",
                file=stderr,
            )
            before_result = loso_interval_f1(tables_old)
            before_loso_f1 = before_result["f1"]
        else:
            print(
                "[retrain] no new corrections since last manifest — single-number mode",
                file=stderr,
            )
    else:
        print("[retrain] no prior manifest — single-number mode", file=stderr)

    # Always compute "after" on all tables
    print(f"[retrain] LOSO after ({len(tables)} tables) …", file=stderr)
    after_result = loso_interval_f1(tables)
    after_loso_f1 = after_result["f1"]
    if before_loso_f1 is not None:
        delta = round(after_loso_f1 - before_loso_f1, 6)

    print(
        f"[retrain] LOSO  before={before_loso_f1}  after={after_loso_f1:.4f}  "
        f"delta={delta}",
        file=stderr,
    )

    # 5. Fit candidate combiner on ALL eligible tables
    print("[retrain] fitting candidate combiner …", file=stderr)
    candidate = _fit_combiner(tables)

    # Stamp created_at AFTER computation (as specified)
    created_at = datetime.now(timezone.utc).isoformat()

    # 6. Write candidate combiner and manifest
    candidate_path = _candidate_path(combiner_path)
    candidate_manifest_path = _candidate_manifest_path(combiner_path)

    candidate.save(candidate_path)
    print(f"[retrain] wrote candidate combiner → {candidate_path}", file=stderr)

    manifest_data: dict[str, Any] = {
        "created_at": created_at,
        "source_audio_model": str(model_path.resolve()),
        "training_file_count": len(tables),
        "skipped": skipped,
        "validation": {
            "before_loso_f1": before_loso_f1,
            "after_loso_f1": round(after_loso_f1, 6),
            "delta": delta,
        },
    }
    candidate_manifest_path.write_text(
        json.dumps(manifest_data, indent=2), encoding="utf-8"
    )
    print(f"[retrain] wrote candidate manifest → {candidate_manifest_path}", file=stderr)

    # 7. Final JSON to stdout
    result: dict[str, Any] = {
        "status": "ok",
        "eligible": n_eligible,
        "skipped": skipped,
        "before_loso_f1": before_loso_f1,
        "after_loso_f1": round(after_loso_f1, 6),
        "delta": delta,
        "candidate": str(candidate_path.resolve()),
        "manifest": str(candidate_manifest_path.resolve()),
    }
    print(json.dumps(result))
    return 0


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------


def _run_apply(args: argparse.Namespace) -> int:
    combiner_path: Path = args.combiner.resolve()
    candidate_path = _candidate_path(combiner_path)
    candidate_manifest_path = _candidate_manifest_path(combiner_path)
    live_manifest_path = _live_manifest_path(combiner_path)
    bak_path = combiner_path.parent / (combiner_path.name + ".bak")

    if not candidate_path.exists():
        msg = (
            f"Candidate not found at {candidate_path}.  "
            "Run without --apply first to generate a candidate."
        )
        print(json.dumps({"status": "error", "message": msg}))
        return 1

    if not combiner_path.exists():
        msg = f"Live combiner not found at {combiner_path}.  Cannot back it up."
        print(json.dumps({"status": "error", "message": msg}))
        return 1

    # Backup live combiner
    shutil.copy2(str(combiner_path), str(bak_path))

    # Move candidate → live combiner
    candidate_path.rename(combiner_path)

    # Move candidate manifest → live manifest (if it exists)
    if candidate_manifest_path.exists():
        candidate_manifest_path.rename(live_manifest_path)

    result: dict[str, Any] = {
        "status": "applied",
        "backup": str(bak_path.resolve()),
        "combiner": str(combiner_path.resolve()),
        "manifest": str(live_manifest_path.resolve()),
    }
    print(json.dumps(result))
    return 0


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point.  Returns 0 on success, 1 on error."""
    ap = argparse.ArgumentParser(
        prog="retrain_rally_combiner",
        description=(
            "Re-fit the audio+visual rally combiner on corrected training data.  "
            "The audio CNN is frozen; only the logistic combiner is updated."
        ),
    )
    ap.add_argument(
        "--dir",
        type=Path,
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "Directory to search for *.training.json files (repeatable).  "
            "Default: ~/Videos/pickleball"
        ),
    )
    ap.add_argument(
        "--combiner",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to the live joint_combiner.json.  "
            "Default: PathConfig().checkpoints_dir / 'joint_combiner.json'"
        ),
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply the previously generated candidate: back up the live combiner "
            "and swap in the candidate."
        ),
    )

    args = ap.parse_args(argv)

    # Fill in defaults after parsing (avoids import-time side effects)
    if args.dir is None:
        args.dir = [Path.home() / "Videos" / "pickleball"]
    if args.combiner is None:
        args.combiner = PathConfig().checkpoints_dir / "joint_combiner.json"

    try:
        if args.apply:
            return _run_apply(args)
        return _run_generate(args)
    except Exception as exc:  # noqa: BLE001 — top-level error boundary
        msg = f"{type(exc).__name__}: {exc}"
        print(json.dumps({"status": "error", "message": msg}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
