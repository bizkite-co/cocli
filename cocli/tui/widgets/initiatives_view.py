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

import asyncio
import logging
from pathlib import Path
from typing import Any, cast, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..app import CocliApp

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll

from textual.widgets import Label, ListItem, ListView, Static

from ...core.paths import paths
from .message_templates_view import TemplateListItem, TemplatePreview

if TYPE_CHECKING:
    pass

_CATEGORY_LABELS = {
    "email-sequences": "Email Sequences",
    "rendered-outreach": "Rendered Outreach",
    "tracking": "Tracking",
    "responses": "Responses",
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
    def __init__(
        self,
        entry: Any,
        event_type: str | None = None,
        clicked: bool = False,
    ) -> None:
        super().__init__()
        self.entry = entry
        self.event_type = event_type
        self.clicked = clicked

    def compose(self) -> Any:
        if hasattr(self.entry, "event_type") and hasattr(self.entry, "source"):
            # EngagementEvent (web landing page / UTM / GTM signal)
            icon_map = {
                "link_click": "[bold green]click[/bold green]",
                "feedback_submit": "[bold magenta]feedback[/bold magenta]",
                "testimonial_submitted": "[bold magenta]testimonial[/bold magenta]",
                "signup_submitted": "[bold magenta]signup[/bold magenta]",
                "cta_click": "[bold cyan]cta_click[/bold cyan]",
                "landing_page_view": "[bold yellow]page_view[/bold yellow]",
                "demo_video_start": "[bold green]video_start[/bold green]",
                "calculator_interactive_use": "[bold blue]calculator[/bold blue]",
            }
            badge = icon_map.get(self.entry.event_type, f"[bold]{self.entry.event_type}[/bold]")
            # Stored timestamps are UTC (EngagementEvent.timestamp defaults
            # to datetime.now(UTC)) - astimezone() with no args converts to
            # this machine's local timezone, which is what the cocli
            # operator actually wants to read, not the storage timezone.
            ts_str = self.entry.timestamp.astimezone().strftime("%m/%d %H:%M")
            co = self.entry.company_slug or self.entry.utm_content or "(web visitor)"
            person = f" [cyan]({self.entry.utm_term})[/cyan]" if getattr(self.entry, "utm_term", None) else ""
            source_tag = self.entry.utm_source or self.entry.source
            yield Label(f"{badge}  {co}{person}  [dim]{source_tag} ({ts_str})[/dim]")
        else:
            # SendLogEntry
            icon = "[green]sent[/green]" if self.entry.status == "sent" else "[red]failed[/red]"
            label = f"{icon}  {self.entry.recipient}  {self.entry.subject[:40]}"
            if self.clicked:
                label += "  [bold green][CLICKED][/bold green]"
            if self.event_type:
                label += f"  [bold red]{self.event_type}[/bold red]"
            yield Label(label)


class TrackingPreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select an entry to see details", id="tracking-preview-empty")
        yield Static("", id="tracking-preview-body")

    def update_preview(
        self,
        entry: Any | None,
        event_type: str | None = None,
        clicked: bool = False,
    ) -> None:
        empty = self.query_one("#tracking-preview-empty", Label)
        body = self.query_one("#tracking-preview-body", Static)
        if entry is None:
            empty.display = True
            body.update("")
            return
        empty.display = False
        lines: list[str] = []

        if hasattr(entry, "event_type") and hasattr(entry, "source"):
            # EngagementEvent
            lines = [
                f"[bold magenta]Signal:[/] {entry.event_type}",
                f"[bold]Company Slug:[/] {entry.company_slug or '(unknown)'}",
            ]
            if getattr(entry, "utm_term", None):
                lines.append(f"[bold]Contact (Person):[/] [cyan]{entry.utm_term}[/cyan]")
            lines.extend([
                f"[bold]Source:[/] {entry.source}",
                f"[bold]UTM Source:[/] {entry.utm_source or 'N/A'}",
                f"[bold]UTM Medium:[/] {entry.utm_medium or 'N/A'}",
                f"[bold]UTM Campaign:[/] {entry.utm_campaign or 'N/A'}",
                f"[bold]UTM Content:[/] {entry.utm_content or 'N/A'}",
                f"[bold]UTM Term:[/] {entry.utm_term or 'N/A'}",
                f"[bold]Timestamp:[/] {entry.timestamp.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
            ])
            if getattr(entry, "details", None):
                lines.append("")
                lines.append("[bold]Payload Details:[/bold]")
                details_dict = entry.details if isinstance(entry.details, dict) else {}
                feedback_msg = details_dict.get("message")
                if feedback_msg:
                    lines.append(f"\n[bold green]Advisor Feedback Message:[/] {feedback_msg}\n")
                for k, v in details_dict.items():
                    if k != "message":
                        lines.append(f"  [dim]{k}:[/dim] {v}")
            if getattr(entry, "company_slug", None):
                lines.append("")
                lines.append("[dim]l: open company detail   p: pull GA4 telemetry   r: refresh[/dim]")
        else:
            # SendLogEntry
            lines = [
                f"[bold]Recipient:[/bold] {entry.recipient}",
                f"[bold]Company:[/bold] {entry.company_slug}",
                f"[bold]Subject:[/bold] {entry.subject}",
                f"[bold]Status:[/bold] {entry.status}",
            ]
            if clicked:
                lines.append("[bold green]Link Clicked:[/] Yes [bold green][CLICKED][/bold green]")
            lines.extend([
                f"[bold]Batch:[/bold] {entry.batch_id}",
                f"[bold]Template:[/bold] {entry.template_id}",
                f"[bold]Sent at:[/bold] {entry.sent_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
            ])
            if getattr(entry, "message_id", None):
                lines.append(f"[bold]Message ID:[/bold] {entry.message_id}")
            if getattr(entry, "error", None):
                lines.append(f"[bold]Error:[/bold] {entry.error}")
            if event_type:
                lines.append(f"[bold red]{event_type}[/bold red] - see the tracking event log for details")
            lines.append("")
            lines.append("[dim]l: open company   p: pull GA4 telemetry   r: refresh[/dim]")

        body.update("\n".join(lines))


class _TrackingPane(Horizontal):
    """Tracking category content: this initiative's send log (sent +
    failed attempts) and web engagement signals (landing page views, CTA
    clicks, feedback submissions), newest first."""

    BINDINGS = [
        Binding("p", "pull_telemetry", "Pull GA4", show=True),
        Binding("r", "refresh_tracking", "Refresh", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "navigate_back", "Back", show=False),
        Binding("l", "drill_down", "Open Company", show=False),
    ]

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
        await self.refresh_tracking()

    async def refresh_tracking(self) -> None:
        from cocli.application.engagement_service import EngagementService
        from cocli.application.personalized_outreach_service import PersonalizedOutreachService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        service = PersonalizedOutreachService(campaign)
        eng_service = EngagementService(campaign)

        entries = service.list_send_log(initiative=self.initiative)
        sent = sum(1 for e in entries if e.status == "sent")
        failed = sum(1 for e in entries if e.status == "failed")
        events = service.list_ses_events(initiative=self.initiative)
        bounced = sum(1 for e in events if e.event_type == "BOUNCE")
        complaints = sum(1 for e in events if e.event_type == "COMPLAINT")

        web_events = eng_service.list_events(initiative=self.initiative)

        # Calculate clicked companies
        clicked_slugs = {
            e.company_slug
            for e in web_events
            if e.company_slug
            and e.event_type in ("link_click", "cta_click", "feedback_submit", "landing_page_view")
        }
        sent_clicked = sum(1 for e in entries if e.company_slug in clicked_slugs)
        ctr_str = f"{(sent_clicked / sent * 100):.1f}%" if sent > 0 else "0.0%"

        stats_line = (
            f"Sent: {sent}   Failed: {failed}   Bounced: {bounced}   Complaints: {complaints}   "
            f"Web Signals: {len(web_events)}   CTR: {ctr_str} ({sent_clicked}/{sent})"
        )

        # Unprocessed form submissions sit invisibly in the S3 queue until
        # `cocli telemetry process-testimonials` is run - surfaced here so
        # that gap (previously only visible via `cocli telemetry report`)
        # doesn't require leaving the TUI to notice.
        if self.initiative in ("testimonials", "signups"):
            try:
                pending_submissions = sum(
                    1
                    for s in eng_service.list_form_submissions(queue_names=(self.initiative,))
                    if s.get("_status") == "pending"
                )
                stats_line += f"   Unprocessed Submissions: {pending_submissions}"
            except Exception as exc:
                logger.debug("Could not count pending %s submissions: %s", self.initiative, exc)

        self.stats_label.update(stats_line)

        await self.entry_list.clear()

        # Newest event wins if a message_id somehow has more than one
        event_by_message_id: dict[str, str] = {}
        for event in reversed(events):
            if event.message_id:
                event_by_message_id[event.message_id] = event.event_type

        # Mount web events first (newest real-time incoming signals)
        for w_evt in web_events:
            await self.entry_list.append(TrackingListItem(w_evt))

        for entry in entries:
            is_clicked = bool(entry.company_slug and entry.company_slug in clicked_slugs)
            await self.entry_list.append(
                TrackingListItem(
                    entry,
                    event_type=event_by_message_id.get(entry.message_id or ""),
                    clicked=is_clicked,
                )
            )

        if not entries and not web_events:
            self.preview.update_preview(None)
        elif self.entry_list.children:
            self.entry_list.index = 0
            first_child = self.entry_list.children[0]
            if isinstance(first_child, TrackingListItem):
                self.preview.update_preview(
                    first_child.entry,
                    event_type=first_child.event_type,
                    clicked=getattr(first_child, "clicked", False),
                )
        self.entry_list.focus()

    def action_pull_telemetry(self) -> None:
        self.run_worker(self.pull_telemetry(), exclusive=True)

    def action_refresh_tracking(self) -> None:
        self.run_worker(self.refresh_tracking(), exclusive=True)

    def action_cursor_down(self) -> None:
        self.entry_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self.entry_list.action_cursor_up()

    def action_navigate_back(self) -> None:
        self.app.query_one("#categories_list", ListView).focus()

    def action_drill_down(self) -> None:
        highlighted = self.entry_list.highlighted_child
        if isinstance(highlighted, TrackingListItem):
            co_slug = getattr(highlighted.entry, "company_slug", None)
            if co_slug:
                cast("CocliApp", self.app).open_company_detail(co_slug)

    async def pull_telemetry(self) -> None:
        from cocli.application.engagement_service import EngagementService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        eng_service = EngagementService(campaign)

        self.notify("Pulling GA4 telemetry...")
        try:
            new_events = await asyncio.to_thread(
                eng_service.pull_from_ga4,
                initiative=self.initiative,
            )
            count = len(new_events)
            self.notify(f"Pulled {count} new GA4 signal(s)")
            await self.refresh_tracking()
        except Exception as exc:
            self.notify(f"GA4 pull failed: {exc}", severity="error")

    @on(ListView.Selected)
    def on_entry_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, TrackingListItem):
            return
        self.preview.update_preview(
            message.item.entry,
            event_type=message.item.event_type,
            clicked=getattr(message.item, "clicked", False),
        )

    @on(ListView.Highlighted)
    def on_entry_highlighted(self, message: ListView.Highlighted) -> None:
        if not isinstance(message.item, TrackingListItem):
            return
        self.preview.update_preview(
            message.item.entry,
            event_type=message.item.event_type,
            clicked=getattr(message.item, "clicked", False),
        )


