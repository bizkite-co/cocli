import pytest
from cocli.models.campaign import Campaign
from cocli.tui.campaign_app import CampaignApp

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

        'prospecting': {'locations': ['Test Location'], 'tools': ['test-tool'], 'queries': ['test-query']}

    })

async def test_campaign_app(campaign_fixture: Campaign):
    app = CampaignApp(campaign=campaign_fixture)
    async with app.run_test():
        assert app.query_one("DataTable").row_count == len(campaign_fixture.model_dump())
