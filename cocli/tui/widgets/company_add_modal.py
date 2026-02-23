# POLICY: frictionless-data-policy-enforcement
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Input, Button, Checkbox
from textual.containers import Container, Vertical, Horizontal
from textual import on

from cocli.models.companies.company import Company
from cocli.core.config import get_campaign
from cocli.core.text_utils import slugify
from cocli.models.campaigns.queues.gm_details import GmItemTask
from cocli.models.campaigns.queues.enrichment import EnrichmentTask
from cocli.core.paths import paths

class CompanyAddModal(ModalScreen[bool]):
    """A modal form to add a new company and optionally enqueue it."""

    def compose(self) -> ComposeResult:
        campaign = get_campaign() or "default"
        
        with Container(id="add_company_form"):
            yield Label(f"[bold]ADD NEW COMPANY[/bold] (Campaign: {campaign})", classes="modal-title")
            
            yield Label("Company Name", classes="input-label")
            yield Input(placeholder="e.g. Acme Corp", id="add_company_name")
            
            yield Label("Domain (Optional)", classes="input-label")
            yield Input(placeholder="e.g. acme.com", id="add_company_domain")

            yield Label("Add to Queues:", classes="input-label")
            with Vertical(id="queue_selections"):
                yield Checkbox("To-Call Queue", value=True, id="q_to_call")
                yield Checkbox("GM Details Queue", value=False, id="q_gm_details")
                yield Checkbox("Enrichment Queue", value=False, id="q_enrichment")

            with Horizontal(id="modal_buttons"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Add Company", variant="primary", id="add_btn")

    @on(Button.Pressed, "#cancel_btn")
    def cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#add_btn")
    @on(Input.Submitted)
    def add_company(self) -> None:
        name = self.query_one("#add_company_name", Input).value.strip()
        domain = self.query_one("#add_company_domain", Input).value.strip()
        
        if not name:
            self.app.notify("Company name is required", severity="error")
            return

        campaign = get_campaign()
        slug = slugify(name)
        
        try:
            # 1. Create Company
            company = Company(
                name=name,
                domain=domain or None,
                slug=slug,
                tags=[campaign] if campaign else []
            )
            
            # 2. Add To-Call Tag if selected
            if self.query_one("#q_to_call", Checkbox).value:
                if "to-call" not in company.tags:
                    company.tags.append("to-call")
            
            company.save()
            self.app.notify(f"Added company: {name}")

            # 3. Handle Queues
            if campaign:
                # GM Details
                if self.query_one("#q_gm_details", Checkbox).value:
                    manual_pid = f"MANUAL_{slug}"
                    gm_task = GmItemTask(
                        place_id=manual_pid, 
                        campaign_name=campaign,
                        name=name, 
                        company_slug=slug
                    )
                    q_dir = paths.campaign(campaign).queue("gm-details").path / "pending"
                    q_dir.mkdir(parents=True, exist_ok=True)
                    import json
                    with open(q_dir / f"{slug}.json", "w") as f:
                        json.dump(gm_task.model_dump(mode="json"), f)
                    self.app.notify("Enqueued in gm-details")

                # Enrichment
                if self.query_one("#q_enrichment", Checkbox).value:
                    if domain:
                        e_task = EnrichmentTask(
                            domain=domain,
                            company_slug=slug,
                            campaign_name=campaign,
                            ack_token=None
                        )
                        q_dir = paths.campaign(campaign).queue("enrichment").path / "pending"
                        q_dir.mkdir(parents=True, exist_ok=True)
                        import json
                        with open(q_dir / f"{slug}.json", "w") as f:
                            json.dump(e_task.model_dump(mode="json"), f)
                        self.app.notify("Enqueued in enrichment")
                    else:
                        self.app.notify("Domain required for enrichment queue", severity="warning")

            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Failed to add company: {e}", severity="error")
