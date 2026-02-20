import logging
import webbrowser
import subprocess
import re
from typing import Dict, Optional, Any, Union, cast, TYPE_CHECKING
from datetime import datetime
from pathlib import Path

from textual.widgets import DataTable, Label, Input
from textual.containers import Container
from textual.app import ComposeResult
from textual import events, on
from textual.widget import Widget
from textual.binding import Binding

from rich.text import Text
from rich.markup import escape

from ...models.companies.company import Company
from ...models.companies.note import Note
from ...models.phone import PhoneNumber
from ...core.paths import paths
from ...core.config import get_editor_command
from .confirm_screen import ConfirmScreen

if TYPE_CHECKING:
    from ..app import CocliApp

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

def format_email_display(value: Any) -> Union[Text, str]:
    """Helper to consistently format email addresses for display."""
    if not value:
        return ""
    return Text(str(value), style="cyan")

class QuadrantTable(DataTable[Any]):
    """
    A specialized DataTable for quadrants that supports VIM keys 
    and escaping back to the panel level.
    """
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("escape", "exit_quadrant", "Exit Quadrant"),
    ]

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "i":
            if hasattr(self, "action_edit_row"):
                self.action_edit_row()
                event.stop()
                event.prevent_default()
            elif hasattr(self, "action_edit_item"):
                self.action_edit_item()
                event.stop()
                event.prevent_default()
        elif event.key == "d":
            if hasattr(self, "action_delete_item"):
                self.action_delete_item()
                event.stop()
                event.prevent_default()
        elif event.key in ("alt+s", "meta+s"):
            from ..app import tui_debug_log
            tui_debug_log(f"DETAIL: Table bubbling {event.key} to app")
            app = cast("CocliApp", self.app)
            app.action_navigate_up()
            event.stop()
            event.prevent_default()
        else:
            await super()._on_key(event)

    def action_exit_quadrant(self) -> None:
        """Move focus back up to the DetailPanel."""
        from ..app import tui_debug_log
        tui_debug_log(f"DETAIL: Exit quadrant triggered from {self.__class__.__name__}")
        if self.parent and isinstance(self.parent, DetailPanel):
            self.parent.focus()

