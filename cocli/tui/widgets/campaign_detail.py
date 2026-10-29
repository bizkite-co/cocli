from __future__ import annotations

import logging
from typing import Optional

from rich.markup import escape
from rich.panel import Panel
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from cocli.models.campaigns.campaign import Campaign

logger = logging.getLogger(__name__)


class CampaignDetail(VerticalScroll):
    """A widget to display the details of a campaign."""

    can_focus = True

    BINDINGS = [
        Binding("f", "manage_features", "Features", show=True),
        Binding("a", "add_campaign", "New", show=True),
    ]

    def __init__(
        self,
        campaign: Optional[Campaign] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.campaign = campaign

    def on_mount(self) -> None:
        if self.campaign:
            self.update_detail(self.campaign)

    def action_manage_features(self) -> None:
        """Open the Manage Features modal for the selected campaign."""
        if not self.campaign:
            return
        from .campaign_features_modal import CampaignFeaturesModal

        def on_dismiss(saved: bool | None) -> None:
            if saved and self.campaign:
                try:
                    reloaded = Campaign.load(self.campaign.name)
                    self.update_detail(reloaded)
                except Exception as exc:
                    logger.error("Failed to reload campaign %s: %s", self.campaign.name, exc)

        self.app.push_screen(
            CampaignFeaturesModal(self.campaign), callback=on_dismiss
        )

    def action_add_campaign(self) -> None:
        """Open the Add Campaign modal."""
        from .campaign_add_modal import CampaignAddModal

        def on_dismiss(created_name: Optional[str]) -> None:
            if created_name:
                try:
                    from .campaign_selection import CampaignSelection
                    selection = self.app.query_one(CampaignSelection)
                    self.run_worker(selection.reload_campaigns(created_name))
                except Exception:
                    pass

        self.app.push_screen(CampaignAddModal(), callback=on_dismiss)

    def update_detail(self, campaign: Campaign) -> None:
        logger.debug(
            "update_detail called with campaign: %s",
            campaign.name if campaign else "None",
        )
        self.campaign = campaign
        self.remove_children()

        lines: list[str] = []
        # 1. Core Info
        lines.append("[b][cyan]Core Info[/][/b]")
        lines.append(f"  Name: {escape(campaign.name)}")
        lines.append(f"  Tag: {escape(campaign.tag)}")
        lines.append(f"  Domain: {escape(campaign.domain or '(none)')}")
        if campaign.promotional_sites:
            lines.append(
                f"  Promotional Sites: {escape(', '.join(campaign.promotional_sites))}"
            )
        lines.append(f"  Workflows: {escape(', '.join(campaign.workflows))}")
        lines.append("")

        # 2. Email
        if campaign.email:
            lines.append("[b][cyan]Email[/][/b]")
            lines.append(f"  From: {escape(campaign.email.from_address or '(none)')}")
            lines.append(f"  Reply-To: {escape(campaign.email.reply_to or '(none)')}")
            lines.append(f"  Backend: {escape(campaign.email.backend)}")
            lines.append("")

        # 3. Video Pipeline
        if campaign.video or "video" in campaign.workflows:
            lines.append("[b][cyan]Video Pipeline[/][/b]")
            lines.append("  Status: [green]Active[/green]")
            if campaign.video and campaign.video.transcription:
                provider = campaign.video.transcription.provider
                model = campaign.video.transcription.model
                lines.append(f"  Transcription: {escape(provider)} ({escape(model)})")
            lines.append("")

        # 4. Google Maps
        if campaign.google_maps and (campaign.google_maps.email or campaign.google_maps.one_password_path):
            lines.append("[b][cyan]Google Maps[/][/b]")
            lines.append(f"  Email: {escape(campaign.google_maps.email)}")
            lines.append(f"  1P Path: {escape(campaign.google_maps.one_password_path)}")
            lines.append("")

        # 5. Prospecting
        if campaign.prospecting and (campaign.prospecting.queries or campaign.prospecting.locations or campaign.prospecting.keywords):
            lines.append("[b][cyan]Prospecting[/][/b]")
            lines.append(f"  Keywords: {escape(', '.join(campaign.prospecting.keywords))}")
            lines.append(
                f"  Locations: {escape(', '.join(campaign.prospecting.locations or []))}"
            )
            lines.append(f"  Panning: {campaign.prospecting.panning_distance_miles} miles")
            lines.append(f"  Initial Zoom: {campaign.prospecting.initial_zoom_out_level}")

        panel = Panel(
            "\n".join(lines),
            title=f"Settings: {campaign.name}",
            subtitle="[dim]a: new campaign   f: manage features[/dim]",
            border_style="green",
        )
        self.mount(Static(panel))

    def display_error(self, title: str, message: str) -> None:
        logger.debug("display_error called with title: %s, message: %s", title, message)
        self.campaign = None
        self.remove_children()
        self.mount(
            Static(Panel(message, title=title, border_style="red"), id="error_message")
        )
