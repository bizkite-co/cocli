import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_search import CompanySearchView
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.template_list import TemplateList
from cocli.models.search import SearchResult
from cocli.application.services import ServiceContainer
from textual.widgets import ListView

def setup_mocks(monkeypatch):
    mock_search = MagicMock()
    mock_search.return_value = [
        SearchResult(
            type="company",
            name="Test Company",
            slug="test-company",
            display="Test Company",
            unique_id="test-company"
        )
    ]
    
    # Patch at the source module to avoid Pydantic issues
    monkeypatch.setattr("cocli.application.services.get_template_counts", lambda campaign=None: {"tpl_all": 1})
    
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    return services

@pytest.mark.asyncio
async def test_search_view_displayed_on_startup(monkeypatch):
    """Verify that CompanySearchView and its list are visible on startup."""
    services = setup_mocks(monkeypatch)
    # We want to test the default startup behavior, so auto_show=True (default)
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        
        # Check if CompanySearchView is mounted and visible
        search_views = list(app.query(CompanySearchView))
        assert len(search_views) == 1
        assert search_views[0].visible
        
        # Check if CompanyList is visible inside it
        company_lists = list(app.query(CompanyList))
        assert len(company_lists) == 1
        assert company_lists[0].visible
        
        # Check if ListView has items
        list_view = app.query_one("#company_list_view", ListView)
        assert len(list_view.children) > 0

@pytest.mark.asyncio
async def test_t_key_navigates_to_templates(monkeypatch):
    """Verify that 't' key focuses the TemplateList."""
    services = setup_mocks(monkeypatch)
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        # Wait for mount
        await driver.pause(0.5)
        
        # Press t
        await driver.press("t")
        await driver.pause(0.2)
        
        # TemplateList should have focus
        focused = app.focused
        assert isinstance(focused, ListView)
        # Ensure it's the template list's listview
        assert focused.parent and isinstance(focused.parent, TemplateList)
