import logging
import webbrowser
import subprocess
import re
from typing import Dict, Optional, Any, Union, cast
from datetime import datetime
from pathlib import Path

from textual.widgets import DataTable, Label, Input, TextArea, Button
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from textual import events, on
from textual.widget import Widget
from textual.binding import Binding
from textual.screen import ModalScreen

from rich.text import Text
from rich.markup import escape

from ...models.company import Company
from ...models.note import Note
from ...models.phone import PhoneNumber
from ...core.config import get_companies_dir

logger = logging.getLogger(__name__)

def format_phone_display(value: Any) -> Union[Text, str]:
    """Helper to consistently format phone numbers for display."""
    if not value:
        return ""
    try:
        pn = PhoneNumber.model_validate(value)
        if pn:
            return Text(pn.format("international"), style="bold #00ff00")
    except Exception:
        pass
    return str(value)

class NoteEditor(ModalScreen[Optional[Note]]):
    """A full-screen modal for editing a multi-line note."""
    
    BINDINGS = [
        ("ctrl+s", "save_note", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, note: Optional[Note] = None):
        super().__init__()
        self.note = note or Note(title="", content="")
        self.title_input = Input(value=self.note.title, placeholder="Note Title...")
        self.content_area = TextArea(self.note.content)

    def compose(self) -> ComposeResult:
        with Vertical(id="note-editor-container"):
            yield Label("EDIT NOTE" if self.note.title else "NEW NOTE", classes="panel-header")
            yield self.title_input
            yield self.content_area
            with Horizontal(classes="editor-buttons"):
                yield Button("Save (Ctrl+S)", variant="success", id="save-btn")
                yield Button("Cancel (ESC)", variant="error", id="cancel-btn")

    def on_mount(self) -> None:
        if not self.note.title:
            self.title_input.focus()
        else:
            self.content_area.focus()

    def action_save_note(self) -> None:
        self.note.title = self.title_input.value
        self.note.content = self.content_area.text
        if not self.note.title:
            self.app.notify("Title is required", severity="error")
            return
        self.dismiss(self.note)

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def on_save_click(self) -> None:
        self.action_save_note()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_click(self) -> None:
        self.dismiss(None)

class QuadrantTable(DataTable[Any]):
    """
    A specialized DataTable for quadrants that supports VIM keys 
    and escaping back to the panel level.
    """
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("escape", "exit_quadrant", "Exit Quadrant"),
        Binding("alt+s", "exit_quadrant", "Exit Quadrant"),
    ]

    def action_exit_quadrant(self) -> None:
        """Move focus back up to the DetailPanel."""
        if self.parent and isinstance(self.parent, DetailPanel):
            self.parent.focus()

class InfoTable(QuadrantTable):
    """Specific bindings for the Info quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("i", "edit_row", "Edit Field"),
        Binding("enter", "edit_row", "Edit Field"),
    ]

class ContactsTable(QuadrantTable):
    """Specific bindings for the Contacts quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("a", "add_contact", "Add Contact"),
    ]

class MeetingsTable(QuadrantTable):
    """Specific bindings for the Meetings quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("a", "add_meeting", "Add Meeting"),
    ]

class NotesTable(QuadrantTable):
    """Specific bindings for the Notes quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("a", "add_note", "Add Note"),
        Binding("i", "edit_note", "Edit Note"),
        Binding("enter", "edit_note", "Edit Note"),
    ]

class EditInput(Input):
    """Custom Input widget that carries field metadata."""
    def __init__(self, field_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.field_name = field_name

class DetailPanel(Container):
    """A focusable panel containing a title and a widget."""
    def __init__(self, title: str, child: Widget, id: str):
        super().__init__(id=id, classes="panel")
        self.can_focus = True
        self.title = title
        self.child = child

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="panel-header")
        yield self.child

