"""Human-facing path display for video CLI (WSL ↔ Windows)."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote

from rich.console import Console
from rich.style import Style


def to_windows_path(path: Path) -> Optional[str]:
    """
    Best-effort conversion of a Linux/WSL path to a Windows path.

    Prefers ``wslpath -w`` when available; falls back to mapping ``/mnt/<drive>/…``
    to ``X:\\…``. Returns None if no conversion applies (native Linux without WSL).
    """
    resolved = path.expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = path

    wslpath = shutil.which("wslpath")
    if wslpath:
        try:
            result = subprocess.run(
                [wslpath, "-w", str(resolved)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                win = (result.stdout or "").strip()
                if win:
                    return win
        except OSError:
            pass

    # /mnt/d/foo -> D:\foo
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", str(resolved))
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"

    # Already on Windows host
    if platform.system() == "Windows":
        return str(resolved)

    return None


def to_file_uri(path: Path, *, windows_path: Optional[str] = None) -> str:
    """
    Build a file:// URI suitable for terminal hyperlinks.

    Prefer a Windows/UNC form when available so Windows hosts (Explorer, VLC)
    can open the link from WSL terminals.
    """
    win = windows_path if windows_path is not None else to_windows_path(path)
    if win:
        # UNC: \\wsl.localhost\Debian\home\... -> file://wsl.localhost/Debian/home/...
        if win.startswith("\\\\"):
            unc = win.lstrip("\\").replace("\\", "/")
            # quote path segments but keep slashes
            parts = unc.split("/")
            return "file://" + "/".join(quote(p, safe="") for p in parts if p != "")
        # Drive letter: C:\foo -> file:///C:/foo
        if re.match(r"^[A-Za-z]:[\\/]", win):
            as_posix = win.replace("\\", "/")
            # file:///C:/path
            return "file:///" + quote(as_posix, safe="/:")
    # POSIX fallback
    resolved = path.expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        pass
    return "file://" + quote(str(resolved), safe="/")


def print_accessible_path(
    console: Console,
    label: str,
    path: Path,
    *,
    style: str = "cyan",
) -> Tuple[str, Optional[str]]:
    """
    Print a path with optional Windows form and a clickable terminal hyperlink.

    ``style`` is a Rich style string (e.g. ``cyan``, ``dim cyan``), not only a color.
    Returns (linux_path, windows_path_or_none).
    """
    linux = str(path.expanduser())
    try:
        linux = str(path.resolve())
    except OSError:
        pass
    win = to_windows_path(path)
    display = win or linux
    uri = to_file_uri(path, windows_path=win)
    # Rich OSC-8 link when the terminal supports it (Windows Terminal, etc.)
    path_style = Style.parse(style) + Style(link=uri)
    console.print(f"{label} ", end="")
    console.print(display, style=path_style)
    if win and win != linux:
        console.print(f"[dim]  (WSL: {linux})[/dim]")
    return linux, win
