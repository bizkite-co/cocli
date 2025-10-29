from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message

# from cocli.models.person import Person # No longer needed for direct Person.get_all()
from cocli.utils.textual_utils import sanitize_id # Re-added
from cocli.tui.fz_utils import get_filtered_items_from_fz # New import

class PersonList(Screen[None]):
    """A screen to display a list of people."""

    class PersonSelected(Message):
        """Posted when a person is selected from the list."""
        def __init__(self, person_slug: str) -> None:
            super().__init__()
            self.person_slug = person_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.all_fz_items = get_filtered_items_from_fz(item_type="person") # Get initial items from fz
        self.filtered_fz_items = self.all_fz_items # Initialize filtered list

    def compose(self) -> ComposeResult:
        yield Label("People")
        yield Input(placeholder="Search people...", id="person_search_input")
        with VerticalScroll():
            yield ListView(
                id="person_list_view"
            )

    async def on_mount(self) -> None:
        """Called when the screen is mounted."""
        await self.update_person_list_view()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value
        self.filtered_fz_items = get_filtered_items_from_fz(search_query=search_query, item_type="person")
        await self.update_person_list_view()

    async def update_person_list_view(self) -> None:
        """Updates the ListView with filtered people."""
        list_view = self.query_one("#person_list_view", ListView)
        await list_view.clear()
        for item in self.filtered_fz_items[:20]:
            list_view.append(ListItem(Label(item["name"]), id=sanitize_id(item["unique_id"])))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a person is selected from the list."""
        if event.item.id:
            # We need to extract the original slug from the unique_id
            # Assuming unique_id is original_slug or original_slug-counter
            original_slug = event.item.id.split('-')[0] if '-' in event.item.id and not event.item.id.startswith('_') else event.item.id
            self.post_message(self.PersonSelected(original_slug))
