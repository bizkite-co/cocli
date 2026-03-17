import logging
from typing import Any
from textual import events
from textual.widgets import Static
from textual.containers import Vertical
from textual.app import ComposeResult
from ..base import BaseModalScreen

logger = logging.getLogger(__name__)


class ConfirmScreen(BaseModalScreen[bool]):
    """A modal screen for confirmation dialogs."""

    def __init__(self, message: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.message = message

    def on_mount(self) -> None:
        super().on_mount()
        dialog = self.query_one("#confirm-dialog")
        dialog.can_focus = True
        dialog.focus()
        logger.info(f"ConfirmScreen mounted. Dialog has focus: {dialog.has_focus}")

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self.message, id="confirm-message")
            yield Static("([bold]y[/])es / ([bold]n[/])o", id="confirm-prompt")

    def on_key(self, event: events.Key) -> None:
        # Prevent key events from bubbling up

        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)
