from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label, ListItem, ListView


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
