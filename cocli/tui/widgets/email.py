from typing import Any, Optional
from textual.widgets import Label
from rich.text import Text

class Email(Label):
    """A widget to display a cyan-colored email address."""
    
    def __init__(self, value: Optional[str], *args: Any, **kwargs: Any):
        self.raw_value = value
        display_text = self._format_email(value)
        super().__init__(display_text, *args, **kwargs)

    def update_email(self, value: Optional[str]) -> None:
        """Update the email address displayed."""
        self.raw_value = value
        self.update(self._format_email(value))

    def _format_email(self, value: Optional[str]) -> Text | str:
        """Format email address with cyan color."""
        if not value:
            return "N/A"
        return Text(str(value), style="cyan")
