import logging
import asyncio
from typing import List, TYPE_CHECKING, cast

from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual import on, work

if TYPE_CHECKING:
    from ..app import CocliApp
from cocli.models.search import SearchResult

logger = logging.getLogger(__name__)

class PersonList(Screen[None]):
    """A screen to display a list of people."""

    class PersonSelected(Message):
        """Posted when a person is selected from the list."""
        def __init__(self, person_slug: str) -> None:
            super().__init__()
            self.person_slug = person_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.all_fz_items: List[SearchResult] = []
        self.filtered_fz_items: List[SearchResult] = []

    def compose(self) -> ComposeResult:
        yield Label("People")
        yield Input(placeholder="Search people...", id="person_search_input")
        with VerticalScroll():
            yield ListView(
                id="person_list_view"
            )

    async def on_mount(self) -> None:
        """Called when the screen is mounted."""
        app = cast("CocliApp", self.app)
        if app.services.sync_search:
            results = app.services.fuzzy_search(search_query="", item_type="person")
            self.filtered_fz_items = results
            self.update_person_list_view()
        else:
            self.run_search("")
        self.query_one(Input).focus()

    @on(Input.Changed)
    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        app = cast("CocliApp", self.app)
        if app.services.sync_search:
            results = app.services.fuzzy_search(search_query=event.value, item_type="person")
            self.filtered_fz_items = results
            self.update_person_list_view()
        else:
            self.run_search(event.value)

    @work(exclusive=True, thread=True)
    async def run_search(self, query: str) -> None:
        """
        Runs the fuzzy search in a background thread to avoid blocking the UI.
        """
        # Small debounce
        await asyncio.sleep(0.1)
        
        try:
            if not self.is_running or not self.app:
                return
            
            app = cast("CocliApp", self.app)
            if not hasattr(app, 'services'):
                return

            results = app.services.fuzzy_search(search_query=query, item_type="person")
            
            if not self.is_running:
                return

            self.filtered_fz_items = results
            self.call_after_refresh(self.update_person_list_view)
        except Exception as e:
            logger.error(f"Person search worker failed: {e}", exc_info=True)

    def update_person_list_view(self) -> None:
        """Updates the ListView with filtered people."""
        try:
            list_view = self.query_one("#person_list_view", ListView)
            list_view.clear()
            for item in self.filtered_fz_items[:20]:
                list_view.append(ListItem(Label(item.name), name=item.name))
            
            if len(self.filtered_fz_items) > 0:
                list_view.index = 0
        except Exception as e:
            logger.error(f"Error updating person list view: {e}")

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a person is selected from the list."""
        list_view = self.query_one("#person_list_view", ListView)
        idx = list_view.index
        if idx is not None and idx < len(self.filtered_fz_items):
            selected_item = self.filtered_fz_items[idx]
            if selected_item.slug:
                self.post_message(self.PersonSelected(selected_item.slug))
