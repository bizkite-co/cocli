import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.application.services import ServiceContainer
from textual.widgets import Input, ListView

@pytest.fixture
def mock_company_data():
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com"
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": []
    }

def create_mock_services():
    mock_search = MagicMock()
    mock_search.return_value = []
    return ServiceContainer(search_service=mock_search, sync_search=True)

@pytest.mark.asyncio
async def test_alt_s_in_company_list_resets_search_and_focuses_list():
    """Test that alt+s in CompanyList clears search and focuses the LIST, not input."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await app.query_one("#app_content").mount(CompanyList())
        await driver.pause(0.1)
        
        search_input = app.query_one("#company_search_input", Input)
        search_input.value = "something"
        search_input.focus()
        
        # Press alt+s
        await driver.press("alt+s")
        await driver.pause(0.1)
        
        # Input should be cleared
        assert search_input.value == ""
        # BUT Input should NOT have focus
        assert not search_input.has_focus
        # ListView SHOULD have focus
        assert app.query_one(ListView).has_focus

@pytest.mark.asyncio
async def test_alt_s_in_company_detail_navigates_up_to_list_focus(mock_company_data):
    """Test that alt+s in CompanyDetail navigates back to CompanyList and focuses the list."""
    services = create_mock_services()
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        # Start in detail view
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        
        # Verify we are in Detail
        assert len(app.query(CompanyDetail)) == 1
        
        # Press alt+s
        await driver.press("alt+s")
        await driver.pause(0.5)
        
        # Should be back at List
        assert len(app.query(CompanyList)) == 1
        assert len(app.query(CompanyDetail)) == 0
        
        # ListView should have focus for immediate j/k navigation
        assert app.query_one(ListView).has_focus
        assert not app.query_one(Input).has_focus
