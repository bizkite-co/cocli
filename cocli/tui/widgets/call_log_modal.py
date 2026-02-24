# POLICY: frictionless-data-policy-enforcement
from datetime import datetime, UTC, timedelta
from typing import Any
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea, Static, Checkbox
from textual.containers import Container, Vertical, Horizontal
from textual import on, events

from cocli.models.companies.company import Company
from cocli.models.companies.meeting import Meeting
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.core.config import get_campaign
from cocli.core.paths import paths
from .inputs import CocliInput

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
        
        try:
            company = Company.get(self.company_slug)
            if not company:
                self.app.notify("Company not found", severity="error")
                return

            campaign = get_campaign() or "default"

            # 1. Log the Meeting
            meeting = Meeting(
                title=f"Logged Call to {self.phone}",
                type="phone-call",
                content=notes or "No notes provided."
            )
            meetings_dir = paths.companies.entry(self.company_slug).path / "meetings"
            meeting.to_file(meetings_dir)

            # 2. Queue Lifecycle: Move from PENDING to COMPLETED
            # We don't remove the tag anymore, as it's decoupled.
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
                # Move and rename to .usv with timestamp for uniqueness in completed
                ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                target_path = completed_dir / f"{ts}_{self.company_slug}.usv"
                pending_path.rename(target_path)
                self.app.notify("Task moved to completed.")

            # 3. Schedule Follow-up if requested
            if should_schedule and callback_str:
                try:
                    cb_date = datetime.strptime(callback_str, "%Y-%m-%d").replace(tzinfo=UTC)
                    company.callback_at = cb_date
                    
                    # Create sharded USV task marker
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
