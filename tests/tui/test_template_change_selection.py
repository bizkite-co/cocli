import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.models.search import SearchResult
from cocli.application.services import ServiceContainer
from cocli.tui.widgets.company_list import CompanyList
from textual.widgets import ListView

def setup_mock_services():
    mock_search = MagicMock()
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
        return [
            SearchResult(
                type="company",
                name="All Company 1",
                slug="all-1",
                display="All 1",
                unique_id="all-1"
            )
        ]

    mock_search.side_effect = side_effect
    
    services = ServiceContainer(
        search_service=mock_search, 
        sync_search=True,
        template_counts_service=MagicMock(return_value={"tpl_all": 1, "tpl_with_email": 1})
    )
    return services

@pytest.mark.asyncio
async def test_template_change_updates_selection():
    """Verify that changing a template updates the list and selects the first item."""
    services = setup_mock_services()
    app = CocliApp(services=services, auto_show=False)
    
    async with app.run_test() as driver:
        # Manually show companies after app is ready
        await driver.app.action_show_companies()
        # Ample time for initial load
        await driver.pause(1.5)
        
        company_list = app.query_one(CompanyList)
        
        # Initial check
        assert len(company_list.filtered_fz_items) > 0
        assert company_list.filtered_fz_items[0].name == "All Company 1"
        
        # Focus templates and select "With Email" (index 2)
        await driver.press("t")
        await driver.press("j") # Down to "To Call Tomorrow"
        await driver.press("j") # Down to "With Email"
        await driver.press("enter")
        
        # Ample time for search worker and UI refresh synchronization
        await driver.pause(2.0)
        
        # Check internal state FIRST
        assert company_list.filtered_fz_items[0].name == "Email Company 1"
        
        # Check if list UI updated
        list_view = company_list.query_one("#company_list_view", ListView)
        assert "Email Company 1" in str(list_view.children[0])
        assert list_view.index == 0

@pytest.mark.asyncio
async def test_l_key_drill_down_updates_selection():
    """Verify that using 'l' to drill down updates the list and selects the first item."""
    services = setup_mock_services()
    app = CocliApp(services=services, auto_show=False)
    
    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        await driver.pause(1.5)
        
        # Focus templates
        await driver.press("t")
        await driver.press("j") # Down to "To Call Tomorrow"
        await driver.press("j") # Down to "With Email"
        
        # Press 'l' to drill down
        await driver.press("l")
        
        # Ample time for search worker and UI refresh synchronization
        await driver.pause(2.0)
        
        # Company list should have focus
        focused = app.focused
        assert isinstance(focused, ListView)
        assert focused.id == "company_list_view"
        
        # Check if list updated and first item is selected
        company_list = app.query_one(CompanyList)
        assert company_list.filtered_fz_items[0].name == "Email Company 1"
        assert "Email Company 1" in str(focused.children[0])
        assert focused.index == 0
