from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message

# from cocli.models.company import Company # No longer needed for direct Company.get_all()
from cocli.utils.textual_utils import sanitize_id # Re-added
from cocli.tui.fz_utils import get_filtered_items_from_fz # New import

class CompanyList(Screen[None]):
    """A screen to display a list of companies."""

    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        # self.all_companies = list(Company.get_all()) # Removed
        self.all_fz_items = get_filtered_items_from_fz(item_type="company") # Get initial items from fz
        self.filtered_fz_items = self.all_fz_items # Initialize filtered list

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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a company is selected from the list."""
        if event.item.id:
            # We need to extract the original slug from the unique_id
            # Assuming unique_id is original_slug or original_slug-counter
            original_slug = event.item.id.split('-')[0] if '-' in event.item.id and not event.item.id.startswith('_') else event.item.id
            self.post_message(self.CompanySelected(original_slug))
