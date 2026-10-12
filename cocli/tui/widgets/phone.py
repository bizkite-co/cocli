from __future__ import annotations
from typing import Any, Union
from textual.widgets import Label
from rich.text import Text
from cocli.models.phone import as_phone_number, render_phone

class Phone(Label):
    """A widget to display and interact with a phone number."""
    
    def __init__(self, value: Any, *args: Any, **kwargs: Any):
        self.raw_value = value
        display_text = self._format_phone(value)
        super().__init__(display_text, *args, **kwargs)

    def update_phone(self, value: Any) -> None:
        """Update the phone number displayed."""
        self.raw_value = value
        self.update(self._format_phone(value))

    def _format_phone(self, value: Any) -> Union[Text, str]:
        """Consistently format phone numbers for display."""
        if not value:
            return "N/A"
        rendered = render_phone(value)
        if as_phone_number(value) is not None:
            return Text(rendered, style="bold #00ff00")
        return rendered or str(value)
