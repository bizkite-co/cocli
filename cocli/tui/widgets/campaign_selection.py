import logging
import asyncio
from typing import TYPE_CHECKING, Any

from textual.widgets import ListView, ListItem, Label, Static
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual import events

from cocli.core.config import get_all_campaign_dirs
from cocli.core.text_utils import slugify

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class CampaignListItem(ListItem):
    def __init__(self, name: str) -> None:
        super().__init__(Label(name), id=slugify(name))
        self.campaign_name = name


class CampaignSelection(Static):
    """A widget to select a campaign."""

    class CampaignSelected(Message):
        """Message sent when a campaign is selected."""

        def __init__(self, campaign_name: str) -> None:
            super().__init__()
            self.campaign_name = campaign_name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield Label("Select a Campaign")
        with VerticalScroll():
            yield ListView(id="campaign_list_view")
    
    def on_mount(self) -> None:
        # Load campaigns in a non-blocking worker
        self.run_worker(self.load_campaigns())

    async def load_campaigns(self) -> None:
        """Asynchronously discovers available campaigns."""
        try:
            # Move I/O to a thread
            campaign_dirs = await asyncio.to_thread(get_all_campaign_dirs)
            campaign_names = sorted([d.name for d in campaign_dirs])
            
            list_view = self.query_one("#campaign_list_view", ListView)
            items = [CampaignListItem(name) for name in campaign_names]
            
            # Update UI on next refresh
            def populate() -> None:
                list_view.extend(items)
                if items:
                    list_view.index = 0
            
            self.call_after_refresh(populate)
        except Exception as e:
            logger.error(f"Failed to load campaigns: {e}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, CampaignListItem):
            self.post_message(self.CampaignSelected(event.item.campaign_name))

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the CampaignSelection."""
        list_view = self.query_one("#campaign_list_view", ListView)
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l" or event.key == "enter":
            list_view.action_select_cursor()
            event.prevent_default()
            event.stop()
