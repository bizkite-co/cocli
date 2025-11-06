from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.panel import Panel
from cocli.models.campaign import Campaign
import logging

logger = logging.getLogger(__name__)

class CampaignDetail(VerticalScroll):
    """A widget to display the details of a campaign."""

    def __init__(self, campaign: Campaign | None = None, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.campaign = campaign

    def on_mount(self) -> None:
        if self.campaign:
            self.update_detail(self.campaign)

    def update_detail(self, campaign: Campaign) -> None:
        logger.debug(f"update_detail called with campaign: {campaign.name if campaign else 'None'}")
        """Update the detail view with the given campaign."""
        self.campaign = campaign
        self.remove_children()
        # Create a string representation of the campaign data for the panel
        campaign_data_str = "\n".join([f"[b]{key.replace('_', ' ').title()}:[/b] {value}" for key, value in self.campaign.model_dump().items()])
        self.mount(Static(Panel(campaign_data_str, title=self.campaign.name, border_style="green")))

    def display_error(self, title: str, message: str) -> None:
        logger.debug(f"display_error called with title: {title}, message: {message}")
        """Display an error message within the detail pane."""
        self.campaign = None # Clear any previous campaign data
        self.remove_children()
        self.mount(Static(Panel(message, title=title, border_style="red")))