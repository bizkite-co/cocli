from textual.screen import Screen
from textual.widgets import Static
from textual.app import ComposeResult

from rich.panel import Panel
from rich.markdown import Markdown

from cocli.models.campaign import Campaign

class CampaignDetail(Screen[None]):
    """A screen to display the details of a campaign."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, campaign: Campaign, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.campaign = campaign

    def compose(self) -> ComposeResult:
        output = ""
        for key, value in self.campaign.model_dump().items():
            if value is None or key == "name":
                continue
            key_str = key.replace('_', ' ').title()
            output += f"- **{key_str}**: {value}\n"

        panel_content = Panel(Markdown(output), title="Campaign Details", border_style="green")
        yield Static(panel_content)