# POLICY: frictionless-data-policy-enforcement
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Checkbox, Static
from textual.containers import Container, Vertical, Horizontal
from textual import on

from cocli.models.companies.company import Company
from cocli.core.config import get_campaign
from cocli.core.text_utils import slugify
from cocli.models.campaigns.queues.gm_details import GmItemTask
from cocli.models.campaigns.queues.enrichment import EnrichmentTask
from cocli.core.paths import paths
from .inputs import CocliInput

class CompanyAddModal(ModalScreen[bool]):
    """A keyboard-driven modal form to add a new company and optionally enqueue it."""

    BINDINGS = [
        ("escape", "dismiss(False)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        campaign = get_campaign() or "default"
        
        with Container(id="add_company_form"):
            yield Label("ADD NEW COMPANY", classes="modal-title")
            
            with Vertical(id="form_fields"):
                # Row 1: Name and Campaign
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group", id="fg_name"):
                        yield Label("Company Name*", classes="field-label")
                        yield CocliInput(placeholder="Acme Corp", id="add_company_name")
                    with Vertical(classes="field-group", id="fg_campaign"):
                        yield Label("Campaign Tag", classes="field-label")
                        yield CocliInput(value=campaign, id="add_company_campaign")

                # Row 2: Domain and Email
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("Domain", classes="field-label")
                        yield CocliInput(placeholder="acme.com", id="add_company_domain")
                    with Vertical(classes="field-group"):
                        yield Label("Email", classes="field-label")
                        yield CocliInput(placeholder="hello@acme.com", id="add_company_email")

                # Row 3: Phone and Address
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("Phone", classes="field-label")
                        yield CocliInput(placeholder="555-0123", id="add_company_phone")
                    with Vertical(classes="field-group"):
                        yield Label("Street Address", classes="field-label")
                        yield CocliInput(placeholder="123 Main St", id="add_company_address")

                # Row 4: City, State, Zip (Triple Column)
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("City", classes="field-label")
                        yield CocliInput(placeholder="Anytown", id="add_company_city")
                    with Vertical(classes="field-group", id="fg_state"):
                        yield Label("State", classes="field-label")
                        yield CocliInput(placeholder="CA", id="add_company_state")
                    with Vertical(classes="field-group", id="fg_zip"):
                        yield Label("Zip", classes="field-label")
                        yield CocliInput(placeholder="90210", id="add_company_zip")

            yield Label("Add to Queues:", classes="field-label-header")
            with Horizontal(id="queue_selections_row"):
                yield Checkbox("To-Call", value=True, id="q_to_call")
                yield Checkbox("GM Details", value=False, id="q_gm_details")
                yield Checkbox("Enrichment", value=False, id="q_enrichment")

            yield Static("[bold reverse] ENTER: SAVE & CLOSE [/]  [dim] ESC: CANCEL [/]", id="modal_help")

    @on(CocliInput.Submitted)
    def handle_submit(self) -> None:
        self.add_company()

    def add_company(self) -> None:
        name = self.query_one("#add_company_name", CocliInput).value.strip()
        campaign_tag = self.query_one("#add_company_campaign", CocliInput).value.strip()
        domain = self.query_one("#add_company_domain", CocliInput).value.strip()
        email = self.query_one("#add_company_email", CocliInput).value.strip()
        phone = self.query_one("#add_company_phone", CocliInput).value.strip()
        address = self.query_one("#add_company_address", CocliInput).value.strip()
        city = self.query_one("#add_company_city", CocliInput).value.strip()
        state = self.query_one("#add_company_state", CocliInput).value.strip()
        zip_code = self.query_one("#add_company_zip", CocliInput).value.strip()
        
        if not name:
            self.app.notify("Company name is required", severity="error")
            return

        slug = slugify(name)
        from cocli.models.email_address import EmailAddress
        from cocli.models.phone import PhoneNumber
        
        try:
            # Validate fields if provided
            validated_email = None
            if email:
                try:
                    validated_email = EmailAddress(email)
                except Exception:
                    self.app.notify(f"Invalid email format: {email}", severity="warning")
            
            validated_phone = None
            if phone:
                try:
                    validated_phone = PhoneNumber.validate(phone)
                except Exception:
                    self.app.notify(f"Invalid phone format: {phone}", severity="warning")

            # 1. Create Company
            company = Company(
                name=name,
                domain=domain or None,
                slug=slug,
                email=validated_email,
                phone_1=validated_phone,
                street_address=address or None,
                city=city or None,
                state=state or None,
                zip_code=zip_code or None,
                tags=[campaign_tag] if campaign_tag else []
            )
            
            # 2. Add To-Call Tag if selected
            if self.query_one("#q_to_call", Checkbox).value:
                if "to-call" not in company.tags:
                    company.tags.append("to-call")
            
            company.save()
            self.app.notify(f"Added company: {name}")

            # 3. Handle Queues
            if campaign_tag:
                # GM Details
                if self.query_one("#q_gm_details", Checkbox).value:
                    manual_pid = f"MANUAL_{slug}"
                    gm_task = GmItemTask(
                        place_id=manual_pid, 
                        campaign_name=campaign_tag,
                        name=name, 
                        company_slug=slug
                    )
                    q_dir = paths.campaign(campaign_tag).queue("gm-details").path / "pending"
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
                            campaign_name=campaign_tag,
                            ack_token=None
                        )
                        q_dir = paths.campaign(campaign_tag).queue("enrichment").path / "pending"
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
