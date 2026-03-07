import pytest
from cocli.tui.app import CocliApp
from cocli.models.search import SearchResult
from cocli.application.services import ServiceContainer
from textual.widgets import ListView

def setup_mocks(monkeypatch, mock_cocli_env):
    # Mock the search service synchronously
    def mock_search_fn(*args, **kwargs):
        return [
            SearchResult(
                type="company",
                name="Test Company",
                slug="test-company",
                display="Test Company",
                unique_id="test-company"
            )
        ]
    
    # Patch at the source module
    monkeypatch.setattr("cocli.application.services.get_template_counts", lambda campaign=None: {"tpl_all": 1})
    
    services = ServiceContainer(sync_search=False)
    # Inject the mock into the search_service field
    services.search_service = mock_search_fn
    return services

@pytest.mark.asyncio
async def test_search_view_displayed_on_startup(monkeypatch, mock_cocli_env):
    """Verify that CompanySearchView and its list are visible on startup."""
    campaign_name = "test-campaign"
    monkeypatch.setattr("cocli.core.config.get_campaign", lambda: campaign_name)
    
    services = setup_mocks(monkeypatch, mock_cocli_env)
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        # Wait for the view to mount
        await driver.pause(0.5)
        
        # Wait for ListView to have items (async load)
        list_view = app.query_one("#company_list_view", ListView)
        
        # Use a retry loop to wait for items to appear, with longer timeout
        items_loaded = False
        for i in range(50):
            if len(list_view.children) > 0:
                items_loaded = True
                break
            await driver.pause(0.1)
            
        assert items_loaded, "Companies did not load in the ListView on startup"

@pytest.mark.asyncio
async def test_search_view_loads_after_switch(monkeypatch, mock_cocli_env):
    """Verify that CompanySearchView still loads companies after switching from another view."""
    campaign_name = "test-campaign"
    monkeypatch.setattr("cocli.core.config.get_campaign", lambda: campaign_name)
    
    services = setup_mocks(monkeypatch, mock_cocli_env)
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        # 1. Start at Search (default)
        await driver.pause(0.5)
        
        # 2. Switch to Application (via space+a)
        await driver.press("space", "a")
        await driver.pause(0.5)
        
        # 3. Switch back to Companies (via space+c)
        await driver.press("space", "c")
        await driver.pause(0.5)
        
        # 4. Check if ListView has items (async load)
        list_view = app.query_one("#company_list_view", ListView)
        
        items_loaded = False
        for i in range(50):
            if len(list_view.children) > 0:
                items_loaded = True
                break
            await driver.pause(0.1)
            
        assert items_loaded, "Companies did not load after switching back from ApplicationView"
