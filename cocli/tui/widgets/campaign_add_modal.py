from __future__ import annotations

import logging
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Label, Static

from cocli.application.campaign_service import CampaignService
from cocli.core.text_utils import slugify

from .inputs import CocliInput

logger = logging.getLogger(__name__)


class CampaignAddModal(ModalScreen[Optional[str]]):
    """A keyboard-driven modal form to create a new campaign with customizable features."""

    DEFAULT_CSS = """
    CampaignAddModal {
        align: center middle;
    }
    #add_campaign_form {
        width: 76;
        height: auto;
        max-height: 90%;
        background: #111111;
        border: double #00ff00;
        padding: 1 2;
    }
    .modal-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: #00ff00;
        margin-bottom: 1;
    }
    .form-row {
        height: auto;
        margin-bottom: 1;
    }
    .field-group {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    .field-label {
        color: #aaaaaa;
        text-style: bold;
    }
    .field-label-header {
        margin-top: 1;
        color: #aaaaaa;
        text-style: bold;
    }
    #feature_selections_row {
        height: auto;
        margin-bottom: 1;
    }
    #feature_selections_row Checkbox {
        margin-right: 2;
    }
    #modal_help {
        content-align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss(None)", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="add_campaign_form"):
            yield Label("CREATE NEW CAMPAIGN", classes="modal-title")

            with Vertical(id="form_fields"):
                # Row 1: Campaign Name and Company Slug
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("Campaign Name*", classes="field-label")
                        yield CocliInput(placeholder="Handex", id="add_camp_name")
                    with Vertical(classes="field-group"):
                        yield Label("Company Slug", classes="field-label")
                        yield CocliInput(placeholder="handex", id="add_camp_slug")

                # Row 2: Primary Domain & Outbound Email
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("Primary Domain", classes="field-label")
                        yield CocliInput(placeholder="handex.io", id="add_camp_domain")
                    with Vertical(classes="field-group"):
                        yield Label("Outbound Email", classes="field-label")
                        yield CocliInput(
                            placeholder="mark@onehandmobilekeyboard.com",
                            id="add_camp_email",
                        )

                # Row 3: Promotional Sites (Comma-separated)
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label(
                            "Promotional Sites (comma-separated)",
                            classes="field-label",
                        )
                        yield CocliInput(
                            placeholder="handex.io, handterm.com",
                            id="add_camp_promotional_sites",
                        )

            yield Label("Enable Features:", classes="field-label-header")
            with Horizontal(id="feature_selections_row"):
                yield Checkbox("Video Pipeline", value=True, id="feat_video")
                yield Checkbox("Email Outreach", value=True, id="feat_email")
                yield Checkbox("Prospecting / Maps", value=False, id="feat_prospecting")

            yield Static(
                "[bold reverse] ENTER: CREATE CAMPAIGN [/]  [dim] ESC: CANCEL [/]",
                id="modal_help",
            )

    @on(CocliInput.Submitted)
    def handle_submit(self) -> None:
        self.create_campaign()

    def create_campaign(self) -> None:
        name = self.query_one("#add_camp_name", CocliInput).value.strip()
        slug_input = self.query_one("#add_camp_slug", CocliInput).value.strip()
        domain = self.query_one("#add_camp_domain", CocliInput).value.strip()
        email = self.query_one("#add_camp_email", CocliInput).value.strip()
        promo_raw = self.query_one(
            "#add_camp_promotional_sites", CocliInput
        ).value.strip()

        feat_video = self.query_one("#feat_video", Checkbox).value
        feat_email = self.query_one("#feat_email", Checkbox).value
        feat_prospecting = self.query_one("#feat_prospecting", Checkbox).value

        if not name:
            self.app.notify("Campaign name is required", severity="error")
            return

        company_slug = slug_input or slugify(name)
        promotional_sites = [
            s.strip() for s in promo_raw.split(",") if s.strip()
        ] if promo_raw else ([domain] if domain else [])

        try:
            path = CampaignService.create_campaign(
                name=name,
                company=company_slug,
                domain=domain or None,
                promotional_sites=promotional_sites or None,
                email=email if (email and feat_email) else None,
                enable_video=feat_video,
                enable_prospecting=feat_prospecting,
            )
            campaign_tag = slugify(name)
            self.app.notify(f"Created campaign '{name}' at {path.name}")
            self.dismiss(campaign_tag)
        except Exception as e:
            logger.error("Failed to create campaign %s: %s", name, e)
            self.app.notify(f"Failed to create campaign: {e}", severity="error")
