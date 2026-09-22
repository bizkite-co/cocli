from __future__ import annotations
import logging
import subprocess
import time
import re
import textwrap
from typing import Optional, Any, Union, cast, Literal, TYPE_CHECKING
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import DataTable, Label, Input, Static
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
from ...models.companies.activity import CompanyActivity
from ...models.phone import PhoneNumber
from ...core.paths import paths
from ...core.config import get_editor_command
from .mark_prefix import MarkPrefixMixin
from ..base import CocliPanel
from ...utils.open_url import open_url
from .confirm_screen import ConfirmScreen
from .company_local_time import CompanyLocalTime

if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

PREVIEW_WIDTH = 52
PREVIEW_MAX_LINES = 3


def notes_newest_first(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest timestamp first so the Notes quadrant reads like a mailbox."""

    def _key(note: dict[str, Any]) -> datetime:
        ts = note.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=UTC)
            return ts
        return datetime.min.replace(tzinfo=UTC)

    return sorted(notes, key=_key, reverse=True)


def wrap_content(
    content: str, width: int = PREVIEW_WIDTH, max_lines: int = PREVIEW_MAX_LINES
) -> Text:
    """Wrap content to a specified width and max lines, returning Rich Text."""
    lines = textwrap.wrap(content, width=width)
    if lines is None:
        return Text(content)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1] + "…"]
    return Text("\n".join(lines))


def format_activity_datetime(
    dt: Optional[Union[datetime, str]],
    is_scheduled: bool = False,
    is_overdue: bool = False,
) -> Text:
    """Format datetime: MM-DD on line 1 (dim yellow) and HH:MM on line 2 (dim green)."""
    if not dt:
        return Text("Unknown", style="dim")
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt)
            dt = parsed
        except (ValueError, TypeError):
            return Text(str(dt)[:10], style="dim yellow")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    date_part = dt.strftime("%m-%d")
    time_part = dt.strftime("%H:%M")

    if is_overdue:
        return Text(f"{date_part}\n{time_part}", style="bold red")

    res = Text()
    res.append(date_part, style="dim yellow")
    res.append("\n")
    res.append(time_part, style="dim green")
    return res


def format_activity_preview(activity: Union[CompanyActivity, dict[str, Any]]) -> Text:
    """Format Rich Text preview for an activity item (call, email, meeting, note, callback, follow-up)."""
    if isinstance(activity, dict):
        title = str(activity.get("title") or "")
        content = str(activity.get("content") or "")
        act_type = str(
            activity.get("activity_type") or activity.get("type") or ""
        ).lower()
        meta = activity.get("metadata") or {}
        is_scheduled = bool(activity.get("is_scheduled", False))
        preview = activity.get("preview")
    else:
        title = activity.title or ""
        content = activity.content or ""
        act_type = (activity.activity_type or "").lower()
        meta = activity.metadata or {}
        is_scheduled = activity.is_scheduled
        preview = activity.preview

    clean_content = content[:200].replace("\n", " ").strip()

    if is_scheduled:
        if "overdue" in title.lower():
            return Text("[Callback overdue]", style="bold red")
        elif "callback scheduled" in title.lower():
            return Text("[Callback scheduled]", style="bold yellow")
        elif "follow-up" in title.lower() or act_type in ("email", "follow-up"):
            if preview:
                return Text(str(preview), style="bold cyan")
            fmt = meta.get("format", act_type)
            detail = meta.get("template_id") or fmt
            return Text(f"[Follow-up: {fmt}] {detail}", style="bold cyan")
        elif act_type == "meeting":
            m_type = meta.get("meeting_type", "meeting")
            return wrap_content(
                f"📅 [{m_type}] {clean_content or title}", max_lines=PREVIEW_MAX_LINES
            )
        elif preview:
            return Text(str(preview), style="bold yellow")

    if (
        act_type == "call"
        or "disposition" in meta
        or title.lower().startswith("call log:")
    ):
        icon = "📞"
        disp = meta.get("disposition")
        prefix = f"[{disp}] " if disp else ""
        return wrap_content(
            f"{icon} {prefix}{clean_content}"
            if clean_content
            else f"{icon} {prefix}{title}",
            max_lines=PREVIEW_MAX_LINES,
        )
    elif (
        act_type == "email"
        or "direction" in meta
        or title.lower().startswith(("email sent:", "email received:"))
    ):
        icon = "✉"
        direction = str(meta.get("direction") or "EMAIL").upper()
        return wrap_content(
            f"{icon} [{direction}] {title}: {clean_content}"
            if clean_content
            else f"{icon} [{direction}] {title}",
            max_lines=PREVIEW_MAX_LINES,
        )
    elif act_type == "meeting":
        icon = "📅"
        m_type = meta.get("meeting_type", "meeting")
        return wrap_content(
            f"{icon} [{m_type}] {clean_content}"
            if clean_content
            else f"{icon} [{m_type}] {title}",
            max_lines=PREVIEW_MAX_LINES,
        )
    else:
        icon = "📝"
        return wrap_content(
            f"{icon} {clean_content}" if clean_content else f"{icon} {title}",
            max_lines=PREVIEW_MAX_LINES,
        )


def format_note_preview(n: dict[str, Any]) -> Text:
    return format_activity_preview(n)


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


def format_domain_display(value: Any) -> Union[Text, str]:
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = ""

    def watch_title(self, title: str) -> None:
        """Override Textual's reactive watcher to prevent title from populating border_title."""
        self.border_title = ""

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
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
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
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            # detail_view.action_edit_contact() # TODO
            detail_view.app.notify("Edit Contact coming soon")


class ActivityTable(QuadrantTable):
    """Specific bindings for the unified Activity timeline."""

    BINDINGS = QuadrantTable.BINDINGS + [
        Binding("a", "add_item", "Add Note"),
        Binding("i", "edit_item", "Edit Item"),
        Binding("enter", "edit_item", "Edit Item"),
        Binding("d", "delete_item", "Delete"),
        Binding("v", "view_item", "View"),
        Binding("P", "promote_item", "Promote"),
        Binding("r", "reply_email", "Reply"),
    ]

    def action_reply_email(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.action_reply_email()

    def action_edit_item(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.action_edit_item()

    def action_add_item(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.action_add_note()

    def action_delete_item(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.app.run_worker(detail_view.action_delete_activity())

    def action_view_item(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.action_view_item()

    def action_promote_item(self) -> None:
        detail_view = next(
            (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
        )
        if detail_view:
            detail_view.action_promote_item()


# Backward compatibility aliases
NotesTable = ActivityTable
MeetingsTable = ActivityTable


class EditInput(Input):
    """Custom Input widget that carries field metadata."""

    def __init__(self, field_name: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.field_name = field_name

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "alt+s", "meta+s"):
            from ..app import tui_debug_log

            tui_debug_log(f"DETAIL: Cancel edit for {self.field_name} via {event.key}")
            detail_view = next(
                (a for a in self.ancestors if isinstance(a, CompanyDetail)), None
            )
            if detail_view:
                detail_view.action_cancel_edit()
            event.stop()
            event.prevent_default()


class DetailPanel(CocliPanel):
    """A focusable panel containing a title and a widget."""

    def __init__(
        self,
        title: str,
        child: Widget,
        id: str,
        subtitle_widget: Optional[Widget] = None,
    ):
        super().__init__(panel_title=title, id=id, classes="panel")
        self.can_focus = True
        self.child = child
        self.subtitle_widget = subtitle_widget

    def compose(self) -> ComposeResult:
        yield Label(self.panel_title, classes="panel-header")
        if self.subtitle_widget:
            yield self.subtitle_widget
        yield self.child


class CompanyDetail(MarkPrefixMixin, Container):
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
        Binding("w", "open_website", "Website"),
        Binding("g", "open_gmb", "Google Maps"),
        Binding("V", "view_enrichment", "Enrichment"),
        Binding("m", "open_mark_menu", "Mark"),
        Binding("p", "call_company", "Call"),
        Binding("f", "enqueue_follow_up", "Follow-up"),
        Binding("t", "toggle_to_call", "To Call"),
        Binding("R", "re_enqueue_scrape", "Re-enqueue Scrape"),
        Binding("E", "re_enrich", "Re-enrich"),
        Binding("D", "delete_company", "Delete Company"),
        Binding("U", "unsubscribe_company", "Unsubscribe"),
        Binding("C", "compose_email", "Compose email"),
    ]

    def __init__(
        self,
        company_data: dict[str, Any],
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data
        self.company_data["notes"] = notes_newest_first(
            list(self.company_data.get("notes") or [])
        )

        # Debugging the data discrepancy
        company_info = self.company_data.get("company", {})
        logger.info(
            f"DEBUG DETAIL: Company={company_info.get('name')}, "
            f"Phone={company_info.get('phone_number')}, "
            f"Reviews={company_info.get('reviews_count')}"
        )

        # Initialize tables
        self._activity_row_items: list[Optional[CompanyActivity]] = []
        self.info_table = self._create_info_table()
        self.contacts_table = self._create_contacts_table()
        self.activity_table = self._create_activity_table()

        # Backward compatibility aliases
        self.notes_table = self.activity_table
        self.meetings_table = self.activity_table

        # Screenshot (see Website.screenshot_bytes) - always-visible, under
        # the metadata panel. Mark, 2026-08-30: "It should just show it
        # under the metadata. We don't need a shortcut key." Replaces the
        # earlier modal-triggered-by-keypress design.
        self.screenshot_widget = self._create_screenshot_widget()

        # Initialize panels
        self.local_time_widget = CompanyLocalTime(
            company=self.company_data,
            id="company_local_time",
        )
        self.panel_info = DetailPanel(
            "COMPANY INFO",
            self.info_table,
            id="panel-info",
            subtitle_widget=self.local_time_widget,
        )
        self.panel_contacts = DetailPanel(
            "CONTACTS", self.contacts_table, id="panel-contacts"
        )
        self.panel_activity = DetailPanel(
            "ACTIVITY", self.activity_table, id="panel-activity"
        )

        # Backward compatibility aliases
        self.panel_notes = self.panel_activity
        self.panel_meetings = self.panel_activity

        # Define panel order for navigation
        self.panels = [
            self.panel_info,
            self.panel_contacts,
            self.panel_activity,
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="company-detail-root"):
            with Horizontal(id="company-detail-container"):
                with Vertical(id="info-column"):
                    yield self.panel_info
                    yield self.screenshot_widget
                with Vertical(id="engagement-column"):
                    yield self.panel_contacts
                    yield self.panel_activity
            yield Static("", id="mark-prefix-bar", classes="mark-prefix-bar hidden")

    def on_mount(self) -> None:
        self.panel_info.focus()

    def _screenshot_path(self) -> Optional[Path]:
        enrichment_path = self.company_data.get("enrichment_path")
        if enrichment_path:
            return Path(enrichment_path).parent / "screenshot.png"
        slug = self.company_data.get("company", {}).get("slug")
        if slug:
            return paths.companies.entry(slug).path / "enrichments" / "screenshot.png"
        return None

    async def _refresh_screenshot_widget(self) -> None:
        """Recompose the screenshot panel after a scrape/enrich writes the PNG."""
        try:
            old = self.query_one("#screenshot-panel")
        except Exception:
            return
        new = self._create_screenshot_widget()
        await old.remove()
        info_column = self.query_one("#info-column")
        await info_column.mount(new, after=self.panel_info)
        self.screenshot_widget = new

    def _create_screenshot_widget(self) -> Widget:
        """A small, always-visible preview of the company's website
        screenshot (see Website.screenshot_bytes / enrichments/screenshot.png)
        - "we've got a little room to just show it" (Mark, 2026-08-30), not
        a full-size viewer behind a keypress."""
        screenshot_path = self._screenshot_path()

        if screenshot_path and screenshot_path.exists():
            # Backend selection (default: terminal detection - Sixel graphics
            # where supported, text otherwise) lives in
            # cocli.utils.textual_utils.get_image_widget_class, including the
            # self-healing full repaint that keeps Sixel-desynced terminals
            # (Windows Terminal) from doubling pane/table headers
            # (2026-09-13 investigation). COCLI_IMAGE_BACKEND overrides.
            from ...utils.textual_utils import get_image_widget_class

            image_cls = get_image_widget_class()
            if image_cls is not None:
                return Container(
                    image_cls(str(screenshot_path), id="screenshot-image"),
                    id="screenshot-panel",
                )

        return Container(
            Label("[dim]No screenshot[/]", classes="panel-header"),
            id="screenshot-panel",
        )

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
        if (
            focused in (self.panel_activity, self.panel_notes, self.panel_meetings)
            or self.activity_table.has_focus
        ):
            self.action_add_note()
        elif focused == self.panel_contacts or self.contacts_table.has_focus:
            self.app.notify("Add Contact coming soon")

    def action_delete_item(self) -> None:
        """Route 'd' key based on the focused quadrant."""
        focused = self.app.focused
        if (
            focused in (self.panel_activity, self.panel_notes, self.panel_meetings)
            or self.activity_table.has_focus
        ):
            self.app.run_worker(self.action_delete_activity())
        elif focused == self.panel_contacts or self.contacts_table.has_focus:
            self.app.notify("Delete Contact coming soon")

    def on_key(self, event: events.Key) -> None:
        # IF we are in leader mode, do NOT handle any keys here, let them bubble to App
        if getattr(self.app, "leader_mode", False):
            return

        if self.handle_mark_prefix_key(event):
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
                if focused in (
                    self.panel_contacts,
                    self.panel_activity,
                    self.panel_meetings,
                    self.panel_notes,
                ):
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
                    self.panel_activity.focus()
                elif focused in (
                    self.panel_activity,
                    self.panel_meetings,
                    self.panel_notes,
                ):
                    self.panel_contacts.focus()

                event.stop()
                event.prevent_default()
                return
            elif event.key == "k":
                if focused == self.panel_contacts:
                    self.panel_activity.focus()
                elif focused in (
                    self.panel_activity,
                    self.panel_meetings,
                    self.panel_notes,
                ):
                    self.panel_contacts.focus()

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

    def _open_desktop_browser(self, url: str, success_message: str) -> None:
        if open_url(url):
            self.app.notify(success_message)
        else:
            self.app.notify(f"Could not open browser for {url}", severity="error")

    def action_open_website(self) -> None:
        domain = self.company_data["company"].get("domain")
        if domain:
            url = f"http://{domain}"
            self._open_desktop_browser(url, f"Opening {url}")
        else:
            self.app.notify("No domain found", severity="warning")

    def action_open_gmb(self) -> None:
        company = self.company_data["company"]
        gmb_url = company.get("gmb_url")
        # Legacy computed URLs used query=google, which opens Maps at the
        # user's current location instead of the place.
        if gmb_url and "query=google" in gmb_url:
            gmb_url = None
        if not gmb_url:
            from ...utils.google_maps_url import google_maps_url

            gmb_url = google_maps_url(
                place_id=company.get("place_id"),
                name=company.get("name"),
                street_address=company.get("street_address"),
                city=company.get("city"),
            )
        if gmb_url:
            self._open_desktop_browser(gmb_url, "Opening Google Maps...")
        else:
            self.app.notify("No Google Maps URL found", severity="warning")

    def action_view_enrichment(self) -> None:
        path = self.company_data.get("enrichment_path")
        if path and Path(path).exists():
            self._edit_with_nvim(Path(path))
        else:
            self.app.notify("Enrichment file not found", severity="warning")

    def action_open_mark_menu(self) -> None:
        """``m`` then ``i`` invalid, ``v`` valid, or ``h`` high-value. Nav mode only."""
        if isinstance(self.app.focused, Input):
            return
        self.enter_mark_prefix()

    def action_mark_invalid(self) -> None:
        company = self.company_data.get("company", {})
        slug = company.get("slug")
        if not slug:
            self.app.notify("No slug found", severity="error")
            return

        from ...core.config import get_campaign
        from ...application.to_call_disposition_service import (
            REASON_NONCONFORMING,
            mark_to_call_invalid,
        )

        campaign = get_campaign() or "default"
        name = company.get("name") or slug
        mark_to_call_invalid(
            campaign=campaign,
            slug=slug,
            domain=company.get("domain"),
            reason=REASON_NONCONFORMING,
        )
        self.app.notify(f"Marked '{name}' invalid — off to-call, in to-call-invalid")

    def action_mark_valid(self) -> None:
        company = self.company_data.get("company", {})
        slug = company.get("slug")
        if not slug:
            self.app.notify("No slug found", severity="error")
            return

        from ...core.config import get_campaign
        from ...application.to_call_disposition_service import mark_to_call_valid

        campaign = get_campaign() or "default"
        name = company.get("name") or slug
        mark_to_call_valid(
            campaign=campaign,
            slug=slug,
            domain=company.get("domain"),
        )
        self.app.notify(f"Marked '{name}' valid — removed from invalid list")

    def action_mark_high_value(self) -> None:
        company = self.company_data.get("company", {})
        slug = company.get("slug")
        if not slug:
            self.app.notify("No slug found", severity="error")
            return

        from ...core.config import get_campaign
        from ...application.to_call_disposition_service import toggle_to_call_high_value

        campaign = get_campaign() or "default"
        name = company.get("name") or slug
        now_on = toggle_to_call_high_value(
            campaign=campaign,
            slug=slug,
            domain=company.get("domain"),
        )
        if now_on:
            self.app.notify(f"Marked '{name}' high-value")
        else:
            self.app.notify(f"Cleared high-value on '{name}'")

    def action_enqueue_follow_up(self) -> None:
        """Open modal to enqueue an email follow-up."""
        slug = self.company_data.get("company", {}).get("slug")
        if not slug:
            self.app.notify("Company slug missing", severity="warning")
            return
        company_name = self.company_data.get("company", {}).get("name") or slug
        from .enqueue_follow_up_modal import EnqueueFollowUpModal

        def on_dismiss(result: bool | None) -> None:
            if result:
                self.refresh_notes_data()

        self.app.push_screen(
            EnqueueFollowUpModal(company_slug=slug, company_name=company_name),
            on_dismiss,
        )

    def action_call_company(self) -> None:
        """Sync dispatcher + run_worker - see action_delete_company's
        docstring for the general reason. Here the bug wasn't a discarded
        confirm value but a discarded *wait*: plain push_screen() awaits
        the modal's mount, not its dismissal, so the refresh calls used to
        fire before the user had actually finished logging the call,
        showing stale data. push_screen_wait blocks until CallLogModal is
        actually dismissed (its return value isn't needed here, just the
        wait)."""
        # Prefer phone_1 which is our primary standardized field
        phone = self.company_data["company"].get("phone_1") or self.company_data[
            "company"
        ].get("phone_number")
        slug = self.company_data["company"].get("slug")
        domain = self.company_data["company"].get("domain")

        if not (phone and slug):
            self.app.notify("Phone number or slug missing", severity="warning")
            return

        async def run_call() -> None:
            cleaned = re.sub(r"\D", "", str(phone))
            if not cleaned.startswith("1") and len(cleaned) == 10:
                cleaned = "1" + cleaned

            # 1. Open Google Voice (or whichever calling provider is configured)
            from ...core.config import get_campaign
            from ...utils.calling_provider import (
                GoogleVoiceEdgeAppProvider,
                TwilioBridgeCallingProvider,
                get_calling_provider,
            )

            provider = get_calling_provider(get_campaign())
            voice_opened = provider.dial(str(phone), get_campaign())
            paste_hint = (
                " (Twilio Bridge: ringing your phone)"
                if isinstance(provider, TwilioBridgeCallingProvider)
                else " (Google Voice PWA)"
                if isinstance(provider, GoogleVoiceEdgeAppProvider)
                else ""
            )
            if isinstance(provider, TwilioBridgeCallingProvider):
                is_low, bal, curr = provider.is_low_balance()
                if is_low and bal is not None:
                    self.app.notify(
                        f"⚠️ Low Twilio Balance: ${bal:.2f} {curr or 'USD'} (Threshold: ${provider.low_balance_threshold:.2f})",
                        severity="warning",
                        timeout=8,
                    )

            # 2. Open Company Website if it exists
            if domain:
                site_opened = open_url(f"http://{domain}")
                if voice_opened:
                    self.app.notify(f"Calling {phone}{paste_hint} & Opening Website...")
                elif site_opened:
                    provider_name = (
                        "Twilio"
                        if isinstance(provider, TwilioBridgeCallingProvider)
                        else "Google Voice"
                    )
                    last_err = getattr(provider, "last_error", None)
                    err_hint = f" ({last_err})" if last_err else ""
                    self.app.notify(
                        f"Opened website; could not place call via {provider_name} for {phone}{err_hint}",
                        severity="warning",
                        timeout=10,
                    )
                else:
                    provider_name = (
                        "Twilio"
                        if isinstance(provider, TwilioBridgeCallingProvider)
                        else "browser"
                    )
                    last_err = getattr(provider, "last_error", None)
                    err_hint = f": {last_err}" if last_err else ""
                    self.app.notify(
                        f"Could not open {provider_name} to call {phone}{err_hint}",
                        severity="error",
                        timeout=10,
                    )
            elif voice_opened:
                self.app.notify(f"Calling {phone}{paste_hint}...")
            else:
                provider_name = (
                    "Twilio"
                    if isinstance(provider, TwilioBridgeCallingProvider)
                    else "browser"
                )
                last_err = getattr(provider, "last_error", None)
                err_hint = f": {last_err}" if last_err else ""
                self.app.notify(
                    f"Could not open {provider_name} to call {phone}{err_hint}",
                    severity="error",
                    timeout=10,
                )

            # Push the embedded call logger - wait for it to actually be
            # dismissed before refreshing (see docstring).
            from .call_log_modal import CallLogModal

            await self.app.push_screen_wait(
                CallLogModal(company_slug=slug, phone=str(phone))
            )

            self.refresh_notes_data()
            self.refresh_meetings_data()
            self._refresh_info_table()

        self.app.run_worker(run_call())

    def action_toggle_to_call(self) -> None:
        """Toggles the company in the 'to-call' queue.

        Sync dispatcher + run_worker - see action_delete_company's
        docstring for why (push_screen_wait requires an active worker).
        """
        company = Company.get(self.company_data["company"]["slug"])
        if not company:
            self.app.notify("Company not found", severity="error")
            return

        async def run_toggle() -> None:
            from cocli.models.campaigns.queues.to_call import ToCallTask
            from cocli.core.config import get_campaign

            campaign = get_campaign() or "default"
            task = ToCallTask(
                company_slug=company.slug,
                domain=company.domain or "unknown",
                campaign_name=campaign,
                ack_token=None,
            )
            task_path = task.get_local_path()

            if task_path.exists():
                from .confirm_screen import ConfirmScreen

                confirm = await self.app.push_screen_wait(
                    ConfirmScreen(f"Remove '{company.name}' from To-Call list?")
                )
                if not confirm:
                    return
                task_path.unlink()
                status = "Removed from"
            else:
                task.save()
                status = "Added to"

            self.app.notify(f"{status} To-Call Queue")
            self._refresh_info_table()

        self.app.run_worker(run_toggle())

    def action_re_enqueue_scrape(self) -> None:
        """Triggers a local detail scrape for the current company."""
        slug = self.company_data["company"].get("slug")
        place_id = self.company_data["company"].get("place_id")

        if not place_id:
            self.app.notify(
                "Error: No Place ID found for this company", severity="error"
            )
            return

        self.app.notify(f"Starting local scrape for {slug or place_id}...")

        # We run this as a worker since it involves opening a browser
        async def run_scrape() -> None:
            app = cast("CocliApp", self.app)
            result = await app.services.operation_service.execute(
                "op_scrape_details", params={"place_id": place_id, "company_slug": slug}
            )

            if result.get("status") == "success":
                inner = result.get("result") or {}
                domain = inner.get("domain") if isinstance(inner, dict) else None
                suffix = f" — {domain}" if domain else ""
                self.app.notify(f"Scrape successful{suffix}! Refreshing view...")
                if domain:
                    self.app.notify(
                        "Press E to enrich the website (emails + screenshot)",
                        severity="information",
                    )
                # The view needs to be re-hydrated to show the new data
                if slug:
                    new_data = app.services.get_company_details(slug)
                    if new_data:
                        self.company_data = new_data
                        self._refresh_info_table()
                        await self._refresh_screenshot_widget()
            else:
                self.app.notify(
                    f"Scrape failed: {result.get('message')}", severity="error"
                )

        self.app.run_worker(run_scrape())

    def action_re_enrich(self) -> None:
        """Triggers a local website enrichment for the current company."""
        slug = self.company_data["company"].get("slug")
        domain = self.company_data["company"].get("domain")

        if not domain:
            self.app.notify("Error: No domain found for this company", severity="error")
            return

        self.app.notify(f"Starting local re-enrichment for {domain}...")

        async def run_enrichment() -> None:
            app = cast("CocliApp", self.app)
            result = await app.services.operation_service.execute(
                "op_re_enrich", params={"domain": domain, "company_slug": slug}
            )

            from ...application.enrichment_outcome import notify_from_execute_result

            message, severity = notify_from_execute_result(result)
            self.app.notify(message, severity=severity, timeout=8)
            if slug:
                new_data = app.services.get_company_details(slug)
                if new_data:
                    self.company_data = new_data
                    self._refresh_info_table()
                    self._refresh_contacts_table()
                    await self._refresh_screenshot_widget()
                    self.refresh_notes_data()

        self.app.run_worker(run_enrichment())

    def action_delete_company(self) -> None:
        """Permanently deletes the entire company directory.

        Sync dispatcher + run_worker: push_screen_wait (needed to properly
        await ConfirmScreen's dismiss value - plain push_screen() without
        wait_for_dismiss always returns None regardless of what's pressed,
        confirmed empirically 2026-08-30, so `if confirm:` never used to
        fire) requires an active worker, which a BINDINGS-triggered action
        doesn't get for free. Matches the existing pattern already used by
        action_re_enqueue_scrape/action_re_enrich in this same file.
        """
        slug = self.company_data["company"].get("slug")
        name = self.company_data["company"].get("name", slug)
        if not slug:
            return

        async def run_delete() -> None:
            from .confirm_screen import ConfirmScreen

            confirm = await self.app.push_screen_wait(
                ConfirmScreen(f"Are you sure you want to PERMANENTLY DELETE '{name}'?")
            )

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

                        threading.Thread(
                            target=build_cache,
                            kwargs={"campaign": get_campaign()},
                            daemon=True,
                        ).start()

                        # Go back to list
                        app = cast("CocliApp", self.app)
                        await app.action_show_companies()
                    else:
                        self.app.notify(
                            f"Directory not found: {path}", severity="error"
                        )
                except Exception as e:
                    logger.error(f"Failed to delete company: {e}")
                    self.app.notify(f"Delete failed: {e}", severity="error")

        self.app.run_worker(run_delete())

    def action_unsubscribe_company(self) -> None:
        """Unsubscribe company and suppress all email communications."""
        if isinstance(self.app.focused, Input):
            return

        company_info = self.company_data.get("company", {})
        slug = company_info.get("slug")
        name = company_info.get("name") or slug or "Company"
        email = company_info.get("email")

        if not email:
            contacts = self.company_data.get("contacts", [])
            for c in contacts:
                if c.get("email"):
                    email = c.get("email")
                    break

        async def run_unsubscribe() -> None:
            from .confirm_screen import ConfirmScreen
            from ...core.config import get_campaign, load_campaign_config
            from ...core.exclusions import ExclusionManager

            target_desc = f"'{name}' ({email})" if email else f"'{name}'"
            confirm = await self.app.push_screen_wait(
                ConfirmScreen(
                    f"Unsubscribe and suppress all email communications for {target_desc}?"
                )
            )
            if not confirm:
                return

            campaign_name = get_campaign() or "default"
            ex_mgr = ExclusionManager(campaign_name)
            ex_mgr.add_exclusion(
                domain=email, slug=slug, reason="tui_phone_unsubscribe"
            )

            ses_success = False
            if email:
                try:
                    from ...application.ses_suppression_service import (
                        SesSuppressionService,
                    )

                    cfg = load_campaign_config(campaign_name)
                    aws_cfg = cfg.get("aws", {})
                    profile = (
                        aws_cfg.get("profile")
                        or aws_cfg.get("aws_profile")
                        or cfg.get("aws-profile")
                    )
                    ses_suppress = SesSuppressionService(profile=profile)
                    ses_success = ses_suppress.suppress_email(email, reason="COMPLAINT")
                except Exception as e:
                    logger.warning(f"AWS SES suppression failed for {email}: {e}")

            if slug:
                notes_dir = paths.companies.entry(slug) / "notes"
                unsub_note = Note(
                    title="UNSUBSCRIBED",
                    content=(
                        f"Manually unsubscribed email communications via TUI.\n"
                        f"Email: {email or 'N/A'}\n"
                        f"Reason: tui_phone_unsubscribe\n"
                        f"SES Suppressed: {ses_success}\n"
                        f"Timestamp: {datetime.now(UTC).isoformat()}"
                    ),
                )
                unsub_note.to_file(notes_dir)

            msg = f"Unsubscribed '{name}'. Local exclusion added."
            if email:
                msg += f" SES: {'Suppressed' if ses_success else 'Offline/Failed'}"
            self.app.notify(msg)

            self.refresh_notes_data()
            self._refresh_info_table()

        self.app.run_worker(run_unsubscribe())

    def action_compose_email(self) -> None:
        slug = self.company_data["company"].get("slug")
        if not slug:
            self.app.notify("No slug found", severity="error")
            return
        to_address = str(self.company_data["company"].get("email") or "")
        if self.contacts_table.has_focus:
            row = self.contacts_table.cursor_row
            contacts = self.company_data.get("contacts") or []
            if isinstance(row, int) and 0 <= row < len(contacts):
                to_address = str(contacts[row].get("email") or to_address)
        self._push_email_compose(slug, to_address=to_address)

    def action_reply_email(self) -> None:
        slug = self.company_data["company"].get("slug")
        if not slug:
            return
        item = self._get_current_activity()
        content = ""
        title = ""
        if item:
            content = str(item.content or "")
            title = str(item.title or "")
        else:
            notes = self.company_data.get("notes") or []
            row = self.activity_table.cursor_row
            if isinstance(row, int) and 0 <= row < len(notes):
                content = str(notes[row].get("content") or "")
                title = str(notes[row].get("title") or "")

        if not content and not title:
            self.app.notify("No note selected", severity="warning")
            return

        to_address = ""
        quoted_lines: list[str] = []
        past_headers = False
        for line in content.splitlines():
            lower = line.lower()
            if not past_headers:
                if lower.startswith("- from:"):
                    to_address = line.split(":", 1)[1].strip()
                if line.strip() == "":
                    past_headers = True
                continue
            quoted_lines.append(f"> {line}" if line else ">")
        if not to_address:
            self.app.notify(
                "Selected note has no From: (not an email note)", severity="warning"
            )
            return
        subject = title
        prefix = "email received:"
        if subject.lower().startswith(prefix):
            subject = subject[len(prefix) :].strip()
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        quoted = "\n".join(quoted_lines).strip()
        body = f"\n\n{quoted}" if quoted else ""
        self._push_email_compose(
            slug, to_address=to_address, subject=subject, body=body
        )

    def _push_email_compose(
        self,
        slug: str,
        *,
        to_address: str = "",
        subject: str = "",
        body: str = "",
    ) -> None:
        from .email_compose_modal import EmailComposeModal

        def _after(sent: Optional[bool]) -> None:
            if sent:
                self.refresh_activity_data()

        self.app.push_screen(
            EmailComposeModal(
                company_slug=slug,
                to_address=to_address,
                subject=subject,
                body=body,
            ),
            _after,
        )

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

    def _get_current_activity(self) -> Optional[CompanyActivity]:
        row_idx = self.activity_table.cursor_row
        if row_idx is None or not (0 <= row_idx < len(self._activity_row_items)):
            return None
        return self._activity_row_items[row_idx]

    def action_edit_item(self) -> None:
        """Edit current selected activity item."""
        item = self._get_current_activity()
        if not item:
            self.action_edit_note()
            return
        if item.activity_type == "meeting":
            self.action_edit_meeting()
        else:
            self.action_edit_note()

    def action_edit_note(self) -> None:
        """Edit selected note using NVim."""
        item = self._get_current_activity()
        file_path = item.file_path if item else None
        if not file_path:
            row_idx = self.activity_table.cursor_row
            notes = self.company_data.get("notes", [])
            if row_idx is not None and row_idx < len(notes):
                file_path = notes[row_idx].get("file_path")

        if file_path:
            self._edit_with_nvim(Path(file_path))
        else:
            self.app.notify(
                "No note selected or item is not editable", severity="warning"
            )

    def action_edit_meeting(self) -> None:
        """Edit selected meeting using NVim."""
        item = self._get_current_activity()
        file_path = item.file_path if item else None
        if not file_path:
            row_idx = self.activity_table.cursor_row
            meetings = self.company_data.get("meetings", [])
            if row_idx is not None and row_idx < len(meetings):
                file_path = meetings[row_idx].get("file_path")

        if file_path:
            self._edit_with_nvim(Path(file_path))
        else:
            self.app.notify("No meeting selected", severity="warning")

    def action_view_item(self) -> None:
        """View activity item in a modal."""
        item = self._get_current_activity()
        if not item:
            return
        self._show_content_viewer(item.title, item.content)

    def action_view_meeting(self) -> None:
        item = self._get_current_activity()
        if item:
            self._show_content_viewer(item.title, item.content)
            return
        row_idx = self.activity_table.cursor_row
        meetings = self.company_data.get("meetings", [])
        if row_idx is not None and row_idx < len(meetings):
            m = meetings[row_idx]
            self._show_content_viewer(m.get("title", "Meeting"), m.get("content", ""))

    def action_view_note(self) -> None:
        item = self._get_current_activity()
        if item:
            self._show_content_viewer(item.title, item.content)
            return
        row_idx = self.activity_table.cursor_row
        notes = self.company_data.get("notes", [])
        if row_idx is not None and row_idx < len(notes):
            n = notes[row_idx]
            self._show_content_viewer(n.get("title", "Note"), n.get("content", ""))

    def _show_content_viewer(self, title: str, content: str) -> None:
        """Show content in a modal viewer."""
        from .content_viewer_modal import ContentViewerModal

        self.app.push_screen(ContentViewerModal(title=title, content=content))

    async def action_delete_activity(self) -> None:
        """Delete an existing activity item with confirmation."""
        item = self._get_current_activity()
        file_path = item.file_path if item else None
        act_type = item.activity_type if item else "item"

        if not file_path:
            row_idx = self.activity_table.cursor_row
            notes = self.company_data.get("notes", [])
            if row_idx is not None and row_idx < len(notes):
                file_path = notes[row_idx].get("file_path")
                act_type = "note"

        if not file_path:
            self.app.notify("No deletable item selected", severity="warning")
            return

        confirm = await self.app.push_screen_wait(
            ConfirmScreen(f"Are you sure you want to delete this {act_type}?")
        )
        if confirm:
            try:
                Path(file_path).unlink()
                self.app.notify(f"{act_type.capitalize()} deleted")
                self.refresh_activity_data()
            except Exception as e:
                logger.error(f"Failed to delete {act_type}: {e}")
                self.app.notify(f"Delete failed: {e}", severity="error")

    async def action_delete_note(self) -> None:
        await self.action_delete_activity()

    def action_promote_item(self) -> None:
        """Toggle promote flag on the selected activity item."""
        item = self._get_current_activity()
        file_path = item.file_path if item else None
        if not file_path:
            row_idx = self.activity_table.cursor_row
            notes = self.company_data.get("notes", [])
            if row_idx is not None and row_idx < len(notes):
                file_path = notes[row_idx].get("file_path")
            else:
                meetings = self.company_data.get("meetings", [])
                if row_idx is not None and row_idx < len(meetings):
                    file_path = meetings[row_idx].get("file_path")

        if not file_path:
            self.app.notify("No item selected to promote", severity="warning")
            return

        self._toggle_promote_flag(Path(file_path))

    def action_promote_meeting(self) -> None:
        self.action_promote_item()

    def action_promote_note(self) -> None:
        self.action_promote_item()

    def _toggle_promote_flag(self, file_path: Path) -> None:
        """Toggle the promote flag in a note/meeting file's frontmatter."""
        import yaml

        if not file_path.exists():
            self.app.notify("File not found", severity="warning")
            return

        content = file_path.read_text()
        frontmatter_data: dict[str, Any] = {}
        markdown_content = content

        if content.startswith("---") and "---" in content[3:]:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                markdown_content = parts[2]
                try:
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError as e:
                    logger.warning(f"Error parsing YAML frontmatter: {e}")

        current_promote = frontmatter_data.get("promote", False)
        frontmatter_data["promote"] = not current_promote

        frontmatter = yaml.dump(
            frontmatter_data,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
        new_content = f"---\n{frontmatter}---\n{markdown_content}"

        file_path.write_text(new_content)

        status = "flagged for promotion" if frontmatter_data["promote"] else "unflagged"
        self.app.notify(f"Item {status}")
        self.refresh_activity_data()

    def _run_external_in_suspend(self, argv: list[str]) -> None:
        """Yield the tty to an interactive process, then restore the TUI."""
        with self.app.suspend():
            subprocess.run(argv, check=False)
        self.app.refresh()
        time.sleep(0.1)

    def _edit_with_nvim(self, path: Path) -> None:
        """Suspend the TUI and open NVim."""
        editor = get_editor_command() or "nvim"

        try:
            self._run_external_in_suspend([editor, str(path)])
            self.app.notify("Item saved")
            self.refresh_activity_data()
        except Exception as e:
            logger.error(f"NVim editor session failed: {e}")
            self.app.notify(f"Editor failed: {e}", severity="error")

    def refresh_activity_data(self) -> None:
        """Reload all company activities from filesystem and refresh table."""
        slug = self.company_data["company"].get("slug")
        if not slug:
            return

        try:
            from ...application.company_service import get_company_details_for_view

            reloaded = get_company_details_for_view(slug)
            if reloaded:
                self.company_data["activity"] = reloaded.get("activity")
                self.company_data["notes"] = notes_newest_first(
                    list(reloaded.get("notes") or [])
                )
                self.company_data["meetings"] = reloaded.get("meetings", [])
                self.refresh_activity_table()
        except Exception as e:
            logger.error(f"Failed to refresh activity data: {e}")

    def refresh_notes_data(self) -> None:
        self.refresh_activity_data()

    def refresh_meetings_data(self) -> None:
        self.refresh_activity_data()

    def refresh_notes_table(self) -> None:
        self.refresh_activity_table()

    def refresh_meetings_table(self) -> None:
        self.refresh_activity_table()

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "info-table":
            self.trigger_row_edit(cast(InfoTable, event.data_table))
        elif event.data_table.id in ("activity-table", "notes-table", "meetings-table"):
            self.action_edit_item()

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
            "Email": "email",
            "Phone": "phone_number",
            "Domain": "domain",
            "Name": "name",
            "Street": "street_address",
            "CSZ": "csz",
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
            city_input = EditInput(
                field_name="city", value=city, placeholder="City", id="edit-city"
            )
            state_input = EditInput(
                field_name="state", value=state, placeholder="State", id="edit-state"
            )
            zip_input = EditInput(
                field_name="zip_code",
                value=zip_code,
                placeholder="Zip",
                id="edit-zip_code",
            )

            panel.mount(container)
            container.mount(city_input, state_input, zip_input)
            city_input.focus()
        else:
            input_widget = EditInput(
                field_name=model_field, value=current_value, id=f"edit-{model_field}"
            )
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
        csz_container = (
            panel.query_one("#edit-csz-container", Horizontal)
            if "csz" in str(event.input.id)
            or "city" in str(event.input.id)
            or "state" in str(event.input.id)
            or "zip" in str(event.input.id)
            else None
        )

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
        if hasattr(self, "local_time_widget"):
            self.local_time_widget.set_company(self.company_data)
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
        reviews_val = (
            f"({review_count} reviews)" if review_count is not None else "(0 reviews)"
        )
        self.info_table.add_row("Rating", f"{rating_val} {reviews_val}")

        self.info_table.add_row("Domain", format_domain_display(c.get("domain")))
        self.info_table.add_row("Email", format_email_display(c.get("email")))
        extras = [
            str(e)
            for e in (c.get("all_emails") or [])
            if str(e).strip() and str(e) != str(c.get("email") or "")
        ]
        if extras:
            self.info_table.add_row("Emails", ", ".join(extras))
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
            dt = (
                datetime.fromisoformat(scraped_at)
                if isinstance(scraped_at, str)
                else scraped_at
            )
            scraped_val = dt.strftime("%Y-%m-%d")
        self.info_table.add_row("gm-list", scraped_val)

        details_at = c.get("details_found_at")
        details_val = "-"
        if details_at:
            dt = (
                datetime.fromisoformat(details_at)
                if isinstance(details_at, str)
                else details_at
            )
            details_val = dt.strftime("%Y-%m-%d")
        self.info_table.add_row("gm-detail", details_val)

        enqueued_at = c.get("enqueued_at")
        enrich_val = "No"
        if enrichment_mtime:
            dt = datetime.fromisoformat(enrichment_mtime)
            enrich_val = f"[bold green]{dt.strftime('%Y-%m-%d %H:%M')}[/]"
        elif enqueued_at:
            dt = (
                datetime.fromisoformat(enqueued_at)
                if isinstance(enqueued_at, str)
                else enqueued_at
            )
            enrich_val = f"[bold yellow]{dt.strftime('%Y-%m-%d')} (pending)[/]"
        self.info_table.add_row("enrichment", enrich_val)

        if tags:
            self.info_table.add_row("Tags", ", ".join(tags))

        if keywords:
            self.info_table.add_row("Keywords", ", ".join(keywords))

        # Social Media (Keep conditional to avoid empty rows cluttering the dense view)
        socials = []
        if c.get("facebook_url") or (website_data and website_data.get("facebook_url")):
            socials.append("FB")
        if c.get("linkedin_url") or (website_data and website_data.get("linkedin_url")):
            socials.append("LI")
        if c.get("instagram_url") or (
            website_data and website_data.get("instagram_url")
        ):
            socials.append("IG")
        if c.get("twitter_url") or (website_data and website_data.get("twitter_url")):
            socials.append("TW")

        if socials:
            self.info_table.add_row("Socials", " | ".join(socials))

        # Desc
        desc = c.get("description") or (
            website_data and website_data.get("description")
        )
        if desc:
            self.info_table.add_row(
                "Desc", escape(str(desc)[:100].replace("\n", " ") + "...")
            )

    def _create_info_table(self) -> InfoTable:
        table = InfoTable(id="info-table")
        table.add_column("Attribute", width=10)
        table.add_column("Value")
        # Initialize content
        self.info_table = table  # Temporarily assign so _refresh works
        self._refresh_info_table()
        return table

    def _create_contacts_table(self) -> ContactsTable:
        table = ContactsTable(id="contacts-table")
        table.add_column("Name")
        table.add_column("Role")
        table.add_column("Email")
        self.contacts_table = table
        self._refresh_contacts_table()
        return table

    def _refresh_contacts_table(self) -> None:
        self.contacts_table.clear()
        contacts = self.company_data.get("contacts", [])
        for c in contacts:
            name = c.get("name") or ("Unknown" if c.get("source") != "website" else "")
            table_name = escape(str(name)) if name else ""
            self.contacts_table.add_row(
                table_name,
                escape(str(c.get("role") or "")),
                str(c.get("email") or ""),
            )

    def _upcoming_schedule_rows(self) -> list[tuple[str, Text]]:
        """Scheduled-but-not-yet-happened items for this company - a
        pending to-call callback_at and/or pending FollowUpTask entries -
        rendered as synthetic rows so they're visible right where you'd
        look for "what's coming up," rather than requiring you to know to
        check queues/to-call or queues/follow-up directly (Mark,
        2026-09-17, re: Jimmy Jean: "there is not indication of an
        upcoming meeting... he is also not in the to-call")."""
        rows: list[tuple[str, Text]] = []
        company = self.company_data.get("company", {})
        callback_at_raw = company.get("callback_at")
        if callback_at_raw:
            try:
                callback_dt = datetime.fromisoformat(str(callback_at_raw))
                if callback_dt.tzinfo is None:
                    callback_dt = callback_dt.replace(tzinfo=UTC)
                overdue = callback_dt <= datetime.now(UTC)
                style = "bold red" if overdue else "bold yellow"
                dt_str = callback_dt.strftime("%Y-%m-%d %H:%M")
                label = "Callback overdue" if overdue else "Callback scheduled"
                rows.append((dt_str, Text(f"[{label}]", style=style)))
            except (ValueError, TypeError):
                pass

        slug = company.get("slug")
        campaign_name = None
        try:
            from ...core.config import get_campaign

            campaign_name = get_campaign()
        except Exception:
            pass
        if slug and campaign_name:
            try:
                from ...application.follow_up_service import FollowUpService

                for task in FollowUpService(campaign_name).list_pending(slug):
                    dt_str = task.scheduled_at.strftime("%Y-%m-%d %H:%M")
                    detail = task.template_id or task.format
                    rows.append(
                        (
                            dt_str,
                            Text(
                                f"[Follow-up: {task.format}] {detail}",
                                style="bold cyan",
                            ),
                        )
                    )
            except Exception:
                pass

        return rows

    def _get_activities(self) -> list[CompanyActivity]:
        """Fetch unified activities from data, disk, or synthesize from notes/meetings/callback."""
        # 1. Directly in company_data
        raw = self.company_data.get("activity")
        if raw:
            res: list[CompanyActivity] = []
            for item in raw:
                if isinstance(item, CompanyActivity):
                    res.append(item)
                elif isinstance(item, dict):
                    res.append(CompanyActivity(**item))
            return res

        # 2. Try loading from company_service
        slug = self.company_data.get("company", {}).get("slug")
        if slug:
            try:
                from ...application.company_service import get_company_activity

                disk_activities = get_company_activity(slug, include_scheduled=True)
                if disk_activities:
                    return disk_activities
            except Exception as e:
                logger.debug("Could not load activity for %s: %s", slug, e)

        # 3. Fallback: synthesize from company_data (for in-memory fixtures / mock tests)
        activities: list[CompanyActivity] = []
        now = datetime.now(UTC)

        # Notes in company_data
        for n in self.company_data.get("notes", []):
            ts = n.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = now
            elif not isinstance(ts, datetime):
                ts = now
            title = str(n.get("title") or "Note")
            content = str(n.get("content") or "")
            n_type = str(n.get("type") or "note").lower()
            file_path = Path(n["file_path"]) if n.get("file_path") else None
            meta = {
                k: v
                for k, v in n.items()
                if k not in ("title", "content", "timestamp", "file_path")
            }
            clean_act_type: Literal["call", "email", "note", "meeting"] = (
                "call"
                if n_type == "call"
                else ("email" if n_type == "email" else "note")
            )
            activities.append(
                CompanyActivity(
                    timestamp=ts,
                    activity_type=clean_act_type,
                    icon="📞"
                    if clean_act_type == "call"
                    else ("✉" if clean_act_type == "email" else "📝"),
                    title=title,
                    preview=format_activity_preview(n).plain,
                    content=content,
                    file_path=file_path,
                    metadata=meta,
                    is_scheduled=False,
                )
            )

        # Meetings in company_data
        for m in self.company_data.get("meetings", []):
            raw_dt = m.get("datetime_utc") or m.get("timestamp")
            if isinstance(raw_dt, str):
                try:
                    dt = datetime.fromisoformat(raw_dt)
                except Exception:
                    dt = now
            elif isinstance(raw_dt, datetime):
                dt = raw_dt
            else:
                dt = now
            dt_aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
            is_future = dt_aware > now
            title = str(m.get("title") or "Meeting")
            content = str(m.get("content") or "")
            file_path = Path(m["file_path"]) if m.get("file_path") else None
            meta = {
                k: v
                for k, v in m.items()
                if k
                not in ("title", "content", "timestamp", "datetime_utc", "file_path")
            }
            activities.append(
                CompanyActivity(
                    timestamp=dt,
                    activity_type="meeting",
                    icon="📅",
                    title=title,
                    preview=f"[{m.get('type', 'meeting')}] {content[:80]}",
                    content=content,
                    file_path=file_path,
                    metadata=meta,
                    is_scheduled=is_future,
                )
            )

        # Scheduled callback
        company_info = self.company_data.get("company", {})
        cb_raw = company_info.get("callback_at")
        if cb_raw:
            try:
                cb_dt = (
                    datetime.fromisoformat(str(cb_raw))
                    if isinstance(cb_raw, str)
                    else cb_raw
                )
                cb_dt_aware = (
                    cb_dt.replace(tzinfo=UTC) if cb_dt.tzinfo is None else cb_dt
                )
                overdue = cb_dt_aware <= now
                label = "Callback overdue" if overdue else "Callback scheduled"
                activities.append(
                    CompanyActivity(
                        timestamp=cb_dt,
                        activity_type="call",
                        icon="📞",
                        title=label,
                        preview=f"[{label}]",
                        content="",
                        file_path=None,
                        metadata={"overdue": overdue, "scheduled": True},
                        is_scheduled=True,
                    )
                )
            except Exception:
                pass

        # Pending follow-ups
        if slug:
            try:
                from ...core.config import get_campaign

                campaign = get_campaign()
                if campaign:
                    from ...application.follow_up_service import FollowUpService

                    for task in FollowUpService(campaign).list_pending(slug):
                        fmt = task.format or "email"
                        task_act_type: Literal["call", "email", "note", "meeting"] = (
                            "email" if fmt == "email" else "call"
                        )
                        activities.append(
                            CompanyActivity(
                                timestamp=task.scheduled_at,
                                activity_type=task_act_type,
                                icon="✉" if task_act_type == "email" else "📞",
                                title=f"Follow-up: {fmt}",
                                preview=f"[Follow-up: {fmt}] {task.template_id or fmt}",
                                content=task.template_id or "",
                                file_path=None,
                                metadata={"task_id": task.task_id, "scheduled": True},
                                is_scheduled=True,
                            )
                        )
            except Exception:
                pass

        def _ts_aware(a: CompanyActivity) -> datetime:
            t = a.timestamp
            return t.replace(tzinfo=UTC) if t.tzinfo is None else t

        b0 = sorted(
            [a for a in activities if a.is_scheduled and _ts_aware(a) > now],
            key=_ts_aware,
            reverse=True,
        )
        b1 = sorted(
            [a for a in activities if a.is_scheduled and _ts_aware(a) <= now],
            key=_ts_aware,
            reverse=True,
        )
        b2 = sorted(
            [a for a in activities if not a.is_scheduled],
            key=_ts_aware,
            reverse=True,
        )
        return b0 + b1 + b2

    def _create_activity_table(self) -> ActivityTable:
        table = ActivityTable(id="activity-table")
        table.add_column("Date", width=7)
        table.add_column("Preview", width=52)
        self.activity_table = table
        self.refresh_activity_table()
        return table

    def refresh_activity_table(self) -> None:
        """Repopulate the unified activity table with stacked date/time and now-divider."""
        self.activity_table.clear()
        self._activity_row_items = []
        activities = self._get_activities()

        scheduled_items = [a for a in activities if a.is_scheduled]
        past_items = [a for a in activities if not a.is_scheduled]
        now_utc = datetime.now(UTC)

        # 1. Scheduled items (above now)
        for a in scheduled_items:
            ts = a.timestamp
            ts_aware = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts
            is_overdue = ts_aware <= now_utc
            dt_text = format_activity_datetime(
                ts, is_scheduled=True, is_overdue=is_overdue
            )
            preview_text = format_activity_preview(a)
            self.activity_table.add_row(dt_text, preview_text, height=PREVIEW_MAX_LINES)
            self._activity_row_items.append(a)

        # 2. Thin 50% opacity yellow HR for now-time
        if scheduled_items:
            divider_dt = Text("──────", style="dim yellow")
            divider_line = Text(
                "── now ───────────────────────────────────", style="dim yellow"
            )
            self.activity_table.add_row(
                divider_dt, divider_line, height=1, key="now-divider"
            )
            self._activity_row_items.append(None)

        # 3. Past history items (below now)
        for a in past_items:
            ts = a.timestamp
            dt_text = format_activity_datetime(ts, is_scheduled=False, is_overdue=False)
            preview_text = format_activity_preview(a)
            self.activity_table.add_row(dt_text, preview_text, height=PREVIEW_MAX_LINES)
            self._activity_row_items.append(a)

        if self.activity_table.has_focus:
            self.activity_table.focus()

    def _create_meetings_table(self) -> ActivityTable:
        return self._create_activity_table()

    def _create_notes_table(self) -> ActivityTable:
        return self._create_activity_table()
