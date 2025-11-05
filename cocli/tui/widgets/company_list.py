import logging

from textual.containers import Container
from textual.widgets import Input, ListView, ListItem, Label
from textual.app import ComposeResult

from textual.message import Message

from cocli.utils.textual_utils import sanitize_id
from cocli.tui.fz_utils import get_filtered_items_from_fz

from textual import on

logger = logging.getLogger(__name__)

class CompanyList(Container):
    DEFAULT_CSS = """
    CompanyList {
        height: auto;
    }
    CompanyList:focus {
        border: thick solid blue;
    }
    """

    """A screen to display a list of companies."""





    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.can_focus = True
        self.all_fz_items = get_filtered_items_from_fz(item_type="company")
        print(f"DEBUG: CompanyList.__init__ - self.all_fz_items: {self.all_fz_items}") # Temporary debug print
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




    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value
        logger.debug(f"Search input changed: {search_query}")
        self.filtered_fz_items = get_filtered_items_from_fz(search_query=search_query, item_type="company")
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





    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a company is selected from the list."""
        logger.debug(f"ListView.Selected event received in CompanyList for item ID: {event.item.id}")
        selected_id = event.item.id
        print(f"DEBUG: on_list_view_selected - selected_id: {selected_id}") # Temporary debug print
        selected_item = next((item for item in self.filtered_fz_items if sanitize_id(item.unique_id) == selected_id), None)
        if selected_item and selected_item.slug:
            print(f"DEBUG: on_list_view_selected - selected_item.slug: {selected_item.slug}") # Temporary debug print
            self.post_message(self.CompanySelected(selected_item.slug))
        else:
            logger.warning(f"Could not find selected item or slug for ID: {selected_id}")












