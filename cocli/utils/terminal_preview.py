"""Render HTML and Markdown content for terminal viewing using pandoc or fallbacks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Union


def render_html_for_terminal(
    source: Union[str, Path],
    width: int = 76,
    mode: str = "plain",
) -> Optional[str]:
    """Render an HTML file or HTML snippet to formatted terminal text using pandoc.

    Matches the behaviour of Yazi's html.yazi previewer:
    pandoc -f html -t plain --wrap=auto --columns=<width> <path>
    """
    pandoc_bin = shutil.which("pandoc")
    if not pandoc_bin:
        return None

    cols = max(30, width)
    cmd = [pandoc_bin, "-f", "html", "-t", mode, "--wrap=auto", f"--columns={cols}"]

    try:
        if isinstance(source, Path):
            if not source.exists():
                return None
            cmd.append(str(source))
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
        else:
            res = subprocess.run(cmd, input=source, capture_output=True, text=True, timeout=2.0)

        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
    except Exception:
        return None

    return None
