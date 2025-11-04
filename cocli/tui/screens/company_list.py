import logging

from textual.containers import Container
from textual.widgets import Input, ListView, ListItem, Label
from textual.app import ComposeResult

from textual.message import Message

from cocli.utils.textual_utils import sanitize_id
from cocli.tui.fz_utils import get_filtered_items_from_fz

from textual import events, on

logger = logging.getLogger(__name__)

class CompanyList(Container):
    """A screen to display a list of companies."""





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
        self.query_one("#company_search_input").focus()

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

    def action_select_item(self) -> None:
        """Called when the user presses 'l' or 'enter' to select an item."""
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_select_cursor()

    def select_highlighted_company(self) -> None:
        """Handle the selection of a company in the list."""
        list_view = self.query_one("#company_list_view", ListView)
        if list_view.highlighted_child and list_view.index is not None:
            selected_id = list_view.highlighted_child.id
            selected_item = next((item for item in self.filtered_fz_items if sanitize_id(item.unique_id) == selected_id), None)
            if selected_item and selected_item.slug:
                self.post_message(self.CompanySelected(selected_item.slug))
            else:
                pass
        else:
            pass

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a company is selected from the list."""
        logger.debug(f"ListView.Selected event received in CompanyList for item ID: {event.item.id}")
        selected_id = event.item.id
        selected_item = next((item for item in self.filtered_fz_items if sanitize_id(item.unique_id) == selected_id), None)
        if selected_item and selected_item.slug:
            self.post_message(self.CompanySelected(selected_item.slug))
        else:
            logger.warning(f"Could not find selected item or slug for ID: {selected_id}")

    async def on_key(self, event: events.Key) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        if self.query_one("#company_search_input").has_focus:
            if event.key == "down":
                list_view.focus()
                if len(list_view.children) > 0:
                    list_view.index = 0
                event.stop()
            elif event.key == "enter":
                list_view.focus() # Transfer focus to the list view
                if len(list_view.children) > 0:
                    list_view.index = 0 # Ensure an item is highlighted before selecting
                    list_view.action_select_cursor() # This should trigger ListView.Selected
                event.stop()
        elif list_view.has_focus:
            if event.key == "up" and list_view.index == 0:
                self.query_one("#company_search_input").focus()
                event.stop()
            elif event.key == "j":
                list_view.action_cursor_down()
                event.stop()
            elif event.key == "k":
                list_view.action_cursor_up()
                event.stop()

    def action_cursor_up(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_up()

    def action_cursor_down(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_down()








