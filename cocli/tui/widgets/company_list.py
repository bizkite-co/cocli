import logging

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

    def compose(self) -> ComposeResult:
        yield Label("Companies")
        yield Input(placeholder="Search companies...", id="company_search_input")
        yield ListView(
            *[ListItem(Label(item.name), name=item.name, id=sanitize_id(item.unique_id)) for item in self.filtered_fz_items[:20]],
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
        """Called when the search input changes."""
        search_query = event.value
        logger.debug(f"Search input changed: {search_query}")
        self.filtered_fz_items = get_fuzzy_search_results(search_query=search_query, item_type="company")
        await self.update_company_list_view()
        list_view = self.query_one("#company_list_view", ListView)
        if len(list_view.children) > 0:
            list_view.index = 0

    async def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        list_view = self.query_one("#company_list_view", ListView)
        await list_view.clear()
        logger.debug(f"Updating company list with {len(self.filtered_fz_items)} items.")
        for item in self.filtered_fz_items[:20]:
            logger.debug(f"Adding item to list view: {item.name}")
            list_view.append(ListItem(Label(item.name), name=item.name, id=sanitize_id(item.unique_id)))





    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id:
            self.post_message(self.CompanySelected(event.item.id))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            # Find the search result from the list of items
            search_result = next((item for item in self.all_fz_items if item.unique_id == event.item.id), None)
            if search_result and search_result.slug:
                company = Company.get(search_result.slug)
                if company:
                    self.post_message(self.CompanyHighlighted(company))












