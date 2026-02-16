import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, EditInput, InfoTable
from cocli.tui.widgets.company_list import CompanyList
from cocli.application.services import ServiceContainer

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
async def test_cancel_inline_edit_with_escape(mock_company_data):
    """Test that pressing 'escape' cancels the inline edit."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)

        # 1. Enter quadrant (focus info table)
        await driver.press("i")
        info_table = app.query_one(InfoTable)
        assert info_table.has_focus

        # 2. Trigger edit on the first row (Name)
        await driver.press("i")
        await driver.pause(0.1)

        # Verify EditInput is present
        edit_input = app.query_one(EditInput)
        assert edit_input.has_focus

        # 3. Press escape to cancel
        await driver.press("escape")
        await driver.pause(0.1)

        # Verify EditInput is gone and table is back
        assert len(app.query(EditInput)) == 0
        assert info_table.display
        assert info_table.has_focus

@pytest.mark.asyncio
async def test_navigate_up_with_alt_s(mock_company_data):
    """Test that pressing 'alt+s' in CompanyDetail navigates up to CompanyList."""
    # We need real or mock services that handle action_show_companies
    services = create_mock_services()
    app = CocliApp(services=services, auto_show=False)
    
    async with app.run_test() as driver:
        # Manually set up state: show CompanyDetail
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        
        assert len(app.query(CompanyDetail)) == 1
        
        # Press alt+s to navigate UP
        await driver.press("alt+s")
        await driver.pause(0.5)
        
        # Should be back at CompanyList (Search)
        assert len(app.query(CompanyList)) == 1
        assert len(app.query(CompanyDetail)) == 0
        
        # Search input should have focus and be empty (from action_search_fresh)
        from textual.widgets import Input
        search_input = app.query_one("#company_search_input", Input)
        assert search_input.has_focus
        assert search_input.value == ""
