import logging
import webbrowser
import subprocess
import re
from typing import Dict, Optional, Any, Union, cast, TYPE_CHECKING
from datetime import datetime
from pathlib import Path

from textual.widgets import DataTable, Label, Input
from textual.containers import Container, Horizontal, Vertical
from textual.app import ComposeResult
from textual import events, on
from textual.widget import Widget
from textual.binding import Binding

from rich.text import Text
from rich.markup import escape

from ...models.companies.company import Company
from ...models.companies.note import Note
from ...models.companies.meeting import Meeting
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
        Binding("h", "exit_quadrant", "Back", show=False),
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
        Binding("i", "edit_item", "Edit Contact"),
        Binding("enter", "edit_item", "Edit Contact"),
    ]

    def action_edit_item(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
             # detail_view.action_edit_contact() # TODO
             detail_view.app.notify("Edit Contact coming soon")

class MeetingsTable(QuadrantTable):
    """Specific bindings for the Meetings quadrant."""
    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("a", "add_meeting", "Add Meeting"),
        Binding("i", "edit_item", "Edit Meeting"),
        Binding("enter", "edit_item", "Edit Meeting"),
    ]

    def action_edit_item(self) -> None:
        detail_view = next((a for a in self.ancestors if isinstance(a, CompanyDetail)), None)
        if detail_view:
             detail_view.action_edit_meeting()

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
        Binding("t", "toggle_to_call", "To Call"),
        Binding("R", "re_enqueue_scrape", "Re-enqueue Scrape"),
        Binding("D", "delete_company", "Delete Company"),
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
        with Horizontal(id="company-detail-container"):
            yield self.panel_info
            with Vertical(id="engagement-column"):
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
            self.action_add_meeting()

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
        # IF we are in leader mode, do NOT handle any keys here, let them bubble to App
        if getattr(self.app, "leader_mode", False):
            return

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

        # If we are focused on a child (like a table), h should move focus to the panel first
        # QuadrantTable handles this, but we want to ensure it doesn't escape to search
        if isinstance(focused, DataTable):
            if event.key == "h":
                parent = focused.parent
                if parent and isinstance(parent, DetailPanel):
                    parent.focus()
                    event.stop()
                    event.prevent_default()
                    return

        if isinstance(focused, DetailPanel):
            if event.key == "h":
                if focused in (self.panel_contacts, self.panel_meetings, self.panel_notes):
                    self.panel_info.focus()
                    event.stop()
                    event.prevent_default()
                else:
                    # Already in left column, trigger back navigation to trunk
                    app = cast("CocliApp", self.app)
                    app.action_navigate_up()
                    event.stop()
                    event.prevent_default()
                return
            elif event.key == "l":
                if focused == self.panel_info:
                    self.panel_contacts.focus()
                    event.stop()
                    event.prevent_default()
                return
            elif event.key == "j":
                if focused == self.panel_contacts:
                    self.panel_meetings.focus()
                elif focused == self.panel_meetings:
                    self.panel_notes.focus()
                elif focused == self.panel_notes:
                    self.panel_contacts.focus()
                
                event.stop()
                event.prevent_default()
                return
            elif event.key == "k":
                if focused == self.panel_contacts:
                    self.panel_notes.focus()
                elif focused == self.panel_meetings:
                    self.panel_contacts.focus()
                elif focused == self.panel_notes:
                    self.panel_meetings.focus()
                
                event.stop()
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

    async def action_call_company(self) -> None:
        # Prefer phone_1 which is our primary standardized field
        phone = self.company_data["company"].get("phone_1") or self.company_data["company"].get("phone_number")
        slug = self.company_data["company"].get("slug")
        domain = self.company_data["company"].get("domain")
        
        if phone and slug:
            cleaned = re.sub(r'\D', '', str(phone))
            if not cleaned.startswith('1') and len(cleaned) == 10:
                cleaned = '1' + cleaned
            
            # 1. Open Google Voice
            voice_url = f"https://voice.google.com/u/0/calls?a=nc,%2B{cleaned}"
            webbrowser.open(voice_url)
            
            # 2. Open Company Website if it exists
            if domain:
                webbrowser.open(f"http://{domain}")
                self.app.notify(f"Calling {phone} & Opening Website...")
            else:
                self.app.notify(f"Calling {phone}...")
            
            # Push the embedded call logger
            from .call_log_modal import CallLogModal
            await self.app.push_screen(CallLogModal(company_slug=slug, phone=str(phone)))
            
            # Refresh data after modal dismiss
            self.refresh_notes_data()
            self.refresh_meetings_data()
            self._refresh_info_table()
        else:
            self.app.notify("Phone number or slug missing", severity="warning")

    async def action_toggle_to_call(self) -> None:
        slug = self.company_data["company"].get("slug")
        if not slug:
            return
        
        company = Company.get(slug)
        if company:
            # Check if it is already in the to-call list (by tag or task file)
            # toggle_to_call uses task_path.exists() as the source of truth
            from cocli.models.campaigns.queues.to_call import ToCallTask
            from cocli.core.config import get_campaign
            campaign = get_campaign() or "default"
            task = ToCallTask(
                company_slug=company.slug,
                domain=company.domain or "unknown",
                campaign_name=campaign,
                ack_token=None
            )
            is_already_to_call = task.get_local_path().exists()

            if is_already_to_call:
                from .confirm_screen import ConfirmScreen
                confirm = await self.app.push_screen(ConfirmScreen(f"Remove '{company.name}' from To-Call list?"))
                if not confirm:
                    return

            is_added = company.toggle_to_call()
            status = "Added to" if is_added else "Removed from"
            self.app.notify(f"{status} To-Call Queue")
            
            # Update local data and refresh
            self.company_data["company"]["tags"] = company.tags
            self._refresh_info_table()

    def action_re_enqueue_scrape(self) -> None:
        """Triggers a local detail scrape for the current company."""
        slug = self.company_data["company"].get("slug")
        place_id = self.company_data["company"].get("place_id")
        
        if not place_id:
            self.app.notify("Error: No Place ID found for this company", severity="error")
            return
            
        self.app.notify(f"Starting local scrape for {slug or place_id}...")
        
        # We run this as a worker since it involves opening a browser
        async def run_scrape() -> None:
            app = cast("CocliApp", self.app)
            result = await app.services.operation_service.execute(
                "op_scrape_details",
                params={"place_id": place_id, "company_slug": slug}
            )
            
            if result.get("status") == "success":
                self.app.notify("Scrape successful! Refreshing view...")
                # The view needs to be re-hydrated to show the new data
                if slug:
                    new_data = app.services.get_company_details(slug)
                    if new_data:
                        self.company_data = new_data
                        self._refresh_info_table()
            else:
                self.app.notify(f"Scrape failed: {result.get('message')}", severity="error")
                
        self.app.run_worker(run_scrape())

    async def action_delete_company(self) -> None:
        """Permanently deletes the entire company directory."""
        slug = self.company_data["company"].get("slug")
        name = self.company_data["company"].get("name", slug)
        if not slug:
            return

        from .confirm_screen import ConfirmScreen
        confirm = await self.app.push_screen(ConfirmScreen(f"Are you sure you want to PERMANENTLY DELETE '{name}'?"))
        
        if confirm:
            try:
                import shutil
                from cocli.core.paths import paths
                from cocli.core.cache import build_cache
                import threading
                
                path = paths.companies.entry(slug).path
                if path.exists():
                    shutil.rmtree(path)
                    self.app.notify(f"Deleted company: {name}")
                    
                    # Rebuild cache so it's gone from search
                    from cocli.core.config import get_campaign
                    threading.Thread(target=build_cache, kwargs={"campaign": get_campaign()}, daemon=True).start()
                    
                    # Go back to list
                    self.app.action_show_companies()
                else:
                    self.app.notify(f"Directory not found: {path}", severity="error")
            except Exception as e:
                logger.error(f"Failed to delete company: {e}")
                self.app.notify(f"Delete failed: {e}", severity="error")

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

    def action_add_meeting(self) -> None:
        """Create a new meeting using NVim."""
        slug = self.company_data["company"].get("slug")
        if not slug:
            return

        new_meeting = Meeting(title="New Meeting", type="meeting", content="")
        meetings_dir = paths.companies.entry(slug) / "meetings"
        meeting_path = new_meeting.to_file(meetings_dir)
        self._edit_with_nvim(meeting_path)

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

    def action_edit_meeting(self) -> None:
        """Edit an existing meeting using NVim."""
        row_idx = self.meetings_table.cursor_row
        num_meetings = len(self.company_data.get("meetings", []))
        
        if row_idx is None or row_idx >= num_meetings:
            self.app.notify("No meeting selected", severity="warning")
            return
        
        meeting_data = self.company_data["meetings"][row_idx]
        file_path = meeting_data.get("file_path")
        
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
            
            self.app.notify("Item saved")
            # Reload data from disk
            self.refresh_notes_data()
            self.refresh_meetings_data()
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
        
        # Only re-focus if we had focus before
        if self.notes_table.has_focus:
            self.notes_table.focus()

    def refresh_meetings_data(self) -> None:
        """Reload meetings from the filesystem and refresh the table."""
        slug = self.company_data["company"].get("slug")
        if not slug:
            return
            
        try:
            from ...application.company_service import get_company_details_for_view
            reloaded = get_company_details_for_view(slug)
            if reloaded:
                self.company_data["meetings"] = reloaded["meetings"]
                self.refresh_meetings_table()
        except Exception as e:
            logger.error(f"Failed to refresh meetings: {e}")

    def refresh_meetings_table(self) -> None:
        """Repopulate the existing table rather than replacing it for stability."""
        self.meetings_table.clear()
        meetings = self.company_data.get("meetings", [])
        for m in meetings:
            raw_dt = m.get("datetime_utc")
            dt_str = "Unknown"
            time_str = ""
            if raw_dt:
                try:
                    dt = datetime.fromisoformat(raw_dt) if isinstance(raw_dt, str) else raw_dt
                    dt_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    dt_str = str(raw_dt)[:10]
            
            content_preview = escape(m.get("content", "")[:100].replace("\n", " "))
            m_type = m.get("type", "meeting")
            self.meetings_table.add_row(dt_str, time_str, f"[{m_type}] {content_preview}")
        
        if self.meetings_table.has_focus:
            self.meetings_table.focus()

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "info-table":
            self.trigger_row_edit(cast(InfoTable, event.data_table))
        elif event.data_table.id == "notes-table":
            self.action_edit_note()
        elif event.data_table.id == "meetings-table":
            self.action_edit_meeting()

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
            "Street": "street_address", "CSZ": "csz"
        }
        model_field = field_map.get(field_name)
        if not model_field:
            self.app.notify(f"Cannot edit {field_name} yet.", severity="warning")
            return
        
        panel = self.query_one("#panel-info", DetailPanel)
        self.info_table.display = False

        if model_field == "csz":
            c = self.company_data["company"]
            city = str(c.get("city") or "")
            state = str(c.get("state") or "")
            zip_code = str(c.get("zip_code") or "")
            
            container = Horizontal(id="edit-csz-container")
            city_input = EditInput(field_name="city", value=city, placeholder="City", id="edit-city")
            state_input = EditInput(field_name="state", value=state, placeholder="State", id="edit-state")
            zip_input = EditInput(field_name="zip_code", value=zip_code, placeholder="Zip", id="edit-zip_code")
            
            panel.mount(container)
            container.mount(city_input, state_input, zip_input)
            city_input.focus()
        else:
            input_widget = EditInput(field_name=model_field, value=current_value, id=f"edit-{model_field}")
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
        
        company_slug = self.company_data["company"].get("slug")
        if not company_slug:
            return

        panel = self.query_one("#panel-info", DetailPanel)
        csz_container = panel.query_one("#edit-csz-container", Horizontal) if "csz" in str(event.input.id) or "city" in str(event.input.id) or "state" in str(event.input.id) or "zip" in str(event.input.id) else None

        try:
            company = Company.get(company_slug)
            if not company:
                return

            if csz_container:
                # Save all 3 fields at once
                city_val = csz_container.query_one("#edit-city", EditInput).value
                state_val = csz_container.query_one("#edit-state", EditInput).value
                zip_val = csz_container.query_one("#edit-zip_code", EditInput).value
                
                company.city = city_val
                company.state = state_val
                company.zip_code = zip_val
                company.save()
                
                self.app.notify("Updated City, State, and Zip")
                self.company_data["company"]["city"] = city_val
                self.company_data["company"]["state"] = state_val
                self.company_data["company"]["zip_code"] = zip_val
                csz_container.remove()
            else:
                field_name = event.input.field_name
                new_value = event.value
                setattr(company, field_name, new_value)
                company.save()
                self.app.notify(f"Updated {field_name}")
                self.company_data["company"][field_name] = new_value
                event.input.remove()

            # Restore table
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
        keywords = c.get("keywords", [])
        website_data = self.company_data.get("website_data")
        enrichment_mtime = self.company_data.get("enrichment_mtime")

        self.info_table.add_row("Name", escape(str(c.get("name", "Unknown"))))
        
        # Rating & Reviews (Always shown)
        rating = c.get("average_rating")
        review_count = c.get("reviews_count")
        rating_val = f"{rating}" if rating is not None else "0.0"
        reviews_val = f"({review_count} reviews)" if review_count is not None else "(0 reviews)"
        self.info_table.add_row("Rating", f"{rating_val} {reviews_val}")

        self.info_table.add_row("Domain", escape(str(c.get("domain") or "")))
        self.info_table.add_row("Email", format_email_display(c.get("email")))
        self.info_table.add_row("Phone", format_phone_display(c.get("phone_number")))
        
        self.info_table.add_row("Street", escape(str(c.get("street_address") or "")))
        
        city = c.get("city") or ""
        state = c.get("state") or ""
        zip_code = c.get("zip_code") or ""
        self.info_table.add_row("CSZ", f"{city}, {state} {zip_code}")

        # Lifecycle Status (Always shown to emphasize OMAP pipeline)
        scraped_at = c.get("list_found_at")
        scraped_val = "-"
        if scraped_at:
            dt = datetime.fromisoformat(scraped_at) if isinstance(scraped_at, str) else scraped_at
            scraped_val = dt.strftime("%Y-%m-%d")
        self.info_table.add_row("gm-list", scraped_val)
        
        details_at = c.get("details_found_at")
        details_val = "-"
        if details_at:
            dt = datetime.fromisoformat(details_at) if isinstance(details_at, str) else details_at
            details_val = dt.strftime("%Y-%m-%d")
        self.info_table.add_row("gm-detail", details_val)

        enqueued_at = c.get("enqueued_at")
        enrich_val = "No"
        if enrichment_mtime:
            dt = datetime.fromisoformat(enrichment_mtime)
            enrich_val = f"[bold green]{dt.strftime('%Y-%m-%d %H:%M')}[/]"
        elif enqueued_at:
            dt = datetime.fromisoformat(enqueued_at) if isinstance(enqueued_at, str) else enqueued_at
            enrich_val = f"[bold yellow]{dt.strftime('%Y-%m-%d')} (pending)[/]"
        self.info_table.add_row("enrichment", enrich_val)

        if tags:
            display_tags = []
            for t in tags:
                if t == "to-call":
                    display_tags.append("[bold yellow]to-call[/]")
                else:
                    display_tags.append(t)
            self.info_table.add_row("Tags", ", ".join(display_tags))

        if keywords:
            self.info_table.add_row("Keywords", ", ".join(keywords))
        
        # Social Media (Keep conditional to avoid empty rows cluttering the dense view)
        socials = []
        if c.get("facebook_url") or (website_data and website_data.get("facebook_url")):
            socials.append("FB")
        if c.get("linkedin_url") or (website_data and website_data.get("linkedin_url")):
            socials.append("LI")
        if c.get("instagram_url") or (website_data and website_data.get("instagram_url")):
            socials.append("IG")
        if c.get("twitter_url") or (website_data and website_data.get("twitter_url")):
            socials.append("TW")
        
        if socials:
            self.info_table.add_row("Socials", " | ".join(socials))

        # Desc
        desc = c.get("description") or (website_data and website_data.get("description"))
        if desc:
            self.info_table.add_row("Desc", escape(str(desc)[:100].replace("\n", " ") + "..."))

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
        table.add_column("Time", width=8)
        table.add_column("Preview")
        meetings = self.company_data.get("meetings", [])
        for m in meetings:
            # Handle local time display
            raw_dt = m.get("datetime_utc")
            dt_str = "Unknown"
            time_str = ""
            if raw_dt:
                try:
                    dt = datetime.fromisoformat(raw_dt)
                    # Convert to local for display? Textual apps usually stay local.
                    # For now, just show the HH:MM
                    dt_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    dt_str = str(raw_dt)[:10]
            
            content_preview = escape(m.get("content", "")[:100].replace("\n", " "))
            m_type = m.get("type", "meeting")
            table.add_row(dt_str, time_str, f"[{m_type}] {content_preview}")
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
