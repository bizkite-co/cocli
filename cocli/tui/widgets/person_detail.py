from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Label, Markdown
from textual.app import ComposeResult
from textual import events

from cocli.models.people.person import Person
from cocli.models.phone import render_phone
from cocli.models.social import SOCIAL_URL_FIELDS
from ..base import CocliPanel


class PersonDetail(CocliPanel, can_focus=True):
    """A view container to display the details of a single person."""

    DEFAULT_CSS = """
    PersonDetail {
        height: 1fr;
    }
    PersonDetail VerticalScroll {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("h", "app.navigate_up", "Back", show=False, priority=True),
        Binding("escape", "app.navigate_up", "Back", show=False),
        Binding("alt+s", "app.navigate_up", "Navigate Up", show=False),
    ]

    def __init__(
        self,
        person_slug: str,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(panel_title="PERSON INFO", name=name, id=id, classes=classes)
        self.person_slug = person_slug
        # Load before compose. The first paint used to run with person=None
        # and flash "Person not found." before on_mount filled the record.
        self.person: Person | None = Person.get(person_slug)

    def compose(self) -> ComposeResult:
        yield Label("PERSON INFO", classes="pane-header")
        yield VerticalScroll(
            Markdown(self._get_person_description(), id="person-description")
        )

    def on_mount(self) -> None:
        self.focus()

    def reload(self) -> None:
        """Reread the person file after an outside edit, such as Yazi."""
        self.person = Person.get(self.person_slug)
        self.query_one("#person-description", Markdown).update(self._get_person_description())

    def on_key(self, event: events.Key) -> None:
        """h / escape leave this record for the people list."""
        if event.key not in ("h", "escape", "alt+s", "meta+s"):
            return
        if getattr(self.app, "leader_mode", False):
            return
        navigate_up = getattr(self.app, "action_navigate_up", None)
        if callable(navigate_up):
            navigate_up()
        event.prevent_default()
        event.stop()

    def _get_person_description(self) -> str:
        if not self.person:
            return "Person not found."

        description_parts = [f"# {self.person.name}"]
        if self.person.email:
            description_parts.append(f"**Email:** {self.person.email}")
        if self.person.phone:
            description_parts.append(f"**Phone:** {render_phone(self.person.phone)}")
        if self.person.company_name:
            description_parts.append(f"**Company:** {self.person.company_name}")
        if self.person.role:
            description_parts.append(f"**Role:** {self.person.role}")
        if self.person.profile_url:
            description_parts.append(f"**Profile:** {self.person.profile_url}")
        for field_name, label in SOCIAL_URL_FIELDS:
            url = getattr(self.person, field_name, None)
            if url:
                description_parts.append(f"**{label}:** {url}")
        if self.person.tags:
            description_parts.append(f"**Tags:** {', '.join(self.person.tags)}")

        # A single newline is a Markdown soft break, so every field was
        # drawn on one wrapped line. A blank line makes each field a block.
        return "\n\n".join(description_parts)

