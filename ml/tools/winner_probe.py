"""Go/no-go feasibility probe: is a rally's winner predictable from existing data?

This is a *finding*, not a shipped feature.  It measures whether ``winning_team``
(0/1) can be recovered from the data we already cache — player motion (the raw
court-point .npz) and match audio (the cached predict wav) — over the terminal /
post-rally window, evaluated **leave-one-session-out** (LOSO) against dumb
baselines (class prior, per-fold majority, a kitchen-geometry rule, and an
audio-parity rule).  If the learned models only match the class prior, that is
the honest "no signal" answer and the table will say so.

Pipeline (reuses existing loaders, reinvents nothing):

* eligible rallies          -> :class:`ml.examples.RallyExampleIndex`
* per-video raw motion cache -> :func:`ml.motion.features.load_feature_series`
* court projection           -> :func:`ml.motion.court_apply.apply_court`
* session grouping (YYYYMMDD)-> :func:`ml.motion.joint_dataset.group_id_for`
* motion cache location      -> :func:`ml.motion.joint_dataset.motion_cache_path`
* audio fallback extraction  -> :func:`ml.dataset.extract_audio`

Features are built over four windows per rally — whole ``[start,end]``,
final-5s ``[end-5,end]``, final-2s ``[end-2,end]``, post-rally-3s ``[end,end+3]``
— plus an all-windows-combined feature set.  Motion features are kept
court-side-relative (near = court-plane ``y<0.5``, far = ``y>0.5``, net at 0.5)
because ``winning_team`` is court-side-aligned by design; the classifier learns
the side->team mapping.

CRITICAL — no leakage: StandardScaler, the two sklearn models, and the majority
baseline are all fit INSIDE each LOSO fold on the TRAIN sessions only, then used
to predict the held-out session.  Grouping is strictly by session date prefix,
never random.

Run::

    PYTHONPATH="$PWD" .venv/bin/python -m ml.tools.winner_probe
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import wave
from collections import Counter
from pathlib import Path

import numpy as np

# cv2 is an early, load-bearing dependency (court projection lives behind it).
# Fail clearly now rather than deep inside a per-video loop.
try:  # noqa: SIM105 — third-party availability boundary, an explicit message is the point
    import cv2  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment guard
    print(
        "FATAL: cv2 (OpenCV) is required for court projection but is not "
        f"importable: {exc}\nInstall it into .venv before running the probe.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

from scipy.signal import butter, find_peaks, sosfiltfilt
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.config import PathConfig
from ml.dataset import extract_audio
from ml.examples import RallyExampleIndex
from ml.motion.court_apply import DEFAULT_DILATION, apply_court
from ml.motion.features import load_feature_series
from ml.motion.joint_dataset import group_id_for, motion_cache_path

__all__ = ["main"]

# Four analysis windows, expressed as (offset-from-start, offset-from-end) closures.
# Each entry maps a name to a function (start, end) -> (w0, w1).
WINDOWS: dict[str, "callable[[float, float], tuple[float, float]]"] = {
    "whole": lambda s, e: (s, e),
    "final5": lambda s, e: (max(0.0, e - 5.0), e),
    "final2": lambda s, e: (max(0.0, e - 2.0), e),
    "post3": lambda s, e: (e, e + 3.0),
}

MOTION_KEYS = (
    "near_n", "far_n", "n_delta",
    "near_net", "far_net", "net_delta",
    "near_spread", "far_spread", "spread_delta",
    "near_disp", "far_disp", "disp_delta",
    "total_n",
)
AUDIO_KEYS = (
    "n_hits", "hits_per_sec", "parity", "term_silence",
    "last_ioi", "mean_ioi", "std_ioi", "term_energy_ratio",
)

_HOP_S = 0.01


# ---------------------------------------------------------------------------
# Audio: stdlib wav read + an inline onset detector (no private imports)
# ---------------------------------------------------------------------------

def load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a mono/stereo PCM-16 wav with the stdlib ``wave`` module."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if ch == 2:
        a = a.reshape(-1, 2).mean(axis=1)
    return a / 32768.0, sr


def detect_onsets(seg: np.ndarray, sr: int) -> np.ndarray:
    """Paddle-hit onset times (s, relative to ``seg`` start) via HP energy peaks."""
    if seg.size < sr * 0.15:
        return np.empty(0)
    sos = butter(4, 1500, "hp", fs=sr, output="sos")
    hp = sosfiltfilt(sos, seg)
    win = max(1, int(_HOP_S * sr))
    env = np.array([np.sqrt(np.mean(hp[i:i + win] ** 2)) for i in range(0, len(hp) - win, win)])
    if env.size == 0 or env.max() <= 0:
        return np.empty(0)
    mad = np.median(np.abs(env - np.median(env))) * 1.4826
    thr = np.median(env) + 3.0 * mad
    pk, _ = find_peaks(env, height=max(thr, env.max() * 0.18), distance=max(1, int(0.12 / _HOP_S)))
    return pk * _HOP_S


def audio_window_feats(sig: np.ndarray, sr: int, w0: float, w1: float) -> dict[str, float]:
    """Onset-cadence + terminal-energy features for the audio in ``[w0, w1]``."""
    dur = max(0.05, w1 - w0)
    seg = sig[max(0, int(w0 * sr)):max(0, int(w1 * sr))]
    if seg.size == 0:
        return {k: 0.0 for k in AUDIO_KEYS}
    t = detect_onsets(seg, sr)
    n = int(t.size)
    f: dict[str, float] = {
        "n_hits": float(n),
        "hits_per_sec": n / dur,
        "parity": float(n % 2),
        "term_silence": float(dur - t[-1]) if n else dur,
    }
    if n >= 2:
        iois = np.diff(t)
        f["last_ioi"] = float(iois[-1])
        f["mean_ioi"] = float(iois.mean())
        f["std_ioi"] = float(iois.std())
    else:
        f["last_ioi"] = dur
        f["mean_ioi"] = dur
        f["std_ioi"] = 0.0
    tail = seg[-int(0.5 * sr):] if seg.size > int(0.5 * sr) else seg
    f["term_energy_ratio"] = float(
        (np.sqrt(np.mean(tail ** 2)) + 1e-9) / (np.sqrt(np.mean(seg ** 2)) + 1e-9)
    )
    return f


# ---------------------------------------------------------------------------
# Motion: per-side, court-side-relative features for a window
# ---------------------------------------------------------------------------

def motion_window_feats(
    court_points: list[np.ndarray],
    ids_per_frame: list[np.ndarray],
    times: np.ndarray,
    w0: float,
    w1: float,
) -> tuple[dict[str, float], float | None, float | None]:
    """Per-side motion features in ``[w0, w1]``.

    Near = court-plane ``y < 0.5`` (player side nearest the camera-defined near
    half), far = ``y > 0.5``; the net is at 0.5.  Returns ``(feats, near_net,
    far_net)`` where ``near_net`` / ``far_net`` are the per-side mean distance to
    the net (kitchen proximity; smaller = closer) or ``None`` when that side had
    no players in the window — exposed separately for the geometry baseline.
    """
    sel = np.nonzero((times >= w0) & (times <= w1))[0]
    near_cnt: list[float] = []
    far_cnt: list[float] = []
    near_net: list[float] = []
    far_net: list[float] = []
    near_spread: list[float] = []
    far_spread: list[float] = []
    near_disp_sum = far_disp_sum = 0.0
    near_disp_cnt = far_disp_cnt = 0
    prev_xy: dict[int, np.ndarray] = {}

    for i in sel:
        pts = np.asarray(court_points[i], dtype=np.float64).reshape(-1, 2)
        ids = np.asarray(ids_per_frame[i], dtype=np.int64).reshape(-1)
        near_mask = pts[:, 1] < 0.5
        near = pts[near_mask]
        far = pts[~near_mask]
        near_cnt.append(float(len(near)))
        far_cnt.append(float(len(far)))
        if len(near):
            near_net.append(float(np.mean(np.abs(near[:, 1] - 0.5))))
        if len(far):
            far_net.append(float(np.mean(np.abs(far[:, 1] - 0.5))))
        if len(near) >= 2:
            near_spread.append(float(np.sqrt(near[:, 0].var() + near[:, 1].var())))
        if len(far) >= 2:
            far_spread.append(float(np.sqrt(far[:, 0].var() + far[:, 1].var())))
        # per-track displacement, classified by current side
        m = min(pts.shape[0], ids.shape[0])
        cur = {int(ids[j]): pts[j] for j in range(m) if int(ids[j]) >= 0}
        for tid, xy in cur.items():
            if tid in prev_xy:
                d = float(np.linalg.norm(xy - prev_xy[tid]))
                if xy[1] < 0.5:
                    near_disp_sum += d
                    near_disp_cnt += 1
                else:
                    far_disp_sum += d
                    far_disp_cnt += 1
        prev_xy = cur

    def _mean(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else 0.0

    nn = _mean(near_cnt)
    fn = _mean(far_cnt)
    n_net = _mean(near_net)
    f_net = _mean(far_net)
    nsp = _mean(near_spread)
    fsp = _mean(far_spread)
    ndisp = near_disp_sum / near_disp_cnt if near_disp_cnt else 0.0
    fdisp = far_disp_sum / far_disp_cnt if far_disp_cnt else 0.0

    feats = {
        "near_n": nn, "far_n": fn, "n_delta": nn - fn,
        "near_net": n_net, "far_net": f_net, "net_delta": n_net - f_net,
        "near_spread": nsp, "far_spread": fsp, "spread_delta": nsp - fsp,
        "near_disp": ndisp, "far_disp": fdisp, "disp_delta": ndisp - fdisp,
        "total_n": nn + fn,
    }
    g_near = float(np.mean(near_net)) if near_net else None
    g_far = float(np.mean(far_net)) if far_net else None
    return feats, g_near, g_far


# ---------------------------------------------------------------------------
# Per-video feature assembly
# ---------------------------------------------------------------------------

def _resolve_predict_wav(stem: str, cache_dir: Path) -> Path | None:
    """Prefer the cached predict wav, then the plain stem wav."""
    cand = cache_dir / f"{stem}_predict.wav"
    if cand.exists():
        return cand
    cand = cache_dir / f"{stem}.wav"
    if cand.exists():
        return cand
    return None


def build_rows(
    index: RallyExampleIndex,
    cache_dir: Path,
    dilation: float,
    allow_extract: bool,
) -> tuple[list[dict[str, float]], list[int], list[str], dict[str, int]]:
    """Assemble one feature row per rally, grouped by video to bound memory.

    Returns ``(rows, labels, groups, coverage)`` where ``coverage`` tallies how
    many rallies / videos / sessions had motion and audio.
    """
    by_video: dict[Path, list] = {}
    for ex in index.examples:
        by_video.setdefault(ex.video_path, []).append(ex)

    rows: list[dict[str, float]] = []
    labels: list[int] = []
    groups: list[str] = []

    motion_videos: set[Path] = set()
    audio_videos: set[Path] = set()
    motion_sessions: set[str] = set()
    audio_sessions: set[str] = set()
    motion_rallies = audio_rallies = 0

    for vi, (video, rallies) in enumerate(sorted(by_video.items()), start=1):
        stem = video.stem
        group = group_id_for(video)
        print(f"[{vi}/{len(by_video)}] {stem} ({len(rallies)} rallies)", file=sys.stderr)

        # --- motion (cheap path) -------------------------------------------
        # motion_cache_path defaults to <cache_dir>/motion; the audio wavs live
        # directly under <cache_dir>, so the two caches use different roots.
        court_points = ids_per_frame = mtimes = None
        npz = motion_cache_path(video)
        if npz.exists():
            raw = load_feature_series(npz)
            court_points, ids_per_frame = apply_court(raw, dilation)
            mtimes = np.asarray(raw["t"], dtype=np.float64).reshape(-1)
            motion_videos.add(video)
            motion_sessions.add(group)

        # --- audio ----------------------------------------------------------
        sig = sr = None
        tmp_wav: Path | None = None
        wav = _resolve_predict_wav(stem, cache_dir)
        if wav is None and allow_extract and video.exists():
            tmp_wav = Path(tempfile.gettempdir()) / f"winner_probe_{stem}.wav"
            wav = extract_audio(video, tmp_wav)
        if wav is not None and wav.exists():
            sig, sr = load_wav(wav)
            audio_videos.add(video)
            audio_sessions.add(group)

        for ex in rallies:
            has_motion = court_points is not None
            has_audio = sig is not None
            if has_motion:
                motion_rallies += 1
            if has_audio:
                audio_rallies += 1

            row: dict[str, float] = {"has_motion": float(has_motion), "has_audio": float(has_audio)}
            g_near = g_far = None  # final-2s per-side net distance, for geometry baseline
            for wname, wfn in WINDOWS.items():
                w0, w1 = wfn(ex.raw_start, ex.raw_end)
                if has_motion:
                    mf, gn, gf = motion_window_feats(court_points, ids_per_frame, mtimes, w0, w1)
                else:
                    mf = {k: 0.0 for k in MOTION_KEYS}
                    gn = gf = None
                if wname == "final2":
                    g_near, g_far = gn, gf
                for k in MOTION_KEYS:
                    row[f"{wname}_m_{k}"] = mf[k]
                af = audio_window_feats(sig, sr, w0, w1) if has_audio else {k: 0.0 for k in AUDIO_KEYS}
                for k in AUDIO_KEYS:
                    row[f"{wname}_a_{k}"] = af[k]

            # heuristic raw signals (validity preserved via NaN where absent)
            row["_geo_near_net"] = g_near if g_near is not None else np.nan
            row["_geo_far_net"] = g_far if g_far is not None else np.nan
            row["_parity"] = row["whole_a_n_hits"] % 2 if has_audio else np.nan

            rows.append(row)
            labels.append(int(ex.winning_team))
            groups.append(group)

        # free per-video buffers
        del court_points, ids_per_frame, mtimes, sig
        if tmp_wav is not None and tmp_wav.exists():
            tmp_wav.unlink()

    coverage = {
        "motion_rallies": motion_rallies,
        "audio_rallies": audio_rallies,
        "motion_videos": len(motion_videos),
        "audio_videos": len(audio_videos),
        "total_videos": len(by_video),
        "motion_sessions": len(motion_sessions),
        "audio_sessions": len(audio_sessions),
    }
    return rows, labels, groups, coverage


# ---------------------------------------------------------------------------
# Feature-set selection
# ---------------------------------------------------------------------------

def feature_columns(rows: list[dict[str, float]]) -> list[str]:
    """All numeric model columns (excludes the leading-underscore raw signals)."""
    return [k for k in rows[0] if not k.startswith("_")]


def select_matrix(rows: list[dict[str, float]], window: str) -> np.ndarray:
    """Build the feature matrix for one window (or 'combined' = every window)."""
    cols = feature_columns(rows)
    if window != "combined":
        prefix = f"{window}_"
        cols = [c for c in cols if c.startswith(prefix) or c in ("has_motion", "has_audio")]
    return np.array([[r[c] for c in cols] for r in rows], dtype=np.float64)


# ---------------------------------------------------------------------------
# LOSO evaluation primitives (all fitting happens on TRAIN groups only)
# ---------------------------------------------------------------------------

def _make_logreg() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
    ])


def _make_gbm() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", GradientBoostingClassifier(n_estimators=100, max_depth=3)),
    ])


def loso_learned(make, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Out-of-fold P(y=1): fit on train sessions, predict the held-out session."""
    prob = np.zeros(len(y), dtype=np.float64)
    for g in sorted(set(groups)):
        tr = groups != g
        te = groups == g
        pipe = make()
        pipe.fit(X[tr], y[tr])
        prob[te] = pipe.predict_proba(X[te])[:, 1]
    return prob


