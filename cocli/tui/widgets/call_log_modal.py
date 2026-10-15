# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

import logging
from datetime import datetime, UTC, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea, Static, Markdown
from textual.containers import Container, Horizontal, VerticalScroll
from textual import on, events

from cocli.models.companies.company import Company
from cocli.models.companies.meeting import Meeting
from cocli.models.companies.call_note import CallNote
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.models.phone import format_us_phone
from cocli.application.follow_up_service import FollowUpService
from cocli.application.personalized_outreach_service import PersonalizedOutreachService
from cocli.application.to_call_disposition_service import mark_to_call_invalid
from cocli.core.config import get_campaign
from cocli.core.paths import paths
from cocli.application.company_service import format_contact_line, list_known_contacts
from cocli.utils.company_local_time import CompanyPlace
from cocli.utils.when import parse_follow_up_when
from .company_local_time import CompanyLocalTime, resolve_place_from_company
from .inputs import CocliInput
from .search_select import SearchSelect

# Email follow-ups always render from a template (Mark, 2026-09-16: "I
# don't want to generate a whole email for just this one... It will be
# templated, and then I can edit the rendered email before sending") -
# this sentinel is the "don't schedule one" choice, always first/default.
NO_EMAIL_FOLLOW_UP = "(No email follow-up)"


def _recent_call_text(call: Any) -> str:
    """The words logged for the call. The meeting title is only the
    disposition ("Logged Call: Follow Up Needed"), so the right-hand
    column shows the notes instead. A call saved with no notes falls
    back to that disposition."""
    raw = (getattr(call, "content", None) or "").replace("\r\n", "\n").strip()
    notes = raw
    if raw.lower().startswith("disposition:"):
        _, _, rest = raw.partition("\n")
        notes = rest.strip()
    notes = " ".join(notes.split())
    if len(notes) > 180:
        notes = notes[:177] + "..."
    if notes:
        return notes
    title = (getattr(call, "title", None) or "").replace("\n", " ").strip()
    for prefix in ("Logged Call:", "Call Log:"):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
    return title or "(no notes)"

DISPOSITION_CHOICES = [
    ("Follow Up Needed", "Follow Up Needed"),
    ("Interested / Qualified", "Interested"),
    ("Not Interested", "Not Interested"),
    ("Wrong Trade / No Fit", "Wrong Trade / No Fit"),
    ("Objection: Price", "Objection: Price"),
    ("Objection: Feature Gap", "Objection: Feature Gap"),
    ("Bad Number", "Bad Number"),
]

# "Wrong Trade / No Fit": the business isn't the kind of customer the
# product serves at all (wrong industry, or right industry but doesn't do
# the specific installation type) - the standard sales term for this is
# "not ICP" (Ideal Customer Profile), used here in plain English per Mark's
# preference (conversation 2026-09-14).
EXCLUDING_DISPOSITIONS = {"Not Interested", "Bad Number", "Wrong Trade / No Fit"}


