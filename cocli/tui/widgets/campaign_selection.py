import logging
import asyncio
from typing import TYPE_CHECKING, Any

from textual.widgets import ListView, ListItem, Label, Static
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual import events, on

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
        """Triggered by ENTER/l - implies action (Activation)."""
        def __init__(self, campaign_name: str) -> None:
            super().__init__()
            self.campaign_name = campaign_name

    class CampaignHighlighted(Message):
        """Triggered by Cursor movement - implies browsing."""
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
        self.run_worker(self.load_campaigns())

    async def load_campaigns(self) -> None:
        try:
            campaign_dirs = await asyncio.to_thread(get_all_campaign_dirs)
            campaign_names = sorted([d.name for d in campaign_dirs])
            
            list_view = self.query_one("#campaign_list_view", ListView)
            items = [CampaignListItem(name) for name in campaign_names]
            
            def populate() -> None:
                list_view.extend(items)
                if items:
                    list_view.index = 0
            
            self.call_after_refresh(populate)
        except Exception as e:
            logger.error(f"Failed to load campaigns: {e}")

    @on(ListView.Selected, "#campaign_list_view")
    def handle_select(self, event: ListView.Selected) -> None:
        if isinstance(event.item, CampaignListItem):
            self.post_message(self.CampaignSelected(event.item.campaign_name))

    @on(ListView.Highlighted, "#campaign_list_view")
    def handle_highlight(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, CampaignListItem):
            self.post_message(self.CampaignHighlighted(event.item.campaign_name))

    def on_key(self, event: events.Key) -> None:
        # Standard j/k/l/enter handled by ApplicationView parent now
        pass
