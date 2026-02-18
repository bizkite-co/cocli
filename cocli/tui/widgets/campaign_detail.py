from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.panel import Panel
from rich.markup import escape
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
        
        lines = []
        # 1. Core Info
        lines.append("[b][cyan]Core Info[/][/b]")
        lines.append(f"  Name: {escape(campaign.name)}")
        lines.append(f"  Tag: {escape(campaign.tag)}")
        lines.append(f"  Domain: {escape(campaign.domain)}")
        lines.append(f"  Workflows: {escape(', '.join(campaign.workflows))}")
        lines.append("")

        # 2. Google Maps
        lines.append("[b][cyan]Google Maps[/][/b]")
        lines.append(f"  Email: {escape(campaign.google_maps.email)}")
        lines.append(f"  1P Path: {escape(campaign.google_maps.one_password_path)}")
        lines.append("")

        # 3. Prospecting
        lines.append("[b][cyan]Prospecting[/][/b]")
        lines.append(f"  Keywords: {escape(', '.join(campaign.prospecting.keywords))}")
        lines.append(f"  Locations: {escape(', '.join(campaign.prospecting.locations or []))}")
        lines.append(f"  Panning: {campaign.prospecting.panning_distance_miles} miles")
        lines.append(f"  Initial Zoom: {campaign.prospecting.initial_zoom_out_level}")

        self.mount(Static(Panel("\n".join(lines), title=f"Settings: {campaign.name}", border_style="green")))

    def display_error(self, title: str, message: str) -> None:
        logger.debug(f"display_error called with title: {title}, message: {message}")
        """Display an error message within the detail pane."""
        self.campaign = None # Clear any previous campaign data
        self.remove_children()
        self.mount(Static(Panel(message, title=title, border_style="red"), id="error_message"))