class ResponseListItem(ListItem):
    """One raw form submission (testimonial or signup), read straight
    from the S3-backed intake queue - pending (not yet processed into
    the engagement log/a company note) or completed (already
    processed). Unlike TrackingListItem's engagement events, these
    don't carry a resolved company_slug - that resolution only happens
    during `cocli telemetry process-testimonials`."""

    def __init__(self, submission: dict[str, Any]) -> None:
        super().__init__()
        self.submission = submission

    def compose(self) -> Any:
        import datetime as _dt

        status = self.submission.get("_status", "?")
        badge = (
            "[bold yellow]pending[/bold yellow]"
            if status == "pending"
            else "[bold green]completed[/bold green]"
        )
        received_at = self.submission.get("received_at")
        when = (
            _dt.datetime.fromtimestamp(received_at).astimezone().strftime("%m/%d %H:%M")
            if received_at
            else "(unknown)"
        )
        name = self.submission.get("name") or self.submission.get("email") or "(anonymous)"
        yield Label(f"{badge}  {name}  [dim]({when})[/dim]")


class ResponsePreview(VerticalScroll):
    def compose(self) -> Any:
        yield Label("Select a response to see details", id="response-preview-empty")
        yield Static("", id="response-preview-body")

    def update_preview(self, submission: dict[str, Any] | None) -> None:
        empty = self.query_one("#response-preview-empty", Label)
        body = self.query_one("#response-preview-body", Static)
        if submission is None:
            empty.display = True
            body.update("")
            return
        empty.display = False

        import datetime as _dt

        received_at = submission.get("received_at")
        when = (
            _dt.datetime.fromtimestamp(received_at).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            if received_at
            else "(unknown)"
        )
        lines = [
            f"[bold]Status:[/] {submission.get('_status', '?')}",
            f"[bold]Name:[/] {submission.get('name') or '(not given)'}",
            f"[bold]Firm:[/] {submission.get('firm') or 'N/A'}",
            f"[bold]Email:[/] {submission.get('email') or '(not given)'}",
            f"[bold]Permission to quote:[/] {submission.get('permission_to_quote') or 'N/A'}",
            f"[bold]UTM Source:[/] {submission.get('utm_source') or 'N/A'}",
            f"[bold]UTM Campaign:[/] {submission.get('utm_campaign') or 'N/A'}",
            f"[bold]Received:[/] {when}",
        ]
        message = submission.get("message")
        if message:
            lines.append("")
            lines.append(f"[bold green]Message:[/]\n{message}")
        body.update("\n".join(lines))


