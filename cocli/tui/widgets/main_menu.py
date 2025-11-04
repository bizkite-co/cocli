from textual.widgets import ListView, ListItem, Label
from textual.containers import Container
from textual.app import ComposeResult

class MainMenu(Container):
    """The main menu widget."""

    def compose(self) -> ComposeResult:
        yield ListView(
            ListItem(Label("Campaigns"), id="campaigns"),
            ListItem(Label("Companies"), id="companies"),
            ListItem(Label("People"), id="people"),
            ListItem(Label("Prospect"), id="prospect"),
            ListItem(Label("Exit"), id="exit"),
            id="main_menu_list"
        )
