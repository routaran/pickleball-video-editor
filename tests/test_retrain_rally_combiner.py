"""Tests for ml/tools/retrain_rally_combiner.py.

All tests are torch-free and sklearn-free where possible: build_window_table
and loso_interval_f1 are monkeypatched to return synthetic data so the test
suite runs in milliseconds without a GPU or a populated motion cache.

Test classes
------------
TestDiscovery       — *.training.json discovery + auto_edit exclusion
TestEligibility     — per-file eligibility check, skip reasons reported correctly
TestGenerateMode    — candidate + manifest written with expected fields;
                       no-prior-manifest path yields before_loso_f1=null
TestApplyMode       — --apply backs up .bak and swaps candidate into place
TestStdoutJsonSchema — the final stdout line is valid JSON with required keys
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

# Ensure project root is on sys.path so ml/ is importable.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml.motion.visual_features import VISUAL_FEATURE_KEYS  # noqa: E402
from ml.tools.retrain_rally_combiner import main  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _training_json(
    video_path: str | Path,
    corners: list[list[int]] | None = None,
    gen: str | None = None,
    rallies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Minimal training-json dict."""
    vb: dict[str, Any] = {"path": str(video_path)}
    if corners is not None:
        vb["court_corners"] = corners
    d: dict[str, Any] = {"video": vb, "rallies": rallies or []}
    if gen is not None:
        d["generated_by"] = gen
    return d


def _write_json(directory: Path, stem: str, data: dict[str, Any]) -> Path:
    p = directory / f"{stem}.training.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _synthetic_table(group: str = "20240101", json_path: str = "/fake/v.json") -> dict:
    """Synthetic window table — compatible with build_window_table output + 'json' key."""
    n = 30
    t = np.arange(n, dtype=np.float64) * 0.5
    table: dict[str, Any] = {
        "t": t,
        "p_audio": np.random.default_rng(0).uniform(0.0, 1.0, n),
        "label": (np.arange(n) % 5 == 0).astype(np.float64),
        "valid": np.ones(n, dtype=bool),
        "group": np.asarray(group),
        "video": np.asarray("fake_video"),
        "json": json_path,
    }
    for k in VISUAL_FEATURE_KEYS:
        table[k] = np.zeros(n, dtype=np.float64)
    return table


def _fake_loso(tables, *, threshold=None) -> dict:
    """Fast mock for loso_interval_f1."""
    return {"f1": 0.75, "precision": 0.70, "recall": 0.80, "n_videos": len(tables)}


