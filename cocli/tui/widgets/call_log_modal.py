# POLICY: frictionless-data-policy-enforcement
from datetime import datetime, UTC, timedelta
from typing import Any
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea, Static, Checkbox, Select
from textual.containers import Container, Vertical, Horizontal
from textual import on, events

from cocli.models.companies.company import Company
from cocli.models.companies.meeting import Meeting
from cocli.models.companies.call_note import CallNote
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.application.campaign_service import CampaignService
from cocli.core.config import get_campaign
from cocli.core.paths import paths
from .inputs import CocliInput

DISPOSITION_CHOICES = [
    ("Follow Up Needed", "Follow Up Needed"),
    ("Interested / Qualified", "Interested"),
    ("Not Interested", "Not Interested"),
    ("Objection: Price", "Objection: Price"),
    ("Objection: Feature Gap", "Objection: Feature Gap"),
    ("Bad Number", "Bad Number"),
]

EXCLUDING_DISPOSITIONS = {"Not Interested", "Bad Number"}


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

            yield Label("Call Disposition", classes="field-label")
            yield Select(DISPOSITION_CHOICES, value="Follow Up Needed", id="call_disposition")

            yield Label("Call Notes (VIM-ish keys supported)", classes="field-label")
            yield TextArea(id="call_notes", classes="notes-area")

            with Horizontal(id="callback_row"):
                with Vertical(classes="field-group"):
                    yield Label("Follow-up Date (YYYY-MM-DD)", classes="field-label")
                    yield CocliInput(value=default_callback, id="callback_date")
                with Vertical(classes="field-group"):
                    yield Label("Schedule?", classes="field-label")
                    yield Checkbox("Re-queue for callback", value=True, id="should_schedule")

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
        should_schedule = self.query_one("#should_schedule", Checkbox).value
        disposition_val = self.query_one("#call_disposition", Select).value
        if disposition_val is Select.BLANK or not disposition_val:
            disposition = "Follow Up Needed"
        else:
            disposition = str(disposition_val)

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

            # 3. Handle Exclusions if disposition is not interested / bad number
            is_excluded_disposition = disposition in EXCLUDING_DISPOSITIONS
            if is_excluded_disposition:
                CampaignService(campaign).add_exclude(self.company_slug, reason=disposition)
                self.app.notify(f"Added exclusion for {self.company_slug} ({disposition})")

            # 4. Queue Lifecycle: Move from PENDING to COMPLETED
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
            if should_schedule and callback_str and not is_excluded_disposition:
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

