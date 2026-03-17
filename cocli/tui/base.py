from textual.screen import ModalScreen
from textual import events
from typing import TypeVar, Generic

T = TypeVar("T")


class BaseModalScreen(ModalScreen[T], Generic[T]):
    """
    Base class for all modal screens that enforces focus management
    on mount to prevent event propagation to underlying widgets.
    """

    def on_mount(self) -> None:
        """
        Ensures the modal screen (or its primary child) receives focus
        immediately upon being mounted.
        """
        self.focus()

    def on_key(self, event: events.Key) -> None:
        """
        Ensures key events are stopped at the modal level by default.
        """
        event.stop()
