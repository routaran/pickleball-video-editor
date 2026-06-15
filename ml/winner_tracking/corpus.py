"""Enumerate training-ready labeled rallies for the winner-tracking audit.

A rally is "training-ready" when its source training JSON has 4 court corners,
is human-authored (``generated_by != "auto_edit"``), and the rally itself is a
scored (non-post-game) rally carrying a ``winning_team`` label.

Grouping: every video filename starts with an 8-digit ``YYYYMMDD`` recording
date.  Games recorded on the same date share venue / court / camera setup, so the
date is the strongest available grouping key for leak-resistant cross-validation
(leave-one-date-out is stricter than leave-one-video-out).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["RallyRecord", "load_rally_records", "stratified_dev_sample", "summarize"]

_DATE_RE = re.compile(r"(\d{8})")


@dataclass(frozen=True)
class RallyRecord:
    """One scored, labeled rally and everything needed to extract its clip."""

    json_path: Path
    video_path: Path
    video_name: str
    date_group: str                 # YYYYMMDD parsed from the video filename
    corners: list[list[int]]        # 4 × [x, y] in native pixel coords (TL,TR,BR,BL)
    native_size: tuple[int, int]    # (width, height) from the JSON video block
    rally_index: int
    winning_team: int               # 0 = Team1 = canonical top (court-side absolute)
    winner_role: str                # "server" | "receiver"
    score_at_start: str
    start_s: float
    end_s: float                    # rally end timestamp (clip anchor)
    duration_s: float

    @property
    def key(self) -> str:
        """Stable per-rally identifier (also the cache key stem)."""
        return f"{self.video_name}#{self.rally_index}"

    @property
    def duration_bucket(self) -> str:
        if self.duration_s < 3.0:
            return "short"
        if self.duration_s < 6.0:
            return "mid"
        return "long"


def _rally_window(rally: dict) -> tuple[float, float] | None:
    """Return sane (start_s, end_s) for a rally, preferring ``raw`` over ``padded``.

    Some rallies have malformed ``raw`` spans (negative duration); fall back to
    ``padded`` and finally reject if neither yields a positive duration.
    """
    for key in ("raw", "padded"):
        span = rally.get(key) or {}
        start = span.get("start_seconds")
        end = span.get("end_seconds")
        if start is None or end is None:
            continue
        if end - start > 0.3:
            return float(start), float(end)
    return None


def load_rally_records(
    root: Path = Path.home() / "Videos" / "pickleball",
) -> list[RallyRecord]:
    """Load every training-ready scored rally under ``root``.

    Skips files lacking corners, ``auto_edit``-generated files, post-game rallies,
    rallies without a 0/1 ``winning_team``, and rallies with no sane time window.
    """
    records: list[RallyRecord] = []
    for json_path in sorted(root.glob("*.training.json")):
        data = json.loads(json_path.read_text())
        if data.get("generated_by") == "auto_edit":
            continue
        video = data.get("video", {})
        corners = video.get("court_corners")
        if not corners or len(corners) != 4:
            continue
        video_path = Path(video["path"])
        video_name = video_path.name
        date_match = _DATE_RE.match(video_name)
        date_group = date_match.group(1) if date_match else "unknown"
        native_size = (int(video.get("width", 0)), int(video.get("height", 0)))

        for rally in data.get("rallies", []):
            if rally.get("is_post_game"):
                continue
            winning_team = rally.get("winning_team")
            if winning_team not in (0, 1):
                continue
            window = _rally_window(rally)
            if window is None:
                continue
            start_s, end_s = window
            records.append(
                RallyRecord(
                    json_path=json_path,
                    video_path=video_path,
                    video_name=video_name,
                    date_group=date_group,
                    corners=[[int(x), int(y)] for x, y in corners],
                    native_size=native_size,
                    rally_index=int(rally.get("index", -1)),
                    winning_team=int(winning_team),
                    winner_role=str(rally.get("winner", "")),
                    score_at_start=str(rally.get("score_at_start", "")),
                    start_s=start_s,
                    end_s=end_s,
                    duration_s=end_s - start_s,
                )
            )
    return records


def stratified_dev_sample(
    records: list[RallyRecord],
    target: int = 200,
    per_video_cap: int = 8,
    seed: int = 17,
) -> list[RallyRecord]:
    """Pick a development subset spread across videos, winner class, and duration.

    Deterministic (seeded).  Caps per-video contribution so the dev set spans many
    courts, and round-robins across (date_group, winning_team, duration_bucket)
    strata so all are represented.
    """
    import random

    rng = random.Random(seed)
    buckets: dict[tuple[str, int, str], list[RallyRecord]] = {}
    for r in records:
        buckets.setdefault((r.date_group, r.winning_team, r.duration_bucket), []).append(r)
    for items in buckets.values():
        rng.shuffle(items)

    chosen: list[RallyRecord] = []
    per_video: dict[str, int] = {}
    stratum_keys = sorted(buckets.keys())
    progressed = True
    while len(chosen) < target and progressed:
        progressed = False
        for sk in stratum_keys:
            pool = buckets[sk]
            while pool:
                cand = pool.pop()
                if per_video.get(cand.video_name, 0) >= per_video_cap:
                    continue
                chosen.append(cand)
                per_video[cand.video_name] = per_video.get(cand.video_name, 0) + 1
                progressed = True
                break
            if len(chosen) >= target:
                break
    return chosen


def summarize(records: list[RallyRecord]) -> str:
    """Return a one-block text summary of a record set for logging."""
    from collections import Counter

    videos = {r.video_name for r in records}
    dates = Counter(r.date_group for r in records)
    teams = Counter(r.winning_team for r in records)
    roles = Counter(r.winner_role for r in records)
    durs = Counter(r.duration_bucket for r in records)
    lines = [
        f"rallies={len(records)}  videos={len(videos)}  date_groups={len(dates)}",
        f"  winning_team: {dict(sorted(teams.items()))}",
        f"  winner_role:  {dict(roles)}",
        f"  duration:     {dict(durs)}",
        f"  per-date rally counts: {dict(sorted(dates.items()))}",
    ]
    return "\n".join(lines)
