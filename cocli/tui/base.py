from typing import Any, TypeVar, Generic
from textual.containers import Container
from textual.screen import ModalScreen
from textual import events

T = TypeVar("T")


class CocliPanel(Container):
    """
    A base container for titled panels in the cocli TUI.

    Use this base class for any focusable or titled panel container that renders
    its own header Label in `compose()`. It structurally prevents duplicate header rendering
    by ensuring `border_title` is always suppressed.
    """

    def __init__(
        self,
        panel_title: str = "",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.panel_title = panel_title
        self.border_title = ""

    def watch_title(self, title: str) -> None:
        """Override Textual's reactive watcher to prevent title from populating border_title."""
        self.border_title = ""


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

