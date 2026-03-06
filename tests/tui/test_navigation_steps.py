import pytest
import asyncio
from unittest.mock import patch

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.campaign_detail import CampaignDetail
from conftest import wait_for_widget

@pytest.mark.asyncio
async def test_valid_campaign_selection(mock_cocli_env):
    """Test that selecting a valid campaign shows the CampaignDetail widget."""
    # Arrange
    campaign_dir = mock_cocli_env / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True, exist_ok=True)
    (campaign_dir / "config.toml").write_text("""
[campaign]
name = "Test Campaign"
tag = "test"
domain = "example.com"
company-slug = "test-company"
workflows = []

[import]
format = "csv"

[google_maps]
email = "test@example.com"
one_password_path = "path/to/password"

[prospecting]
locations = []
tools = []
queries = []
""")

    app = CocliApp()

    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        await wait_for_widget(driver, CampaignSelection, selector="#sidebar_campaigns")

        # NAVIGATION FIX: Highlight an item first to trigger the detail update
        await driver.press("j")
        await driver.pause(0.2)
        await driver.press("k")
        await driver.pause(0.2)

        await driver.press("enter")
        await driver.pause(0.5)

        detail_widget = await wait_for_widget(driver, CampaignDetail, selector="#campaign-detail")
        assert detail_widget.visible is True

@pytest.mark.asyncio
@patch("cocli.tui.widgets.campaign_detail.CampaignDetail.display_error")
async def test_invalid_campaign_selection(mock_display_error, mock_cocli_env):
        """Test that selecting an invalid campaign shows the ErrorScreen."""
        # Arrange
        campaign_dir = mock_cocli_env / "campaigns" / "invalid-campaign"
        campaign_dir.mkdir(parents=True, exist_ok=True)
        (campaign_dir / "config.toml").write_text("""
[campaign]
name = "Invalid Campaign"
""")

        app = CocliApp()

        async with app.run_test() as driver:
            # Act
            await driver.press("space", "a")
            await wait_for_widget(driver, CampaignSelection, selector="#sidebar_campaigns")

            # Trigger highlight to trigger the error display
            await driver.press("j")
            await driver.pause(0.2)
            await driver.press("k")
            await driver.pause(0.2)

            await driver.press("enter")
            await driver.pause(0.5)

            # Check if error display was called
            # Wait a bit for async calls
            await asyncio.sleep(0.1)
            mock_display_error.assert_called_once()
            args, kwargs = mock_display_error.call_args
            assert "Error Loading Campaign" in args[0]
            assert "Invalid Campaign: invalid-campaign" in args[1]
