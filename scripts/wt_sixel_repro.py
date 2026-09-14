"""Minimal Windows Terminal Sixel-desync repro - no cocli dependencies.

Purpose: isolate the "stale duplicated keymap row above the Footer" artifact
seen in `cocli tui` on Windows Terminal into a ~60-line standalone app, so it
can be attached to a microsoft/terminal issue (or used to check whether a WT
canary build fixes it).

Background (2026-09-13/14 investigation): textual_image's Sixel widget
injects raw DCS payloads plus absolute-cursor escapes into Textual's
differential screen updates. Byte-capture verified the emitted stream is
internally consistent; on Windows Terminal the result nonetheless shows a
stale copy of the footer keymaps that no later repaint clears. Windows
Terminal 1.22+ (Sixel support) is required.

Run inside Windows Terminal (from WSL or Windows Python):

    uv run python scripts/wt_sixel_repro.py

Controls:
    j / k    toggle the text above the image (forces differential updates
             that repaint around the Sixel region, like TUI scrolling)
    q        quit

Watch the bottom of the screen: the Footer keymaps should always occupy
exactly ONE row. If a second, stale keymap row appears directly above the
Footer and never clears, that is the WT-side sixel rendering bug.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image as PILImage
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Static
from textual_image.widget.sixel import Image as SixelImage


def make_test_png() -> Path:
    """A deterministic gradient PNG - no external files needed."""
    img = PILImage.new("RGB", (820, 460))
    px = img.load()
    assert px is not None
    for y in range(img.height):
        for x in range(img.width):
            px[x, y] = (x * 255 // img.width, y * 255 // img.height, 128)
    path = Path(tempfile.gettempdir()) / "wt_sixel_repro.png"
    img.save(path)
    return path


class SixelFooterApp(App[None]):
    """One Sixel image sitting directly above a Textual Footer."""

    CSS = """
    #body { height: 1fr; }
    #image-holder {
        height: 20;
        border-top: solid #444444;
    }
    """

    BINDINGS = [
        ("j", "toggle", "Toggle text"),
        ("k", "toggle", "Toggle text"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, png_path: Path) -> None:
        super().__init__()
        self._png_path = png_path
        self._toggle = False

    def compose(self) -> ComposeResult:
        with Vertical(id="body"):
            yield Static(
                "Sixel + Footer desync repro - press j/k to force differential "
                "updates around the image, q to quit.",
                id="headline",
            )
            yield Static("", id="status")
        with Vertical(id="image-holder"):
            image = SixelImage(str(self._png_path))
            image.styles.width = "1fr"
            image.styles.height = "100%"
            yield image
        yield Footer()

    def action_toggle(self) -> None:
        self._toggle = not self._toggle
        if self._toggle:
            message = "toggle ON - this row changes every keypress, driving partial repaints around the Sixel"
        else:
            message = "toggle OFF"
        self.query_one("#status", Static).update(message)


def main() -> None:
    SixelFooterApp(make_test_png()).run()


if __name__ == "__main__":
    main()