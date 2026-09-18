from __future__ import annotations
from typing import Optional

from cocli.utils.open_url import (
    _candidate_commands,
    _escape_for_cmd_exe,
    copy_to_windows_clipboard,
    open_url,
    spawn_detached,
)


URL = "http://acme.example"
# Real shape from google_voice_url.py - the case that actually broke.
GV_URL = "https://voice.google.com/u/0/calls?authuser=a%40b.com&a=nc,%2B15551234567"


def _which_map(mapping: dict[str, str]):
    def which(name: str) -> Optional[str]:
        return mapping.get(name)

    return which


def test_wsl_candidates_prefer_windows_handlers_not_playwright(monkeypatch) -> None:
    monkeypatch.setattr("cocli.utils.open_url.is_wsl", lambda: True)
    monkeypatch.setattr("cocli.utils.open_url.sys.platform", "linux")
    monkeypatch.setattr(
        "cocli.utils.open_url.shutil.which",
        _which_map(
            {
                "wslview": "/usr/bin/wslview",
                "cmd.exe": "/mnt/c/WINDOWS/system32/cmd.exe",
                "explorer.exe": "/mnt/c/WINDOWS/explorer.exe",
                "xdg-open": "/usr/bin/xdg-open",
                "chromium": "/home/u/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
            }
        ),
    )

    cmds = _candidate_commands(URL)

    assert cmds[0] == ["/usr/bin/wslview", URL]
    assert cmds[1] == ["/mnt/c/WINDOWS/system32/cmd.exe", "/c", "start", "", URL]
    assert cmds[2] == ["/mnt/c/WINDOWS/explorer.exe", URL]
    assert all("ms-playwright" not in part for cmd in cmds for part in cmd)


def test_wsl_without_wslview_uses_cmd_start(monkeypatch) -> None:
    monkeypatch.setattr("cocli.utils.open_url.is_wsl", lambda: True)
    monkeypatch.setattr("cocli.utils.open_url.sys.platform", "linux")
    monkeypatch.setattr(
        "cocli.utils.open_url.shutil.which",
        _which_map(
            {
                "cmd.exe": "/mnt/c/WINDOWS/system32/cmd.exe",
                "explorer.exe": "/mnt/c/WINDOWS/explorer.exe",
            }
        ),
    )

    cmds = _candidate_commands(URL)
    assert cmds[0] == ["/mnt/c/WINDOWS/system32/cmd.exe", "/c", "start", "", URL]


def test_cmd_exe_command_escapes_ampersand(monkeypatch) -> None:
    """2026-09-14 production bug: cmd.exe's own command-line parser treats
    an unescaped `&` as a command separator even though the URL arrived as
    a single argv element - it silently truncated Google Voice call URLs
    at the `&`, dropping the phone-number parameter. Google Voice opened
    to the right account but never pre-filled the number to call."""
    monkeypatch.setattr("cocli.utils.open_url.is_wsl", lambda: True)
    monkeypatch.setattr("cocli.utils.open_url.sys.platform", "linux")
    monkeypatch.setattr(
        "cocli.utils.open_url.shutil.which",
        _which_map({"cmd.exe": "/mnt/c/WINDOWS/system32/cmd.exe"}),
    )

    cmds = _candidate_commands(GV_URL)

    assert cmds[0] == [
        "/mnt/c/WINDOWS/system32/cmd.exe", "/c", "start", "", _escape_for_cmd_exe(GV_URL),
    ]
    assert cmds[0][4] == (
        "https://voice.google.com/u/0/calls?authuser=a%40b.com^&a=nc,%2B15551234567"
    )


def test_escape_for_cmd_exe_round_trips_through_real_cmd_exe() -> None:
    """Only meaningful on WSL with cmd.exe present - skips elsewhere."""
    import shutil
    import subprocess

    cmd_exe = shutil.which("cmd.exe")
    if not cmd_exe:
        import pytest

        pytest.skip("cmd.exe not available in this environment")

    escaped = _escape_for_cmd_exe(GV_URL)
    result = subprocess.run(
        [cmd_exe, "/c", "echo", escaped], capture_output=True, text=True, timeout=30
    )
    assert result.stdout.strip().splitlines()[-1] == GV_URL


