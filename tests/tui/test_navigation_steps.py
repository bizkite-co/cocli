import pytest
from unittest.mock import patch

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.campaign_detail import CampaignDetail
from conftest import wait_for_widget, wait_for_campaign_detail_update

@pytest.mark.asyncio
async def test_valid_campaign_selection(tmp_path, monkeypatch):
    """Test that selecting a valid campaign shows the CampaignDetail widget."""
    # Arrange
    monkeypatch.setenv("COCLI_DATA_HOME", str(tmp_path))
    campaign_dir = tmp_path / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)
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
        await wait_for_widget(driver, CampaignSelection, selector=None)
        await driver.press("enter")
        await driver.pause()
        await driver.pause()
        await driver.pause() # Give the app time to process events
        detail_widget = await wait_for_widget(driver, CampaignDetail, selector=None)
        await wait_for_campaign_detail_update(detail_widget)

        # Assert
        assert detail_widget.campaign is not None
        assert detail_widget.campaign.name == "Test Campaign"

@pytest.mark.asyncio
@patch("cocli.tui.widgets.campaign_detail.CampaignDetail.display_error")
async def test_invalid_campaign_selection(mock_display_error, tmp_path, monkeypatch):
        """Test that selecting an invalid campaign shows the ErrorScreen."""
        # Arrange
        monkeypatch.setenv("COCLI_DATA_HOME", str(tmp_path))
        campaign_dir = tmp_path / "campaigns" / "invalid-campaign"
        campaign_dir.mkdir(parents=True)
        (campaign_dir / "config.toml").write_text("""
[campaign]
name = "Invalid Campaign"
""")

        app = CocliApp()

        async with app.run_test() as driver:
            # Act
            await driver.press("space", "a")
            await wait_for_widget(driver, CampaignSelection, selector=None)
            await driver.press("enter")
            await driver.pause()
            await driver.pause()
            await driver.pause() # Give the app time to process events
            detail_widget = await wait_for_widget(driver, CampaignDetail, selector=None)

            # Assert
            assert detail_widget.campaign is None # No valid campaign loaded
            await driver.pause(0.1)
            mock_display_error.assert_called_once()
            args, kwargs = mock_display_error.call_args
            assert "Invalid Campaign: invalid-campaign" in args[0]
