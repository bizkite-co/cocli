import logging
import asyncio
from typing import TYPE_CHECKING, cast

from textual.widgets import ListView, ListItem, Label, Input
from textual.app import ComposeResult
from textual.message import Message
from textual import events, on, work

if TYPE_CHECKING:
    from ..app import CocliApp
from cocli.models.search import SearchResult
from .inputs import CocliSearchInput
from ..base import CocliPanel

logger = logging.getLogger(__name__)

# Same page size as the company list. A hard cap of 20 made the search box
# look broken: matches past the first screen never appeared, and j/k could
# not walk the rest of the directory.
PERSON_SEARCH_LIMIT = 500

class PersonList(CocliPanel):
    """A view container to display a list of people."""

    DEFAULT_CSS = """
    PersonList {
        height: 1fr;
    }
    #person_list_view {
        height: 1fr;
    }
    """

    class PersonSelected(Message):
        """Posted when a person is selected from the list."""
        def __init__(self, person_slug: str) -> None:
            super().__init__()
            self.person_slug = person_slug

    BINDINGS = [
        ("s", "focus_search", "Search"),
        ("alt+s", "reset_view", "Return to List"),
    ]

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(panel_title="PEOPLE", name=name, id=id, classes=classes)
        self.all_fz_items: list[SearchResult] = []
        self.filtered_fz_items: list[SearchResult] = []

    def compose(self) -> ComposeResult:
        yield Label("PEOPLE", id="person_list_header", classes="pane-header")
        yield CocliSearchInput(placeholder="Search people...", id="person_search_input")
        yield ListView(id="person_list_view")

    async def on_mount(self) -> None:
        """Called when the screen is mounted."""
        app = cast("CocliApp", self.app)
        if app.services.sync_search:
            results = app.services.fuzzy_search(
                search_query="",
                item_type="person",
                limit=PERSON_SEARCH_LIMIT,
            )
            self.filtered_fz_items = results
            self.update_person_list_view()
        else:
            self.run_search("")
        self.focus_list()

    def focus_list(self) -> None:
        """Move focus to the result list so j/k/l drive the cursor."""
        list_view = self.query_one("#person_list_view", ListView)
        if list_view.children and list_view.index is None:
            list_view.index = 0
        list_view.focus()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#person_search_input", CocliSearchInput).focus()

    def action_open_highlighted(self) -> None:
        """Open the person under the cursor."""
        list_view = self.query_one("#person_list_view", ListView)
        idx = list_view.index
        if idx is None or not (0 <= idx < len(self.filtered_fz_items)):
            return
        slug = self.filtered_fz_items[idx].slug
        if slug:
            self.post_message(self.PersonSelected(slug))

    def action_reset_view(self) -> None:
        """Clear the search input and return focus to the list."""
        search_input = self.query_one("#person_search_input", CocliSearchInput)
        search_input.value = ""
        self.focus_list()

    def on_key(self, event: events.Key) -> None:
        """Vim keys match the company list: s searches, j/k move, l opens."""
        if getattr(self.app, "leader_mode", False):
            return

        search_input = self.query_one("#person_search_input", CocliSearchInput)
        list_view = self.query_one("#person_list_view", ListView)

        if search_input.has_focus:
            if event.key in ("escape", "enter"):
                self.focus_list()
                event.prevent_default()
                event.stop()
            elif event.key == "up":
                list_view.action_cursor_up()
                event.prevent_default()
                event.stop()
            elif event.key == "down":
                list_view.action_cursor_down()
                event.prevent_default()
                event.stop()
            return

        if event.key == "s":
            self.action_focus_search()
            event.prevent_default()
            event.stop()
        elif event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            self.action_open_highlighted()
            event.prevent_default()
            event.stop()

    @on(Input.Changed)
    async def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        app = cast("CocliApp", self.app)
        if app.services.sync_search:
            results = app.services.fuzzy_search(
                search_query=event.value,
                item_type="person",
                limit=PERSON_SEARCH_LIMIT,
            )
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

            results = app.services.fuzzy_search(
                search_query=query,
                item_type="person",
                limit=PERSON_SEARCH_LIMIT,
            )
            
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
            rows = [
                ListItem(Label(str(item.name) if item.name else ""), name=str(item.name or ""))
                for item in self.filtered_fz_items
            ]
            if rows:
                list_view.extend(rows)
                list_view.index = 0
            else:
                list_view.index = None
            count = len(self.filtered_fz_items)
            self.query_one("#person_list_header", Label).update(f"PEOPLE ({count})")
        except Exception as e:
            logger.error(f"Error updating person list view: {e}")

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a person is selected from the list."""
        event.stop()
        self.action_open_highlighted()
