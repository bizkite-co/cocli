import pytest
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, EditInput, InfoTable

@pytest.fixture
def mock_company_data():
    return {
        "company": {"name": "Test Co", "slug": "test-co", "domain": "test.com"},
        "notes": [],
        "contacts": [],
        "meetings": [],
        "tags": []
    }

@pytest.mark.asyncio
async def test_cancel_inline_edit_with_esc(mock_company_data):
    """Test that pressing 'escape' cancels the inline edit."""
    app = CocliApp(auto_show=False)
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
        assert not info_table.display

        # 3. Press Escape to cancel
        await driver.press("escape")
        await driver.pause(0.1)

        # Verify EditInput is gone and table is back
        assert len(app.query(EditInput)) == 0
        assert info_table.display
        assert info_table.has_focus

@pytest.mark.asyncio
async def test_cancel_inline_edit_with_alt_s(mock_company_data):
    """Test that pressing 'alt+s' cancels the inline edit."""
    app = CocliApp(auto_show=False)
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

        # 3. Press Alt+s to cancel
        await driver.press("alt+s")
        await driver.pause(0.1)

        # Verify EditInput is gone and table is back
        assert len(app.query(EditInput)) == 0
        assert info_table.display
        assert info_table.has_focus
