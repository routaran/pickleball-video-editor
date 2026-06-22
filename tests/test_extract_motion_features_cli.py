"""Tests for the extract_motion_features single-video CLI contract.

Only the light, pure-Python argument handling is exercised here (the heavy
detector imports in the tool are lazy, so importing the module is cheap and
cv2/ultralytics-free).
"""

from __future__ import annotations

from ml.tools.extract_motion_features import _parse_corners_json, main


def test_parse_corners_json_valid() -> None:
    corners = _parse_corners_json("[[121,784],[1813,807],[1137,474],[790,472]]")
    assert corners == [(121, 784), (1813, 807), (1137, 474), (790, 472)]


def test_parse_corners_json_wrong_count() -> None:
    assert _parse_corners_json("[[1,2],[3,4],[5,6]]") is None


def test_parse_corners_json_malformed() -> None:
    assert _parse_corners_json("not json") is None
    assert _parse_corners_json("[[1],[2],[3],[4]]") is None


def test_main_requires_both_video_and_corners(capsys) -> None:
    # --video without --corners-json is a usage error (exit 2), no detector run.
    rc = main(["--video", "/tmp/does-not-matter.mp4"])
    assert rc == 2
    assert "must be supplied together" in capsys.readouterr().err


def test_main_rejects_missing_video(tmp_path, capsys) -> None:
    rc = main([
        "--video", str(tmp_path / "missing.mp4"),
        "--corners-json", "[[1,2],[3,4],[5,6],[7,8]]",
    ])
    assert rc == 2
    assert "video not found" in capsys.readouterr().err
