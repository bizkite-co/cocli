import logging
import asyncio
from typing import Optional

from textual.containers import Container
from textual.widgets import Input, ListView, ListItem, Label
from textual.app import ComposeResult

from textual.message import Message

from textual import events

from cocli.utils.textual_utils import sanitize_id
from cocli.application.search_service import get_fuzzy_search_results
from cocli.models.company import Company

from textual import on


logger = logging.getLogger(__name__)

class CompanyList(Container):

    class CompanyHighlighted(Message):
        def __init__(self, company: Company) -> None:
            super().__init__()
            self.company = company


    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.can_focus = True
        self.all_fz_items = get_fuzzy_search_results(item_type="company")
        self.filtered_fz_items = self.all_fz_items
        self._update_task: Optional[asyncio.Task[None]] = None

    def compose(self) -> ComposeResult:
        yield Label("Companies")
        yield Input(placeholder="Search companies...", id="company_search_input")
        yield ListView(
            *[ListItem(Label(item.name), name=item.name, id=f"item-{i}-{sanitize_id(item.unique_id)}") for i, item in enumerate(self.filtered_fz_items[:20])],
            id="company_list_view"
        )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user presses enter on the search input."""
        list_view = self.query_one(ListView)
        list_view.action_select_cursor()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the CompanyList widget."""
        if event.key == "down":
            list_view = self.query_one(ListView)
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "up":
            list_view = self.query_one(ListView)
            list_view.action_cursor_up()
            event.prevent_default()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes (debounced)."""
        # Cancel any pending update task
        if self._update_task:
            self._update_task.cancel()
        
        # Start a new debounced task
        async def debounced_update() -> None:
            try:
                await asyncio.sleep(0.1) # 100ms debounce
                search_query = event.value
                logger.debug(f"Search input changed: {search_query}")
                self.filtered_fz_items = get_fuzzy_search_results(search_query=search_query, item_type="company")
                await self.update_company_list_view()
                list_view = self.query_one("#company_list_view", ListView)
                if len(list_view.children) > 0:
                    list_view.index = 0
            except asyncio.CancelledError:
                pass

        self._update_task = asyncio.create_task(debounced_update())

    async def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        list_view = self.query_one("#company_list_view", ListView)
        
        # Textual items should be cleared before adding new ones
        await list_view.clear()
        
        logger.debug(f"Updating company list with {len(self.filtered_fz_items)} items.")
        new_items = []
        for i, item in enumerate(self.filtered_fz_items[:20]):
            # Use index in ID to guarantee uniqueness and prevent DuplicateIds
            new_items.append(ListItem(Label(item.name), name=item.name, id=f"item-{i}-{sanitize_id(item.unique_id)}"))
        
        await list_view.extend(new_items)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            # The ID now contains 'item-N-' prefix, we need to find the item in our filtered list
            # Match based on the index in the ID
            try:
                idx_str = event.item.id.split("-")[1]
                idx = int(idx_str)
                if idx < len(self.filtered_fz_items):
                    selected_item = self.filtered_fz_items[idx]
                    if selected_item.slug:
                        self.post_message(self.CompanySelected(selected_item.slug))
            except (IndexError, ValueError):
                logger.warning(f"Could not parse index from item ID: {event.item.id}")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            try:
                idx_str = event.item.id.split("-")[1]
                idx = int(idx_str)
                if idx < len(self.filtered_fz_items):
                    highlighted_item = self.filtered_fz_items[idx]
                    if highlighted_item.slug:
                        company = Company.get(highlighted_item.slug)
                        if company:
                            self.post_message(self.CompanyHighlighted(company))
            except (IndexError, ValueError):
                pass












