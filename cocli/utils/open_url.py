"""Open a URL in the user's real desktop browser.

Python's ``webbrowser`` module looks for Linux tools such as ``xdg-open``
and ``chromium``. On WSL2 those often do not exist, so ``webbrowser.open``
returns False while callers still show an "Opening ..." notification.

Playwright's bundled Chromium is a scraper, not the desktop browser, and
must not be used here.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


def is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    try:
        version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl" in version


def open_url(url: str) -> bool:
    """Launch ``url`` in the desktop browser. Returns True if a launcher started."""
    for command in _candidate_commands(url):
        if spawn_detached(command):
            logger.debug("Opened URL with %s", command[0])
            return True
    if _webbrowser_open(url):
        return True
    logger.warning("Could not open URL in a desktop browser: %s", url)
    return False


def _escape_for_cmd_exe(url: str) -> str:
    """Escape cmd.exe metacharacters in a URL passed via ``cmd /c``.

    cmd.exe's own command-line parser treats & | < > ( ) as operators even
    inside an argv element that arrived quoted from the calling process -
    the OS-level argv boundary doesn't protect against cmd.exe's *own*
    reparsing of the reconstructed command line. An unescaped `&` (common
    in any URL with more than one query parameter) silently truncates the
    URL at that point and runs whatever follows as a separate command -
    confirmed 2026-09-14: this dropped the phone-number parameter from
    Google Voice call URLs (`?authuser=...&a=nc,+15551234567`), so Google
    Voice opened to the right account but never pre-filled the number.
    ``^`` is cmd.exe's escape character, so it must be escaped first.
    """
    for ch in "^&|<>()":
        url = url.replace(ch, "^" + ch)
    return url


def _candidate_commands(url: str) -> list[list[str]]:
    commands: list[list[str]] = []
    if sys.platform == "darwin":
        open_bin = shutil.which("open")
        if open_bin:
            commands.append([open_bin, url])
        return commands

    if sys.platform == "win32":
        cmd_exe = shutil.which("cmd") or shutil.which("cmd.exe")
        if cmd_exe:
            commands.append([cmd_exe, "/c", "start", "", _escape_for_cmd_exe(url)])
        return commands

    if is_wsl():
        wslview = shutil.which("wslview")
        if wslview:
            commands.append([wslview, url])
        cmd_exe = shutil.which("cmd.exe")
        if cmd_exe:
            commands.append([cmd_exe, "/c", "start", "", _escape_for_cmd_exe(url)])
        explorer = shutil.which("explorer.exe")
        if explorer:
            commands.append([explorer, url])

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        commands.append([xdg_open, url])
    gio = shutil.which("gio")
    if gio:
        commands.append([gio, "open", url])
    return commands


def spawn_detached(command: Sequence[str]) -> bool:
    # Regression (2026-09-17): a TUI test that pressed "p" but only
    # mocked company_detail's own open_url() call - not the calling
    # provider it now goes through - actually launched the real
    # msedge_proxy.exe on Mark's machine on every test run, because
    # nothing here stops a real subprocess from being spawned when a
    # test forgets to mock. This is the single choke point every
    # real launch (browser tab or Windows PWA) passes through, so the
    # safety net belongs here, not in each caller. PYTEST_CURRENT_TEST
    # is set by pytest itself for the duration of every test - no
    # fixture/config required.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.debug("spawn_detached: refusing to launch %s under pytest", command)
        return False
    try:
        subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        logger.debug("Failed to spawn %s: %s", command, exc)
        return False
    return True


def _webbrowser_open(url: str) -> bool:
    # Same rationale as the guard in spawn_detached() - this is the other
    # path open_url() can use to actually launch something.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        controller = webbrowser.get()
    except webbrowser.Error:
        return False
    name = str(getattr(controller, "name", "") or getattr(controller, "basename", "") or "")
    if "ms-playwright" in name:
        return False
    try:
        return bool(controller.open(url, new=2))
    except Exception:
        return False
