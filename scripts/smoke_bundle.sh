#!/usr/bin/env bash
# scripts/smoke_bundle.sh — Bundle smoke test for the rally-trainer binary.
#
# Usage:
#   bash scripts/smoke_bundle.sh [BUNDLE_PATH]
#
# Runs each subcommand (train, train-winner, predict) with sentinel arguments
# that pass argparse validation but fail benignly at runtime (no data / file
# not found).  Captures combined stdout+stderr, greps for
# ModuleNotFoundError|ImportError across all runs, and exits 1 if any match
# is found.
#
# Exit codes:
#   0 — No import errors detected across all runs.
#   1 — At least one ModuleNotFoundError or ImportError was detected.
#
# Sentinel arg rationale (verified against ml/cli.py argparse signatures):
#   train --data-dir <empty-tmpdir>
#       Passes argparse (--data-dir is required, string).
#       Reaches ml.train.main() -> prepare_all() -> finds no .training.json
#       files -> "Need at least 2 videos" -> sys.exit(1).  Benign.
#
#   train-winner --root <empty-tmpdir>
#       Passes argparse (--root is required, string).
#       cli.py LBYL-checks root_dir.exists() (tmpdir exists, passes).
#       Calls train_winner() -> load_winner_dataset() -> empty dataset ->
#       "No training samples found" -> sys.exit(1).  Benign.
#
#   predict --video /tmp/__nonexistent_smoke__.mp4
#       Passes argparse (--video is required; --model defaults to None).
#       NOTE: predict uses --model, not --checkpoint (plan suggestion was
#       incorrect; verified against ml/cli.py and ml/predict.py).
#       Reaches predict_video() -> load_model(default_checkpoint) ->
#       torch.load(nonexistent) -> FileNotFoundError.  Benign.
#       All heavy imports (torchaudio, torch, ml.model) are exercised during
#       module import before the file-not-found failure.

set -euo pipefail

# ---------------------------------------------------------------------------
# Bundle path: optional first positional argument.
# ---------------------------------------------------------------------------
BUNDLE="${1:-dist/rally-trainer/rally-trainer}"

if [[ ! -f "${BUNDLE}" ]]; then
    echo "FAIL: bundle not found at '${BUNDLE}'"
    echo "      Build the bundle first with: make build-ml"
    exit 1
fi

# ---------------------------------------------------------------------------
# Temp directory for sentinel data-dir / root args.
# Cleaned up automatically on exit.
# ---------------------------------------------------------------------------
TMPDIR_SENTINEL="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_SENTINEL}"' EXIT

# ---------------------------------------------------------------------------
# Accumulated output from all runs (written to a temp file so we can grep
# once after all runs complete).
# ---------------------------------------------------------------------------
COMBINED_OUTPUT="$(mktemp)"
trap 'rm -rf "${TMPDIR_SENTINEL}" "${COMBINED_OUTPUT}"' EXIT

# ---------------------------------------------------------------------------
# Nonexistent video path for predict sentinel.
# ---------------------------------------------------------------------------
NONEXISTENT_VIDEO="/tmp/__nonexistent_smoke_video__.mp4"

# ---------------------------------------------------------------------------
# Run subcommands and collect output.
# ---------------------------------------------------------------------------
echo "==> Smoke testing: ${BUNDLE}"
echo ""

# ---- train ----
echo "  [1/3] train --data-dir <empty-tmpdir>"
"${BUNDLE}" train --data-dir "${TMPDIR_SENTINEL}" >> "${COMBINED_OUTPUT}" 2>&1 || true

# ---- train-winner ----
echo "  [2/3] train-winner --root <empty-tmpdir>"
"${BUNDLE}" train-winner --root "${TMPDIR_SENTINEL}" >> "${COMBINED_OUTPUT}" 2>&1 || true

# ---- predict ----
echo "  [3/3] predict --video /tmp/__nonexistent_smoke_video__.mp4"
"${BUNDLE}" predict --video "${NONEXISTENT_VIDEO}" >> "${COMBINED_OUTPUT}" 2>&1 || true

echo ""

# ---------------------------------------------------------------------------
# Grep combined output for import errors.
# ---------------------------------------------------------------------------
if grep -qE 'ModuleNotFoundError|ImportError' "${COMBINED_OUTPUT}"; then
    echo "FAIL: import error(s) detected in bundle output:"
    echo "------"
    grep -E 'ModuleNotFoundError|ImportError' "${COMBINED_OUTPUT}"
    echo "------"
    echo "Full output saved to: ${COMBINED_OUTPUT}"
    # Prevent trap from deleting the output so the caller can inspect it.
    trap 'rm -rf "${TMPDIR_SENTINEL}"' EXIT
    exit 1
fi

echo "PASS: no ModuleNotFoundError or ImportError detected across all subcommands."
exit 0
