from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from cocli.core.config import get_all_campaign_dirs

class CampaignSelection(Screen[None]):
    """A screen to select a campaign."""

    def compose(self) -> ComposeResult:
        campaign_dirs = get_all_campaign_dirs()
        campaign_names = sorted([d.name for d in campaign_dirs])

        yield Label("Select a Campaign")
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(name), id=name) for name in campaign_names]
            )
