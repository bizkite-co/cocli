import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail, InfoTable, DetailPanel
from cocli.application.services import ServiceContainer
from textual.widgets import Input

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
async def test_alt_s_in_company_list_resets_search():
    """Test that alt+s in CompanyList clears and focuses search."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await app.query_one("#app_content").mount(CompanyList())
        await driver.pause(0.1)
        
        search_input = app.query_one("#company_search_input", Input)
        search_input.value = "something"
        
        # Focus something else
        app.query_one("ListView").focus()
        assert not search_input.has_focus
        
        # Press alt+s
        await driver.press("alt+s")
        await driver.pause(0.1)
        
        assert search_input.has_focus
        assert search_input.value == ""

@pytest.mark.asyncio
async def test_alt_s_in_company_detail_navigates_up(mock_company_data):
    """Test that alt+s in CompanyDetail navigates back to CompanyList."""
    services = create_mock_services()
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        # Start in detail view
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        
        # Verify we are in Detail
        assert len(app.query(CompanyDetail)) == 1
        assert app.query_one(DetailPanel).has_focus
        
        # Press alt+s
        await driver.press("alt+s")
        await driver.pause(0.5)
        
        # Should be back at List
        assert len(app.query(CompanyList)) == 1
        assert len(app.query(CompanyDetail)) == 0

@pytest.mark.asyncio
async def test_alt_s_inside_quadrant_navigates_up(mock_company_data):
    """Test that alt+s while focused INSIDE a table navigates all the way up to Search."""
    services = create_mock_services()
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        
        # 1. Enter quadrant (focus InfoTable)
        await driver.press("i")
        assert app.query_one(InfoTable).has_focus
        
        # 2. Press alt+s
        await driver.press("alt+s")
        await driver.pause(0.5)
        
        # Should be back at List
        assert len(app.query(CompanyList)) == 1
