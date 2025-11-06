from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from rich.panel import Panel

class ErrorScreen(Screen[None]):
    """A screen to display a formatted error message."""

    BINDINGS = [
        ("escape", "app.pop_screen", "OK"),
    ]

    def __init__(self, title: str, message: str, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.error_title = title
        self.error_message = message

    def compose(self) -> ComposeResult:
        yield Static(Panel(self.error_message, title=self.error_title, border_style="red"))
