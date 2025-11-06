import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.campaign_detail import CampaignDetail
from textual.widgets import Static
from conftest import wait_for_widget, wait_for_campaign_detail_update

@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
@patch('cocli.tui.app.toml.load')
@patch('cocli.tui.app.get_campaign_dir')
async def test_valid_campaign_selection(mock_get_campaign_dir, mock_toml_load, mock_get_all_campaign_dirs):
    """Test that selecting a valid campaign shows the CampaignDetail widget."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'Test Campaign'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_a]

    mock_get_campaign_dir.return_value.exists.return_value = True
    mock_toml_load.return_value = {
        'campaign': {
            'name': 'Test Campaign',
            'tag': 'test',
            'domain': 'example.com',
            'company-slug': 'test-company',
            'workflows': []
        },
        'import': {'format': 'csv'},
        'google_maps': {'email': 'test@example.com', 'one_password_path': 'path/to/password'},
        'prospecting': {'locations': [], 'tools': [], 'queries': []}
    }

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        await wait_for_widget(driver, CampaignSelection)
        await driver.press("enter")
        await driver.pause()
        await driver.pause()
        await driver.pause() # Give the app time to process events
        detail_widget = await wait_for_widget(driver, CampaignDetail)
        await wait_for_campaign_detail_update(detail_widget)

        # Assert
        assert detail_widget.campaign is not None
        assert detail_widget.campaign.name == "Test Campaign"

@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
@patch('cocli.tui.app.toml.load')
@patch('cocli.tui.app.get_campaign_dir')
async def test_invalid_campaign_selection(mock_get_campaign_dir, mock_toml_load, mock_get_all_campaign_dirs):
    """Test that selecting an invalid campaign shows the ErrorScreen."""
    # Arrange
    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'Test Campaign'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_a]

    mock_get_campaign_dir.return_value.exists.return_value = True
    mock_toml_load.return_value = {
        'campaign': {
            'name': 'Test Campaign',
        }
    }

    app = CocliApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("space", "a")
        await wait_for_widget(driver, CampaignSelection)
        await driver.press("enter")
        await driver.pause()
        await driver.pause()
        await driver.pause() # Give the app time to process events
        detail_widget = await wait_for_widget(driver, CampaignDetail)

        # Assert
        assert detail_widget.campaign is None # No valid campaign loaded
        error_static = await wait_for_widget(driver, Static, parent_widget=detail_widget)
        assert "Invalid Campaign: Test Campaign" in str(error_static)
