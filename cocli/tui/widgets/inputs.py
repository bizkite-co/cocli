# POLICY: frictionless-data-policy-enforcement
import asyncio
from textual.widgets import Input
from textual.message import Message
from textual import events, work

class CocliInput(Input):
    """
    Standardized Cocli Input widget.
    - Minimalist style (no borders by default).
    - 250ms debounced 'Changed' message.
    """
    DEFAULT_CSS = """
    CocliInput {
        border: none;
        background: $surface-lighten-1;
        height: 1;
        padding: 0 1;
    }
    CocliInput:focus {
        background: $surface-lighten-2;
        color: $text;
    }
    """

    class DebouncedChanged(Message):
        """Posted after a 250ms delay since the last keypress."""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    @work(exclusive=True)
    async def _debounce_change(self, value: str) -> None:
        """Wait for a brief pause before posting the debounced message."""
        await asyncio.sleep(0.25)
        self.post_message(self.DebouncedChanged(value))

    def on_input_changed(self, event: Input.Changed) -> None:
        # Intercept the standard Changed event and trigger our debounce
        self._debounce_change(event.value)

class CocliSearchInput(CocliInput):
    """
    Extended CocliInput for Search.
    - Supports Up/Down arrow keys to navigate a target list.
    """
    
    def on_key(self, event: events.Key) -> None:
        # Handle Up/Down to let user navigate results while typing
        if event.key == "up":
            # We bubble these up or handle them specifically if we know the target list
            pass
        elif event.key == "down":
            pass
        # Note: Escape is handled by the global CocliApp shield to return focus to list
