"""Two-level "list-above-a-list" browser for a campaign's initiatives/
folder tree - mirrors ApplicationView's Admin-screen pattern (top nav
list + a stacked second list) one level down, inside the Messages
screen's content pane. Deliberately reads the real folder names/nesting
directly (via cocli.core.paths, not a merged abstraction) rather than
inventing a display layer over them, per the stated principle that TUI
navigation should track the actual folder structure - also prep for
treating Yazi as a supplemental UI over the same data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import CocliApp

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll

from textual.widgets import Label, ListItem, ListView, Static

from ...core.paths import paths
from .message_templates_view import TemplateListItem, TemplatePreview

if TYPE_CHECKING:
    from ...models.campaigns.indexes.email_send_log import SendLogEntry

_CATEGORY_LABELS = {
    "email-sequences": "Email Sequences",
    "rendered-outreach": "Rendered Outreach",
    "tracking": "Tracking",
}


class InitiativeListItem(ListItem):
    def __init__(self, initiative: str) -> None:
        super().__init__()
        self.initiative = initiative

    def compose(self) -> Any:
        yield Label(self.initiative)


class CategoryListItem(ListItem):
    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category

    def compose(self) -> Any:
        yield Label(_CATEGORY_LABELS.get(self.category, self.category))


class FileBrowserListItem(ListItem):
    def __init__(self, path: Path, label: str) -> None:
        super().__init__()
        self.path = path
        self._label = label

    def compose(self) -> Any:
        yield Label(self._label)


class FileBrowserPreview(Container):
    def compose(self) -> Any:
        from textual.widgets import Static
        from textual.containers import VerticalScroll

        with VerticalScroll():
            yield Label("Select a file to preview it", id="file-browser-empty")
            yield Static("", id="file-browser-content")

    def update_preview(self, content: str | None) -> None:
        from textual.widgets import Static

        empty = self.query_one("#file-browser-empty", Label)
        body = self.query_one("#file-browser-content", Static)
        if content is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        body.update(content)


class _EmailSequencesPane(Horizontal):
    """Email Sequences category content: list_initiative_templates() +
    generate_copy() rendered with placeholder sample values, correctly
    scoped to whichever initiative is selected (not hardcoded)."""

    def __init__(self, initiative: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.file_list = ListView(id="email_sequences_file_list")
        self.preview = TemplatePreview(id="email_sequences_preview")

    def compose(self) -> ComposeResult:
        yield Container(self.file_list, id="email-sequences-list-pane")
        yield self.preview

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        names = service.list_initiative_templates(self.initiative)
        for name in names:
            self.file_list.append(TemplateListItem(name))
        if not names:
            self.preview.update_preview(None, None)
        self.file_list.focus()

    @on(ListView.Selected)
    def on_template_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, TemplateListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        try:
            subject, body = service.generate_copy(
                first_name="Sample",
                company_name="Sample Co",
                company_slug="sample-co",
                template_name=message.item.template_name,
                initiative=self.initiative,
            )
        except Exception as e:
            self.app.notify(f"Template error: {e}", severity="error")
            self.preview.update_preview(
                "(template error)", f"{e}\n\nFix the placeholder before using this template in a batch."
            )
            return
        self.preview.update_preview(subject, body)

    def on_key(self, event: events.Key) -> None:
        # event.stop() is required on every branch here, not just
        # prevent_default() - without it the key event keeps bubbling to
        # InitiativesView's own on_key in the same keypress, which then
        # (seeing categories_list newly focused) immediately hops focus a
        # second time, straight past it to initiatives_list. Confirmed
        # live 2026-09-16: "h" from this pane skipped the Category list
        # entirely and landed on Initiatives.
        if event.key == "j":
            self.file_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.file_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "h":
            self.app.query_one("#categories_list", ListView).focus()
            event.prevent_default()
            event.stop()


class _FileBrowserPane(Horizontal):
    """Generic read-only file browser for Rendered Outreach / Tracking -
    list_category_files() for the list, raw file content for the preview."""

    def __init__(self, initiative: str, category: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.category = category
        self.file_list = ListView(id="file_browser_list")
        self.preview = FileBrowserPreview(id="file_browser_preview")

    def compose(self) -> ComposeResult:
        yield Container(self.file_list, id="file-browser-list-pane")
        yield self.preview

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        base = paths.campaigns / campaign / "initiatives" / self.initiative / self.category
        files = service.list_category_files(self.initiative, self.category)
        for f in files:
            try:
                label = str(f.relative_to(base))
            except ValueError:
                label = f.name
            self.file_list.append(FileBrowserListItem(f, label))
        if not files:
            self.preview.update_preview(None)
        self.file_list.focus()

    @on(ListView.Selected)
    def on_file_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, FileBrowserListItem):
            return
        try:
            content = message.item.path.read_text(encoding="utf-8")
        except Exception as e:
            content = f"(could not read file: {e})"
        self.preview.update_preview(content)

    def on_key(self, event: events.Key) -> None:
        # See _EmailSequencesPane.on_key()'s comment - event.stop() is
        # required here too, for the same reason.
        if event.key == "j":
            self.file_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.file_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "h":
            self.app.query_one("#categories_list", ListView).focus()
            event.prevent_default()
            event.stop()


class TrackingListItem(ListItem):
    def __init__(self, entry: "SendLogEntry", event_type: str | None = None) -> None:
        super().__init__()
        self.entry = entry
        self.event_type = event_type

    def compose(self) -> Any:
        icon = "[green]sent[/green]" if self.entry.status == "sent" else "[red]failed[/red]"
        label = f"{icon}  {self.entry.recipient}  {self.entry.subject[:40]}"
        if self.event_type:
            label += f"  [bold red]{self.event_type}[/bold red]"
        yield Label(label)


class TrackingPreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select an entry to see details", id="tracking-preview-empty")
        yield Static("", id="tracking-preview-body")

    def update_preview(self, entry: "SendLogEntry | None", event_type: str | None = None) -> None:
        empty = self.query_one("#tracking-preview-empty", Label)
        body = self.query_one("#tracking-preview-body", Static)
        if entry is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        lines = [
            f"[bold]Recipient:[/bold] {entry.recipient}",
            f"[bold]Company:[/bold] {entry.company_slug}",
            f"[bold]Subject:[/bold] {entry.subject}",
            f"[bold]Status:[/bold] {entry.status}",
            f"[bold]Batch:[/bold] {entry.batch_id}",
            f"[bold]Template:[/bold] {entry.template_id}",
            f"[bold]Sent at:[/bold] {entry.sent_at}",
        ]
        if entry.message_id:
            lines.append(f"[bold]Message ID:[/bold] {entry.message_id}")
        if entry.error:
            lines.append(f"[bold]Error:[/bold] {entry.error}")
        if event_type:
            lines.append(f"[bold red]{event_type}[/bold red] - see the tracking event log for details")
        lines.append("")
        lines.append("[dim]l: open company[/dim]")
        body.update("\n".join(lines))


class _TrackingPane(Horizontal):
    """Tracking category content: this initiative's send log (sent +
    failed attempts), newest first - the "list of stats, details on the
    right" shape Mark asked about, backed by real SendLogEntry rows
    instead of the raw JSON/CSV files _FileBrowserPane used to show."""

    def __init__(self, initiative: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.stats_label = Label("", id="tracking-stats")
        self.entry_list = ListView(id="tracking_entry_list")
        self.preview = TrackingPreview(id="tracking_preview")

    def compose(self) -> ComposeResult:
        with Vertical(id="tracking-list-pane"):
            yield self.stats_label
            yield self.entry_list
        yield self.preview

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        entries = service.list_send_log(initiative=self.initiative)
        sent = sum(1 for e in entries if e.status == "sent")
        failed = sum(1 for e in entries if e.status == "failed")
        events = service.list_ses_events(initiative=self.initiative)
        bounced = sum(1 for e in events if e.event_type == "BOUNCE")
        complaints = sum(1 for e in events if e.event_type == "COMPLAINT")
        self.stats_label.update(
            f"Sent: {sent}   Failed: {failed}   Bounced: {bounced}   Complaints: {complaints}"
        )
        # Newest event wins if a message_id somehow has more than one -
        # events list is already sorted newest-first by list_ses_events().
        event_by_message_id: dict[str, str] = {}
        for event in reversed(events):
            if event.message_id:
                event_by_message_id[event.message_id] = event.event_type
        for entry in entries:
            self.entry_list.append(
                TrackingListItem(entry, event_type=event_by_message_id.get(entry.message_id or ""))
            )
        if not entries:
            self.preview.update_preview(None)
        self.entry_list.focus()

    @on(ListView.Selected)
    def on_entry_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, TrackingListItem):
            return
        self.preview.update_preview(message.item.entry, event_type=message.item.event_type)

    def on_key(self, event: events.Key) -> None:
        # See _EmailSequencesPane.on_key()'s comment - event.stop() is
        # required here too, for the same reason.
        if event.key == "j":
            self.entry_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.entry_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "h":
            self.app.query_one("#categories_list", ListView).focus()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            highlighted = self.entry_list.highlighted_child
            if isinstance(highlighted, TrackingListItem):
                cast("CocliApp", self.app).open_company_detail(highlighted.entry.company_slug)
            event.prevent_default()
            event.stop()


class InitiativesView(Container):
    """Master: initiatives list (top) + categories list (second, stacked
    below it in the same left column) - mirrors application_view.py's
    Admin nav_list/sub_nav pattern. Content pane (right) swaps between
    the Email Sequences render-preview pane and the generic file browser,
    per selected category."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiatives_list = ListView(id="initiatives_list")
        self.categories_list = ListView(id="categories_list")
        self.content_container: Container = Container(id="initiatives-content")
        self._current_initiative: str | None = None

    def compose(self) -> ComposeResult:
        # Mirrors application_view.py's Admin sidebar exactly: an outer
        # #app_sidebar_column-equivalent holding two stacked, independently
        # focus-highlighted containers (top nav list, second sub-nav list),
        # same ids-plus-CSS shape (see tui.css), same width.
        with Horizontal():
            with Vertical(id="initiatives_sidebar_column"):
                with Vertical(id="initiatives_nav_container"):
                    yield Label("Initiatives", classes="sidebar-title")
                    yield self.initiatives_list
                with Vertical(id="initiatives_sub_nav_container"):
                    yield Label("Category", classes="sidebar-title")
                    yield self.categories_list
            yield self.content_container

    async def on_mount(self) -> None:
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        for name in service.list_initiatives():
            self.initiatives_list.append(InitiativeListItem(name))
        # Items appended dynamically (not statically composed) don't get
        # an initial highlighted index for free - set it explicitly so
        # h/j/k/l and Enter have something to act on right away.
        if self.initiatives_list.children:
            self.initiatives_list.index = 0
        # No focus() call here - MessagesView.on_mount() grabs focus
        # explicitly via action_focus_master() once this widget is mounted,
        # so a bare re-render/refresh here never steals focus mid-session.

    def action_focus_master(self) -> None:
        """Focuses the top (Initiatives) list. Called by MessagesView on
        first mount and whenever app.py's action_show_messages() reuses an
        already-mounted MessagesView."""
        self.initiatives_list.focus()

    @on(ListView.Selected, "#initiatives_list")
    async def on_initiative_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, InitiativeListItem):
            return
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        self._current_initiative = event.item.initiative
        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)

        await self.categories_list.clear()
        for category in service.list_initiative_categories(self._current_initiative):
            await self.categories_list.append(CategoryListItem(category))

        for child in list(self.content_container.children):
            await child.remove()

        if self.categories_list.children:
            self.categories_list.focus()

    @on(ListView.Selected, "#categories_list")
    async def on_category_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, CategoryListItem) or not self._current_initiative:
            return
        await self._show_category(self._current_initiative, event.item.category)

    async def _show_category(self, initiative: str, category: str) -> None:
        for child in list(self.content_container.children):
            await child.remove()

        pane: Horizontal
        if category == "email-sequences":
            pane = _EmailSequencesPane(initiative)
        elif category == "tracking":
            pane = _TrackingPane(initiative)
        else:
            pane = _FileBrowserPane(initiative, category)
        await self.content_container.mount(pane)

    def on_key(self, event: events.Key) -> None:
        focused = self.app.focused
        if focused is None:
            return

        if event.key == "h" and getattr(focused, "id", None) == "categories_list":
            self.initiatives_list.focus()
            event.prevent_default()
            event.stop()
            return

        if isinstance(focused, ListView) and focused.id in ("initiatives_list", "categories_list"):
            if event.key == "j":
                focused.action_cursor_down()
                event.prevent_default()
                event.stop()
            elif event.key == "k":
                focused.action_cursor_up()
                event.prevent_default()
                event.stop()
            elif event.key == "l":
                focused.action_select_cursor()
                event.prevent_default()
                event.stop()
