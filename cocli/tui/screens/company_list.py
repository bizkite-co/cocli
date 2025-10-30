from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message

from cocli.utils.textual_utils import sanitize_id
from cocli.tui.fz_utils import get_filtered_items_from_fz
from cocli.tui.screens.company_detail import CompanyDetailScreen # New import
from cocli.application.company_service import get_company_details_for_view # New import

class CompanyList(Screen[None]):
    """A screen to display a list of companies."""

    BINDINGS = [
        ("up", "cursor_up", "Cursor Up"),
        ("down", "cursor_down", "Cursor Down"),
        ("enter", "select_company", "Select Company"),
        ("escape", "app.pop_screen", "Back to main menu"),
    ]

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
        with VerticalScroll():
            yield ListView(
                id="company_list_view"
            )

    async def on_mount(self) -> None:
        """Called when the screen is mounted."""
        await self.update_company_list_view()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value
        self.filtered_fz_items = get_filtered_items_from_fz(search_query=search_query, item_type="company")
        await self.update_company_list_view()

    async def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        list_view = self.query_one("#company_list_view", ListView)
        await list_view.clear()
        for item in self.filtered_fz_items[:20]:
            list_view.append(ListItem(Label(item["name"]), id=sanitize_id(item["unique_id"])))

    async def action_cursor_up(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_up()

    async def action_cursor_down(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        list_view.action_cursor_down()

    async def action_select_company(self) -> None:
        list_view = self.query_one("#company_list_view", ListView)
        if list_view.highlighted_child:
            selected_item_id = list_view.highlighted_child.id
            if selected_item_id:
                original_slug = selected_item_id.split('-')[0] if '-' in selected_item_id and not selected_item_id.startswith('_') else selected_item_id
                company_data = get_company_details_for_view(original_slug)
                if company_data:
                    self.app.push_screen(CompanyDetailScreen(company_data), stack=True)
                else:
                    self.app.bell() # Indicate an error or company not found

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a company is selected from the list."""
        # This is still here but action_select_company will handle the ENTER key
        # This might be useful for other selection methods if implemented later
        if event.item.id:
            original_slug = event.item.id.split('-')[0] if '-' in event.item.id and not event.item.id.startswith('_') else event.item.id
            self.post_message(self.CompanySelected(original_slug))
