from typing import TYPE_CHECKING, cast, Dict, Any
from textual.app import ComposeResult
from textual.widgets import Label, ListView, ListItem
from textual.containers import Container
from textual.message import Message
from textual import on, events, work

if TYPE_CHECKING:
    from ..app import CocliApp

class TemplateList(Container):
    """A list of search templates."""

    class TemplateSelected(Message):
        def __init__(self, template_id: str) -> None:
            super().__init__()
            self.template_id = template_id

    def compose(self) -> ComposeResult:
        yield Label("TEMPLATES", id="template_header", classes="pane-header")
        yield ListView(
            ListItem(Label("All Leads"), id="tpl_all"),
            ListItem(Label("With Email"), id="tpl_with_email"),
            ListItem(Label("Missing Email"), id="tpl_no_email"),
            ListItem(Label("Actionable (E+P)"), id="tpl_actionable"),
            ListItem(Label("Missing Address"), id="tpl_no_address"),
            ListItem(Label("Top Rated"), id="tpl_top_rated"),
            ListItem(Label("Most Reviewed"), id="tpl_most_reviewed"),
            id="template_list"
        )

    async def on_mount(self) -> None:
        self.update_counts()

    @work(exclusive=True, thread=True)
    async def update_counts(self) -> None:
        app = cast("CocliApp", self.app)
        counts = app.services.get_template_counts()
        self.call_after_refresh(self._apply_counts, counts)

    def _apply_counts(self, counts: Dict[str, int]) -> None:
        for item_id, count in counts.items():
            try:
                item = self.query_one(f"#{item_id}", ListItem)
                label = item.query_one(Label)
                # Cast to Any to access renderable which exists at runtime but might be tricky for mypy
                base_text = str(cast(Any, label).renderable).split(" (")[0]
                label.update(f"{base_text} ({count})")
            except Exception:
                pass

    @on(ListView.Selected, "#template_list")
    def on_template_selected(self, event: ListView.Selected) -> None:
        if event.item and event.item.id:
            self.post_message(self.TemplateSelected(event.item.id))

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the TemplateList widget."""
        list_view = self.query_one("#template_list", ListView)
        
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()

    def focus_list(self) -> None:
        self.query_one(ListView).focus()
