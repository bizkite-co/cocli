import re
import subprocess

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (Rich styles split e.g. -- into separate spans)."""
    return _ANSI_RE.sub("", text)


def test_cocli_help():
    """Ensure cocli main help displays Options and Commands."""
    # Use python3 cocli/main.py to trigger the self-wrapper logic
    result = subprocess.run(
        ["python3", "cocli/main.py", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    stdout = _strip_ansi(result.stdout)
    assert "Options" in stdout
    assert "Commands" in stdout


def test_cocli_video_help():
    """Ensure cocli video help displays Options and Commands."""
    result = subprocess.run(
        ["python3", "cocli/main.py", "video", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    stdout = _strip_ansi(result.stdout)
    assert "Options" in stdout
    assert "Commands" in stdout


def test_cocli_video_upload_help():
    """Ensure cocli video upload help displays Options and Commands."""
    result = subprocess.run(
        ["python3", "cocli/main.py", "video", "upload", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    stdout = _strip_ansi(result.stdout)
    assert "Options" in stdout
    assert "--campaign" in stdout
    assert "--video" in stdout
    assert "--privacy" in stdout
    assert "--dry-run" in stdout


def test_cocli_video_upload_missing_config():
    """Test that upload fails gracefully when campaign doesn't exist."""
    result = subprocess.run(
        [
            "python3",
            "cocli/main.py",
            "video",
            "upload",
            "-c",
            "nonexistent-campaign",
            "-v",
            "test-video",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Campaign directory not found" in result.stderr
