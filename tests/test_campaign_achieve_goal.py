from typer.testing import CliRunner
from cocli.main import app
import pytest

runner = CliRunner()

async def async_generator():
    yield "mock_prospect_data"

@pytest.fixture
def mock_achieve_goal_dependencies(mocker):
    mocker.patch("cocli.commands.campaign.get_coordinates_from_city_state", return_value={"latitude": 40.7596, "longitude": -111.8868})
    mocker.patch("cocli.commands.campaign.scrape_google_maps", return_value=async_generator())
    mocker.patch("cocli.commands.campaign.import_prospect", return_value=type('obj', (object,), {'name': 'mock_company', 'domain': 'mock.com'}))
    mocker.patch("cocli.commands.campaign.enrich_company_website", return_value=type('obj', (object,), {'email': 'test@example.com'}))
    mocker.patch("httpx.Client.get", return_value=type('obj', (object,), {'raise_for_status': lambda: None}))
    mocker.patch("httpx.AsyncClient.post", return_value=type('obj', (object,), {'raise_for_status': lambda: None, 'json': lambda: {"email": "test@example.com"}}))

def test_achieve_goal(mock_achieve_goal_dependencies):
    result = runner.invoke(app, ["campaign", "achieve-goal", "--emails", "1"], catch_exceptions=False)
    assert result.exit_code == 0