class InfoTable(QuadrantTable):
    """Specific bindings for the Info quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("i", "edit_row", "Edit Field"),
        Binding("enter", "edit_row", "Edit Field"),
    ]

    def action_edit_row(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
            detail_view.trigger_row_edit(self)

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
        Binding("i", "edit_item", "Edit Note"),
        Binding("enter", "edit_item", "Edit Note"),
        Binding("d", "delete_item", "Delete Note"),
    ]

    def action_edit_item(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
             detail_view.action_edit_note()

    def action_add_note(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
             detail_view.action_add_note()

    def action_delete_item(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
             detail_view.app.run_worker(detail_view.action_delete_note())

class EditInput(Input):
    """Custom Input widget that carries field metadata."""
    def __init__(self, field_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.field_name = field_name

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "alt+s", "meta+s"):
            from ..app import tui_debug_log
            tui_debug_log(f"DETAIL: Cancel edit for {self.field_name} via {event.key}")
            detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
            if detail_view:
                detail_view.action_cancel_edit()
            event.stop()
            event.prevent_default()

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
        Binding("escape", "app.action_escape", "Back"),
        Binding("q", "app.action_escape", "Back"),
        Binding("alt+s", "app.navigate_up", "Navigate Up"),
        Binding("meta+s", "app.navigate_up", "Navigate Up", show=False),
        Binding("i", "enter_quadrant", "Enter Quadrant"),
        Binding("enter", "enter_quadrant", "Enter Quadrant"),
        Binding("a", "add_item", "Add Item"),
        Binding("d", "delete_item", "Delete Item"),
        Binding("]", "next_panel", "Next Panel"),
        Binding("[", "prev_panel", "Prev Panel"),
        Binding("w", "open_website", "Website"),
        Binding("g", "open_gmb", "Google Maps"),
        Binding("v", "view_enrichment", "Enrichment"),
        Binding("p", "call_company", "Call"),
        Binding("e", "open_folder", "Explorer (NVim)"),
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
        self.panel_info.focus()

    def action_next_panel(self) -> None:
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
                next_idx = (i + 1) % len(self.panels)
                self.panels[next_idx].focus()
                break

    def action_prev_panel(self) -> None:
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
        focused = self.app.focused
        if isinstance(focused, DetailPanel):
            focused.child.focus()

    def action_add_item(self) -> None:
        """Route 'a' key based on the focused quadrant."""
        focused = self.app.focused
        if focused == self.panel_notes or self.notes_table.has_focus:
            self.action_add_note()
        elif focused == self.panel_contacts or self.contacts_table.has_focus:
            self.app.notify("Add Contact coming soon")
        elif focused == self.panel_meetings or self.meetings_table.has_focus:
            self.app.notify("Add Meeting coming soon")

    def action_delete_item(self) -> None:
        """Route 'd' key based on the focused quadrant."""
        focused = self.app.focused
        if focused == self.panel_notes or self.notes_table.has_focus:
            self.app.run_worker(self.action_delete_note())
        elif focused == self.panel_contacts or self.contacts_table.has_focus:
            self.app.notify("Delete Contact coming soon")
        elif focused == self.panel_meetings or self.meetings_table.has_focus:
            self.app.notify("Delete Meeting coming soon")

    def on_key(self, event: events.Key) -> None:
        # Don't return early if it's NOT a nav key, allow bubbling
        focused = self.app.focused
        
        # Handle alt+s/meta+s explicitly to ensure it reaches app if not handled by children
        if event.key in ("alt+s", "meta+s"):
            from ..app import tui_debug_log
            tui_debug_log(f"DETAIL: CompanyDetail bubbling {event.key} to app")
            app = cast("CocliApp", self.app)
            app.action_navigate_up()
            event.stop()
            event.prevent_default()
            return

        if isinstance(focused, DetailPanel):
            if event.key == "h":
                if focused == self.panel_contacts:
                    self.panel_info.focus()
                elif focused == self.panel_notes:
                    self.panel_meetings.focus()
                event.prevent_default()
                return
            elif event.key == "l":
                if focused == self.panel_info:
                    self.panel_contacts.focus()
                elif focused == self.panel_meetings:
                    self.panel_notes.focus()
                event.prevent_default()
                return
            elif event.key == "j":
                if focused == self.panel_info:
                    self.panel_meetings.focus()
                elif focused == self.panel_contacts:
                    self.panel_notes.focus()
                event.prevent_default()
                return
            elif event.key == "k":
                if focused == self.panel_meetings:
                    self.panel_info.focus()
                elif focused == self.panel_notes:
                    self.panel_contacts.focus()
                event.prevent_default()
                return

        # Explicitly handle DataTable focus without swallowing other keys
        if isinstance(focused, DataTable):
            if event.key == "escape":
                from ..app import tui_debug_log
                tui_debug_log("DETAIL: DataTable escape to Panel")
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

    def action_open_gmb(self) -> None:
        gmb_url = self.company_data["company"].get("gmb_url")
        if gmb_url:
            webbrowser.open(gmb_url)
            self.app.notify("Opening Google Maps...")
        else:
            self.app.notify("No Google Maps URL found", severity="warning")

    def action_view_enrichment(self) -> None:
        path = self.company_data.get("enrichment_path")
        if path and Path(path).exists():
            self._edit_with_nvim(Path(path))
        else:
            self.app.notify("Enrichment file not found", severity="warning")

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
            path = paths.companies.entry(slug)
            self.app.notify(f"Opening {slug} in NVim...")
            subprocess.Popen(["nvim", str(path)])
        else:
            self.app.notify("No slug found", severity="error")

    def action_add_note(self) -> None:
        """Create a new note using NVim."""
        slug = self.company_data["company"].get("slug")
        if not slug:
            return

        new_note = Note(title="New Note", content="")
        notes_dir = paths.companies.entry(slug) / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp_str = new_note.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        temp_path = notes_dir / f"{timestamp_str}-new-note.md"
        
        new_note.to_file(notes_dir)
        self._edit_with_nvim(temp_path)

    def action_edit_note(self) -> None:
        """Edit an existing note using NVim."""
        row_idx = self.notes_table.cursor_row
        num_notes = len(self.company_data.get("notes", []))
        logger.debug(f"action_edit_note: row_idx={row_idx}, num_notes={num_notes}")
        
        if row_idx is None or row_idx >= num_notes:
            self.app.notify("No note selected", severity="warning")
            return
        
        note_data = self.company_data["notes"][row_idx]
        file_path = note_data.get("file_path")
        logger.debug(f"action_edit_note: selected note file_path={file_path}")
        
        if file_path:
            self._edit_with_nvim(Path(file_path))

    async def action_delete_note(self) -> None:
        """Delete an existing note with confirmation."""
        row_idx = self.notes_table.cursor_row
        num_notes = len(self.company_data.get("notes", []))
        logger.debug(f"action_delete_note: row_idx={row_idx}, num_notes={num_notes}")
        
        if row_idx is None or row_idx >= num_notes:
            self.app.notify("No note selected", severity="warning")
            return
        
        note_data = self.company_data["notes"][row_idx]
        file_path = note_data.get("file_path")
        logger.debug(f"action_delete_note: selected note file_path={file_path}")
        
        if not file_path:
            return
            
        confirm = await self.app.push_screen(ConfirmScreen("Are you sure you want to delete this note?"))
        logger.debug(f"action_delete_note: confirmation result={confirm}")
        
        if confirm:
            try:
                Path(file_path).unlink()
                self.app.notify("Note deleted")
                self.refresh_notes_data()
            except Exception as e:
                logger.error(f"Failed to delete note: {e}")
                self.app.notify(f"Delete failed: {e}", severity="error")

    def _edit_with_nvim(self, path: Path) -> None:
        """Suspend the TUI and open NVim."""
        editor = get_editor_command() or "nvim"
        
        try:
            with self.app.suspend():
                subprocess.run([editor, str(path)], check=False)
            
            self.app.notify("Note saved")
            # Reload notes from disk
            self.refresh_notes_data()
        except Exception as e:
            logger.error(f"NVim editor session failed: {e}")
            self.app.notify(f"Editor failed: {e}", severity="error")

    def refresh_notes_data(self) -> None:
        """Reload notes from the filesystem and refresh the table."""
        slug = self.company_data["company"].get("slug")
        if not slug:
            return
            
        try:
            from ...application.company_service import get_company_details_for_view
            reloaded = get_company_details_for_view(slug)
            if reloaded:
                self.company_data["notes"] = reloaded["notes"]
                self.refresh_notes_table()
        except Exception as e:
            logger.error(f"Failed to refresh notes: {e}")

    def refresh_notes_table(self) -> None:
        """Repopulate the existing table rather than replacing it for stability."""
        self.notes_table.clear()
        notes = self.company_data.get("notes", [])
        for n in notes:
            ts = n.get("timestamp")
            if isinstance(ts, datetime):
                ts_str = ts.strftime("%Y-%m-%d")
            else:
                ts_str = str(ts)[:10]
            content_preview = escape(n.get("content", "")[:100].replace("\n", " "))
            self.notes_table.add_row(ts_str, content_preview)
        
        self.notes_table.focus()

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "info-table":
            self.trigger_row_edit(cast(InfoTable, event.data_table))
        elif event.data_table.id == "notes-table":
            self.action_edit_note()

    def trigger_row_edit(self, table: InfoTable) -> None:
        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(table.rows):
            return
        row_data = table.get_row_at(row_idx)
        field_name = str(row_data[0])
        current_value = str(row_data[1])
        if current_value == "None" or current_value == "N/A":
            current_value = ""
        field_map = {
            "Email": "email", "Phone": "phone_number", "Domain": "domain", "Name": "name",
            "Street": "street_address", "City": "city", "State": "state", "Zip": "zip_code"
        }
        model_field = field_map.get(field_name)
        if not model_field:
            self.app.notify(f"Cannot edit {field_name} yet.", severity="warning")
            return
        input_widget = EditInput(field_name=model_field, value=current_value, id=f"edit-{model_field}")
        panel = self.query_one("#panel-info", DetailPanel)
        self.info_table.display = False
        panel.mount(input_widget)
        input_widget.focus()

    def action_cancel_edit(self) -> None:
        """Cancel the current inline edit and restore the table."""
        from ..app import tui_debug_log
        tui_debug_log("DETAIL: action_cancel_edit triggered")
        panel = self.query_one("#panel-info", DetailPanel)
        edit_inputs = panel.query(EditInput)
        if edit_inputs:
            for edit_input in edit_inputs:
                edit_input.remove()
            self.info_table.display = True
            self.info_table.focus()

    @on(Input.Submitted)
    async def handle_edit_submitted(self, event: Input.Submitted) -> None:
        if not isinstance(event.input, EditInput):
            return
        field_name = event.input.field_name
        new_value = event.value
        company_slug = self.company_data["company"].get("slug")
        if company_slug:
            try:
                company = Company.get(company_slug)
                if company:
                    setattr(company, field_name, new_value)
                    company.save()
                    self.app.notify(f"Updated {field_name}")
                    self.company_data["company"][field_name] = new_value
                    event.input.remove()
                    # Re-render info table content (identity/address)
                    self._refresh_info_table()
                    self.info_table.display = True
                    self.info_table.focus()
            except Exception as e:
                self.app.notify(f"Save failed: {e}", severity="error")

    def _refresh_info_table(self) -> None:
        """Repopulate info table content."""
        self.info_table.clear()
        c = self.company_data["company"]
        tags = self.company_data.get("tags", [])
        website_data = self.company_data.get("website_data")
        enrichment_mtime = self.company_data.get("enrichment_mtime")

        self.info_table.add_row("Name", escape(str(c.get("name", "Unknown"))))
        self.info_table.add_row("Domain", escape(str(c.get("domain") or "")))
        self.info_table.add_row("Email", format_email_display(c.get("email")))
        self.info_table.add_row("Phone", format_phone_display(c.get("phone_number")))
        
        rating = c.get("average_rating")
        review_count = c.get("reviews_count")
        if rating or review_count:
            rating_str = f"{rating or '?'}/5.0 ({review_count or 0} reviews)"
            self.info_table.add_row("Rating", rating_str)

        self.info_table.add_row("Street", escape(str(c.get("street_address") or "")))
        self.info_table.add_row("City", escape(str(c.get("city") or "")))
        self.info_table.add_row("State", escape(str(c.get("state") or "")))
        self.info_table.add_row("Zip", escape(str(c.get("zip_code") or "")))

        # Lifecycle
        scraped_at = c.get("list_found_at")
        if scraped_at:
            dt = datetime.fromisoformat(scraped_at) if isinstance(scraped_at, str) else scraped_at
            self.info_table.add_row("Scraped", dt.strftime("%Y-%m-%d"))
        
        details_at = c.get("details_found_at")
        if details_at:
            dt = datetime.fromisoformat(details_at) if isinstance(details_at, str) else details_at
            self.info_table.add_row("Details", dt.strftime("%Y-%m-%d"))

        if enrichment_mtime:
            dt = datetime.fromisoformat(enrichment_mtime)
            self.info_table.add_row("Enriched", dt.strftime("%Y-%m-%d %H:%M"))
        else:
            self.info_table.add_row("Enriched", "No (website.md missing)")

        if tags:
            self.info_table.add_row("Tags", ", ".join(tags))
        
        if website_data:
            socials = []
            if website_data.get("linkedin_url"):
                socials.append("LinkedIn")
            if website_data.get("facebook_url"):
                socials.append("FB")
            if website_data.get("instagram_url"):
                socials.append("IG")
            if socials:
                self.info_table.add_row("Socials", " | ".join(socials))
            
            desc = website_data.get("description")
            if desc:
                self.info_table.add_row("Desc", escape(desc[:100] + "..."))

    def _create_info_table(self) -> InfoTable:
        table = InfoTable(id="info-table")
        table.add_column("Attribute", width=10)
        table.add_column("Value")
        # Initialize content
        self.info_table = table # Temporarily assign so _refresh works
        self._refresh_info_table()
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
