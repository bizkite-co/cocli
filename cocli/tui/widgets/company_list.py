import logging
import asyncio
from typing import List

from textual.containers import Container
from textual.widgets import Label, ListView, ListItem, Input
from textual.app import ComposeResult
from textual.message import Message
from textual import events, on, work

from cocli.models.company import Company
from cocli.models.search import SearchResult

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
        self.all_fz_items: List[SearchResult] = []
        self.filtered_fz_items: List[SearchResult] = []

    async def on_mount(self) -> None:
        """Initialize the list on mount."""
        # Initial load of companies
        self.run_search("")
        self.query_one(Input).focus()

    def compose(self) -> ComposeResult:
        yield Label("Companies")
        yield Input(placeholder="Search companies...", id="company_search_input")
        yield ListView(
            id="company_list_view"
        )

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
        """Called when the search input changes."""
        self.run_search(event.value)

    @work(exclusive=True, thread=True)
    async def run_search(self, query: str) -> None:
        """
        Runs the fuzzy search in a background thread to avoid blocking the UI.
        Exclusive=True ensures only the latest search task runs.
        """
        # Small debounce
        await asyncio.sleep(0.1)
        
        try:
            # We use the app's service container
            if not self.is_running or not self.app or not hasattr(self.app, 'services'):
                return

            results = self.app.services.fuzzy_search(search_query=query, item_type="company")
            
            if not self.is_running:
                return

            # Update the UI state safely
            self.filtered_fz_items = results
            self.call_after_refresh(self.update_company_list_view)
        except Exception as e:
            logger.error(f"Search worker failed: {e}", exc_info=True)

    def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        try:
            list_view = self.query_one("#company_list_view", ListView)
            list_view.clear()
            
            new_items = []
            for i, item in enumerate(self.filtered_fz_items[:20]):
                # Remove manual ID to prevent DuplicateIds. Textual will handle it.
                new_items.append(ListItem(Label(item.name), name=item.name))
            
            list_view.extend(new_items)
            if len(new_items) > 0:
                list_view.index = 0
        except Exception as e:
            logger.error(f"Error updating list view: {e}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Use the index instead of parsing IDs
        list_view = self.query_one("#company_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            selected_item = self.filtered_fz_items[idx]
            if selected_item.slug:
                self.post_message(self.CompanySelected(selected_item.slug))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        # Use the index instead of parsing IDs
        list_view = self.query_one("#company_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            highlighted_item = self.filtered_fz_items[idx]
            if highlighted_item.slug:
                company = Company.get(highlighted_item.slug)
                if company:
                    self.post_message(self.CompanyHighlighted(company))
