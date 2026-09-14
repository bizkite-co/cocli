# POLICY: frictionless-data-policy-enforcement
from datetime import datetime, UTC, timedelta
from typing import Any
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea, Static
from textual.containers import Container
from textual import on, events

from cocli.models.companies.company import Company
from cocli.models.companies.meeting import Meeting
from cocli.models.companies.call_note import CallNote
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.application.to_call_disposition_service import mark_to_call_invalid
from cocli.core.config import get_campaign
from cocli.core.paths import paths
from .inputs import CocliInput
from .search_select import SearchSelect

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
        ("escape", "dismiss(False)", "Cancel"),
        ("ctrl+s", "save_call", "Save & Close"),
    ]

    def __init__(self, company_slug: str, phone: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.company_slug = company_slug
        self.phone = phone

    def compose(self) -> ComposeResult:
        # Default callback to 7 days from now
        default_callback = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d")

        with Container(id="call_log_form"):
            yield Label(f"LOGGING CALL: [bold cyan]{self.company_slug}[/]", id="call_modal_title")
            yield Label(f"Phone: {self.phone}", classes="modal-subtitle")

            yield Label("Call Disposition (type to filter, Enter to pick)", classes="field-label")
            yield SearchSelect(DISPOSITION_CHOICES, initial_value="Follow Up Needed", id="call_disposition")

            yield Label("Call Notes (VIM-ish keys supported)", classes="field-label")
            yield TextArea(id="call_notes", classes="notes-area")

            yield Label("Follow-up Date (YYYY-MM-DD, blank = don't re-queue)", classes="field-label")
            yield CocliInput(value=default_callback, id="callback_date")

            yield Static("[bold reverse] CTRL+S: SAVE & REMOVE FROM LIST [/]  [dim] ESC: CANCEL [/]", id="modal_help")

    def on_mount(self) -> None:
        self.query_one("#call_notes", TextArea).focus()

    @on(events.Key)
    def handle_keys(self, event: events.Key) -> None:
        if event.key == "ctrl+s":
            self.save_call()

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
            meeting.to_file(meetings_dir)

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
                    cb_date = datetime.strptime(callback_str, "%Y-%m-%d").replace(tzinfo=UTC)
                    company.callback_at = cb_date

                    scheduled_task = ToCallTask(
                        company_slug=self.company_slug,
                        domain=company.domain or "unknown",
                        campaign_name=campaign,
                        callback_at=cb_date,
                        ack_token=None
                    )
                    scheduled_task.save()
                    self.app.notify(f"Scheduled callback for {callback_str}")
                except ValueError:
                    self.app.notify(f"Invalid date format: {callback_str}", severity="warning")

            company.save()
            self.app.notify("Call logged.")
            self.dismiss(True)

        except Exception as e:
            self.app.notify(f"Failed to save call log: {e}", severity="error")

