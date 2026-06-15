"""Render terminal frames with ball-candidate overlays for a candidate-recall audit.

Two outputs per rally:
- ``*_candX.png``: a terminal frame with EVERY detected candidate circled, at full
  resolution.  Recall is then judged per frame ("is a circle on the ball?") without
  needing precise ball coordinates.
- ``*_clean.png``: the same frames with no overlay (for higher-quality human ball
  annotation if desired).

This is the measurement GPT-5.5 flagged as gating: it tells us whether the true ball
is present in the candidate set (detection adequate) or not (detection is the
bottleneck) — which decides whether tracker work is even worthwhile.
"""

from pathlib import Path

import cv2
import numpy as np

from ml.winner_tracking.clip_io import extract_raw_frames
from ml.winner_tracking.corpus import RallyRecord
from ml.winner_tracking.detect import DetectorConfig, detect_candidates


def render_recall_frames(
    rec: RallyRecord,
    out_dir: Path,
    n_frames: int = 4,
    before_end_s: float = 0.6,
    fps: int = 60,
    clean: bool = True,
) -> list[Path]:
    """Render the last ``n_frames`` candidate frames before rally end (full res).

    Frames are taken from a small window ending at the rally end, evenly spaced, so
    the deciding terminal event is in view.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, _ = extract_raw_frames(
        rec.video_path, rec.end_s - 2.5, rec.end_s + 0.5, fps, rec.native_size
    )
    cands = detect_candidates(frames, rec.corners, DetectorConfig())
    poly = np.asarray(rec.corners, np.int32)

    # Choose frames in the terminal window [end-before_end_s, end].
    total = len(frames)
    end_idx = int(round((2.5) * fps))            # index of rally-end within the clip
    lo = max(1, end_idx - int(before_end_s * fps))
    hi = min(total - 2, end_idx)
    picks = np.linspace(lo, hi, n_frames).astype(int)

    written: list[Path] = []
    stem = rec.key.replace("#", "_").replace(".mp4", "")
    for j, i in enumerate(picks):
        bgr = cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR)
        if clean:
            p_clean = out_dir / f"{stem}_f{j}_clean.png"
            cv2.imwrite(str(p_clean), bgr)
            written.append(p_clean)
        vis = bgr.copy()
        cv2.polylines(vis, [poly], True, (255, 0, 0), 1)
        for c in cands[i]:
            cv2.circle(vis, (int(c.x), int(c.y)), max(int(c.radius) + 3, 6), (0, 255, 0), 1)
        cv2.putText(vis, f"{stem} f{i} ({len(cands[i])} cand)", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        p_cand = out_dir / f"{stem}_f{j}_cand.png"
        cv2.imwrite(str(p_cand), vis)
        written.append(p_cand)
    return written
