"""Tests for ml.motion.detector.ensure_weights deterministic resolution.

Only the no-download branches are exercised here (an existing checkpoint or an
already-cached target), so the heavy ultralytics dependency is never imported.
The download branch is covered by the integration run in the .venv-motion env.
"""

from __future__ import annotations

from ml.motion.detector import default_weights_dir, ensure_weights


def test_existing_path_used_as_is(tmp_path):
    f = tmp_path / "custom.pt"
    f.write_bytes(b"weights")
    assert ensure_weights(str(f)) == f.resolve()


def test_cached_target_is_reused(tmp_path):
    (tmp_path / "yolov8n.pt").write_bytes(b"weights")
    out = ensure_weights("yolov8n.pt", weights_dir=tmp_path)
    assert out == (tmp_path / "yolov8n.pt").resolve()


def test_bare_name_gets_pt_suffix(tmp_path):
    (tmp_path / "yolov8n.pt").write_bytes(b"weights")
    out = ensure_weights("yolov8n", weights_dir=tmp_path)
    assert out.name == "yolov8n.pt"


def test_default_weights_dir_under_cache():
    # ml/cache/weights/ — consistent with the ml/cache/motion/ feature cache.
    d = default_weights_dir()
    assert d.name == "weights"
    assert d.parent.name == "cache"
