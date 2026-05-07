"""Unit tests for clean_subprocess_env() helper.

Verifies that site-packages entries are stripped from LD_LIBRARY_PATH before
ffmpeg/ffprobe subprocesses are spawned, preventing ABI mismatches from
opencv-python-headless bundled libraries.
"""

import pytest

from src.video._subprocess_env import clean_subprocess_env


def test_polluted_ld_library_path_preserves_system_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/x/site-packages/cv2/.libs:/usr/lib",
    )

    result = clean_subprocess_env()

    assert result.get("LD_LIBRARY_PATH") == "/usr/lib"


def test_only_site_packages_entries_removes_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/x/site-packages/cv2/.libs:/y/site-packages/pillow.libs",
    )

    result = clean_subprocess_env()

    assert "LD_LIBRARY_PATH" not in result


def test_no_ld_library_path_key_absent_in_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)

    result = clean_subprocess_env()

    assert "LD_LIBRARY_PATH" not in result
