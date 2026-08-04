"""Tests for video path resolution and add/import CLI wiring."""

import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cocli.commands.video import app, resolve_video_path

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (Rich styles split e.g. -- into separate spans)."""
    return _ANSI_RE.sub("", text)


class TestResolveVideoPath:
    def test_linux_absolute_path_unchanged(self) -> None:
        assert resolve_video_path("/mnt/d/Video/clip.mp4") == Path(
            "/mnt/d/Video/clip.mp4"
        )

    def test_strips_quotes(self) -> None:
        assert resolve_video_path('"/home/me/clip.mp4"') == Path("/home/me/clip.mp4")
        assert resolve_video_path("'/home/me/clip.mp4'") == Path("/home/me/clip.mp4")

    def test_windows_backslash_path_maps_on_linux(self) -> None:
        with patch("cocli.commands.video.platform.system", return_value="Linux"):
            result = resolve_video_path(r"D:\Video\task-agent-intro-shotcut.mp4")
        assert result == Path("/mnt/d/Video/task-agent-intro-shotcut.mp4")

    def test_windows_forward_slash_path_maps_on_linux(self) -> None:
        with patch("cocli.commands.video.platform.system", return_value="Linux"):
            result = resolve_video_path("D:/Video/clip.mp4")
        assert result == Path("/mnt/d/Video/clip.mp4")

    def test_windows_path_drive_only(self) -> None:
        with patch("cocli.commands.video.platform.system", return_value="Linux"):
            result = resolve_video_path("E:\\")
        assert result == Path("/mnt/e")

    def test_windows_path_unchanged_on_windows(self) -> None:
        with patch("cocli.commands.video.platform.system", return_value="Windows"):
            result = resolve_video_path(r"D:\Video\clip.mp4")
        # Path may normalize separators; keep drive letter form
        assert str(result) in (r"D:\Video\clip.mp4", r"D:/Video/clip.mp4") or (
            result.drive.upper() == "D:" and result.name == "clip.mp4"
        )


class TestAddImportCli:
    def test_import_is_registered_alias(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "import" in result.output

    def test_add_help_mentions_paths_and_normalize(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["add", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--normalize" in output
        # Path guidance (backslash form may be escaped in help)
        assert "Linux" in output or "/path" in output or "mnt" in output

    def test_import_help_matches_add(self) -> None:
        runner = CliRunner()
        add_help = runner.invoke(app, ["add", "--help"])
        import_help = runner.invoke(app, ["import", "--help"])
        assert add_help.exit_code == 0
        assert import_help.exit_code == 0
        assert "--normalize" in _strip_ansi(import_help.output)
