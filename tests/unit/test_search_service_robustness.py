import pytest
from cocli.application.search_service import get_fuzzy_search_results
from cocli.core.paths import paths
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.core.cache import build_cache

@pytest.fixture
def repro_env(mock_cocli_env, mocker):
    """
    Sets up an environment with a real-ish checkpoint file that lacks 'email'.
    """
    campaign = "test/repro"
    campaign_node = paths.campaign(campaign)
    prospect_idx = campaign_node.index("google_maps_prospects")
    prospect_idx.path.mkdir(parents=True, exist_ok=True)
    
    checkpoint_path = prospect_idx.checkpoint
    
    # 1. Create a dummy prospect without email
    from cocli.models.place_id import PlaceID
    from cocli.models.company_slug import CompanySlug
    
    prospect = GoogleMapsProspect(
        place_id=PlaceID("ChIJtest_longer_place_id_for_validation"),
        company_slug=CompanySlug("test-co"),
        name="Test Co"
    )
    
    with open(checkpoint_path, "w") as f:
        f.write(prospect.to_usv())
        
    # 2. Save datapackage (which won't have email)
    GoogleMapsProspect.write_datapackage(campaign)
    
    # 3. Setup mock campaign
    mocker.patch('cocli.core.config.get_campaign', return_value=campaign)
    mocker.patch('cocli.application.search_service.get_campaign', return_value=campaign)
    
    # 4. Build cache
    comp_dir = paths.companies / "test-co"
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text("---\nname: Test Co\ntags:\n  - test/repro\n---")
    build_cache(campaign=campaign)
    
    return campaign

def test_search_fails_on_missing_email_column(repro_env):
    """
    This test should FAIL with the binder error before the fix.
    """
    # This should NOT raise an exception or return an empty list if it's working
    results = get_fuzzy_search_results(search_query="", campaign_name=repro_env)
    
    # If the bug exists, search_service.py:267 catches the exception and returns []
    # So we assert that we actually got results.
    assert len(results) > 0, "Search results should not be empty (indicates DuckDB failure)"
