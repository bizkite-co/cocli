import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from cocli.services.enrichment_service.main import app
from cocli.models.website import Website

client = TestClient(app)

@pytest.fixture
def mock_playwright():
    with patch("cocli.services.enrichment_service.main.async_playwright") as mock:
        # Mock the context manager
        mock_context = AsyncMock()
        mock.return_value = mock_context
        
        # Mock browser
        mock_browser = AsyncMock()
        mock_context.__aenter__.return_value = MagicMock(chromium=MagicMock(launch=AsyncMock(return_value=mock_browser)))
        
        yield mock_browser

@pytest.fixture
def mock_enrich_company_website():
    with patch("cocli.services.enrichment_service.main.enrich_company_website", new_callable=AsyncMock) as mock:
        # Return a dummy Website object
        mock.return_value = Website(url="http://example.com", domain="example.com")
        yield mock

def test_enrich_domain_stateless_success(mock_playwright, mock_enrich_company_website):
    """
    Test that the enrichment endpoint works with provided parameters
    even when local config is missing (stateless mode).
    """
    payload = {
        "domain": "example.com",
        "campaign_name": "test-campaign",
        "aws_profile_name": "test-profile",
        "company_slug": "test-company"
    }
    
    response = client.post("/enrich", json=payload)
    
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"
    
    # Verify that enrich_company_website was called
    mock_enrich_company_website.assert_called_once()
    
    # Inspect the Campaign object passed to enrich_company_website
    _, kwargs = mock_enrich_company_website.call_args
    campaign = kwargs.get("campaign")
    assert campaign is not None
    assert campaign.name == "test-campaign"
    assert campaign.aws_profile_name == "test-profile"
    assert campaign.company_slug == "test-company"

def test_enrich_domain_missing_config_and_params(mock_playwright):
    """
    Test that it fails with 404 if config is missing and params are insufficient.
    """
    payload = {
        "domain": "example.com",
        "campaign_name": "non-existent-campaign"
        # Missing aws_profile_name and company_slug
    }
    
    response = client.post("/enrich", json=payload)
    
    assert response.status_code == 404
    assert "configuration not found and params missing" in response.json()["detail"]
