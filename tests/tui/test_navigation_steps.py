import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.tui.app import CocliApp
from cocli.tui.widgets.campaign_selection import CampaignSelection
from cocli.tui.widgets.campaign_detail import CampaignDetail
from conftest import wait_for_screen

@pytest.mark.asyncio
@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_navigation_to_campaign_selection(mock_get_all_campaign_dirs):
    """Test that pressing space -> a navigates to the CampaignSelection screen."""
    # Arrange
    mock_get_all_campaign_dirs.return_value = []
    app = CocliApp()

    # Act
    async with app.run_test() as driver:
        await driver.press("space", "a")
        await wait_for_screen(driver, CampaignSelection)

        # Assert
        assert isinstance(app.screen, CampaignSelection)


@patch('cocli.tui.widgets.campaign_selection.get_all_campaign_dirs')
async def test_campaign_selection_widget_sends_message(mock_get_all_campaign_dirs):
    """Test that the CampaignSelection widget sends a CampaignSelected message."""
    # Arrange
    from textual.app import App, ComposeResult

    mock_campaign_a = MagicMock(spec=Path)
    mock_campaign_a.name = 'Test Campaign'
    mock_get_all_campaign_dirs.return_value = [mock_campaign_a]

    class TestApp(App[None]):
        def __init__(self):
            super().__init__()
            self.messages = []

        def compose(self) -> ComposeResult:
            yield CampaignSelection()

        def on_campaign_selection_campaign_selected(self, message: CampaignSelection.CampaignSelected):
            self.messages.append(message)

    app = TestApp()
    async with app.run_test() as driver:
        # Act
        await driver.press("enter")

    # Assert
    assert any(isinstance(m, CampaignSelection.CampaignSelected) and m.campaign_name == 'Test Campaign' for m in app.messages)


@patch('cocli.tui.app.get_campaign_dir')
@patch('cocli.tui.app.toml.load')
def test_app_handles_campaign_selected_message(mock_toml_load, mock_get_campaign_dir):
    """Test that the app handles the CampaignSelected message and pushes the correct screen."""
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
    app.push_screen = MagicMock() # Mock the push_screen method

    # Act
    app.on_campaign_selection_campaign_selected(
        CampaignSelection.CampaignSelected(campaign_name='Test Campaign')
    )

    # Assert
    app.push_screen.assert_called_once()
    pushed_screen = app.push_screen.call_args[0][0]
    assert isinstance(pushed_screen, CampaignDetail)
    assert pushed_screen.campaign.name == 'Test Campaign'
