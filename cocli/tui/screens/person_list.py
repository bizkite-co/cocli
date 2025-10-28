from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input # New import Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message

from cocli.models.person import Person
from cocli.utils.textual_utils import sanitize_id

class PersonList(Screen[None]):
    """A screen to display a list of people."""

    class PersonSelected(Message):
        """Posted when a person is selected from the list."""
        def __init__(self, person_slug: str) -> None:
            super().__init__()
            self.person_slug = person_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.all_people = list(Person.get_all()) # Store all people
        self.filtered_people = self.all_people # Initialize filtered list

    def compose(self) -> ComposeResult:
        yield Label("People")
        yield Input(placeholder="Search people...", id="person_search_input") # Add search input
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(person.name), id=sanitize_id(person.slug)) for person in self.filtered_people], # Use filtered_people
                id="person_list_view"
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value.lower()
        self.filtered_people = [
            person for person in self.all_people
            if search_query in person.name.lower() or \
               (person.email and search_query in person.email.lower()) or \
               (person.company_name and search_query in person.company_name.lower()) or \
               (person.slug and search_query in person.slug.lower())
        ]
        self.update_person_list_view()

    def update_person_list_view(self) -> None:
        """Updates the ListView with filtered people."""
        list_view = self.query_one("#person_list_view", ListView)
        list_view.clear()
        for person in self.filtered_people:
            list_view.append(ListItem(Label(person.name), id=sanitize_id(person.slug)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a person is selected from the list."""
        if event.item.id:
            self.post_message(self.PersonSelected(event.item.id))
