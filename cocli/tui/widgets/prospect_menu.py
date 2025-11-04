from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult

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