def test_linux_non_wsl_uses_xdg_open(monkeypatch) -> None:
    monkeypatch.setattr("cocli.utils.open_url.is_wsl", lambda: False)
    monkeypatch.setattr("cocli.utils.open_url.sys.platform", "linux")
    monkeypatch.setattr(
        "cocli.utils.open_url.shutil.which",
        _which_map({"xdg-open": "/usr/bin/xdg-open"}),
    )

    assert _candidate_commands(URL) == [["/usr/bin/xdg-open", URL]]


def test_open_url_spawns_first_successful_command(monkeypatch) -> None:
    monkeypatch.setattr(
        "cocli.utils.open_url._candidate_commands",
        lambda url: [["xdg-open", url], ["explorer.exe", url]],
    )
    spawned: list[list[str]] = []

    def fake_spawn(command: list[str]) -> bool:
        spawned.append(command)
        return command[0] == "explorer.exe"

    monkeypatch.setattr("cocli.utils.open_url.spawn_detached", fake_spawn)
    webbrowser_called = {"value": False}
    monkeypatch.setattr(
        "cocli.utils.open_url._webbrowser_open",
        lambda url: webbrowser_called.__setitem__("value", True) or False,
    )

    assert open_url(URL) is True
    assert spawned == [["xdg-open", URL], ["explorer.exe", URL]]
    assert webbrowser_called["value"] is False


def test_open_url_does_not_claim_success_when_nothing_launches(monkeypatch) -> None:
    monkeypatch.setattr("cocli.utils.open_url._candidate_commands", lambda url: [])
    monkeypatch.setattr("cocli.utils.open_url.spawn_detached", lambda command: False)
    monkeypatch.setattr("cocli.utils.open_url._webbrowser_open", lambda url: False)

    assert open_url(URL) is False


def test_spawn_detached_refuses_to_launch_under_pytest() -> None:
    """Regression (2026-09-17): a TUI test that forgot to mock the
    calling-provider path it exercised actually launched the real
    msedge_proxy.exe on every test run - nothing stopped a real
    subprocess.Popen from firing just because a test forgot to mock.
    PYTEST_CURRENT_TEST is always set while a test is running (pytest
    sets it itself), so this is true for this test too - proving the
    guard fires without needing to fake being outside pytest."""
    import os

    assert "PYTEST_CURRENT_TEST" in os.environ
    # "true" is a real, harmless binary - if the guard didn't fire this
    # would actually spawn it (and return True).
    assert spawn_detached(["true"]) is False


def test_copy_to_windows_clipboard_refuses_under_pytest() -> None:
    """Same PYTEST_CURRENT_TEST rationale as spawn_detached above - this
    must never actually shell out to clip.exe during a test run."""
    import os

    assert "PYTEST_CURRENT_TEST" in os.environ
    assert copy_to_windows_clipboard("+15551234567") is False


def test_copy_to_windows_clipboard_pipes_text_to_clip_exe(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        "cocli.utils.open_url.shutil.which",
        lambda name: "/mnt/c/WINDOWS/system32/clip.exe" if name == "clip.exe" else None,
    )
    captured: dict[str, object] = {}

    def fake_run(command, input, timeout, check):  # noqa: A002
        captured["command"] = command
        captured["input"] = input
        return None

    monkeypatch.setattr("cocli.utils.open_url.subprocess.run", fake_run)

    assert copy_to_windows_clipboard("+15551234567") is True
    assert captured["command"] == ["/mnt/c/WINDOWS/system32/clip.exe"]
    assert captured["input"] == b"+15551234567"


def test_copy_to_windows_clipboard_returns_false_when_clip_exe_missing(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr("cocli.utils.open_url.shutil.which", lambda name: None)

    assert copy_to_windows_clipboard("+15551234567") is False
