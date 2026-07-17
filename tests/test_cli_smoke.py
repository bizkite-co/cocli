import re
import subprocess


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (Rich help splits '--' across styles)."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cocli_help():
    """Ensure cocli main help displays Options and Commands."""
    # Use python3 cocli/main.py to trigger the self-wrapper logic
    result = subprocess.run(
        ["python3", "cocli/main.py", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Options" in result.stdout
    assert "Commands" in result.stdout


def test_cocli_video_help():
    """Ensure cocli video help displays Options and Commands."""
    result = subprocess.run(
        ["python3", "cocli/main.py", "video", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Options" in result.stdout
    assert "Commands" in result.stdout


def test_cocli_video_upload_help():
    """Ensure cocli video upload help displays Options and Commands."""
    result = subprocess.run(
        ["python3", "cocli/main.py", "video", "upload", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    plain = _strip_ansi(result.stdout)
    assert "Options" in plain
    assert "--campaign" in plain
    assert "--video" in plain
    assert "--privacy" in plain
    assert "--dry-run" in plain


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
