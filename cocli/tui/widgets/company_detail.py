import logging
from typing import Dict, Optional, Any

from textual.widgets import DataTable, Label
from textual.containers import Container
from textual.app import ComposeResult

from rich.text import Text
from rich.markup import escape

from ...models.company import Company
from ...models.website import Website
from ...models.person import Person
from ...models.note import Note

logger = logging.getLogger(__name__)

class DetailPanel(Container):
    """A focusable panel containing a title and a widget."""
    def __init__(self, title: str, child: Any, id: str):
        super().__init__(id=id, classes="panel")
        self.title = title
        self.child = child

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="panel-header")
        yield self.child

class CompanyDetail(Container):
    """
    Highly dense company detail view with VIM-like panel navigation.
    Layout: 2x2 Grid
    [ Info ] [ Contacts ]
    [ Meetings ] [ Notes ]
    """
    
    BINDINGS = [
        ("escape", "app.action_escape", "Back"),
        ("q", "app.action_escape", "Back"),
        # VIM Navigation between panels
        ("ctrl+k", "focus_up", "Focus Up"),
        ("ctrl+j", "focus_down", "Focus Down"),
        ("ctrl+h", "focus_left", "Focus Left"),
        ("ctrl+l", "focus_right", "Focus Right"),
    ]

    def __init__(self, company_data: Dict[str, Any], name: Optional[str] = None, id: Optional[str] = None, classes: Optional[str] = None):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data
        
        # Initialize tables
        self.info_table = self._create_info_table()
        self.contacts_table = self._create_contacts_table()
        self.meetings_table = self._create_meetings_table()
        self.notes_table = self._create_notes_table()

    def compose(self) -> ComposeResult:
        with Container(classes="detail-grid"):
            yield DetailPanel("COMPANY INFO", self.info_table, id="panel-info")
            yield DetailPanel("CONTACTS", self.contacts_table, id="panel-contacts")
            yield DetailPanel("MEETINGS", self.meetings_table, id="panel-meetings")
            yield DetailPanel("NOTES", self.notes_table, id="panel-notes")

    def on_mount(self) -> None:
        # Default focus to info table
        self.info_table.focus()

    def action_focus_up(self) -> None:
        if self.meetings_table.has_focus:
            self.info_table.focus()
        elif self.notes_table.has_focus:
            self.contacts_table.focus()

    def action_focus_down(self) -> None:
        if self.info_table.has_focus:
            self.meetings_table.focus()
        elif self.contacts_table.has_focus:
            self.notes_table.focus()

    def action_focus_left(self) -> None:
        if self.contacts_table.has_focus:
            self.info_table.focus()
        elif self.notes_table.has_focus:
            self.meetings_table.focus()

    def action_focus_right(self) -> None:
        if self.info_table.has_focus:
            self.contacts_table.focus()
        elif self.meetings_table.has_focus:
            self.notes_table.focus()

    def _create_info_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="info-table")
        table.add_column("Attribute", width=15)
        table.add_column("Value")
        
        company = Company.model_validate(self.company_data["company"])
        tags = self.company_data["tags"]
        website_data = Website.model_validate(self.company_data["website_data"]) if self.company_data["website_data"] else None

        table.add_row("Name", escape(company.name))
        
        # Address Group
        addr_parts = [company.street_address, company.city, company.state, company.zip_code]
        full_addr = ", ".join([p for p in addr_parts if p])
        if full_addr:
            table.add_row("Address", escape(full_addr))
        
        if company.domain:
            table.add_row("Domain", Text(company.domain, style="link"))
        if company.email:
            table.add_row("Email", str(company.email))
        if company.phone_number:
            table.add_row("Phone", str(company.phone_number))
        if tags:
            table.add_row("Tags", ", ".join(tags))
        
        # Website Socials
        if website_data:
            socials = []
            if website_data.linkedin_url:
                socials.append("LinkedIn")
            if website_data.facebook_url:
                socials.append("FB")
            if website_data.instagram_url:
                socials.append("IG")
            if socials:
                table.add_row("Socials", " | ".join(socials))
            
            if website_data.description:
                table.add_row("Description", escape(website_data.description[:200] + "..."))
            if website_data.services:
                table.add_row("Services", ", ".join(website_data.services[:10]))

        return table

    def _create_contacts_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="contacts-table")
        table.add_column("Name")
        table.add_column("Role")
        table.add_column("Email")

        contacts = self.company_data.get("contacts", [])
        for c in contacts:
            p = Person.model_validate(c)
            table.add_row(escape(p.name), escape(p.role or ""), str(p.email or ""))
        return table

    def _create_meetings_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="meetings-table")
        table.add_column("Date", width=12)
        table.add_column("Title")

        meetings = self.company_data.get("meetings", [])
        for m in meetings:
            # meetings data might be raw dicts
            dt = m.get("datetime_utc", "")[:10]
            table.add_row(dt, escape(m.get("title", "Untitled")))
        return table

    def _create_notes_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="notes-table")
        table.add_column("Date", width=12)
        table.add_column("Preview")

        notes = self.company_data.get("notes", [])
        for n in notes:
            note = Note.model_validate(n)
            date_str = note.timestamp.strftime("%Y-%m-%d")
            content_preview = escape(note.content[:100].replace("\n", " "))
            table.add_row(date_str, content_preview)
        return table
