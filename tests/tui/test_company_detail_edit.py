import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, InfoTable, MeetingsTable, EditInput
from cocli.models.companies.company import Company
from cocli.core.paths import paths

@pytest.fixture
def mock_company_data():
    return {
        "company": {
            "name": "Test Co", 
            "slug": "test-co", 
            "domain": "test.com",
            "city": "Austin",
            "state": "TX",
            "zip_code": "78701",
            "street_address": "123 Main St"
        },
        "notes": [],
        "contacts": [],
        "meetings": [
            {
                "datetime_utc": "2026-01-01T12:00:00Z",
                "content": "First Meeting",
                "type": "meeting",
                "file_path": "/tmp/meeting1.md"
            }
        ],
        "tags": []
    }

@pytest.mark.asyncio
@patch('cocli.models.companies.company.Company.get')
@patch('cocli.application.company_service.get_company_details_for_view')
async def test_edit_csz_flow(mock_get_details, mock_get_company, mock_company_data, tmp_path, monkeypatch):
    """Test the multi-field CSZ editing flow."""
    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    
    # Mock company object for saving
    mock_company = MagicMock(spec=Company)
    mock_company.city = "Austin"
    mock_company.state = "TX"
    mock_company.zip_code = "78701"
    mock_get_company.return_value = mock_company

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        # 1. Focus Info Table
        info_table = app.query_one(InfoTable)
        info_table.focus()
        
        # 2. Navigate to CSZ row (Index 6)
        # 0:Name, 1:Rating, 2:Domain, 3:Email, 4:Phone, 5:Street, 6:CSZ
        for _ in range(6):
            await pilot.press("j")
        
        assert info_table.cursor_row == 6
        
        # 3. Trigger edit
        await pilot.press("enter")
        await pilot.pause()
        
        # 4. Verify 3 inputs are mounted
        city_input = app.query_one("#edit-city", EditInput)
        state_input = app.query_one("#edit-state", EditInput)
        zip_input = app.query_one("#edit-zip_code", EditInput)
        
        assert city_input.value == "Austin"
        assert state_input.value == "TX"
        assert zip_input.value == "78701"
        
        # 5. Change values and submit
        await pilot.press("ctrl+a", "backspace") # Clear Austin (if supported by pilot)
        # Simplification for test: just set value directly if pilot.press is tricky
        city_input.value = "Dallas"
        state_input.value = "TX"
        zip_input.value = "75201"
        
        await pilot.press("enter")
        await pilot.pause()
        
        # 6. Verify save was called with new values
        assert mock_company.city == "Dallas"
        assert mock_company.state == "TX"
        assert mock_company.zip_code == "75201"
        mock_company.save.assert_called_once()
        
        # 7. Verify table is back
        assert info_table.display is True
        # Check if table row is updated in local state
        assert "Dallas, TX 75201" in str(info_table.get_row_at(6)[1])

@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_detail.get_editor_command')
@patch('cocli.application.company_service.get_company_details_for_view')
async def test_edit_meeting_flow(mock_get_details, mock_get_editor, mock_company_data, tmp_path, monkeypatch):
    """Test that editing a meeting triggers the editor with correct path."""
    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_get_editor.return_value = "true"

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        # 1. Focus Meetings Panel
        # Info(h) -> Contacts(l) -> Meetings(j)
        await pilot.press("l") # to engagement col
        await pilot.press("j") # to meetings
        
        meetings_panel = app.query_one("#panel-meetings")
        assert meetings_panel.has_focus
        
        # 2. Enter quadrant (focus table)
        await pilot.press("i")
        meetings_table = app.query_one(MeetingsTable)
        assert meetings_table.has_focus
        
        # 3. Trigger edit
        with patch.object(CompanyDetail, '_edit_with_nvim') as mock_edit_nvim:
            await pilot.press("enter")
            await pilot.pause()
            mock_edit_nvim.assert_called_once_with(Path("/tmp/meeting1.md"))