class CompanyDetail(Container):
    """
    Highly dense company detail view with Layered VIM-like navigation.
    """
    
    BINDINGS = [
        ("escape", "app.action_escape", "Back"),
        ("q", "app.action_escape", "Back"),
        ("i", "enter_quadrant", "Enter Quadrant"),
        ("enter", "enter_quadrant", "Enter Quadrant"),
        # Sequential Jumping
        ("]", "next_panel", "Next Panel"),
        ("[", "prev_panel", "Prev Panel"),
        # CLI-Legacy Keymaps
        ("w", "open_website", "Website"),
        ("p", "call_company", "Call"),
        ("e", "open_folder", "Explorer (NVim)"),
    ]

    def __init__(self, company_data: Dict[str, Any], name: Optional[str] = None, id: Optional[str] = None, classes: Optional[str] = None):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data
        
        # Initialize tables
        self.info_table = self._create_info_table()
        self.contacts_table = self._create_contacts_table()
        self.meetings_table = self._create_meetings_table()
        self.notes_table = self._create_notes_table()
        
        # Initialize panels
        self.panel_info = DetailPanel("COMPANY INFO", self.info_table, id="panel-info")
        self.panel_contacts = DetailPanel("CONTACTS", self.contacts_table, id="panel-contacts")
        self.panel_meetings = DetailPanel("MEETINGS", self.meetings_table, id="panel-meetings")
        self.panel_notes = DetailPanel("NOTES", self.notes_table, id="panel-notes")
        
        # Define panel order for navigation
        self.panels = [self.panel_info, self.panel_contacts, self.panel_meetings, self.panel_notes]

    def compose(self) -> ComposeResult:
        with Container(classes="detail-grid"):
            yield self.panel_info
            yield self.panel_contacts
            yield self.panel_meetings
            yield self.panel_notes

    def on_mount(self) -> None:
        # Default focus to the Info panel (High level)
        self.panel_info.focus()

    def action_next_panel(self) -> None:
        """Jump to next panel in the grid."""
        current = self.app.focused
        if current is None:
            return

        # If focused on a child, focus the parent panel first
        child_widgets = [p.child for p in self.panels]
        if current in child_widgets:
            parent = current.parent
            if parent and isinstance(parent, DetailPanel):
                current = parent
            
        for i, panel in enumerate(self.panels):
            if current == panel:
                next_idx = (i + 1) % len(self.panels)
                self.panels[next_idx].focus()
                break

    def action_prev_panel(self) -> None:
        """Jump to previous panel in the grid."""
        current = self.app.focused
        if current is None:
            return

        child_widgets = [p.child for p in self.panels]
        if current in child_widgets:
            parent = current.parent
            if parent and isinstance(parent, DetailPanel):
                current = parent

        for i, panel in enumerate(self.panels):
            if current == panel:
                prev_idx = (i - 1) % len(self.panels)
                self.panels[prev_idx].focus()
                break

    def action_enter_quadrant(self) -> None:
        """Move focus from the Panel to the inner content."""
        focused = self.app.focused
        if isinstance(focused, DetailPanel):
            focused.child.focus()

    def on_key(self, event: events.Key) -> None:
        """Implement layered navigation logic."""
        focused = self.app.focused
        
        # Handle Navigation at Panel Level (hjkl switches quadrants)
        if isinstance(focused, DetailPanel):
            if event.key == "h":
                if focused == self.panel_contacts:
                    self.panel_info.focus()
                elif focused == self.panel_notes:
                    self.panel_meetings.focus()
                event.prevent_default()
            elif event.key == "l":
                if focused == self.panel_info:
                    self.panel_contacts.focus()
                elif focused == self.panel_meetings:
                    self.panel_notes.focus()
                event.prevent_default()
            elif event.key == "j":
                if focused == self.panel_info:
                    self.panel_meetings.focus()
                elif focused == self.panel_contacts:
                    self.panel_notes.focus()
                event.prevent_default()
            elif event.key == "k":
                if focused == self.panel_meetings:
                    self.panel_info.focus()
                elif focused == self.panel_notes:
                    self.panel_contacts.focus()
                event.prevent_default()
            return

        # Handle Navigation inside Quadrant (DataTable)
        if isinstance(focused, DataTable):
            if event.key == "escape":
                # Exit back to panel level
                parent = focused.parent
                if parent and hasattr(parent, "focus"):
                    parent.focus()
                event.prevent_default()
                event.stop()
            return

    def action_open_website(self) -> None:
        domain = self.company_data["company"].get("domain")
        if domain:
            url = f"http://{domain}"
            webbrowser.open(url)
            self.app.notify(f"Opening {url}")
        else:
            self.app.notify("No domain found", severity="warning")

    def action_call_company(self) -> None:
        phone = self.company_data["company"].get("phone_number")
        if phone:
            cleaned = re.sub(r'\D', '', str(phone))
            if not cleaned.startswith('1'):
                cleaned = '1' + cleaned
            url = f"https://voice.google.com/u/0/calls?a=nc,%2B{cleaned}"
            webbrowser.open(url)
            self.app.notify(f"Calling {phone}...")
        else:
            self.app.notify("No phone number found", severity="warning")

    def action_open_folder(self) -> None:
        slug = self.company_data["company"].get("slug")
        if slug:
            path = get_companies_dir() / slug
            self.app.notify(f"Opening {slug} in NVim...")
            subprocess.Popen(["nvim", str(path)])
        else:
            self.app.notify("No slug found", severity="error")

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "info-table":
            self.trigger_row_edit(cast(InfoTable, event.data_table))
        elif event.data_table.id == "notes-table":
            self.action_edit_note()

    def trigger_row_edit(self, table: InfoTable) -> None:
        """Core logic for entering edit mode on a row."""
        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(table.rows):
            return

        row_data = table.get_row_at(row_idx)
        field_name = str(row_data[0])
        current_value = str(row_data[1])
        if current_value == "None" or current_value == "N/A":
            current_value = ""
        
        # Map display name to actual model field
        field_map = {
            "Email": "email",
            "Phone": "phone_number",
            "Domain": "domain",
            "Name": "name",
            "Street": "street_address",
            "City": "city",
            "State": "state",
            "Zip": "zip_code"
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
                    self.info_table = self._create_info_table() 
                    
                    panel = self.query_one("#panel-info", DetailPanel)
                    panel.query(DataTable).remove()
                    panel.mount(self.info_table)
                    self.info_table.focus()
            except Exception as e:
                self.app.notify(f"Save failed: {e}", severity="error")

    def action_add_note(self) -> None:
        self.app.push_screen(NoteEditor(), self.save_new_note)

    def save_new_note(self, note: Optional[Note]) -> None:
        if note:
            slug = self.company_data["company"].get("slug")
            if slug:
                notes_dir = get_companies_dir() / slug / "notes"
                note.to_file(notes_dir)
                self.app.notify("Note saved")
                # Refresh notes table
                self.company_data["notes"].append(note.model_dump())
                self.refresh_notes_table()

    def action_edit_note(self) -> None:
        row_idx = self.notes_table.cursor_row
        if row_idx is None or row_idx >= len(self.notes_table.rows):
            return
        
        note_data = self.company_data["notes"][row_idx]
        try:
            if "file_path" in note_data:
                note = Note.from_file(Path(note_data["file_path"]))
            else:
                note = Note.model_validate(note_data)
            
            if note:
                self.app.push_screen(NoteEditor(note), lambda n: self.update_existing_note(n, row_idx))
        except Exception as e:
            self.app.notify(f"Could not load note: {e}", severity="error")

    def update_existing_note(self, note: Optional[Note], index: int) -> None:
        if note:
            slug = self.company_data["company"].get("slug")
            if slug:
                notes_dir = get_companies_dir() / slug / "notes"
                note.to_file(notes_dir)
                self.app.notify("Note updated")
                self.company_data["notes"][index] = note.model_dump()
                self.refresh_notes_table()

    def refresh_notes_table(self) -> None:
        new_table = self._create_notes_table()
        panel = self.query_one("#panel-notes", DetailPanel)
        panel.query(DataTable).remove()
        panel.mount(new_table)
        self.notes_table = new_table
        self.notes_table.focus()

    def _create_info_table(self) -> InfoTable:
        table = InfoTable(id="info-table")
        table.add_column("Attribute", width=10)
        table.add_column("Value")
        
        c = self.company_data["company"]
        tags = self.company_data.get("tags", [])
        website_data = self.company_data.get("website_data")

        table.add_row("Name", escape(str(c.get("name", "Unknown"))))
        table.add_row("Domain", escape(str(c.get("domain") or "")))
        table.add_row("Email", escape(str(c.get("email") or "")))
        table.add_row("Phone", format_phone_display(c.get("phone_number")))
        table.add_row("Street", escape(str(c.get("street_address") or "")))
        table.add_row("City", escape(str(c.get("city") or "")))
        table.add_row("State", escape(str(c.get("state") or "")))
        table.add_row("Zip", escape(str(c.get("zip_code") or "")))

        if tags:
            table.add_row("Tags", ", ".join(tags))
        
        if website_data:
            socials = []
            if website_data.get("linkedin_url"):
                socials.append("LinkedIn")
            if website_data.get("facebook_url"):
                socials.append("FB")
            if website_data.get("instagram_url"):
                socials.append("IG")
            if socials:
                table.add_row("Socials", " | ".join(socials))
            
            desc = website_data.get("description")
            if desc:
                table.add_row("Desc", escape(desc[:100] + "..."))

        return table

    def _create_contacts_table(self) -> ContactsTable:
        table = ContactsTable(id="contacts-table")
        table.add_column("Name")
        table.add_column("Role")
        table.add_column("Email")

        contacts = self.company_data.get("contacts", [])
        for c in contacts:
            table.add_row(escape(c.get("name", "Unknown")), escape(c.get("role", "")), str(c.get("email", "")))
        return table

    def _create_meetings_table(self) -> MeetingsTable:
        table = MeetingsTable(id="meetings-table")
        table.add_column("Date", width=12)
        table.add_column("Title")

        meetings = self.company_data.get("meetings", [])
        for m in meetings:
            dt = m.get("datetime_utc", "")[:10]
            table.add_row(dt, escape(m.get("title", "Untitled")))
        return table

    def _create_notes_table(self) -> NotesTable:
        table = NotesTable(id="notes-table")
        table.add_column("Date", width=12)
        table.add_column("Preview")

        notes = self.company_data.get("notes", [])
        for n in notes:
            ts = n.get("timestamp")
            if isinstance(ts, datetime):
                ts_str = ts.strftime("%Y-%m-%d")
            else:
                ts_str = str(ts)[:10]
            content_preview = escape(n.get("content", "")[:100].replace("\n", " "))
            table.add_row(ts_str, content_preview)
        return table
