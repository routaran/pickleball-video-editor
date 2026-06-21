"""Late fusion of the motion signal into the audio binary rally stream.

The audio detector is the primary trigger (the serve sound is acoustically
sharp, so audio has the better rally-*start* precision).  Motion holds two
override powers, applied per audio window:

* **Veto** — audio says "rally" but the court is essentially empty (too few
  on-court detections) -> force the window to dead time.  This attacks the audio
  model's measured weak point: low precision / ``fp_active_seconds`` from
  neighbouring-court audio bleed.  An optional second gate also requires
  near-zero centroid movement, but it is OFF by default — see
  :attr:`FusionConfig.enable_displacement_gate`.
* **Sustain** — audio says "dead time" but on-court detections still show a full,
  distributed two-and-two -> force the window to rally, bridging an audio split.

Both overrides require **hysteresis**: the condition must hold for at least
``hysteresis`` consecutive windows before the flip is applied, so a single noisy
window cannot toggle the state.  Windows with no valid motion features (e.g. a
video without labelled corners) are never overridden — fusion degrades to
audio-only there.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["FusionConfig", "fuse_binary", "runs_at_least"]


@dataclass
class FusionConfig:
    """Thresholds for the veto/sustain rules.

    Detection counts are on-court person counts; displacement and spread are in
    normalised court-plane units (``[0, 1]`` across the court).  Defaults are the
    configuration locked in after the val-split sweep
    (``ml/cache/fusion_sweep_val_2026-06-20.md``): a count-only veto at ``< 1.5``
    on-court detections with hysteresis 3 and the displacement gate OFF.  Re-tune
    against held-out ground truth (see ``ml/tools/sweep_fusion.py``) if the
    feature pipeline changes.
    """

    # Veto: audio rally but too few on-court players.
    veto_max_detections: float = 1.5
    # Optional second veto gate: also require low centroid motion.  OFF by
    # default — without identity tracking the anonymous-centroid displacement is
    # noise (it spikes on detection flicker during exactly the low-count dead
    # time we want to veto), so on the val sweep the gate suppressed more good
    # vetoes than it enabled.  Re-enable once per-track displacement exists.
    enable_displacement_gate: bool = False
    veto_max_displacement: float = 0.01
    # Sustain: audio dead-time with a full, balanced court.
    sustain_min_detections: float = 3.5
    sustain_min_symmetry: float = 0.5
    # Consecutive windows an override must hold before it is applied.
    hysteresis: int = 3
    enable_veto: bool = True
    enable_sustain: bool = True


def runs_at_least(mask: np.ndarray, n: int) -> np.ndarray:
    """Return a mask that is ``True`` only inside runs of ``True`` of length >= n.

    Used to enforce hysteresis: an override fires only where its triggering
    condition holds for at least ``n`` consecutive windows.

    Args:
        mask: 1-D boolean array.
        n: Minimum consecutive-run length (``n <= 1`` returns ``mask`` unchanged).

    Returns:
        Boolean array the same shape as ``mask``.
    """
    mask = np.asarray(mask, dtype=bool)
    if n <= 1 or mask.size == 0:
        return mask.copy()

    out = np.zeros_like(mask)
    run_start = 0
    for i in range(1, mask.size + 1):
        if i == mask.size or mask[i] != mask[i - 1]:
            if mask[i - 1] and (i - run_start) >= n:
                out[run_start:i] = True
            run_start = i
    return out


def fuse_binary(
    audio_binary: np.ndarray,
    features: dict[str, np.ndarray],
    valid: np.ndarray,
    config: FusionConfig | None = None,
) -> np.ndarray:
    """Apply veto/sustain (with hysteresis) to the audio binary stream.

    Args:
        audio_binary: ``(W,)`` bool array — the audio model's per-window
            rally/dead-time decision (``True`` = rally).
        features: Resampled motion features (keys from
            :data:`ml.motion.features.FEATURE_KEYS`), each ``(W,)``.
        valid: ``(W,)`` bool array — ``True`` where motion features exist.
        config: Fusion thresholds (defaults used when ``None``).

    Returns:
        ``(W,)`` bool array — the corrected per-window decision.
    """
    cfg = config or FusionConfig()
    audio_binary = np.asarray(audio_binary, dtype=bool)
    valid = np.asarray(valid, dtype=bool)

    n = np.asarray(features["n_detections"], dtype=np.float64)
    disp = np.asarray(features["displacement"], dtype=np.float64)
    sym = np.asarray(features["cross_net_symmetry"], dtype=np.float64)

    out = audio_binary.copy()

    if cfg.enable_veto:
        veto_cond = audio_binary & valid & (n < cfg.veto_max_detections)
        if cfg.enable_displacement_gate:
            veto_cond = veto_cond & (disp < cfg.veto_max_displacement)
        out[runs_at_least(veto_cond, cfg.hysteresis)] = False

    if cfg.enable_sustain:
        sustain_cond = (
            (~audio_binary)
            & valid
            & (n >= cfg.sustain_min_detections)
            & (sym >= cfg.sustain_min_symmetry)
        )
        out[runs_at_least(sustain_cond, cfg.hysteresis)] = True

    return out
