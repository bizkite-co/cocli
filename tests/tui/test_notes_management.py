import pytest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, NotesTable
from cocli.core.paths import paths

@pytest.fixture
def mock_company_data():
    return {
        "company": {"name": "Test Co", "slug": "test-co", "domain": "test.com"},
        "notes": [
            {"timestamp": datetime(2026, 1, 1), "content": "Note 1", "file_path": "/tmp/note1.md"},
            {"timestamp": datetime(2026, 1, 2), "content": "Note 2", "file_path": "/tmp/note2.md"},
        ],
        "contacts": [],
        "meetings": [],
        "tags": []
    }

@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_detail.get_editor_command')
@patch('cocli.application.company_service.get_company_details_for_view')
async def test_notes_navigation_and_edit_key(mock_get_details, mock_get_editor, mock_company_data, tmp_path, monkeypatch):
    """Test that 'i' focuses notes and then 'i' triggers edit."""
    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_get_editor.return_value = "true" # Mock editor command to just succeed

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        # Manually mount CompanyDetail to bypass selection
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)

        # 1. Focus the Notes panel
        await driver.press("]")
        await driver.press("]")
        await driver.press("]")
        
        notes_panel = app.query_one("#panel-notes")
        assert notes_panel.has_focus

        # 2. Press 'i' to enter quadrant (focus the table)
        await driver.press("i")
        notes_table = app.query_one(NotesTable)
        assert notes_table.has_focus

        # 3. Press 'i' again to edit the note
        # Use a Spy or patch on the method itself since subprocess might fail in run_test
        with patch.object(CompanyDetail, 'action_edit_note', wraps=detail.action_edit_note) as spy_edit:
            # We also need to patch _edit_with_nvim to avoid the app.suspend error
            with patch.object(CompanyDetail, '_edit_with_nvim') as mock_edit_nvim:
                await driver.press("i")
                await driver.pause(0.1)
                spy_edit.assert_called_once()
                mock_edit_nvim.assert_called_once_with(Path("/tmp/note1.md"))

@pytest.mark.asyncio
@patch('cocli.application.company_service.get_company_details_for_view')
async def test_note_deletion_flow(mock_get_details, mock_company_data, tmp_path, monkeypatch):
    """Test that 'd' opens confirmation."""
    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)

        # Focus notes table
        await driver.press("]")
        await driver.press("]")
        await driver.press("]")
        await driver.press("i")
        
        notes_table = app.query_one(NotesTable)
        assert notes_table.has_focus

        # Press 'd' to delete
        await driver.press("d")
        await driver.pause(0.2) # Give it more time to push the screen

        # In run_test, pushing a modal screen might be tricky to verify via app.screen
        # But we can check if the action was called.
        # Actually, let's try to verify the screen again with a longer pause.
        from cocli.tui.widgets.confirm_screen import ConfirmScreen
        assert isinstance(app.screen, ConfirmScreen)
