from __future__ import annotations

from typing import Any, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ..base import BaseModalScreen


class MarkMenuScreen(BaseModalScreen[Optional[str]]):
    """Prefix menu for ``m`` then a letter. ``i`` invalid, ``x`` illegitimate."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="mark-menu-dialog"):
            yield Static("[bold]Mark as[/bold]", id="mark-menu-title")
            yield Static("[bold]i[/]  Invalid — doesn't match scrape or filter")
            yield Static("[bold]x[/]  Illegitimate — ad-injected / not a real business")
            yield Static("[dim]esc cancel[/]", id="mark-menu-hint")

    def on_key(self, event: events.Key) -> None:
        if event.key == "i":
            self.dismiss("invalid")
        elif event.key == "x":
            self.dismiss("illegitimate")
        elif event.key in ("escape", "n", "q"):
            self.dismiss(None)
        event.stop()
