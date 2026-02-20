import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.models.search import SearchResult
from cocli.application.services import ServiceContainer
from textual.widgets import ListView

def setup_mocks(monkeypatch):
    mock_search = MagicMock()
    # Default search results
    mock_search.return_value = [
        SearchResult(
            type="company",
            name="All Company 1",
            slug="all-1",
            display="All 1",
            unique_id="all-1"
        )
    ]
    
    # Mock different results for template switch
    def side_effect(search_query, item_type, filters=None, **kwargs):
        if filters and filters.get("has_email"):
            return [
                SearchResult(
                    type="company",
                    name="Email Company 1",
                    slug="email-1",
                    display="Email 1",
                    unique_id="email-1"
                )
            ]
        return mock_search.return_value

    mock_search.side_effect = side_effect
    
    monkeypatch.setattr("cocli.application.services.get_template_counts", lambda campaign=None: {"tpl_all": 1, "tpl_with_email": 1})
    
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    return services

@pytest.mark.asyncio
async def test_template_change_updates_selection(monkeypatch):
    """Verify that changing a template updates the list and selects the first item."""
    services = setup_mocks(monkeypatch)
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        
        list_view = app.query_one("#company_list_view", ListView)
        # Initial check
        assert "All Company 1" in str(list_view.children[0])
        assert list_view.index == 0
        
        # Focus templates and select "With Email" (index 1)
        await driver.press("t")
        await driver.press("j") # Down to "With Email"
        await driver.press("enter")
        await driver.pause(0.5)
        
        # Check if list updated and first item is selected
        list_view = app.query_one("#company_list_view", ListView)
        assert "Email Company 1" in str(list_view.children[0])
        assert list_view.index == 0
        
        # Verify it's highlighted child
        assert list_view.highlighted_child == list_view.children[0]
