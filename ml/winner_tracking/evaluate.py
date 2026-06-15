"""Evaluate winner predictability from ball-track geometry — with leak controls.

Decisive metric (per the GPT-5.5-reviewed audit design): grouped-CV accuracy of a
SIMPLE model on strictly-geometric features, vs same-covered-subset baselines, with
false-positive controls (label permutation, nuisance-only model) and a selective
accuracy/coverage curve.  A positive result here justifies the full tracker build;
a weak result is interpreted with the three-outcome framing (it does NOT by itself
prove the cue absent — that needs ball ground truth).
"""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

_DEFAULT_IN = Path(__file__).parent / "cache" / "dev_features.jsonl"


def _discover_columns(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Find predictive (f_*) and quality (q_*) feature names present in the data."""
    f_names: set[str] = set()
    q_names: set[str] = set()
    for r in rows:
        for k in r:
            if k.startswith("f_"):
                f_names.add(k[2:])
            elif k.startswith("q_") and k != "q_covered":
                q_names.add(k[2:])
    return sorted(f_names), sorted(q_names)


def _load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if "error" in row:
            continue
        rows.append(row)
    return rows


def _model() -> object:
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced"),
    )


def _oof_predict(X, y, groups, n_splits):
    """Out-of-fold predictions + probabilities via GroupKFold."""
    oof_pred = np.full(len(y), -1)
    oof_prob = np.zeros(len(y))
    gkf = GroupKFold(n_splits=n_splits)
    for tr, te in gkf.split(X, y, groups):
        m = _model()
        m.fit(X[tr], y[tr])
        oof_pred[te] = m.predict(X[te])
        oof_prob[te] = m.predict_proba(X[te]).max(axis=1)
    return oof_pred, oof_prob


def _grouped_cv_acc(X, y, groups, n_splits) -> float:
    pred, _ = _oof_predict(X, y, groups, n_splits)
    return float((pred == y).mean())


def _balanced_acc(y_true, y_pred) -> float:
    accs = []
    for c in (0, 1):
        m = y_true == c
        if m.sum() > 0:
            accs.append((y_pred[m] == c).mean())
    return float(np.mean(accs)) if accs else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=_DEFAULT_IN)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--target", default="winning_team",
                    help="label column to predict (e.g. winning_team or y_role)")
    args = ap.parse_args()
    rng = np.random.default_rng(0)

    rows = _load(args.inp)
    covered = [r for r in rows if r.get("q_covered", 0.0) == 1.0]
    print(f"=== winner-tracking audit eval ===")
    print(f"rows={len(rows)}  covered(track found)={len(covered)}  "
          f"coverage={len(covered)/max(len(rows),1):.1%}")
    if len(covered) < 30:
        print("too few covered rows; wait for the audit to populate.")
        return

    feature_names, quality_names = _discover_columns(covered)
    y = np.array([int(r[args.target]) for r in covered])
    print(f"target column: {args.target}")
    date_groups = np.array([r["date_group"] for r in covered])
    video_groups = np.array([r["video"] for r in covered])
    Xg = np.array([[float(r.get(f"f_{n}", 0.0)) for n in feature_names] for r in covered])
    Xq = (np.array([[float(r.get(f"q_{n}", 0.0)) for n in quality_names] for r in covered])
          if quality_names else np.zeros((len(covered), 1)))
    print(f"predictive features ({len(feature_names)}): {feature_names}")

    n_dates = len(set(date_groups))
    n_vids = len(set(video_groups))
    nsd = min(n_dates, 8)
    nsv = min(n_vids, 8)

    print(f"\nclass balance (covered): team0={int((y==0).sum())} team1={int((y==1).sum())} "
          f"-> majority prior={max((y==0).mean(),(y==1).mean()):.3f}")
    print(f"groups: {n_dates} dates, {n_vids} videos")

    # --- Same-covered-subset baselines ---
    # Per-group oracle majority (upper bound a per-court bias could reach).
    def oracle_group_acc(groups):
        correct = 0
        for g in set(groups):
            m = groups == g
            maj = round(y[m].mean())
            correct += (y[m] == maj).sum()
        return correct / len(y)

    print("\n--- baselines on the SAME covered subset ---")
    print(f"  global majority          : {max((y==0).mean(),(y==1).mean()):.3f}")
    print(f"  per-date oracle majority  : {oracle_group_acc(date_groups):.3f}")
    print(f"  per-video oracle majority : {oracle_group_acc(video_groups):.3f}")

    # --- Geometric model, grouped CV ---
    pred_d, prob_d = _oof_predict(Xg, y, date_groups, nsd)
    pred_v, prob_v = _oof_predict(Xg, y, video_groups, nsv)
    acc_d = float((pred_d == y).mean())
    acc_v = float((pred_v == y).mean())
    print("\n--- geometric model (strictly geometric features) ---")
    print(f"  leave-date-out  GroupKFold acc = {acc_d:.3f}  (balanced {_balanced_acc(y,pred_d):.3f})")
    print(f"  leave-video-out GroupKFold acc = {acc_v:.3f}  (balanced {_balanced_acc(y,pred_v):.3f})")

    # --- Sign analysis: is there a signal masked by per-group sign inconsistency? ---
    # Below-chance grouped accuracy implies the feature->label relation flips across
    # groups.  Oracle-per-group sign is the CEILING if that mapping were known
    # (e.g. by recording which physical side each team is on).
    def oracle_sign_acc(pred, groups):
        correct = 0
        for g in set(groups):
            m = groups == g
            base = (pred[m] == y[m]).sum()
            correct += max(base, m.sum() - base)  # flip this group if it helps
        return correct / len(y)

    glob_flip = max(acc_d, 1.0 - acc_d)
    print("\n--- sign analysis (is signal masked by Team1<->side inconsistency?) ---")
    print(f"  leave-date-out raw={acc_d:.3f}  global-flip={glob_flip:.3f}")
    print(f"  oracle per-DATE  sign (date-OOF preds): {oracle_sign_acc(pred_d, date_groups):.3f}")
    print(f"  oracle per-VIDEO sign (date-OOF preds): {oracle_sign_acc(pred_d, video_groups):.3f}")
    print(f"  (per-video prior {oracle_group_acc(video_groups):.3f}; lift = oracle_video_sign - prior)")

    # --- Control 1: label permutation within date groups ---
    null = []
    for _ in range(args.n_perm):
        yp = y.copy()
        for g in set(date_groups):
            m = date_groups == g
            yp[m] = rng.permutation(yp[m])
        null.append(_grouped_cv_acc(Xg, yp, date_groups, nsd))
    null = np.array(null)
    pval = float((null >= acc_d).mean())
    print("\n--- control: label permutation (within date groups) ---")
    print(f"  null acc mean={null.mean():.3f}  95th pct={np.percentile(null,95):.3f}  "
          f"max={null.max():.3f}")
    print(f"  real leave-date-out acc={acc_d:.3f}  -> permutation p={pval:.3f}")

    # --- Control 2: nuisance-only model (quality fields, no geometry) ---
    pred_n, _ = _oof_predict(Xq, y, date_groups, nsd)
    print("\n--- control: nuisance-only model (track-quality fields, NO geometry) ---")
    print(f"  leave-date-out acc = {float((pred_n==y).mean()):.3f}  "
          f"(should be near prior {max((y==0).mean(),(y==1).mean()):.3f})")

    # --- Selective accuracy / coverage curve (abstain by model confidence) ---
    print("\n--- selective accuracy vs coverage (leave-date-out, abstain by confidence) ---")
    order = np.argsort(-prob_d)
    for frac in (1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2):
        k = max(1, int(frac * len(y)))
        idx = order[:k]
        acc = float((pred_d[idx] == y[idx]).mean())
        base = max((y[idx] == 0).mean(), (y[idx] == 1).mean())
        print(f"  coverage={frac:0.0%} (n={k:4d})  acc={acc:.3f}  (covered-subset prior {base:.3f})")


if __name__ == "__main__":
    main()
