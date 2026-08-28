import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from cocli.services.enrichment_service.main import app
from cocli.models.companies.website import Website

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

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

def test_enrich_domain_stateless_success(client, mock_playwright, mock_enrich_company_website):
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
    assert campaign.aws is not None
    assert campaign.aws.profile == "test-profile"
    assert campaign.company_slug == "test-company"

    # The actual bug this whole test file missed: the endpoint used to
    # always derive the Company's slug from the raw domain
    # (Company(slug=request.domain)), ignoring company_slug entirely -
    # creating an orphaned "example-com" duplicate alongside the real
    # "test-company" record. Assert on the Company object itself, not
    # just the unrelated ephemeral Campaign.company_slug field above.
    company = kwargs.get("company")
    assert company is not None
    assert company.slug == "test-company"


def test_enrich_domain_falls_back_to_domain_derived_slug_when_none_provided(
    client, mock_playwright, mock_enrich_company_website
) -> None:
    """When no company_slug is given at all (the only case a domain-
    derived slug should ever be used), the fallback still works."""
    payload = {
        "domain": "example.com",
        "campaign_name": "test-campaign",
    }

    response = client.post("/enrich", json=payload)

    assert response.status_code == 200
    _, kwargs = mock_enrich_company_website.call_args
    company = kwargs.get("company")
    assert company is not None
    assert company.slug == "example-com"


