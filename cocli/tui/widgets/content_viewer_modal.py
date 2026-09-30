from typing import Any
from textual import events
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Container
from ..base import BaseModalScreen


class ContentViewerModal(BaseModalScreen[None]):
    """A modal to view meeting or note content."""

    def __init__(self, title: str, content: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.viewer_title = title
        self.viewer_content = content

    def compose(self) -> ComposeResult:
        with Container(id="content_viewer"):
            yield Static(f"[bold]{self.viewer_title}[/]", id="viewer_title")
            yield Static(self.viewer_content, id="viewer_content", markup=False)
            yield Static("[dim]Press ESC to close[/]", id="viewer_help")

    def on_key(self, event: events.Key) -> None:
        # BaseModalScreen.on_key() stops every key unconditionally, which
        # (per Textual's dispatch order) prevents a Key event from ever
        # bubbling to where non-priority BINDINGS get resolved - a
        # BINDINGS-based "escape" here would be permanently dead code.
        # ConfirmScreen works around the same issue by handling keys
        # directly; do the same here instead of calling super().on_key().
        if event.key == "escape":
            self.dismiss(None)
        event.stop()