class _ResponsesPane(Horizontal):
    """This initiative's raw form submissions (pending + completed),
    read directly from S3 - the actual testimonial/signup content,
    separate from Tracking's mixed send-log/engagement-event view.
    Right below Tracking in the category list since it's the other half
    of the same data: Tracking shows that a submission happened,
    Responses shows what was actually said."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "navigate_back", "Back", show=False),
        Binding("r", "refresh_responses", "Refresh", show=True),
    ]

    def __init__(self, initiative: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.initiative = initiative
        self.stats_label = Label("", id="response-stats")
        self.entry_list = ListView(id="response_entry_list")
        self.preview = ResponsePreview(id="response_preview")

    def compose(self) -> ComposeResult:
        with Vertical(id="response-list-pane"):
            yield self.stats_label
            yield self.entry_list
        yield self.preview

    async def on_mount(self) -> None:
        await self.refresh_responses()

    async def refresh_responses(self) -> None:
        from cocli.application.engagement_service import EngagementService

        app = cast("CocliApp", self.app)
        campaign = app.services.campaign_name
        eng_service = EngagementService(campaign)

        try:
            submissions = await asyncio.to_thread(
                eng_service.list_form_submissions, queue_names=(self.initiative,)
            )
        except Exception as exc:
            logger.warning("Could not list %s responses: %s", self.initiative, exc)
            submissions = []

        pending = sum(1 for s in submissions if s.get("_status") == "pending")
        completed = sum(1 for s in submissions if s.get("_status") == "completed")
        self.stats_label.update(f"Pending: {pending}   Completed: {completed}   Total: {len(submissions)}")

        await self.entry_list.clear()
        for submission in submissions:
            await self.entry_list.append(ResponseListItem(submission))

        if not submissions:
            self.preview.update_preview(None)
        else:
            self.entry_list.index = 0
            first_child = self.entry_list.children[0]
            if isinstance(first_child, ResponseListItem):
                self.preview.update_preview(first_child.submission)
        self.entry_list.focus()

    def action_refresh_responses(self) -> None:
        self.run_worker(self.refresh_responses(), exclusive=True)

    def action_cursor_down(self) -> None:
        self.entry_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self.entry_list.action_cursor_up()

    def action_navigate_back(self) -> None:
        self.app.query_one("#categories_list", ListView).focus()

    @on(ListView.Selected)
    def on_response_selected(self, message: ListView.Selected) -> None:
        if not isinstance(message.item, ResponseListItem):
            return
        self.preview.update_preview(message.item.submission)

    @on(ListView.Highlighted)
    def on_response_highlighted(self, message: ListView.Highlighted) -> None:
        if not isinstance(message.item, ResponseListItem):
            return
        self.preview.update_preview(message.item.submission)


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
        elif category == "responses":
            pane = _ResponsesPane(initiative)
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
