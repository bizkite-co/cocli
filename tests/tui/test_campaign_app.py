import pytest
import asyncio
import toml
from cocli.models.campaign import Campaign
from cocli.tui.campaign_app import CampaignScreen
from cocli.core.config import get_campaign_dir, get_campaigns_dir

from textual.app import App

class _TestApp(App[None]):
    """A test app to host CampaignScreen."""
    def __init__(self, campaign: Campaign):
        super().__init__()
        self.campaign = campaign

    def on_mount(self) -> None:
        self.push_screen(CampaignScreen(campaign=self.campaign))

@pytest.fixture
def campaign_fixture() -> Campaign:
    return Campaign.model_validate({
        'name': 'Test Campaign',
        'tag': 'test',
        'domain': 'test.com',
        'company-slug': 'test-company',
        'workflows': ['test-workflow'],
        'import': {'format': 'csv'},
        'google_maps': {'email': 'test@test.com', 'one_password_path': 'op://test/test/password'},
        'prospecting': {'locations': ['Test Location'], 'tools': ['test-tool'], 'queries': ['test-query']},
        'aws': {'profile': 'test-profile', 'hosted-zone-id': 'test-zone'}
    })

@pytest.fixture(autouse=True)
def setup_campaign_dir(campaign_fixture: Campaign):
    campaigns_dir = get_campaigns_dir()
    test_campaign_dir = campaigns_dir / campaign_fixture.name
    test_campaign_dir.mkdir(parents=True, exist_ok=True)
    initial_config_path = test_campaign_dir / "config.toml"
    with open(initial_config_path, "w") as f:
        toml.dump(campaign_fixture.model_dump(by_alias=True), f)
    yield
    # Teardown: Clean up the created directory
    import shutil
    if test_campaign_dir.exists():
        shutil.rmtree(test_campaign_dir)

async def test_campaign_app(campaign_fixture: Campaign, setup_campaign_dir):
    app = _TestApp(campaign=campaign_fixture) # Changed to _TestApp
    async with app.run_test():
        # The CampaignScreen is pushed on mount, so we query for it.
        campaign_screen = app.screen # Changed to app.screen
        assert campaign_screen.query_one("DataTable").row_count == len(Campaign.model_fields)

async def test_edit_multiple_cells(campaign_fixture: Campaign):
    # Ensure the campaign directory exists for the test
    campaigns_dir = get_campaigns_dir()
    test_campaign_dir = campaigns_dir / campaign_fixture.name
    test_campaign_dir.mkdir(parents=True, exist_ok=True)

    # Create an initial config.toml file for the campaign
    initial_config_path = test_campaign_dir / "config.toml"
    with open(initial_config_path, "w") as f:
        toml.dump(campaign_fixture.model_dump(by_alias=True), f)

    app = _TestApp(campaign=campaign_fixture) # Changed to _TestApp
    async with app.run_test() as pilot:
        # The CampaignScreen is pushed on mount, so we query for it.
        campaign_screen = app.screen # Changed to app.screen

        # Edit the first cell
        await pilot.press("e")
        await asyncio.sleep(0.1)
        await pilot.press("ctrl+a", "delete")
        await asyncio.sleep(0.1)
        await pilot.press("T", "e", "s", "t", "1")
        await asyncio.sleep(0.1)
        await pilot.press("ctrl+s")

        # Move to the next cell and edit it
        await pilot.press("j")
        await asyncio.sleep(0.1)
        await pilot.press("e")
        await asyncio.sleep(0.1)
        await pilot.press("ctrl+a", "delete")
        await asyncio.sleep(0.1)
        await pilot.press("T", "e", "s", "t", "2")
        await asyncio.sleep(0.1)
        await pilot.press("ctrl+s")

        # Reload the campaign from disk to verify changes
        campaign_path = get_campaign_dir(campaign_fixture.name)
        assert campaign_path is not None
        reloaded_campaign_data = toml.load(campaign_path / "config.toml")
        reloaded_campaign = Campaign.model_validate(reloaded_campaign_data)

        assert reloaded_campaign.name == campaign_screen.campaign.name # Changed app.campaign.name to campaign_screen.campaign.name
        assert reloaded_campaign.tag == campaign_screen.campaign.tag # Changed app.campaign.tag to campaign_screen.campaign.tag