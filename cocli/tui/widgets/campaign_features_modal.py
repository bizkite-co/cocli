from __future__ import annotations

import logging

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Label, Static

from cocli.application.campaign_service import CampaignService
from cocli.models.campaigns.campaign import Campaign
from .inputs import CocliInput

logger = logging.getLogger(__name__)


class CampaignFeaturesModal(ModalScreen[bool]):
    """A modal to view and update features on an existing campaign."""

    DEFAULT_CSS = """
    CampaignFeaturesModal {
        align: center middle;
    }
    #campaign_features_form {
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
        ("escape", "dismiss(False)", "Cancel"),
    ]

    def __init__(self, campaign: Campaign) -> None:
        super().__init__()
        self.campaign = campaign

    def compose(self) -> ComposeResult:
        promo_sites_str = ", ".join(self.campaign.promotional_sites or [])
        email_addr = (
            self.campaign.email.from_address
            if self.campaign.email
            else ""
        )
        has_video = (
            bool(self.campaign.video) or "video" in (self.campaign.workflows or [])
        )
        has_email = bool(self.campaign.email)
        has_prospecting = bool(self.campaign.prospecting) or bool(
            self.campaign.google_maps
        )

        with Container(id="campaign_features_form"):
            yield Label(
                f"MANAGE FEATURES: {self.campaign.name}", classes="modal-title"
            )

            with Vertical(id="form_fields"):
                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label(
                            "Promotional Sites (comma-separated)",
                            classes="field-label",
                        )
                        yield CocliInput(
                            value=promo_sites_str,
                            placeholder="handex.io, handterm.com",
                            id="edit_promo_sites",
                        )

                with Horizontal(classes="form-row"):
                    with Vertical(classes="field-group"):
                        yield Label("Outbound Email", classes="field-label")
                        yield CocliInput(
                            value=email_addr,
                            placeholder="mark@onehandmobilekeyboard.com",
                            id="edit_camp_email",
                        )

            yield Label("Active Features:", classes="field-label-header")
            with Horizontal(id="feature_selections_row"):
                yield Checkbox("Video Pipeline", value=has_video, id="feat_video")
                yield Checkbox("Email Outreach", value=has_email, id="feat_email")
                yield Checkbox("Prospecting / Maps", value=has_prospecting, id="feat_prospecting")

            yield Static(
                "[bold reverse] ENTER: SAVE FEATURES [/]  [dim] ESC: CANCEL [/]",
                id="modal_help",
            )

    @on(CocliInput.Submitted)
    def handle_submit(self) -> None:
        self.save_features()

    def save_features(self) -> None:
        promo_raw = self.query_one("#edit_promo_sites", CocliInput).value.strip()
        email_addr = self.query_one("#edit_camp_email", CocliInput).value.strip()
        feat_video = self.query_one("#feat_video", Checkbox).value

        service = CampaignService(self.campaign.name)
        try:
            # Update promotional sites
            sites = [s.strip() for s in promo_raw.split(",") if s.strip()]
            service.set_promotional_sites(sites)

            # Update email if provided
            if email_addr:
                service.configure_email(email_addr)

            # Enable video if checked
            if feat_video:
                service.enable_video_pipeline()

            self.app.notify(f"Updated features for '{self.campaign.name}'")
            self.dismiss(True)
        except Exception as e:
            logger.error("Failed to update features for %s: %s", self.campaign.name, e)
            self.app.notify(f"Failed to update features: {e}", severity="error")
