"""Tests for WSL/Windows path display helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.core.video.display_paths import to_file_uri, to_windows_path


def test_mnt_drive_fallback() -> None:
    with patch("cocli.core.video.display_paths.shutil.which", return_value=None):
        assert to_windows_path(Path("/mnt/d/Video/clip.mp4")) == r"D:\Video\clip.mp4"


def test_wslpath_preferred() -> None:
    mock_run = MagicMock(
        returncode=0,
        stdout=r"\\wsl.localhost\Debian\home\me\clip.mp4" + "\n",
        stderr="",
    )
    with (
        patch("cocli.core.video.display_paths.shutil.which", return_value="/usr/bin/wslpath"),
        patch("cocli.core.video.display_paths.subprocess.run", return_value=mock_run),
    ):
        win = to_windows_path(Path("/home/me/clip.mp4"))
    assert win == r"\\wsl.localhost\Debian\home\me\clip.mp4"


def test_file_uri_from_unc() -> None:
    uri = to_file_uri(
        Path("/home/me/clip.mp4"),
        windows_path=r"\\wsl.localhost\Debian\home\me\clip.mp4",
    )
    assert uri.startswith("file://wsl.localhost/")
    assert "clip.mp4" in uri


def test_file_uri_from_drive_letter() -> None:
    uri = to_file_uri(Path("/mnt/d/a.mp4"), windows_path=r"D:\Video\a.mp4")
    assert uri.startswith("file:///D:/")
    assert uri.endswith("a.mp4") or "a.mp4" in uri
