from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult

class MainMenu(Screen[None]):
    """The main menu screen for the cocli TUI."""

    def compose(self) -> ComposeResult:
        yield Label("Main Menu")
        yield ListView(
            ListItem(Label("Campaigns"), id="campaigns"),
            ListItem(Label("Companies"), id="companies"),
            ListItem(Label("People"), id="people"),
            ListItem(Label("ETL/Enrichment"), id="etl_enrichment"),
            ListItem(Label("Exit"), id="exit"),
        )
