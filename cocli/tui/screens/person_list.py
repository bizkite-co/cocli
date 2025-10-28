from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from cocli.models.person import Person
from cocli.utils.textual_utils import sanitize_id # New import

class PersonList(Screen[None]):
    """A screen to display a list of people."""

    def compose(self) -> ComposeResult:
        people = Person.get_all()
        # Sort by person name, but use slug for ID
        sorted_people = sorted(people, key=lambda p: p.name)

        yield Label("People")
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(person.name), id=sanitize_id(person.slug)) for person in sorted_people]
            )
