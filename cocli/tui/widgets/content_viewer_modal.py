from typing import Any
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Container
from ..base import BaseModalScreen


class ContentViewerModal(BaseModalScreen[None]):
    """A modal to view meeting or note content."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, title: str, content: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.viewer_title = title
        self.viewer_content = content

    def compose(self) -> ComposeResult:
        with Container(id="content_viewer"):
            yield Static(f"[bold]{self.viewer_title}[/]", id="viewer_title")
            yield Static(self.viewer_content, id="viewer_content", markup=False)
            yield Static("[dim]Press ESC to close[/]", id="viewer_help")

    async def action_dismiss(self, result: None = None) -> None:
        self.app.pop_screen()