class CallLogModal(ModalScreen[bool]):
    """An embedded, keyboard-driven call logger with follow-up scheduling."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save_call", "Save & Close"),
        Binding("ctrl+enter", "save_call", "Save & Close", show=False),
        Binding("f4", "send_followup_now", "Send Follow-up Now"),
        # priority=True so these fire even while call_notes (a TextArea)
        # has focus and would otherwise consume plain "j"/"k" as typed
        # text. Bound to both key-id spellings ("J" vs "shift+j") since
        # which one a terminal reports for Shift+letter varies with its
        # keyboard-protocol support - untested which this environment
        # sends, so cover both rather than guess (2026-09-18).
        Binding("J,shift+j", "scroll_reference_down", "Scroll Ref Down", show=False, priority=True),
        Binding("K,shift+k", "scroll_reference_up", "Scroll Ref Up", show=False, priority=True),
    ]

    def __init__(
        self,
        company_slug: str,
        phone: str,
        caller_id: Optional[str] = None,
        call_error: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.company_slug = company_slug
        self.phone = phone
        self.call_error = call_error
        if caller_id is not None:
            self.caller_id: Optional[str] = caller_id
        else:
            try:
                from cocli.core.config import get_campaign, load_global_config
                from cocli.utils.calling_provider import get_calling_provider

                provider = get_calling_provider(get_campaign())
                self.caller_id = getattr(provider, "caller_id", None) or (
                    load_global_config().get("twilio", {}).get("caller_id")
                )
            except Exception:
                self.caller_id = None
        company = Company.get(company_slug)
        self.local_time_widget = CompanyLocalTime(company=company, slug=company_slug, id="company_local_time")
        self._place: CompanyPlace = self.local_time_widget._place
        self._contacts = list_known_contacts(company_slug)

        # Fetched once here (not per-markup-method) so recent emails and
        # notes don't each re-parse every file under notes/ and meetings/
        # a second/third time - get_company_activity() already returns
        # the unified, deduped, newest-first feed company_detail.py's
        # Activity tab uses.
        try:
            from cocli.application.company_service import get_company_activity

            self._activities = get_company_activity(company_slug, include_scheduled=False)
        except Exception as exc:
            logger.warning(f"Could not load activity history for {company_slug}: {exc}")
            self._activities = []

    @staticmethod
    def _resolve_place(company: Optional[Company]) -> CompanyPlace:
        return resolve_place_from_company(company)

    def _local_time_markup(self) -> str:
        return self.local_time_widget.get_time_markup()

    def compose(self) -> ComposeResult:
        # Default callback to 7 days from now
        default_callback = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d")

        # Every initiative's templates, not just "rta" - Mark, 2026-10-07:
        # request_testimonial.md (initiative "testimonials") was never
        # selectable here at all, which is why it had only ever gone out
        # once, in a one-off batch send outside this modal. The display
        # label ("[testimonials] request_testimonial.md") doubles as the
        # SearchSelect value so two initiatives can't collide on an
        # identical filename; _template_initiative_by_label resolves it
        # back to (template_name, initiative) when actually scheduling or
        # sending.
        service = PersonalizedOutreachService(get_campaign() or "default")
        self._template_initiative_by_label: dict[str, tuple[str, str]] = {
            label: (name, initiative)
            for label, name, initiative in service.list_templates_with_initiative()
        }
        template_choices = [(NO_EMAIL_FOLLOW_UP, "")] + [
            (label, label) for label in self._template_initiative_by_label
        ]
        # The call-script reference panel (opener/phrases/comparison) is
        # genuinely RTA-sales-specific material, independent of which
        # initiative's email template gets picked below - left as "rta".
        reference = service.load_call_reference("rta")
        phone_display = format_us_phone(self.phone) or self.phone
        caller_display = (
            format_us_phone(self.caller_id) or self.caller_id
            if self.caller_id
            else None
        )
        if caller_display:
            phone_markup = f"Phone: {phone_display}    Calling from: [bold yellow]{caller_display}[/bold yellow]"
        else:
            phone_markup = f"Phone: {phone_display}"

        with Container(id="call_log_form"):
            yield Label(f"LOGGING CALL: [bold cyan]{self.company_slug}[/]", id="call_modal_title")
            yield self.local_time_widget
            yield Label(phone_markup, classes="modal-subtitle", id="call_phone")
            if self.call_error:
                yield Label(
                    f"⚠️ [bold red]Call Failed:[/] [yellow]{self.call_error}[/]",
                    id="call_error_banner",
                )

            with Horizontal(id="call-log-columns"):
                with VerticalScroll(id="call-log-left"):
                    yield Static(self._contacts_markup(), id="call-contacts")

                    yield Label("Call Disposition (type to filter, Enter or Space to pick)", classes="field-label")
                    yield SearchSelect(DISPOSITION_CHOICES, initial_value="Follow Up Needed", id="call_disposition")

                    yield Label("Call Notes (VIM-ish keys supported)", classes="field-label")
                    yield TextArea(id="call_notes", classes="notes-area")

                    yield Label(
                        "Follow-up Date (YYYY-MM-DD, 'monday', 'next week'; blank = don't re-queue)",
                        classes="field-label",
                    )
                    yield CocliInput(value=default_callback, id="callback_date")

                    yield Label(
                        "Email Follow-up Template (Up/Down, Enter or Space to pick)",
                        classes="field-label",
                    )
                    yield SearchSelect(template_choices, initial_value="", id="followup_template")

                    yield Label(
                        "Email Follow-up Date (YYYY-MM-DD, 'monday', 'next week'; only if a template is picked)",
                        classes="field-label",
                    )
                    yield CocliInput(value=default_callback, id="followup_email_date")

                with VerticalScroll(id="call-log-right"):
                    yield Static(self._recent_calls_markup(), id="call-recent-calls")
                    yield Static(self._recent_emails_markup(), id="call-recent-emails")
                    yield Static(self._recent_notes_markup(), id="call-recent-notes")

                    # Missing files render as an empty Markdown widget
                    # (harmless) rather than erroring - see
                    # load_call_reference()'s per-file fallback.
                    yield Markdown(reference["call-opener.md"], id="call-script-panel")
                    yield Markdown(reference["preferred-phrases.md"], id="call-phrases-panel")
                    yield Markdown(reference["product-comparison.md"], id="call-comparison-panel")

            yield Static(
                "[bold reverse] CTRL+S / CTRL+ENTER: SAVE [/]  [bold reverse] F4: SEND FOLLOW-UP NOW [/]  [dim] ESC: CANCEL  ·  drag + two-finger tap: COPY [/]",
                id="modal_help",
            )

    def _contacts_markup(self) -> str:
        lines = [format_contact_line(c) for c in self._contacts]
        lines = [line for line in lines if line][:12]
        if not lines:
            return "[dim]No known contacts on file[/dim]"
        body = "\n".join(f"  {line}" for line in lines)
        return f"[bold]Known contacts[/bold]\n{body}"

    def _recent_calls_markup(self) -> str:
        """Recent calls for this company, newest first - sits at the top
        of the right-hand reference column so call history is visible
        without leaving this modal."""
        from cocli.application.meeting_service import MeetingService

        campaign = get_campaign() or "default"
        try:
            calls = MeetingService(campaign).get_recent_calls()
        except Exception as exc:
            logger.warning(f"Could not load recent calls for {self.company_slug}: {exc}")
            return "[bold]Recent calls[/bold]\n[dim]Unavailable[/dim]"

        company_calls = [c for c in calls if c.company_slug == self.company_slug][:8]
        if not company_calls:
            return "[bold]Recent calls[/bold]\n[dim]No recent calls for this company[/dim]"

        lines = []
        for c in company_calls:
            date_str = c.datetime_local.strftime("%Y-%m-%d %H:%M")
            direction = f" ({c.direction})" if c.direction else ""
            lines.append(f"  {c.icon} {date_str}{direction}: {_recent_call_text(c)}")
        body = "\n".join(lines)
        return f"[bold]Recent calls[/bold]\n{body}"

    def _recent_emails_markup(self) -> str:
        """Recent emails for this company, newest first - same spot as
        recent calls, so the rep can see what's already been sent/
        received without leaving this modal."""
        emails = [a for a in self._activities if a.activity_type == "email"][:8]
        if not emails:
            return "[bold]Recent emails[/bold]\n[dim]No recent emails for this company[/dim]"

        lines = []
        for a in emails:
            date_str = a.timestamp.astimezone().strftime("%Y-%m-%d %H:%M")
            clean_title = a.title.replace("\n", " ").strip()
            lines.append(f"  {a.icon} {date_str}: {clean_title}")
        body = "\n".join(lines)
        return f"[bold]Recent emails[/bold]\n{body}"

    def _recent_notes_markup(self) -> str:
        """Recent plain notes for this company, newest first - excludes
        call/email/sms notes, which already have their own dedicated
        panels (recent calls) or aren't relevant here."""
        notes = [a for a in self._activities if a.activity_type == "note"][:8]
        if not notes:
            return "[bold]Recent notes[/bold]\n[dim]No recent notes for this company[/dim]"

        lines = []
        for a in notes:
            date_str = a.timestamp.astimezone().strftime("%Y-%m-%d %H:%M")
            clean_preview = a.preview.replace("\n", " ").strip()
            lines.append(f"  {a.icon} {date_str}: {clean_preview}")
        body = "\n".join(lines)
        return f"[bold]Recent notes[/bold]\n{body}"

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick_local_time)
        self.query_one("#call_notes", TextArea).focus()

    def _tick_local_time(self) -> None:
        self.local_time_widget.tick()

    def action_scroll_reference_down(self) -> None:
        self.query_one("#call-log-right", VerticalScroll).scroll_down()

    def action_scroll_reference_up(self) -> None:
        self.query_one("#call-log-right", VerticalScroll).scroll_up()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        if event.key in ("ctrl+s", "ctrl+enter"):
            self.save_call()
        elif event.key == "f4":
            self.send_followup_now()

    def action_cancel(self) -> None:
        """Real call notes were lost to an unconfirmed instant discard here
        (2026-09-16, a live call to Jimmy Jean Insurance) - app.py's alt+s
        "universal escape" shim and this screen's own plain "escape"
        binding both used to call dismiss(False) directly with zero
        confirmation. Now: empty notes discard immediately (nothing to
        lose, no need to nag); non-empty notes require an explicit yes.

        Sync dispatcher + run_worker: push_screen_wait requires an active
        worker, which a BINDINGS-triggered action doesn't get for free -
        matches the pattern in company_detail.py's action_delete_company.
        """
        notes = self.query_one("#call_notes", TextArea).text.strip()
        if not notes:
            self.dismiss(False)
            return

        async def run_cancel() -> None:
            from .confirm_screen import ConfirmScreen

            confirmed = await self.app.push_screen_wait(
                ConfirmScreen("Discard unsaved call notes?")
            )
            if confirmed:
                self.dismiss(False)

        self.app.run_worker(run_cancel())

    def send_followup_now(self) -> None:
        """Deliberately named without the "action_" prefix, like save_call()
        above: Textual auto-dispatches a Binding's action string to
        "action_<name>" AND handle_keys() below calls it directly - if this
        were action_send_followup_now, both paths would fire and the email
        would send twice per keypress (caught via a failing test, 2026-10-06).
        The "f4" Binding's action string exists only to show the keybinding
        in the help bar; handle_keys() does the real dispatch, same as
        ctrl+s/ctrl+enter.

        Sends the selected template right now, instead of queueing the
        follow-up for later (FollowUpTask, requiring a separate visit to
        Follow-Up Queue to "prepare" it and then Target Batches to send
        it) - Mark, 2026-10-06: "it doesn't send until I close the call
        log and execute two more actions".

        Deliberately bypasses the normal "render to a draft, review/edit,
        then send" flow (see NO_EMAIL_FOLLOW_UP's docstring note above) -
        that review step exists for the batch/campaign flow; here the
        single explicit keypress on one specific contact, mid-call, *is*
        the human decision to send, same as picking up the phone was.

        Does nothing else - no meeting/call-note write, no disposition,
        no callback scheduling, no dismiss. Mark, 2026-10-08: an earlier
        version also called save_call() afterward (so F4 would log the
        call and close the modal, same as Ctrl+S) - he explicitly wanted
        that removed: "I only want to send the email... it's not
        supposed to do any other actions other than send the email."
        Logging the call is still Ctrl+S/Ctrl+Enter's job, whenever the
        call actually ends - pressing F4 mid-call no longer touches that
        at all, so there's no risk of it logging a half-finished note
        now and a complete one again later.

        Sync dispatcher + run_worker: sending is blocking network I/O and
        this is a BINDINGS-triggered action, which doesn't get a worker
        for free - same pattern as action_cancel above.
        """
        followup_label = self.query_one("#followup_template", SearchSelect).value
        if not followup_label or followup_label == NO_EMAIL_FOLLOW_UP:
            self.app.notify(
                "Pick an email follow-up template first", severity="warning"
            )
            return
        template_id, initiative = self._template_initiative_by_label[followup_label]
        self.app.run_worker(self._send_followup_now_worker(template_id, initiative))

    async def _send_followup_now_worker(self, template_id: str, initiative: str) -> None:
        import asyncio

        from cocli.application.email_service import EmailService
        from cocli.core.config import load_campaign_config
        from cocli.models.mail import EmailSettings

        campaign = get_campaign() or "default"

        def _send() -> tuple[int, int, Optional[str]]:
            service = PersonalizedOutreachService(campaign)
            raw = load_campaign_config(campaign) or {}
            email_raw = raw.get("email") or {}
            settings = EmailSettings.model_validate(email_raw)
            aws = raw.get("aws") or {}
            profile = aws.get("profile") if isinstance(aws.get("profile"), str) else None
            email_service = EmailService(campaign, settings, aws_profile=profile)

            try:
                result = service.send_now(
                    self.company_slug,
                    template_id=template_id,
                    initiative=initiative,
                    email_service=email_service,
                )
            except ValueError as exc:
                return 0, 0, str(exc)
            return result.sent, result.failed, None

        try:
            sent, failed, error = await asyncio.to_thread(_send)
        except Exception as exc:
            logger.exception(f"Failed to send follow-up now for {self.company_slug}")
            self.app.notify(f"Send failed: {exc}", severity="error")
            return

        if error:
            self.app.notify(error, severity="error")
            return
        if failed:
            self.app.notify(
                f"Failed to send follow-up ({template_id}) to {self.company_slug}",
                severity="error",
            )
            return

        self.app.notify(f"Sent follow-up email ({template_id}) now.")

    def save_call(self) -> None:
        notes = self.query_one("#call_notes", TextArea).text.strip()
        callback_str = self.query_one("#callback_date", CocliInput).value.strip()
        # No separate "schedule?" checkbox: a non-empty follow-up date IS
        # the request to re-queue. Clear the date field to opt out.
        should_schedule = bool(callback_str)
        disposition = self.query_one("#call_disposition", SearchSelect).value or "Follow Up Needed"

        try:
            company = Company.get(self.company_slug)
            if not company:
                self.app.notify("Company not found", severity="error")
                return

            campaign = get_campaign() or "default"

            # 1. Log Meeting
            meeting = Meeting(
                title=f"Logged Call: {disposition}",
                type="phone-call",
                content=f"Disposition: {disposition}\n\n{notes}" if notes else f"Disposition: {disposition}"
            )
            meetings_dir = paths.companies.entry(self.company_slug).path / "meetings"
            meeting_file = meeting.to_file(meetings_dir)

            try:
                from cocli.application.meeting_service import MeetingService
                from cocli.models.companies.meeting import CompanyCall
                from tzlocal import get_localzone
                local_tz: Any
                try:
                    local_tz = get_localzone()
                except Exception:
                    local_tz = UTC
                call_record = CompanyCall(
                    datetime_utc=meeting.timestamp,
                    datetime_local=meeting.timestamp.astimezone(local_tz),
                    company_name=str(company.name or self.company_slug.replace("-", " ").title()),
                    company_slug=self.company_slug,
                    title=meeting.title,
                    content=meeting.content,
                    file_path=meeting_file,
                )
                MeetingService(campaign).record_call_in_cache(call_record)
            except Exception as cache_err:
                logger.warning(f"Could not update recent calls cache: {cache_err}")

            # 2. Log CallNote in company notes/ directory
            notes_dir = paths.companies.entry(self.company_slug).path / "notes"
            call_note = CallNote(
                title=f"Call Log: {disposition}",
                disposition=disposition,
                phone=self.phone,
                content=notes or f"Disposition: {disposition}"
            )
            call_note.to_file(notes_dir)

            # 3. Disqualifying dispositions go through the same campaign-wide
            # mechanism as the m,i mark-invalid shortcut (ExclusionManager +
            # the to-call-invalid review pile), not a separate exclude call -
            # same reversibility (m,v), same "Invalid" template visibility,
            # whether the disqualification came from a phone call or a list
            # keypress. This also removes the pending to-call file itself,
            # so skip the completed-queue move below for this branch.
            is_excluded_disposition = disposition in EXCLUDING_DISPOSITIONS
            if is_excluded_disposition:
                mark_to_call_invalid(
                    campaign=campaign,
                    slug=self.company_slug,
                    domain=company.domain,
                    reason=disposition,
                )
                self.app.notify(f"Marked '{self.company_slug}' invalid ({disposition})")

            # 4. Queue Lifecycle: Move from PENDING to COMPLETED
            if not is_excluded_disposition:
                pending_task = ToCallTask(
                    company_slug=self.company_slug,
                    domain=company.domain or "unknown",
                    campaign_name=campaign,
                    ack_token=None
                )
                pending_path = pending_task.get_local_path()
                if pending_path.exists():
                    completed_dir = paths.campaign(campaign).path / "queues" / "to-call" / "completed"
                    completed_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                    target_path = completed_dir / f"{ts}_{self.company_slug}.usv"
                    pending_path.rename(target_path)
                    self.app.notify("Task moved to completed.")

            # 5. Schedule Follow-up if requested and not excluded
            if should_schedule and not is_excluded_disposition:
                try:
                    cb_date = parse_follow_up_when(callback_str)
                    company.callback_at = cb_date

                    scheduled_task = ToCallTask(
                        company_slug=self.company_slug,
                        domain=company.domain or "unknown",
                        campaign_name=campaign,
                        callback_at=cb_date,
                        ack_token=None
                    )
                    scheduled_task.save()
                    self.app.notify(f"Scheduled callback for {cb_date.strftime('%Y-%m-%d %H:%M')} UTC")
                except ValueError:
                    self.app.notify(f"Invalid date: {callback_str}", severity="warning")
            else:
                company.callback_at = None

            # 6. Schedule Email Follow-up, if a template was picked - a
            # separate concept from the call re-queue above (queues/follow-up/,
            # not queues/to-call/), since more than one can be pending for
            # the same company (see FollowUpTask). Always requires a
            # template - the personal touch is added by editing the
            # rendered draft in Target Batches, not by composing from
            # scratch (Mark, 2026-09-16).
            followup_label = self.query_one("#followup_template", SearchSelect).value
            if followup_label and followup_label != NO_EMAIL_FOLLOW_UP:
                followup_template, followup_initiative = self._template_initiative_by_label[
                    followup_label
                ]
                followup_date_str = self.query_one("#followup_email_date", CocliInput).value.strip()
                try:
                    followup_date = parse_follow_up_when(followup_date_str)
                    FollowUpService(campaign).add_follow_up(
                        company_slug=self.company_slug,
                        domain=company.domain or "unknown",
                        scheduled_at=followup_date,
                        format="email",
                        template_id=followup_template,
                        initiative=followup_initiative,
                    )
                    self.app.notify(
                        f"Scheduled email follow-up ({followup_template}) for "
                        f"{followup_date.strftime('%Y-%m-%d %H:%M')} UTC"
                    )
                except ValueError:
                    self.app.notify(f"Invalid email follow-up date: {followup_date_str}", severity="warning")

            company.save()
            self.app.notify("Call logged.")
            self.dismiss(True)

        except Exception as e:
            self.app.notify(f"Failed to save call log: {e}", severity="error")

