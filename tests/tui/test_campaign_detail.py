import pytest
from unittest.mock import patch

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.campaign_detail import CampaignDetail
from conftest import wait_for_screen

@pytest.mark.asyncio
@patch('cocli.tui.app.toml.load')
@patch('cocli.tui.app.get_campaign_dir')
async def test_campaign_selection_shows_detail_view(mock_get_campaign_dir, mock_toml_load):
    """Test that selecting a campaign shows the CampaignDetail screen."""
    # Arrange
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
        app.on_campaign_selection_campaign_selected(
            CampaignSelection.CampaignSelected(campaign_name='Test Campaign')
        )
        await driver.wait_for_animation()

        # Assert
        campaign_detail_screen = await wait_for_screen(driver, CampaignDetail)
        assert isinstance(campaign_detail_screen, CampaignDetail)