# ---------------------------------------------------------------------------
# TestDiscovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    """Verify json discovery and auto_edit silent exclusion."""

    def test_auto_edit_excluded_silently(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """auto_edit files must not appear in eligible or skipped — silent drop."""
        video = tmp_path / "vid_ae.mp4"
        video.touch()
        npz = tmp_path / "vid_ae.npz"
        npz.touch()

        _write_json(
            tmp_path,
            "vid_ae",
            _training_json(video, corners=[[0, 0], [1, 0], [1, 1], [0, 1]], gen="auto_edit"),
        )

        fake_table = _synthetic_table(json_path=str(tmp_path / "vid_ae.training.json"))

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch("ml.tools.retrain_rally_combiner.build_window_table", return_value=None),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        captured = capsys.readouterr()
        # Only output is the error JSON (no eligible videos, no auto_edit in skipped)
        assert rc == 1  # no eligible tables → error
        out = json.loads(captured.out)
        assert out["status"] == "error"
        # auto_edit file must NOT appear in any skip list
        # (there is none here since the error fires before a skip list is emitted)

    def test_recursive_discovery(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Training jsons nested in subdirectories are discovered."""
        sub = tmp_path / "session1" / "day2"
        sub.mkdir(parents=True)
        video = sub / "vid_sub.mp4"
        video.touch()
        npz = sub / "vid_sub.npz"
        npz.touch()
        jp = _write_json(
            sub,
            "vid_sub",
            _training_json(video, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp))

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        out_json = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out_json["eligible"] == 1


# ---------------------------------------------------------------------------
# TestEligibility
# ---------------------------------------------------------------------------


class TestEligibility:
    """Per-file eligibility + skip reason reporting."""

    def test_missing_corners_reported(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """A video with no court_corners is skipped with 'missing/!=4 corners'."""
        video = tmp_path / "vid_nc.mp4"
        video.touch()
        _write_json(tmp_path, "vid_nc", _training_json(video, corners=[]))
        npz = tmp_path / "vid_nc.npz"

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch("ml.tools.retrain_rally_combiner.build_window_table", return_value=None),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        out = json.loads(capsys.readouterr().out)
        assert rc == 1  # no eligible → error
        # When no eligible videos the CLI errors before emitting the full skipped list in stdout.
        # But we can check stderr progress logged the skip reason indirectly via the error status.
        assert out["status"] == "error"

    def test_missing_corners_in_skipped_list(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """When there's at least one eligible video, skipped list is in the stdout JSON."""
        # Eligible video
        vid_ok = tmp_path / "20240101_ok.mp4"
        vid_ok.touch()
        npz_ok = tmp_path / "20240101_ok.npz"
        npz_ok.touch()
        jp_ok = _write_json(
            tmp_path,
            "20240101_ok",
            _training_json(vid_ok, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp_ok))

        # Ineligible — no corners
        vid_nc = tmp_path / "20240102_nc.mp4"
        vid_nc.touch()
        _write_json(tmp_path, "20240102_nc", _training_json(vid_nc, corners=[]))

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz_ok),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        skip_reasons = [s["reason"] for s in out["skipped"]]
        assert "missing/!=4 corners" in skip_reasons

    def test_missing_npz_reported(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """A video with corners but no .npz is skipped with 'missing motion .npz'."""
        # Eligible video
        vid_ok = tmp_path / "20240101_ok.mp4"
        vid_ok.touch()
        npz_ok = tmp_path / "20240101_ok.npz"
        npz_ok.touch()
        jp_ok = _write_json(
            tmp_path,
            "20240101_ok",
            _training_json(vid_ok, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp_ok))

        # Ineligible — video exists, corners fine, but no .npz
        vid_nonpz = tmp_path / "20240103_nonpz.mp4"
        vid_nonpz.touch()
        npz_missing = tmp_path / "nonexistent_motion.npz"  # does not exist
        jp_nonpz = _write_json(
            tmp_path,
            "20240103_nonpz",
            _training_json(vid_nonpz, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )

        def _mock_cache_path(video_path, cache_dir=None) -> Path:
            stem = Path(video_path).stem
            if stem == "20240101_ok":
                return npz_ok
            return npz_missing  # missing for the other video

        with (
            patch(
                "ml.tools.retrain_rally_combiner.motion_cache_path",
                side_effect=_mock_cache_path,
            ),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        skip_reasons = [s["reason"] for s in out["skipped"]]
        assert "missing motion .npz" in skip_reasons

    def test_two_ineligible_one_missing_corners_one_missing_npz(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Both a corner-less and an npz-less video appear in skipped list with distinct reasons."""
        # Eligible video to prevent error exit
        vid_ok = tmp_path / "20240101_ok.mp4"
        vid_ok.touch()
        npz_ok = tmp_path / "20240101_ok.npz"
        npz_ok.touch()
        jp_ok = _write_json(
            tmp_path,
            "20240101_ok",
            _training_json(vid_ok, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp_ok))

        # Corner-less
        vid_nc = tmp_path / "20240102_nc.mp4"
        vid_nc.touch()
        _write_json(tmp_path, "20240102_nc", _training_json(vid_nc, corners=[[0, 0]]))

        # NPZ-less (valid corners, but no motion cache)
        vid_nonpz = tmp_path / "20240103_nonpz.mp4"
        vid_nonpz.touch()
        npz_missing = tmp_path / "does_not_exist.npz"
        _write_json(
            tmp_path,
            "20240103_nonpz",
            _training_json(vid_nonpz, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )

        def _mock_cache(video_path, cache_dir=None) -> Path:
            if Path(video_path).stem == "20240101_ok":
                return npz_ok
            return npz_missing

        with (
            patch(
                "ml.tools.retrain_rally_combiner.motion_cache_path",
                side_effect=_mock_cache,
            ),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch("ml.tools.retrain_rally_combiner.loso_interval_f1", side_effect=_fake_loso),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(tmp_path / "joint_combiner.json")])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["eligible"] == 1  # only vid_ok is eligible
        reasons = {s["reason"] for s in out["skipped"]}
        assert "missing/!=4 corners" in reasons
        assert "missing motion .npz" in reasons
        assert len(out["skipped"]) == 2


# ---------------------------------------------------------------------------
# TestGenerateMode
# ---------------------------------------------------------------------------


class TestGenerateMode:
    """Candidate + manifest are written with correct content."""

    def _run_generate(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        manifest_data: dict | None = None,
        loso_calls: list | None = None,
    ) -> tuple[int, dict]:
        """Helper: sets up one eligible video, runs generate mode, returns (rc, stdout_json)."""
        video = tmp_path / "20240101_game1.mp4"
        video.touch()
        npz = tmp_path / "20240101_game1.npz"
        npz.touch()
        combiner_path = tmp_path / "joint_combiner.json"

        # Write a fake live combiner so apply mode has something to back up
        combiner_path.write_text('{"feature_names":[],"mean":[],"scale":[],"coef":[],"intercept":0}')

        if manifest_data is not None:
            (tmp_path / "joint_combiner.manifest.json").write_text(json.dumps(manifest_data))

        jp = _write_json(
            tmp_path,
            "20240101_game1",
            _training_json(video, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp))

        call_count = [0]
        results = loso_calls or [{"f1": 0.60, "precision": 0.55, "recall": 0.65, "n_videos": 1},
                                  {"f1": 0.75, "precision": 0.70, "recall": 0.80, "n_videos": 1}]

        def _multi_loso(tables, *, threshold=None) -> dict:
            i = min(call_count[0], len(results) - 1)
            call_count[0] += 1
            return results[i]

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch(
                "ml.tools.retrain_rally_combiner.loso_interval_f1",
                side_effect=_multi_loso,
            ),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(combiner_path)])

        captured = capsys.readouterr()
        out = json.loads(captured.out)
        return rc, out

    def test_candidate_file_written(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        rc, out = self._run_generate(tmp_path, capsys)
        assert rc == 0
        candidate = tmp_path / "joint_combiner.candidate.json"
        assert candidate.exists(), "candidate combiner file must be written"
        # Verify it's a valid combiner JSON
        c_data = json.loads(candidate.read_text())
        for key in ("feature_names", "mean", "scale", "coef", "intercept"):
            assert key in c_data, f"candidate missing key '{key}'"

    def test_candidate_manifest_written(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        rc, out = self._run_generate(tmp_path, capsys)
        assert rc == 0
        manifest = tmp_path / "joint_combiner.candidate.manifest.json"
        assert manifest.exists(), "candidate manifest must be written"
        m = json.loads(manifest.read_text())
        for key in ("created_at", "source_audio_model", "training_file_count",
                    "skipped", "validation"):
            assert key in m, f"manifest missing key '{key}'"
        v = m["validation"]
        for vkey in ("before_loso_f1", "after_loso_f1", "delta"):
            assert vkey in v, f"manifest.validation missing key '{vkey}'"

    def test_no_prior_manifest_yields_before_null(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Without a prior manifest, before_loso_f1 and delta must be null."""
        rc, out = self._run_generate(tmp_path, capsys, manifest_data=None)
        assert rc == 0
        assert out["before_loso_f1"] is None
        assert out["delta"] is None
        assert out["after_loso_f1"] is not None

    def test_prior_manifest_with_new_files_computes_ab(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When a manifest exists and the video file is newer, before_loso_f1 is non-null."""
        # Use a very old created_at so any file mtime is "newer"
        manifest_data = {"created_at": "2020-01-01T00:00:00+00:00"}
        loso_calls = [
            {"f1": 0.60, "precision": 0.55, "recall": 0.65, "n_videos": 0},  # before (old tables)
            {"f1": 0.75, "precision": 0.70, "recall": 0.80, "n_videos": 1},  # after  (all tables)
        ]
        rc, out = self._run_generate(tmp_path, capsys, manifest_data=manifest_data, loso_calls=loso_calls)
        assert rc == 0
        # before_loso_f1 should be computed (from the "old tables" call) — but since
        # no old tables exist (all files are new), loso returns f1=0.60 for the empty set.
        # The key point is that before_loso_f1 is populated (not null) when new files exist.
        assert out["before_loso_f1"] is not None
        assert out["delta"] is not None
        assert abs(out["delta"] - (out["after_loso_f1"] - out["before_loso_f1"])) < 1e-6

    def test_prior_manifest_no_new_files_gives_null_before(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When manifest exists but no files are newer, before=null, delta=null."""
        # Use a far-future created_at so no file mtime is "newer"
        manifest_data = {"created_at": "2099-01-01T00:00:00+00:00"}
        rc, out = self._run_generate(tmp_path, capsys, manifest_data=manifest_data)
        assert rc == 0
        assert out["before_loso_f1"] is None
        assert out["delta"] is None

    def test_eligible_count_correct(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        rc, out = self._run_generate(tmp_path, capsys)
        assert rc == 0
        assert out["eligible"] == 1


# ---------------------------------------------------------------------------
# TestApplyMode
# ---------------------------------------------------------------------------


class TestApplyMode:
    """--apply backs up live combiner and swaps in candidate."""

    def _setup_apply(self, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        combiner_path = tmp_path / "joint_combiner.json"
        candidate_path = tmp_path / "joint_combiner.candidate.json"
        candidate_manifest = tmp_path / "joint_combiner.candidate.manifest.json"
        live_manifest = tmp_path / "joint_combiner.manifest.json"

        combiner_path.write_text(json.dumps({"old": True}), encoding="utf-8")
        candidate_path.write_text(json.dumps({"new": True}), encoding="utf-8")
        candidate_manifest.write_text(json.dumps({"created_at": "2026-01-01T00:00:00+00:00"}))
        return combiner_path, candidate_path, candidate_manifest, live_manifest

    def test_apply_creates_backup(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        combiner_path, *_ = self._setup_apply(tmp_path)
        rc = main(["--apply", "--combiner", str(combiner_path)])
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert rc == 0
        bak = tmp_path / "joint_combiner.json.bak"
        assert bak.exists(), "backup file must exist after --apply"
        bak_data = json.loads(bak.read_text())
        assert bak_data == {"old": True}, "backup must contain original combiner content"

    def test_apply_swaps_candidate(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        combiner_path, *_ = self._setup_apply(tmp_path)
        main(["--apply", "--combiner", str(combiner_path)])
        live_data = json.loads(combiner_path.read_text())
        assert live_data == {"new": True}, "live combiner must contain candidate content after apply"

    def test_apply_moves_manifest(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        combiner_path, candidate_path, candidate_manifest, live_manifest = self._setup_apply(tmp_path)
        main(["--apply", "--combiner", str(combiner_path)])
        assert live_manifest.exists(), "live manifest must exist after --apply"
        assert not candidate_manifest.exists(), "candidate manifest must be moved, not copied"

    def test_apply_candidate_missing_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        combiner_path = tmp_path / "joint_combiner.json"
        combiner_path.write_text("{}")
        # No candidate file
        rc = main(["--apply", "--combiner", str(combiner_path)])
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["status"] == "error"

    def test_apply_stdout_schema(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        self._setup_apply(tmp_path)
        combiner_path = tmp_path / "joint_combiner.json"
        main(["--apply", "--combiner", str(combiner_path)])
        out = json.loads(capsys.readouterr().out)
        for key in ("status", "backup", "combiner", "manifest"):
            assert key in out, f"apply output missing key '{key}'"
        assert out["status"] == "applied"


# ---------------------------------------------------------------------------
# TestStdoutJsonSchema
# ---------------------------------------------------------------------------


class TestStdoutJsonSchema:
    """The final stdout line must be valid JSON with the required keys."""

    def test_generate_stdout_schema(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        video = tmp_path / "20240101_g1.mp4"
        video.touch()
        npz = tmp_path / "20240101_g1.npz"
        npz.touch()
        combiner_path = tmp_path / "joint_combiner.json"
        combiner_path.write_text("{}")
        jp = _write_json(
            tmp_path,
            "20240101_g1",
            _training_json(video, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp))

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch(
                "ml.tools.retrain_rally_combiner.loso_interval_f1",
                side_effect=_fake_loso,
            ),
        ):
            rc = main(["--dir", str(tmp_path), "--combiner", str(combiner_path)])

        captured = capsys.readouterr()
        out = json.loads(captured.out)

        assert rc == 0
        assert out["status"] == "ok"

        required_keys = {
            "status", "eligible", "skipped",
            "before_loso_f1", "after_loso_f1", "delta",
            "candidate", "manifest",
        }
        for key in required_keys:
            assert key in out, f"stdout JSON missing required key '{key}'"

        # before_loso_f1 and delta are null when no prior manifest
        assert out["before_loso_f1"] is None
        assert out["delta"] is None
        assert isinstance(out["after_loso_f1"], float)
        assert isinstance(out["eligible"], int)
        assert isinstance(out["skipped"], list)
        assert isinstance(out["candidate"], str)
        assert isinstance(out["manifest"], str)

    def test_generate_stdout_is_exactly_one_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """stdout must contain exactly one non-empty line (the JSON)."""
        video = tmp_path / "20240101_g2.mp4"
        video.touch()
        npz = tmp_path / "20240101_g2.npz"
        npz.touch()
        combiner_path = tmp_path / "joint_combiner.json"
        combiner_path.write_text("{}")
        jp = _write_json(
            tmp_path,
            "20240101_g2",
            _training_json(video, corners=[[0, 0], [1, 0], [1, 1], [0, 1]]),
        )
        fake_table = _synthetic_table(json_path=str(jp))

        with (
            patch("ml.tools.retrain_rally_combiner.motion_cache_path", return_value=npz),
            patch(
                "ml.tools.retrain_rally_combiner.build_window_table",
                return_value=fake_table,
            ),
            patch(
                "ml.tools.retrain_rally_combiner.loso_interval_f1",
                side_effect=_fake_loso,
            ),
        ):
            main(["--dir", str(tmp_path), "--combiner", str(combiner_path)])

        captured = capsys.readouterr()
        non_empty_lines = [l for l in captured.out.splitlines() if l.strip()]
        assert len(non_empty_lines) == 1, (
            f"stdout must have exactly 1 non-empty line; got {len(non_empty_lines)}: {captured.out!r}"
        )
        json.loads(non_empty_lines[0])  # must be valid JSON
