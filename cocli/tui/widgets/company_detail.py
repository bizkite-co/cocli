import logging
from typing import Dict, Optional, Any

from textual.widgets import DataTable, Static
from textual.containers import VerticalScroll, Container
from textual.app import ComposeResult

from rich.text import Text

from ...models.company import Company
from ...models.website import Website
from ...models.person import Person
from ...models.note import Note

logger = logging.getLogger(__name__)

class CompanyDetail(Container):
    BINDINGS = [
        ("escape", "app.go_back", "Back to list"),
        ("q", "app.go_back", "Back to list"),
    ]

    def __init__(self, company_data: Dict[str, Any], name: Optional[str] = None, id: Optional[str] = None, classes: Optional[str] = None):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data
        logger.debug(f"CompanyDetailScreen initialized with data for: {company_data.get('company', {}).get('name')}")

    def compose(self) -> ComposeResult:
        logger.debug("CompanyDetailScreen compose called")
        with VerticalScroll():
            yield Static("Company Details", classes="header")
            yield self._render_company_details()

            yield Static("Contacts", classes="header")
            yield self._render_contacts()

            yield Static("Meetings", classes="header")
            yield self._render_meetings()

            yield Static("Recent Notes", classes="header")
            yield self._render_notes()

    def on_mount(self) -> None:
        logger.debug("CompanyDetailScreen on_mount called")
        self.focus()

    def _render_company_details(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable()
        table.add_column("Attribute")
        table.add_column("Value")

        company = Company.model_validate(self.company_data["company"])
        tags = self.company_data["tags"]
        content = self.company_data["content"]
        website_data = Website.model_validate(self.company_data["website_data"]) if self.company_data["website_data"] else None

        if content.strip():
            table.add_row("Content", content.strip())

        for key, value in company.model_dump().items():
            if value is None or key == "name":
                continue

            key_str = key.replace('_', ' ').title()
            if key == "domain" and isinstance(value, str):
                table.add_row(key_str, Text(value, style=f"link http://{value}"))
            elif key == "phone_number" and isinstance(value, str):
                table.add_row(key_str, f"{value} (p to call)")
            else:
                table.add_row(key_str, str(value))

        if tags:
            table.add_row("Tags", ", ".join(tags))

        if website_data and website_data.services:
            table.add_row("Services", ", ".join(website_data.services))

        return table

    def _render_contacts(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable()
        table.add_column("Name")
        table.add_column("Role")
        table.add_column("Email")
        table.add_column("Phone")

        contacts_data = self.company_data["contacts"]
        if not contacts_data:
            return DataTable()

        for contact_dict in contacts_data:
            person = Person.model_validate(contact_dict)
            table.add_row(person.name, person.role, person.email, person.phone)

        return table

    def _render_meetings(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable()
        table.add_column("Date")
        table.add_column("Time")
        table.add_column("Title")

        meetings_data = self.company_data["meetings"]
        if not meetings_data:
            return DataTable()

        for meeting_dict in meetings_data:
            table.add_row(meeting_dict["datetime_utc"], "", meeting_dict["title"])

        return table

    def _render_notes(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable()
        table.add_column("Date")
        table.add_column("Title")
        table.add_column("Content")

        notes_data = self.company_data["notes"]
        if not notes_data:
            return DataTable()

        for note_dict in notes_data:
            note = Note.model_validate(note_dict)
            table.add_row(note.timestamp.strftime("%Y-%m-%d %H:%M"), note.title, note.content)

        return table


