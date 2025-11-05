from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult
from textual import events

class ProspectMenu(Screen[None]):
    """A screen to display Prospect options."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("ETL/Enrichment Menu")
        yield ListView(
            ListItem(Label("Compile Enrichment"), id="compile_enrichment"),
            ListItem(Label("Enrich Websites"), id="enrich_websites"),
            ListItem(Label("Import Companies"), id="import_companies"),
            ListItem(Label("Import Data"), id="import_data"),
            ListItem(Label("Scrape Shopify"), id="scrape_shopify"),
            ListItem(Label("Scrape"), id="scrape"),
        )

    def on_key(self, event: events.Key) -> None:
        """Handle key events for the ProspectMenu screen."""
        list_view = self.query_one(ListView)
        if event.key == "j":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "k":
            list_view.action_cursor_up()
            event.prevent_default()
        elif event.key == "l" or event.key == "enter":
            list_view.action_select_cursor()
            event.prevent_default()
