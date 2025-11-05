from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual import events

from cocli.core.config import get_all_campaign_dirs

class CampaignSelection(Screen[None]):
    """A screen to select a campaign."""

    class CampaignSelected(Message):
        def __init__(self, campaign_name: str) -> None:
            super().__init__()
            self.campaign_name = campaign_name

    def compose(self) -> ComposeResult:
        campaign_dirs = get_all_campaign_dirs()
        campaign_names = sorted([d.name for d in campaign_dirs])

        yield Label("Select a Campaign")
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(name), id=name) for name in campaign_names]
            )
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id:
            self.post_message(self.CampaignSelected(event.item.id))

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the CampaignSelection screen."""
        list_view = self.query_one(ListView)
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()
        elif event.key == "l" or event.key == "enter":
            list_view.action_select_cursor()
            event.prevent_default()
