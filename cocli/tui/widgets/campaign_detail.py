from textual.screen import Screen
from textual.widgets import Label
from textual.app import ComposeResult

from cocli.models.campaign import Campaign

class CampaignDetail(Screen[None]):
    """A screen to display the details of a campaign."""

    def __init__(self, campaign: Campaign, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.campaign = campaign

    def compose(self) -> ComposeResult:
        yield Label(f"Campaign Details for: {self.campaign.name}")
