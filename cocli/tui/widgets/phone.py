from typing import Any, Union
from textual.widgets import Label
from rich.text import Text
from cocli.models.phone import PhoneNumber

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
        try:
            # If it's already a PhoneNumber object
            if isinstance(value, PhoneNumber):
                return Text(value.format("international"), style="bold #00ff00")
            
            # If it's a string/dict, validate it
            pn = PhoneNumber.model_validate(value)
            if pn:
                return Text(pn.format("international"), style="bold #00ff00")
        except Exception:
            pass
        return str(value)
