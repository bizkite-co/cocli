from textual import events
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Vertical
from textual.app import ComposeResult
from typing import Any

class ConfirmScreen(ModalScreen[bool]):
    """A modal screen for confirmation dialogs."""
    
    def __init__(self, message: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self.message, id="confirm-message")
            yield Static("([bold]y[/])es / ([bold]n[/])o", id="confirm-prompt")

    def on_key(self, event: events.Key) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)
