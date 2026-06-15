"""Audio rally-dynamics features for predicting the `winner` field (server/receiver).

This is the court-side-INDEPENDENT angle: mono audio cannot observe which physical
side won, but it can observe rally dynamics — how many paddle "pock" hits, who hit
last (hit-count parity), and what the terminal acoustics look like (a put-away vs a
soft net dribble vs ball going long after the last hit).  The `winner` field
(server/receiver) maps to `winning_team` via the pipeline's tracked serving team, so
a usable server/receiver model is a usable winner model.

Paddle hits are sharp broadband transients: high-pass filter (>1500 Hz), short-time
energy envelope, adaptive peak-pick.  Uses cached 22050 Hz mono wavs + scipy (no
librosa).  Cheap enough to run on the full 1,846-rally corpus.
"""

import argparse
import glob
import json
import logging
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from ml.winner_tracking.corpus import RallyRecord, load_rally_records

logger = logging.getLogger("audio_winner")
_DEFAULT_OUT = Path(__file__).parent / "cache" / "dev_audio.jsonl"
_HOP_S = 0.01


def load_video_audio(stem: str) -> tuple[np.ndarray, int] | tuple[None, None]:
    cands = glob.glob(f"ml/cache/{stem}_e43a*.wav") or glob.glob(f"ml/cache/{stem}.wav")
    if not cands:
        return None, None
    w = wave.open(cands[0], "rb")
    sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if w.getnchannels() == 2:
        a = a.reshape(-1, 2).mean(1)
    return a / 32768.0, sr


def _onsets(seg: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (onset_times_s, onset_strengths) for paddle hits in ``seg``."""
    if len(seg) < sr * 0.15:
        return np.array([]), np.array([])
    sos = butter(4, 1500, "hp", fs=sr, output="sos")
    hp = sosfiltfilt(sos, seg)
    win = max(1, int(_HOP_S * sr))
    env = np.array([np.sqrt(np.mean(hp[i:i + win] ** 2)) for i in range(0, len(hp) - win, win)])
    if env.size == 0 or env.max() <= 0:
        return np.array([]), np.array([])
    mad = np.median(np.abs(env - np.median(env))) * 1.4826
    thr = np.median(env) + 3 * mad
    pk, props = find_peaks(env, height=max(thr, env.max() * 0.18),
                           distance=max(1, int(0.12 / _HOP_S)))
    return pk * _HOP_S, env[pk]


def audio_features(rec: RallyRecord, sig: np.ndarray, sr: int) -> dict[str, float]:
    dur = max(0.1, rec.end_s - rec.start_s)
    seg = sig[int(rec.start_s * sr):int((rec.end_s + 0.4) * sr)]
    t, s = _onsets(seg, sr)
    n = int(len(t))
    f: dict[str, float] = {"duration_s": dur, "n_hits": float(n),
                           "parity": float(n % 2), "hits_per_sec": n / dur}
    # serve/return phase
    f["first1s_hits"] = float((t < 1.0).sum())
    f["last1p5s_hits"] = float((t > dur - 1.5).sum()) if n else 0.0
    # terminal dynamics
    if n >= 1:
        f["last_gap"] = float(dur - t[-1])            # silence after the last hit
        f["last_onset_strength"] = float(s[-1] / (s.mean() + 1e-9))
    else:
        f["last_gap"] = dur
        f["last_onset_strength"] = 0.0
    if n >= 2:
        iois = np.diff(t)
        f["last_ioi"] = float(iois[-1]); f["mean_ioi"] = float(iois.mean())
        f["std_ioi"] = float(iois.std())
    else:
        f["last_ioi"] = dur; f["mean_ioi"] = dur; f["std_ioi"] = 0.0
    # terminal energy ratio: last 0.4 s RMS vs whole-rally RMS
    tail = seg[-int(0.4 * sr):]
    whole = seg[:int(dur * sr)] if int(dur * sr) > 0 else seg
    f["term_energy_ratio"] = float((np.sqrt(np.mean(tail ** 2)) + 1e-9)
                                   / (np.sqrt(np.mean(whole ** 2)) + 1e-9))
    return f


def run_audio_audit(records, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        done = {json.loads(l)["key"] for l in out_path.read_text().splitlines() if l.strip()}
    by_video: dict[str, list[RallyRecord]] = {}
    for r in records:
        if r.key not in done:
            by_video.setdefault(r.video_name.replace(".mp4", ""), []).append(r)
    total = sum(len(v) for v in by_video.values())
    logger.info("Audio audit: %d rallies across %d videos (%d cached)",
                total, len(by_video), len(done))
    t0 = time.time(); i = 0
    with out_path.open("a") as fh:
        for stem, rs in by_video.items():
            sig, sr = load_video_audio(stem)
            for rec in rs:
                i += 1
                try:
                    if sig is None:
                        raise RuntimeError("no cached wav")
                    feats = audio_features(rec, sig, sr)
                    row = {"key": rec.key, "video": rec.video_name, "date_group": rec.date_group,
                           "winning_team": rec.winning_team,
                           "y_role": 1 if rec.winner_role == "receiver" else 0}
                    row.update({f"f_{k}": round(float(v), 5) for k, v in feats.items()})
                    row["q_covered"] = 1.0
                except Exception as exc:  # noqa: BLE001
                    row = {"key": rec.key, "winning_team": rec.winning_team, "error": str(exc)}
                fh.write(json.dumps(row) + "\n")
            fh.flush()
            if i % 200 < len(rs):
                logger.info("  ~%d/%d  (%.0fs)", i, total, time.time() - t0)
    logger.info("Audio audit done -> %s (%.1fs)", out_path, time.time() - t0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--target", type=int, default=0, help="0 = full corpus")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    records = load_rally_records()
    if args.target > 0:
        from ml.winner_tracking.corpus import stratified_dev_sample
        records = stratified_dev_sample(records, target=args.target)
    run_audio_audit(records, args.out)


if __name__ == "__main__":
    main()
