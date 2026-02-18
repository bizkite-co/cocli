import logging
import asyncio
from typing import List, TYPE_CHECKING, cast, Dict, Any, Optional

from textual.containers import Container, Horizontal, Vertical
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

    @on(ListView.Selected, "#template_list")
    def on_template_selected(self, event: ListView.Selected) -> None:
        """Handle template selection."""
        tpl_id = event.item.id
        self.current_filters = {}
        self.current_sort = None
        
        if tpl_id == "tpl_all":
            self.filter_contact = False
            self.current_sort = None
        elif tpl_id == "tpl_no_email":
            self.current_filters = {"no_email": True}
        elif tpl_id == "tpl_no_address":
            self.current_filters = {"no_address": True}
        elif tpl_id == "tpl_top_rated":
            self.current_sort = "rating"
        elif tpl_id == "tpl_most_reviewed":
            self.current_sort = "reviews"
        
        self.query_one("#company_search_input", Input).value = ""
        self.run_search("")
        self.query_one("#company_list_view").focus()

    async def on_mount(self) -> None:
        """Initialize the list on mount."""
        await self.perform_search("")
        self.query_one(ListView).focus()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search companies...", id="company_search_input")
        with Horizontal():
            with Vertical(id="list_container"):
                yield ListView(id="company_list_view")
            with Vertical(id="template_container"):
                yield Label("TEMPLATES", id="template_header")
                yield ListView(
                    ListItem(Label("All Leads"), id="tpl_all"),
                    ListItem(Label("Missing Email"), id="tpl_no_email"),
                    ListItem(Label("Missing Address"), id="tpl_no_address"),
                    ListItem(Label("Top Rated"), id="tpl_top_rated"),
                    ListItem(Label("Most Reviewed"), id="tpl_most_reviewed"),
                    id="template_list"
                )

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
        template_list = self.query_one("#template_list", ListView)
        
        if event.key == "j":
            focused = self.app.focused
            if isinstance(focused, ListView) and focused in (list_view, template_list):
                focused.action_cursor_down()
                event.prevent_default()
        elif event.key == "k":
            focused = self.app.focused
            if isinstance(focused, ListView) and focused in (list_view, template_list):
                focused.action_cursor_up()
                event.prevent_default()
        elif event.key == "h":
            if template_list.has_focus:
                list_view.focus()
                event.prevent_default()
        elif event.key == "l":
            if list_view.has_focus:
                template_list.focus()
                event.prevent_default()
        elif event.key == "escape":
            # If search is focused, return focus to list
            if self.query_one(Input).has_focus:
                list_view.focus()
                event.prevent_default()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        self.run_search(event.value)

    def run_search(self, query: str) -> None:
        app = cast("CocliApp", self.app)
        sort_by = self.current_sort or ("recent" if self.sort_recent else None)
        
        # Merge template filters with contact filter
        search_filters = dict(self.current_filters)
        if self.filter_contact:
            search_filters["has_contact_info"] = True

        if app.services.sync_search:
            # Synchronous search for tests
            results = app.services.fuzzy_search(
                search_query=query, 
                item_type="company",
                filters=search_filters,
                sort_by=sort_by
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
        if self.filter_contact:
            search_filters["has_contact_info"] = True

        results = app.services.fuzzy_search(
            search_query=query, 
            item_type="company",
            filters=search_filters,
            sort_by=sort_by
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
            if self.filter_contact:
                search_filters["has_contact_info"] = True

            results = app.services.fuzzy_search(
                search_query=query, 
                item_type="company",
                filters=search_filters,
                sort_by=sort_by
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
            for i, item in enumerate(self.filtered_fz_items[:20]):
                new_items.append(ListItem(Label(item.name), name=item.name))
            
            list_view.extend(new_items)
            if len(new_items) > 0:
                list_view.index = 0
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
                company = Company.get(highlighted_item.slug)
                if company:
                    self.post_message(self.CompanyHighlighted(company))
                return

        list_view = self.query_one("#company_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            highlighted_item = self.filtered_fz_items[idx]
            if highlighted_item and highlighted_item.slug:
                company = Company.get(highlighted_item.slug)
                if company:
                    self.post_message(self.CompanyHighlighted(company))
