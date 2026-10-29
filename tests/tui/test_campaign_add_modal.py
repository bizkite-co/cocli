from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Checkbox

from cocli.models.campaigns.campaign import Campaign
from cocli.tui.widgets.campaign_add_modal import CampaignAddModal
from cocli.tui.widgets.campaign_detail import CampaignDetail
from cocli.tui.widgets.campaign_features_modal import CampaignFeaturesModal
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.inputs import CocliInput


class ModalTestApp(App[Any]):
    def compose(self) -> ComposeResult:
        yield CampaignSelection()
        yield CampaignDetail()


@pytest.mark.asyncio
async def test_campaign_add_modal_creates_campaign() -> None:
    app = ModalTestApp()
    async with app.run_test() as driver:
        modal = CampaignAddModal()
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#add_camp_name", CocliInput).value = "Handex"
        modal.query_one("#add_camp_slug", CocliInput).value = "handex"
        modal.query_one("#add_camp_domain", CocliInput).value = "handex.io"
        modal.query_one("#add_camp_email", CocliInput).value = (
            "mark@onehandmobilekeyboard.com"
        )
        modal.query_one("#add_camp_promotional_sites", CocliInput).value = (
            "handex.io, handterm.com"
        )
        modal.query_one("#feat_video", Checkbox).value = True
        modal.query_one("#feat_email", Checkbox).value = True
        modal.query_one("#feat_prospecting", Checkbox).value = False

        with patch(
            "cocli.application.campaign_service.CampaignService.create_campaign"
        ) as mock_create:
            modal.create_campaign()
            mock_create.assert_called_once_with(
                name="Handex",
                company="handex",
                domain="handex.io",
                promotional_sites=["handex.io", "handterm.com"],
                email="mark@onehandmobilekeyboard.com",
                enable_video=True,
                enable_prospecting=False,
            )


@pytest.mark.asyncio
async def test_campaign_features_modal_updates_campaign() -> None:
    camp = Campaign.model_validate(
        {
            "name": "Handex",
            "tag": "handex",
            "domain": "handex.io",
            "company-slug": "handex",
            "promotional-sites": ["handex.io"],
            "workflows": ["outreach"],
        }
    )

    app = ModalTestApp()
    async with app.run_test() as driver:
        modal = CampaignFeaturesModal(camp)
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#edit_promo_sites", CocliInput).value = (
            "handex.io, handterm.com"
        )
        modal.query_one("#edit_camp_email", CocliInput).value = (
            "mark@onehandmobilekeyboard.com"
        )
        modal.query_one("#feat_video", Checkbox).value = True

        with patch(
            "cocli.application.campaign_service.CampaignService.set_promotional_sites"
        ) as mock_sites, patch(
            "cocli.application.campaign_service.CampaignService.configure_email"
        ) as mock_email, patch(
            "cocli.application.campaign_service.CampaignService.enable_video_pipeline"
        ) as mock_video:
            modal.save_features()
            mock_sites.assert_called_once_with(["handex.io", "handterm.com"])
            mock_email.assert_called_once_with("mark@onehandmobilekeyboard.com")
            mock_video.assert_called_once()


@pytest.mark.asyncio
async def test_campaign_detail_renders_features() -> None:
    camp = Campaign.model_validate(
        {
            "name": "Handex",
            "tag": "handex",
            "domain": "handex.io",
            "company-slug": "handex",
            "promotional-sites": ["handex.io", "handterm.com"],
            "workflows": ["video"],
            "email": {
                "backend": "m365",
                "from_address": "mark@onehandmobilekeyboard.com",
            },
        }
    )

    app = ModalTestApp()
    async with app.run_test() as driver:
        detail = app.query_one(CampaignDetail)
        detail.update_detail(camp)
        await driver.pause()
        assert len(detail.children) > 0
