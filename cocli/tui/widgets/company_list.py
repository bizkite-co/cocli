import logging
import asyncio
from datetime import datetime
from typing import List, TYPE_CHECKING, cast, Dict, Any, Optional

from textual.containers import Container
from textual.widgets import Label, ListView, ListItem, Input
from textual.app import ComposeResult
from textual.message import Message
from textual import events, on, work

if TYPE_CHECKING:
    from ..app import CocliApp
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

    BINDINGS = [
        ("f", "toggle_filter", "Toggle Actionable"),
        ("r", "toggle_sort", "Toggle Recent"),
        ("s", "focus_search", "Search"),
        ("alt+s", "reset_view", "Return to List"),
    ]

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.can_focus = True
        self.filtered_fz_items: List[SearchResult] = []
        self.filter_contact: bool = True
        # DEFAULT TO MRU (Most Recently Updated)
        self.sort_recent: bool = True
        self.current_filters: Dict[str, Any] = {}
        self.current_sort: Optional[str] = "recent"
        self.search_offset: int = 0
        self.search_limit: int = 30

    def compose(self) -> ComposeResult:
        yield Label("SEARCH", id="search_header", classes="pane-header")
        yield Input(placeholder="Search companies...", id="company_search_input")
        yield ListView(id="company_list_view")

    def apply_template(self, tpl_id: str) -> None:
        """Handle template selection from external source."""
        self.current_filters = {}
        self.current_sort = None
        self.search_offset = 0
        
        if tpl_id == "tpl_all":
            self.filter_contact = False
            self.sort_recent = True
            self.current_sort = "recent"
        elif tpl_id == "tpl_with_email":
            self.current_filters = {"has_email": True}
        elif tpl_id == "tpl_no_email":
            self.current_filters = {"no_email": True}
        elif tpl_id == "tpl_actionable":
            self.current_filters = {"has_email_and_phone": True}
        elif tpl_id == "tpl_no_address":
            self.current_filters = {"no_address": True}
        elif tpl_id == "tpl_top_rated":
            self.current_sort = "rating"
        elif tpl_id == "tpl_most_reviewed":
            self.current_sort = "reviews"
        
        self.query_one("#company_search_input", Input).value = ""
        self.run_search("")
        
        # We don't want to call .focus() here if run_search is async, 
        # it might cause flicker before results arrive.
        # But for 'l' key from template, we MUST focus.
        list_view = self.query_one("#company_list_view", ListView)
        if not list_view.has_focus:
            list_view.focus()

    async def on_mount(self) -> None:
        """Initialize the list on mount."""
        await self.perform_search("")
        self.query_one(ListView).focus()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one(Input).focus()

    def action_reset_view(self) -> None:
        """Clear the search input and return focus to the list."""
        search_input = self.query_one(Input)
        search_input.value = ""
        self.query_one(ListView).focus()

    def action_toggle_filter(self) -> None:
        """Toggle the 'Actionable Leads' filter (has email OR phone)."""
        self.filter_contact = not self.filter_contact
        # Notification of state change might be nice since header is gone
        status = "Actionable Only" if self.filter_contact else "All Leads"
        self.app.notify(f"Filter: {status}")
        
        query = self.query_one("#company_search_input", Input).value
        self.run_search(query)

    def action_toggle_sort(self) -> None:
        """Toggle sorting between Alphabetical and Recent."""
        self.sort_recent = not self.sort_recent
        status = "Recent" if self.sort_recent else "Alphabetical"
        self.app.notify(f"Sorting: {status}")
        
        query = self.query_one("#company_search_input", Input).value
        self.run_search(query)

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user presses enter on the search input."""
        list_view = self.query_one(ListView)
        list_view.action_select_cursor()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the CompanyList widget."""
        list_view = self.query_one("#company_list_view", ListView)
        
        if event.key == "j":
            if list_view.has_focus:
                list_view.action_cursor_down()
                event.prevent_default()
        elif event.key == "k":
            if list_view.has_focus:
                list_view.action_cursor_up()
                event.prevent_default()
        elif event.key == "]": # Next Page
            if list_view.has_focus:
                self.search_offset += self.search_limit
                self.run_search(self.query_one("#company_search_input", Input).value)
                event.prevent_default()
        elif event.key == "[": # Prev Page
            if list_view.has_focus and self.search_offset >= self.search_limit:
                self.search_offset -= self.search_limit
                self.run_search(self.query_one("#company_search_input", Input).value)
                event.prevent_default()
        elif event.key == "escape":
            # If search is focused, return focus to list
            if self.query_one(Input).has_focus:
                list_view.focus()
                event.prevent_default()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        self.search_offset = 0 # Reset on text change
        self.run_search(event.value)

    def run_search(self, query: str) -> None:
        app = cast("CocliApp", self.app)
        sort_by = self.current_sort or ("recent" if self.sort_recent else None)
        
        # Merge template filters with contact filter
        search_filters = dict(self.current_filters)
        
        # If 'Actionable Only' is on, we normally require email OR phone.
        # But if the user specifically asked for 'Missing Email' template, 
        # we should respect that and NOT force the global actionable filter 
        # to require an email if it conflicts.
        if self.filter_contact and not search_filters.get("no_email"):
            search_filters["has_contact_info"] = True

        if app.services.sync_search:
            # Synchronous search for tests
            results = app.services.fuzzy_search(
                search_query=query, 
                item_type="company",
                filters=search_filters,
                sort_by=sort_by,
                limit=self.search_limit,
                offset=self.search_offset
            )
            self.filtered_fz_items = results
            self.update_company_list_view()
        else:
            self.trigger_async_search(query)

    async def perform_search(self, query: str) -> None:
        """Helper for on_mount and other direct calls."""
        app = cast("CocliApp", self.app)
        sort_by = self.current_sort or ("recent" if self.sort_recent else None)
        
        search_filters = dict(self.current_filters)
        if self.filter_contact and not search_filters.get("no_email"):
            search_filters["has_contact_info"] = True

        results = app.services.fuzzy_search(
            search_query=query, 
            item_type="company",
            filters=search_filters,
            sort_by=sort_by,
            limit=self.search_limit,
            offset=self.search_offset
        )
        self.filtered_fz_items = results
        self.update_company_list_view()

    @work(exclusive=True, thread=True)
    async def trigger_async_search(self, query: str) -> None:
        """
        Runs the fuzzy search in a background thread to avoid blocking the UI.
        Exclusive=True ensures only the latest search task runs.
        """
        await asyncio.sleep(0.1)
        
        try:
            if not self.is_running or not self.app:
                return
            
            app = cast("CocliApp", self.app)
            sort_by = self.current_sort or ("recent" if self.sort_recent else None)
            
            search_filters = dict(self.current_filters)
            if self.filter_contact and not search_filters.get("no_email"):
                search_filters["has_contact_info"] = True

            results = app.services.fuzzy_search(
                search_query=query, 
                item_type="company",
                filters=search_filters,
                sort_by=sort_by,
                limit=self.search_limit,
                offset=self.search_offset
            )
            
            if not self.is_running:
                return

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
            for i, item in enumerate(self.filtered_fz_items):
                new_items.append(ListItem(Label(item.name), name=item.name))
            
            list_view.extend(new_items)
            if len(new_items) > 0:
                # Ensure the index is set to 0. 
                list_view.index = None
                list_view.index = 0
                
                # Manually trigger highlight for the first item to update preview
                item = self.filtered_fz_items[0]
                if item.slug:
                    self.debounce_highlight(item)
            else:
                list_view.index = None
        except Exception as e:
            logger.error(f"Error updating list view: {e}")

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and hasattr(event.item, "name"):
            name = getattr(event.item, "name")
            selected_item = next((item for item in self.filtered_fz_items if item.name == name), None)
            if selected_item and selected_item.slug:
                self.post_message(self.CompanySelected(selected_item.slug))
                return

        list_view = self.query_one("#company_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            selected_item = self.filtered_fz_items[idx]
            if selected_item and selected_item.slug:
                self.post_message(self.CompanySelected(selected_item.slug))

    @on(ListView.Highlighted)
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and hasattr(event.item, "name"):
            name = getattr(event.item, "name")
            highlighted_item = next((item for item in self.filtered_fz_items if item.name == name), None)
            if highlighted_item and highlighted_item.slug:
                self.debounce_highlight(highlighted_item)
                return

        list_view = self.query_one("#company_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            highlighted_item = self.filtered_fz_items[idx]
            if highlighted_item and highlighted_item.slug:
                self.debounce_highlight(highlighted_item)

    @work(exclusive=True)
    async def debounce_highlight(self, item: SearchResult) -> None:
        """Wait for a brief pause before loading company details for the preview."""
        # 250ms is usually the "sweet spot" for UI debouncing
        await asyncio.sleep(0.25)
        
        if not item.slug:
            return

        company = await asyncio.to_thread(Company.get, item.slug)
        if company:
            # Supplement with search result data if missing on disk
            if company.average_rating is None:
                company.average_rating = item.average_rating
            if company.reviews_count is None:
                company.reviews_count = item.reviews_count
            if not company.street_address:
                company.street_address = item.street_address
            if not company.city:
                company.city = item.city
            if not company.state:
                company.state = item.state
            
            # Map lifecycle fields
            if not company.list_found_at and item.list_found_at:
                try:
                    company.list_found_at = datetime.fromisoformat(item.list_found_at)
                except (ValueError, TypeError):
                    pass
            
            if not company.details_found_at and item.details_found_at:
                try:
                    company.details_found_at = datetime.fromisoformat(item.details_found_at)
                except (ValueError, TypeError):
                    pass

            if not company.last_enriched and item.last_enriched:
                try:
                    company.last_enriched = datetime.fromisoformat(item.last_enriched)
                except (ValueError, TypeError):
                    pass

            self.post_message(self.CompanyHighlighted(company))
