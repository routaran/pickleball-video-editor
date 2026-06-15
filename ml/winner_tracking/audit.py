"""Run the detect→track→feature pipeline over a set of rallies and cache results.

Writes one JSON object per rally to a JSONL file (incremental, resumable): the
geometric features + quality fields + the winner label + grouping keys, which the
evaluator then consumes.  Frames are never cached (too large); only the tiny
feature rows are persisted, so re-running the evaluator is instant.
"""

import argparse
import json
import logging
import time
from pathlib import Path

from ml.winner_tracking.clip_io import extract_raw_frames
from ml.winner_tracking.corpus import (
    RallyRecord,
    load_rally_records,
    stratified_dev_sample,
)
from ml.winner_tracking.detect import detect_candidates
from ml.winner_tracking.features import geometric_features
from ml.winner_tracking.track import track_candidates

logger = logging.getLogger("winner_audit")

_DEFAULT_OUT = Path(__file__).parent / "cache" / "dev_features.jsonl"


def _load_done_keys(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    keys: set[str] = set()
    for line in out_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        keys.add(json.loads(line)["key"])
    return keys


def process_rally(
    rec: RallyRecord, pre_s: float, post_s: float, fps: int, person=None
) -> dict[str, object]:
    frames, _ = extract_raw_frames(
        rec.video_path, rec.end_s - pre_s, rec.end_s + post_s, fps, rec.native_size
    )
    person_boxes = person.boxes_per_frame(frames) if person is not None else None
    cands = detect_candidates(frames, rec.corners, person_boxes=person_boxes)
    tracks = track_candidates(cands)
    feats, qual = geometric_features(tracks, rec.corners)
    row: dict[str, object] = {
        "key": rec.key,
        "video": rec.video_name,
        "date_group": rec.date_group,
        "winning_team": rec.winning_team,
        "winner_role": rec.winner_role,
        "duration_s": round(rec.duration_s, 2),
        "n_frames": int(len(frames)),
    }
    row.update({f"f_{k}": round(v, 5) for k, v in feats.items()})
    row.update({f"q_{k}": round(v, 5) for k, v in qual.items()})
    return row


def run_audit(
    records: list[RallyRecord],
    out_path: Path = _DEFAULT_OUT,
    pre_s: float = 2.5,
    post_s: float = 1.0,
    fps: int = 60,
    use_person: bool = False,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    person = None
    if use_person:
        from ml.winner_tracking.person import PersonDetector
        person = PersonDetector()
        logger.info("Person detector enabled (%s)", person.device)
    done = _load_done_keys(out_path)
    todo = [r for r in records if r.key not in done]
    logger.info("Audit: %d rallies (%d already cached, %d to do)",
                len(records), len(done), len(todo))
    t_start = time.time()
    with out_path.open("a") as fh:
        for i, rec in enumerate(todo):
            t0 = time.time()
            try:
                row = process_rally(rec, pre_s, post_s, fps, person)
            except Exception as exc:  # noqa: BLE001 — one bad clip must not abort the run
                logger.warning("FAILED %s: %s", rec.key, exc)
                row = {"key": rec.key, "video": rec.video_name,
                       "date_group": rec.date_group, "winning_team": rec.winning_team,
                       "error": str(exc)}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if (i + 1) % 10 == 0 or i == 0:
                rate = (time.time() - t_start) / (i + 1)
                logger.info("  [%d/%d] %s  %.1fs/clip  eta=%.0fmin",
                            i + 1, len(todo), rec.key, time.time() - t0,
                            rate * (len(todo) - i - 1) / 60)
    logger.info("Audit complete -> %s (%.1f min)", out_path, (time.time() - t_start) / 60)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run winner-tracking feature audit")
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--target", type=int, default=200, help="dev-sample size (0 = full corpus)")
    ap.add_argument("--pre", type=float, default=2.5)
    ap.add_argument("--post", type=float, default=1.0)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--person", action="store_true", help="enable player suppression")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    records = load_rally_records()
    if args.target > 0:
        records = stratified_dev_sample(records, target=args.target)
    run_audit(records, args.out, args.pre, args.post, args.fps, args.person)


if __name__ == "__main__":
    main()
