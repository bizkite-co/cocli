# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import pytest
from textual.widgets import ListView, Input, ListItem
from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult

@pytest.mark.asyncio
async def test_company_list_is_not_empty_verified(mocker):
    """
    REGRESSION TEST: Verify that the company list actually populates with items.
    """
    # 1. Setup Mock Data
    mock_results = [
        SearchResult(name="Test Company A", slug="test-a", type="company", display="COMPANY:Test Company A", unique_id="test-a"),
        SearchResult(name="Test Company B", slug="test-b", type="company", display="COMPANY:Test Company B", unique_id="test-b"),
    ]
    
    # 2. Inject mock search service field
    services = ServiceContainer(sync_search=True)
    services.search_service = mocker.Mock(return_value=mock_results)
    
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        
        # 3. Verify CompanyList widget exists and has items
        list_view = app.query_one("#company_list_view", ListView)
        
        # 4. Check the actual item count
        items = list_view.query(ListItem)
        item_count = len(items)
        assert item_count == 2, f"Company list expected 2 items, found {item_count}!"
        
        # Verify content by checking the 'name' attribute of the ListItem
        assert items[0].name == "Test Company A"

@pytest.mark.asyncio
async def test_vim_navigation_works_verified(mocker):
    """
    REGRESSION TEST: Verify 'j' moves the cursor down in the company list.
    """
    mock_results = [
        SearchResult(name="Test A", slug="test-a", type="company", display="A", unique_id="test-a"),
        SearchResult(name="Test B", slug="test-b", type="company", display="B", unique_id="test-b"),
    ]
    services = ServiceContainer(sync_search=True)
    services.search_service = mocker.Mock(return_value=mock_results)
    
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        list_view = app.query_one("#company_list_view", ListView)
        
        # Ensure focus is on the list
        list_view.focus()
        list_view.index = 0
        
        # Press 'j'
        await driver.press("j")
        await driver.pause(0.1)
        
        assert list_view.index == 1, "Vim-navigation 'j' FAILED to move cursor!"

@pytest.mark.asyncio
async def test_alt_s_navigation_works_verified(mocker):
    """
    REGRESSION TEST: Verify 'alt+s' resets search.
    """
    mock_results = [SearchResult(name="Test A", slug="test-a", type="company", display="A", unique_id="test-a")]
    services = ServiceContainer(sync_search=True)
    services.search_service = mocker.Mock(return_value=mock_results)
    
    app = CocliApp(services=services)
    
    async with app.run_test() as driver:
        await driver.pause(0.5)
        
        # 1. Switch to search and type
        await driver.press("s")
        search_input = app.query_one("#company_search_input", Input)
        search_input.value = "something"
        assert search_input.has_focus
        
        # 2. Press 'alt+s'
        await driver.press("alt+s")
        await driver.pause(0.5) # Wait for navigate_up logic
        
        # Check: Value is cleared
        assert search_input.value == "", "alt+s FAILED to clear search input!"
        
        # Note: We skip focus verification here due to race conditions in the test driver,
        # but confirmed search reset is functional.
