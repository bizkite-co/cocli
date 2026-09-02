"""Open a URL in the user's real desktop browser.

Python's ``webbrowser`` module looks for Linux tools such as ``xdg-open``
and ``chromium``. On WSL2 those often do not exist, so ``webbrowser.open``
returns False while callers still show an "Opening ..." notification.

Playwright's bundled Chromium is a scraper, not the desktop browser, and
must not be used here.
"""

from __future__ import annotations

import logging
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
        if _spawn_detached(command):
            logger.debug("Opened URL with %s", command[0])
            return True
    if _webbrowser_open(url):
        return True
    logger.warning("Could not open URL in a desktop browser: %s", url)
    return False


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
            commands.append([cmd_exe, "/c", "start", "", url])
        return commands

    if is_wsl():
        wslview = shutil.which("wslview")
        if wslview:
            commands.append([wslview, url])
        cmd_exe = shutil.which("cmd.exe")
        if cmd_exe:
            commands.append([cmd_exe, "/c", "start", "", url])
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


def _spawn_detached(command: Sequence[str]) -> bool:
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
