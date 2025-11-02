import logging

from textual.containers import Container
from textual.widgets import Input, ListView, ListItem, Label
from textual.app import ComposeResult

from textual.message import Message

from cocli.utils.textual_utils import sanitize_id
from cocli.tui.fz_utils import get_filtered_items_from_fz

logger = logging.getLogger(__name__)

class CompanyList(Container):
    """A screen to display a list of companies."""

    BINDINGS = [("l", "select_item", "Select Item")]





    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name=name, id=id, classes=classes)
        self.all_fz_items = get_filtered_items_from_fz(item_type="company")
        self.filtered_fz_items = self.all_fz_items

    def compose(self) -> ComposeResult:
        yield Label("Companies")
        yield Input(placeholder="Search companies...", id="company_search_input")
        yield ListView(
            *[ListItem(Label(item.name), name=item.name, id=sanitize_id(item.unique_id)) for item in self.filtered_fz_items[:20]],
            id="company_list_view"
        )

    async def on_mount(self) -> None:
        """Called when the screen is mounted."""
        pass

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value
        logger.debug(f"Search input changed: {search_query}")
        self.filtered_fz_items = get_filtered_items_from_fz(search_query=search_query, item_type="company")
        await self.update_company_list_view()

    async def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        list_view = self.query_one("#company_list_view", ListView)
        await list_view.clear()
        logger.debug(f"Updating company list with {len(self.filtered_fz_items)} items.")
        for item in self.filtered_fz_items[:20]:
            logger.debug(f"Adding item to list view: {item.name}")
            list_view.append(ListItem(Label(item.name), name=item.name, id=sanitize_id(item.unique_id)))

    def action_select_item(self) -> None:
        self.select_highlighted_company()

    def select_highlighted_company(self) -> None:
        """Handle the selection of a company in the list."""
        list_view = self.query_one("#company_list_view", ListView)
        if list_view.highlighted_child and list_view.index is not None:
            selected_id = list_view.highlighted_child.id
            logger.debug(f"Selected item ID: {selected_id}")
            selected_item = next((item for item in self.filtered_fz_items if sanitize_id(item.unique_id) == selected_id), None)
            if selected_item and selected_item.slug:
                logger.debug(f"Found matching item: {selected_item.name}, slug: {selected_item.slug}")
                self.post_message(self.CompanySelected(selected_item.slug))
            else:
                logger.debug("No matching item found for selected ID.")
        else:
            logger.debug("No item highlighted or index is None in ListView when selection was attempted.")

    def action_cursor_up(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_up()

    def action_cursor_down(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_down()