def loso_majority(y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Out-of-fold P(y=1) = the TRAIN-fold class-1 frequency (no features)."""
    prob = np.zeros(len(y), dtype=np.float64)
    for g in sorted(set(groups)):
        tr = groups != g
        prob[groups == g] = float(y[tr].mean())
    return prob


def metrics(
    y: np.ndarray,
    groups: np.ndarray,
    score: np.ndarray,
    mask: np.ndarray | None = None,
) -> tuple[float, float, float, int]:
    """Pooled accuracy, ROC-AUC, worst-fold accuracy, N over an optional mask."""
    if mask is None:
        mask = np.ones(len(y), dtype=bool)
    ym, gm, sm = y[mask], groups[mask], score[mask]
    pred = (sm >= 0.5).astype(int)
    pooled = float(np.mean(pred == ym)) if ym.size else float("nan")
    if np.unique(sm).size >= 2 and np.unique(ym).size >= 2:
        auc = float(roc_auc_score(ym, sm))
    else:
        auc = float("nan")
    fold_acc: list[float] = []
    for g in sorted(set(gm)):
        sub = gm == g
        if sub.any():
            fold_acc.append(float(np.mean(pred[sub] == ym[sub])))
    worst = min(fold_acc) if fold_acc else float("nan")
    return pooled, auc, worst, int(ym.size)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return "  —  " if v != v else f"{v:.3f}"  # NaN check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir", action="append", type=Path,
        help="Directory to scan for .training.json (default ~/Videos/pickleball).",
    )
    parser.add_argument("--dilation", type=float, default=DEFAULT_DILATION)
    parser.add_argument(
        "--no-extract", action="store_true",
        help="Never fall back to ffmpeg audio extraction; cached wavs only.",
    )
    args = parser.parse_args(argv)

    dirs = args.dir or [Path.home() / "Videos" / "pickleball"]
    cache_dir = PathConfig().cache_dir

    index = RallyExampleIndex(dirs=dirs)
    if not index.examples:
        print("No eligible rallies found.", file=sys.stderr)
        return 1

    rows, labels, groups_list, coverage = build_rows(
        index, cache_dir, args.dilation, allow_extract=not args.no_extract
    )
    y = np.array(labels, dtype=int)
    groups = np.array(groups_list, dtype=object)
    n = len(y)

    # -- sanity -------------------------------------------------------------
    class_counts = Counter(labels)
    sess_counts = Counter(groups_list)
    prior1 = class_counts[1] / n
    prior0 = class_counts[0] / n
    print("=" * 78)
    print("WINNER FEASIBILITY PROBE — leave-one-session-out (LOSO)")
    print("=" * 78)
    print(f"Total eligible rallies : {n}")
    print(f"Class balance          : team0={class_counts[0]} ({prior0:.3f})  "
          f"team1={class_counts[1]} ({prior1:.3f})")
    print(f"Sessions (date prefix) : {len(sess_counts)}")
    for s in sorted(sess_counts):
        print(f"    {s}: {sess_counts[s]} rallies")
    print(f"Motion coverage        : {coverage['motion_rallies']}/{n} rallies, "
          f"{coverage['motion_videos']}/{coverage['total_videos']} videos, "
          f"{coverage['motion_sessions']}/{len(sess_counts)} sessions")
    print(f"Audio coverage         : {coverage['audio_rallies']}/{n} rallies, "
          f"{coverage['audio_videos']}/{coverage['total_videos']} videos, "
          f"{coverage['audio_sessions']}/{len(sess_counts)} sessions")
    print("Note: serving_team is None in all files -> the serving-team baseline "
          "is omitted (cannot be computed).")
    print()
    print("Per-fold held-out sample counts:")
    for s in sorted(sess_counts):
        print(f"    {s}: {sess_counts[s]}")
    print()

    header = f"{'PREDICTOR':<46}{'ACC':>7}{'AUC':>7}{'WORST':>7}{'N':>7}"

    # -- baselines ----------------------------------------------------------
    print("-" * 78)
    print("BASELINES")
    print("-" * 78)
    print(header)

    always0 = metrics(y, groups, np.zeros(n))
    always1 = metrics(y, groups, np.ones(n))
    print(f"{'always-team-0':<46}{_fmt(always0[0]):>7}{_fmt(always0[1]):>7}{_fmt(always0[2]):>7}{always0[3]:>7}")
    print(f"{'always-team-1':<46}{_fmt(always1[0]):>7}{_fmt(always1[1]):>7}{_fmt(always1[2]):>7}{always1[3]:>7}")

    maj = metrics(y, groups, loso_majority(y, groups))
    print(f"{'majority-class (LOSO, per-fold train)':<46}{_fmt(maj[0]):>7}{_fmt(maj[1]):>7}{_fmt(maj[2]):>7}{maj[3]:>7}")

    # geometry: kitchen-nearer (smaller mean net-distance) side wins, final-2s.
    geo_near = np.array([r["_geo_near_net"] for r in rows], dtype=np.float64)
    geo_far = np.array([r["_geo_far_net"] for r in rows], dtype=np.float64)
    geo_mask = ~np.isnan(geo_near) & ~np.isnan(geo_far)
    geo_near_wins = (geo_near < geo_far).astype(float)  # 1 if near side is closer to net
    gA = metrics(y, groups, geo_near_wins, geo_mask)            # near-wins -> team0 convention? score=near_wins
    gB = metrics(y, groups, 1.0 - geo_near_wins, geo_mask)      # polarity-flipped
    print(f"{'kitchen-nearer-wins  (final2, polarity A)':<46}{_fmt(gA[0]):>7}{_fmt(gA[1]):>7}{_fmt(gA[2]):>7}{gA[3]:>7}")
    print(f"{'kitchen-nearer-wins  (final2, polarity B)':<46}{_fmt(gB[0]):>7}{_fmt(gB[1]):>7}{_fmt(gB[2]):>7}{gB[3]:>7}")

    # last-hitter parity from whole-rally onset count.
    parity = np.array([r["_parity"] for r in rows], dtype=np.float64)
    par_mask = ~np.isnan(parity)
    par_score = np.nan_to_num(parity)
    pA = metrics(y, groups, par_score, par_mask)
    pB = metrics(y, groups, 1.0 - par_score, par_mask)
    print(f"{'last-hitter-parity   (whole, polarity A)':<46}{_fmt(pA[0]):>7}{_fmt(pA[1]):>7}{_fmt(pA[2]):>7}{pA[3]:>7}")
    print(f"{'last-hitter-parity   (whole, polarity B)':<46}{_fmt(pB[0]):>7}{_fmt(pB[1]):>7}{_fmt(pB[2]):>7}{pB[3]:>7}")
    print()

    # -- learned models -----------------------------------------------------
    print("-" * 78)
    print("LEARNED MODELS (StandardScaler + classifier, fit per LOSO fold)")
    print("-" * 78)
    print(header)
    window_order = ["whole", "final5", "final2", "post3", "combined"]
    for window in window_order:
        X = select_matrix(rows, window)
        lr = metrics(y, groups, loso_learned(_make_logreg, X, y, groups))
        gb = metrics(y, groups, loso_learned(_make_gbm, X, y, groups))
        print(f"{f'LogReg [{window}]  ({X.shape[1]}f)':<46}{_fmt(lr[0]):>7}{_fmt(lr[1]):>7}{_fmt(lr[2]):>7}{lr[3]:>7}")
        print(f"{f'GBM    [{window}]  ({X.shape[1]}f)':<46}{_fmt(gb[0]):>7}{_fmt(gb[1]):>7}{_fmt(gb[2]):>7}{gb[3]:>7}")
    print()
    print("=" * 78)
    print(f"Class prior (max) = {max(prior0, prior1):.3f}.  A learned model that "
          "does not clear this\nby a margin that survives the worst fold = NO "
          "usable winner signal in these features.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
