from textual.screen import Screen
from textual.widgets import Header, Footer, Markdown
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from cocli.models.person import Person

class PersonDetail(Screen[None]):
    """A screen to display the details of a single person."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, person_slug: str, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.person_slug = person_slug
        self.person: Person | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield VerticalScroll(
            Markdown(self._get_person_description(), classes="person-description")
        )

    def on_mount(self) -> None:
        self.person = Person.get(self.person_slug)
        if self.person:
            self.sub_title = self.person.name
        else:
            self.sub_title = "Person Not Found"
        self.query_one(Markdown).update(self._get_person_description())

    def _get_person_description(self) -> str:
        if not self.person:
            return "Person not found."
        
        description_parts = [f"# {self.person.name}"]
        if self.person.email:
            description_parts.append(f"**Email:** {self.person.email}")
        if self.person.phone:
            description_parts.append(f"**Phone:** {self.person.phone}")
        if self.person.company_name:
            description_parts.append(f"**Company:** {self.person.company_name}")
        if self.person.role:
            description_parts.append(f"**Role:** {self.person.role}")
        if self.person.tags:
            description_parts.append(f"**Tags:** {', '.join(self.person.tags)}")
        
        return "\n".join(description_parts)
