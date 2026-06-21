"""Tests for ml.motion.fusion (veto/sustain + hysteresis)."""

from __future__ import annotations

import numpy as np

from ml.motion.fusion import FusionConfig, fuse_binary, runs_at_least


def _feats(n, disp, sym):
    w = len(n)
    return {
        "n_detections": np.asarray(n, dtype=float),
        "displacement": np.asarray(disp, dtype=float),
        "cross_net_symmetry": np.asarray(sym, dtype=float),
        "spatial_std": np.zeros(w),
    }


def test_runs_at_least_drops_short_runs():
    mask = np.array([True, True, False, True, True, True])
    out = runs_at_least(mask, 3)
    np.testing.assert_array_equal(
        out, [False, False, False, True, True, True]
    )


def test_runs_at_least_n_le_one_is_identity():
    mask = np.array([True, False, True])
    np.testing.assert_array_equal(runs_at_least(mask, 1), mask)


def test_veto_flips_sustained_low_motion_rally():
    w = 5
    audio = np.ones(w, dtype=bool)  # audio says rally everywhere
    feats = _feats(n=[0] * w, disp=[0.0] * w, sym=[0.0] * w)
    valid = np.ones(w, dtype=bool)
    out = fuse_binary(audio, feats, valid, FusionConfig(hysteresis=3))
    assert not out.any()  # all vetoed to dead time


def test_veto_default_ignores_displacement():
    # Locked-in default: gate OFF, so a low-count rally is vetoed on the
    # detection count alone even when centroid motion is high (noisy disp).
    w = 5
    audio = np.ones(w, dtype=bool)
    feats = _feats(n=[0] * w, disp=[0.5] * w, sym=[0.0] * w)  # high displacement
    valid = np.ones(w, dtype=bool)
    out = fuse_binary(audio, feats, valid, FusionConfig(hysteresis=3))
    assert not out.any()  # vetoed despite high displacement (gate off)


def test_displacement_gate_blocks_veto_when_re_enabled():
    # Opt back into the gate (the future per-track-displacement path): high
    # motion now blocks the veto, leaving the audio decision untouched.
    w = 5
    audio = np.ones(w, dtype=bool)
    feats = _feats(n=[0] * w, disp=[0.5] * w, sym=[0.0] * w)
    valid = np.ones(w, dtype=bool)
    cfg = FusionConfig(
        hysteresis=3, enable_displacement_gate=True, veto_max_displacement=0.01
    )
    out = fuse_binary(audio, feats, valid, cfg)
    np.testing.assert_array_equal(out, audio)  # high motion -> no veto


def test_veto_blocked_when_too_short_for_hysteresis():
    # Veto condition holds for only 2 consecutive windows (idx 1,2); hysteresis=3.
    audio = np.ones(5, dtype=bool)
    feats = _feats(n=[9, 0, 0, 9, 9], disp=[1.0, 0.0, 0.0, 1.0, 1.0], sym=[0] * 5)
    valid = np.ones(5, dtype=bool)
    out = fuse_binary(audio, feats, valid, FusionConfig(hysteresis=3))
    np.testing.assert_array_equal(out, audio)  # nothing flipped


def test_sustain_bridges_dead_time_with_full_court():
    w = 4
    audio = np.zeros(w, dtype=bool)  # audio says dead time
    feats = _feats(n=[4] * w, disp=[0.05] * w, sym=[1.0] * w)
    valid = np.ones(w, dtype=bool)
    out = fuse_binary(audio, feats, valid, FusionConfig(hysteresis=3))
    assert out.all()  # sustained to rally


def test_invalid_windows_are_never_overridden():
    w = 5
    audio = np.ones(w, dtype=bool)
    feats = _feats(n=[0] * w, disp=[0.0] * w, sym=[0.0] * w)  # veto numerically true
    valid = np.zeros(w, dtype=bool)  # ...but no motion features available
    out = fuse_binary(audio, feats, valid, FusionConfig(hysteresis=3))
    np.testing.assert_array_equal(out, audio)  # audio-only fallback


def test_disable_flags_short_circuit():
    w = 4
    audio = np.zeros(w, dtype=bool)
    feats = _feats(n=[4] * w, disp=[0.05] * w, sym=[1.0] * w)
    valid = np.ones(w, dtype=bool)
    out = fuse_binary(
        audio, feats, valid, FusionConfig(hysteresis=3, enable_sustain=False)
    )
    np.testing.assert_array_equal(out, audio)  # sustain disabled -> unchanged
