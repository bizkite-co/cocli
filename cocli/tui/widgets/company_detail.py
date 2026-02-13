import logging
from typing import Dict, Optional, Any

from textual.widgets import DataTable, Label, Input
from textual.containers import Container
from textual.app import ComposeResult
from textual import events, on

from rich.text import Text
from rich.markup import escape

from ...models.company import Company
from ...models.website import Website

logger = logging.getLogger(__name__)

class EditInput(Input):
    """Custom Input widget that carries field metadata."""
    def __init__(self, field_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.field_name = field_name

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
        ("i", "edit_item", "Edit"),
        ("enter", "edit_item", "Edit"),
        # Sequential Jumping
        ("]", "next_panel", "Next Panel"),
        ("[", "prev_panel", "Prev Panel"),
    ]

    def __init__(self, company_data: Dict[str, Any], name: Optional[str] = None, id: Optional[str] = None, classes: Optional[str] = None):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data
        
        # Initialize tables
        self.info_table = self._create_info_table()
        self.contacts_table = self._create_contacts_table()
        self.meetings_table = self._create_meetings_table()
        self.notes_table = self._create_notes_table()
        
        # Define panel order for sequential navigation
        self.panels = [self.info_table, self.contacts_table, self.meetings_table, self.notes_table]

    def compose(self) -> ComposeResult:
        with Container(classes="detail-grid"):
            yield DetailPanel("COMPANY INFO", self.info_table, id="panel-info")
            yield DetailPanel("CONTACTS", self.contacts_table, id="panel-contacts")
            yield DetailPanel("MEETINGS", self.meetings_table, id="panel-meetings")
            yield DetailPanel("NOTES", self.notes_table, id="panel-notes")

    def on_mount(self) -> None:
        # Default focus to info table
        self.info_table.focus()

    def action_next_panel(self) -> None:
        """Jump to next panel in the grid."""
        current = self.app.focused
        for i, panel in enumerate(self.panels):
            if current == panel:
                next_idx = (i + 1) % len(self.panels)
                self.panels[next_idx].focus()
                break

    def action_prev_panel(self) -> None:
        """Jump to previous panel in the grid."""
        current = self.app.focused
        for i, panel in enumerate(self.panels):
            if current == panel:
                prev_idx = (i - 1) % len(self.panels)
                self.panels[prev_idx].focus()
                break

    def on_key(self, event: events.Key) -> None:
        """Implement boundary-aware j/k/h/l navigation."""
        focused = self.app.focused
        
        # Don't hijack j/k if an Input is focused
        if isinstance(focused, Input):
            return

        if not isinstance(focused, DataTable):
            return

        if event.key == "j":
            # If we are at the last row, jump to quadrant below
            if focused.cursor_row == len(focused.rows) - 1 or len(focused.rows) == 0:
                self.action_focus_down()
                event.prevent_default()
        elif event.key == "k":
            # If we are at the first row, jump to quadrant above
            if focused.cursor_row == 0 or len(focused.rows) == 0:
                self.action_focus_up()
                event.prevent_default()
        elif event.key == "h":
            # Direct horizontal jump
            self.action_focus_left()
            event.prevent_default()
        elif event.key == "l":
            # Direct horizontal jump
            self.action_focus_right()
            event.prevent_default()

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

    def action_edit_item(self) -> None:
        """Enters edit mode for the currently focused row."""
        focused = self.app.focused
        if not isinstance(focused, DataTable):
            return

        row_idx = focused.cursor_row
        if row_idx is None or row_idx >= len(focused.rows):
            return

        row_data = focused.get_row_at(row_idx)
        
        if focused.id == "info-table":
            field_name = str(row_data[0])
            current_value = str(row_data[1])
            
            # Map display name to actual model field
            field_map = {
                "Email": "email",
                "Phone": "phone_number",
                "Domain": "domain",
                "Name": "name"
            }
            
            model_field = field_map.get(field_name)
            if not model_field:
                self.app.notify(f"Cannot edit {field_name} yet.", severity="warning")
                return

            # Replace table with Input
            input_widget = EditInput(field_name=model_field, value=current_value, id=f"edit-{model_field}")
            
            panel = self.query_one("#panel-info", DetailPanel)
            self.info_table.display = False
            panel.mount(input_widget)
            input_widget.focus()

    @on(Input.Submitted)
    async def handle_edit_submitted(self, event: Input.Submitted) -> None:
        """Save the edited value back to the company model."""
        if not isinstance(event.input, EditInput):
            return
            
        field_name = event.input.field_name
        new_value = event.value
        company_slug = self.company_data["company"].get("slug")
        
        if company_slug:
            try:
                # Load, update, and save
                company = Company.get(company_slug)
                if company:
                    setattr(company, field_name, new_value)
                    company.save()
                    self.app.notify(f"Updated {field_name}")
                    
                    # Refresh the local data and UI
                    self.company_data["company"][field_name] = new_value
                    
                    # Clean up
                    event.input.remove()
                    self.info_table = self._create_info_table() # Re-render table
                    
                    panel = self.query_one("#panel-info", DetailPanel)
                    panel.query(DataTable).remove()
                    panel.mount(self.info_table)
                    self.info_table.focus()
            except Exception as e:
                self.app.notify(f"Save failed: {e}", severity="error")

    def _create_info_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="info-table")
        table.add_column("Attribute", width=15)
        table.add_column("Value")
        
        company_data = self.company_data["company"]
        tags = self.company_data.get("tags", [])
        website_data = Website.model_validate(self.company_data["website_data"]) if self.company_data.get("website_data") else None

        table.add_row("Name", escape(company_data.get("name", "Unknown")))
        
        # Address Group
        addr_parts = [company_data.get("street_address"), company_data.get("city"), company_data.get("state"), company_data.get("zip_code")]
        full_addr = ", ".join([str(p) for p in addr_parts if p])
        if full_addr:
            table.add_row("Address", escape(full_addr))
        
        if company_data.get("domain"):
            table.add_row("Domain", Text(str(company_data.get("domain")), style="link"))
        if company_data.get("email"):
            table.add_row("Email", str(company_data.get("email")))
        if company_data.get("phone_number"):
            table.add_row("Phone", str(company_data.get("phone_number")))
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
            table.add_row(escape(c.get("name", "Unknown")), escape(c.get("role", "")), str(c.get("email", "")))
        return table

    def _create_meetings_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="meetings-table")
        table.add_column("Date", width=12)
        table.add_column("Title")

        meetings = self.company_data.get("meetings", [])
        for m in meetings:
            dt = m.get("datetime_utc", "")[:10]
            table.add_row(dt, escape(m.get("title", "Untitled")))
        return table

    def _create_notes_table(self) -> DataTable[Any]:
        table: DataTable[Any] = DataTable(id="notes-table")
        table.add_column("Date", width=12)
        table.add_column("Preview")

        notes = self.company_data.get("notes", [])
        for n in notes:
            date_str = n.get("timestamp", "")[:10] if isinstance(n.get("timestamp"), str) else "N/A"
            content_preview = escape(n.get("content", "")[:100].replace("\n", " "))
            table.add_row(date_str, content_preview)
        return table
