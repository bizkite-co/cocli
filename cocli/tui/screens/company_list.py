import logging

from textual.screen import Screen
from textual.widgets import Input, ListView, ListItem, Label
from textual import on, events
from textual.app import ComposeResult

from textual.message import Message

from cocli.utils.textual_utils import sanitize_id
from cocli.tui.fz_utils import get_filtered_items_from_fz

logger = logging.getLogger(__name__)

class CompanyList(Screen[None]):
    """A screen to display a list of companies."""

    BINDINGS = [
        ("up", "cursor_up", "Cursor Up"),
        ("down", "cursor_down", "Cursor Down"),
        ("escape", "app.pop_screen", "Back to main menu"),
        ("h", "app.go_back", "Back"),
        ("l", "select_item", "Select"),
    ]

    def action_select_item(self) -> None:
        logger.debug("l key pressed in CompanyList, calling handle_company_selection directly.")
        list_view = self.query_one("#company_list_view", ListView)
        if list_view.highlighted_child and list_view.index is not None:
            dummy_event = ListView.Selected(list_view, list_view.highlighted_child, list_view.index)
            self.handle_company_selection(dummy_event)
        else:
            logger.debug("No item highlighted or index is None in ListView when l was pressed.")

    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
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

    async def action_cursor_up(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_up()

    async def action_cursor_down(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_down()


    def handle_company_selection(self, event: ListView.Selected) -> None:
        """Handle the selection of a company in the list."""
        logger.debug(f"Company selection event received for item: {event.item}")
        if event.item.id:
            logger.debug(f"Selected item ID: {event.item.id}")
            selected_item = next((item for item in self.filtered_fz_items if sanitize_id(item.unique_id) == event.item.id), None)
            if selected_item and selected_item.slug:
                logger.debug(f"Found matching item: {selected_item.name}, slug: {selected_item.slug}")
                self.post_message(self.CompanySelected(selected_item.slug))
            else:
                logger.debug("No matching item found for selected ID.")
        else:
            logger.debug("Selected item has no ID.")

    @on(ListView.Highlighted)
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        logger.debug(f"Highlighted item: {event.item}")

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            logger.debug("Enter key pressed in CompanyList, calling handle_company_selection directly.")
            # Manually create a ListView.Selected event to pass to the handler
            # This is a workaround if the ListView is not emitting the event itself
            list_view = self.query_one("#company_list_view", ListView)
            if list_view.highlighted_child and list_view.index is not None:
                dummy_event = ListView.Selected(list_view, list_view.highlighted_child, list_view.index)
                self.handle_company_selection(dummy_event)
            else:
                logger.debug("No item highlighted or index is None in ListView when Enter was pressed.")






