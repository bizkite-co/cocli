from cocli.models.google_maps_prospect import GoogleMapsProspect
from typer.testing import CliRunner
from cocli.main import app
import pytest
from unittest.mock import AsyncMock, MagicMock

runner = CliRunner()

async def async_generator():
    mock_google_maps_data = GoogleMapsProspect(
        Name="Mock Company",
        Place_ID="mock_place_id",
        Website="mock.com",
        Latitude=0.0,
        Longitude=0.0,
        GMB_URL="mock.gmb.url"
    )
    yield mock_google_maps_data

@pytest.fixture
def mock_achieve_goal_dependencies(mocker, tmp_path):
    campaign_name = "test-campaign"
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)
    # ADDED: Create the scraped_data directory
    (tmp_path / "scraped_data").mkdir(parents=True, exist_ok=True) # <--- Added this line
    config_path = campaign_dir / "config.toml"
    config_content = """
[campaign]
name = "test-campaign"

[prospecting]
locations = ["New York"]
queries = ["software company"]
"""
    config_path.write_text(config_content)

    mocker.patch("cocli.core.config.get_campaign", return_value=campaign_name)
    mocker.patch("cocli.commands.campaign.prospecting.get_campaign", return_value=campaign_name)
    mocker.patch("cocli.core.config.get_campaign_dir", return_value=campaign_dir)
    mocker.patch("cocli.commands.campaign.prospecting.get_campaign_dir", return_value=campaign_dir)
    mocker.patch("cocli.core.config.get_cocli_base_dir", return_value=tmp_path)
    # Patched in the manager now
    mocker.patch("cocli.core.prospects_csv_manager.get_campaign_scraped_data_dir", return_value=tmp_path / "scraped_data")
    mocker.patch("cocli.core.config.get_companies_dir", return_value=tmp_path / "companies")
    mocker.patch("cocli.commands.campaign.prospecting.get_companies_dir", return_value=tmp_path / "companies")

    mocker.patch("cocli.core.enrichment_service_utils.ensure_enrichment_service_ready", return_value=None)
    mocker.patch("cocli.commands.campaign.prospecting.ensure_enrichment_service_ready", return_value=None, create=True)

    # Mock the entire async_playwright context manager
    mock_playwright_manager = MagicMock()
    mock_playwright_manager.__aenter__.return_value = AsyncMock(
        chromium=AsyncMock(
            launch=AsyncMock(
                return_value=AsyncMock(
                    close=AsyncMock()
                )
            )
        )
    )
    mock_playwright_manager.__aexit__.return_value = None
    mocker.patch("cocli.commands.campaign.prospecting.async_playwright", return_value=mock_playwright_manager)

    mocker.patch("cocli.core.geocoding.get_coordinates_from_city_state", return_value={"latitude": 40.7596, "longitude": -111.8868})
    mocker.patch("cocli.scrapers.google_maps.scrape_google_maps", return_value=async_generator())
    mocker.patch("cocli.commands.campaign.prospecting.scrape_google_maps", return_value=async_generator())
    mocker.patch("cocli.models.company.Company.get_all", return_value=[]) # <--- Added this line
    mocker.patch("cocli.core.importing.import_prospect", return_value=type('obj', (object,), {'name': 'mock_company', 'domain': 'mock.com', 'slug': 'mock-company', 'email': None}))
    mocker.patch("cocli.commands.campaign.prospecting.import_prospect", return_value=type('obj', (object,), {'name': 'mock_company', 'domain': 'mock.com', 'slug': 'mock-company', 'email': None}))

    mock_website = MagicMock()
    mock_website.email = "test@example.com"
    mock_website.model_dump.return_value = {
        "email": "test@example.com", 
        "url": "http://example.com", 
        "domain": "example.com",
        "company_name": "Test Company"
    }
    mocker.patch("cocli.core.enrichment.enrich_company_website", new_callable=AsyncMock, return_value=mock_website)
    mocker.patch("cocli.commands.campaign.prospecting.enrich_company_website", new_callable=AsyncMock, return_value=mock_website)

    mocker.patch("httpx.Client.get", return_value=MagicMock(raise_for_status=MagicMock()))

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"email": "test@example.com", "url": "mock.com"}
    mocker.patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    )

def test_achieve_goal(mock_achieve_goal_dependencies):
    result = runner.invoke(app, ["campaign", "achieve-goal", "--emails", "1"], catch_exceptions=False)
    assert result.exit_code == 0
