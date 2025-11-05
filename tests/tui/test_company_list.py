import pytest
from unittest.mock import patch
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from textual.widgets import ListView
from conftest import wait_for_widget


from cocli.tui.app import CocliApp

from cocli.models.search import SearchResult

# Mock data for the detail screen
mock_detail_data = {
    "company": {"name": "Selected Company", "slug": "selected-company", "domain": "selected.com"},
    "tags": [], "content": "", "website_data": None, "contacts": [], "meetings": [], "notes": []
}

@pytest.mark.asyncio
@patch('cocli.tui.app.get_company_details_for_view')
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_company_selection_integration(mock_get_fz_items, mock_get_company_details):
    """Test full company selection flow from main menu to detail screen."""
    # Arrange
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    mock_get_company_details.return_value = mock_detail_data

    app = CocliApp()

    # Act & Assert
    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        company_list_screen = await wait_for_widget(driver, CompanyList)
        await driver.pause(1.0)
        # --- Direct Message Capture ---
        posted_messages = []
        original_post_message = company_list_screen.post_message
        def new_post_message(message):
            posted_messages.append(message)
            return original_post_message(message)
        company_list_screen.post_message = new_post_message
        # ----------------------------

        assert isinstance(company_list_screen, CompanyList)

        # Move focus from the search input to the list view
        company_list_screen.query_one(ListView).focus()
        await driver.pause(1.0)
        
        await driver.press("down")
        await driver.pause(1.0)
        
        await driver.press("l")
        await driver.pause(1.0)

        # --- Assert that the correct message was posted ---
        # print("\n--- Posted Message Types ---")
        # for msg in posted_messages:
        #     print(msg.__class__.__name__)
        # print("---------------------------")
        assert len(posted_messages) > 0, "No messages were posted"
        assert any(msg.__class__.__name__ == 'CompanySelected' for msg in posted_messages), "CompanySelected message was not posted"
        # --------------------------------------------------

        company_detail = await wait_for_widget(driver, CompanyDetail)
        await driver.pause(1.0)
        assert isinstance(company_detail, CompanyDetail)
        mock_get_company_details.assert_called_once_with("test-company")