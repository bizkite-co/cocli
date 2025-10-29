import pytest
from textual.app import App
from textual.widgets import ListView, ListItem

from unittest.mock import patch

from cocli.tui.screens.company_list import CompanyList
from cocli.utils.textual_utils import sanitize_id

# Mock data that get_filtered_items_from_fz would return
mock_fz_items = [
    {"name": "Company A", "slug": "company-a", "domain": "company-a.com", "type": "company", "unique_id": "company-a"},
    {"name": "Company B", "slug": "company-b", "domain": "company-b.com", "type": "company", "unique_id": "company-b"},
    {"name": "Company C", "slug": "company-c", "domain": "company-c.com", "type": "company", "unique_id": "company-c"},
    {"name": "1st Company", "slug": "1st-company", "domain": "first-company.com", "type": "company", "unique_id": "_1st-company"},
    {"name": "Duplicate Company 1", "slug": "duplicate-company", "domain": "duplicate1.com", "type": "company", "unique_id": "duplicate-company"},
    {"name": "Duplicate Company 2", "slug": "duplicate-company", "domain": "duplicate2.com", "type": "company", "unique_id": "duplicate-company-1"}, # Unique ID for the duplicate
]

class CompanyListTestApp(App[None]):
    """A test app for the CompanyList screen."""

    SCREENS = {"company_list": CompanyList}

    def on_mount(self) -> None:
        self.push_screen("company_list")

@pytest.mark.asyncio
@patch('cocli.tui.screens.company_list.get_filtered_items_from_fz')
async def test_company_list_display_companies(mock_get_fz_items):
    """Test that the CompanyList screen displays companies correctly."""
    mock_get_fz_items.return_value = mock_fz_items # Return all mock items
    app = CompanyListTestApp()
    async with app.run_test():
        company_list_screen = app.get_screen("company_list")
        assert isinstance(company_list_screen, CompanyList)

        list_view = company_list_screen.query_one(ListView)
        assert isinstance(list_view, ListView)

        # Assert that the ListView contains the expected company unique_ids
        expected_unique_ids = [sanitize_id(item["unique_id"]) for item in mock_fz_items[:20]]
        displayed_items_ids = [item.id for item in list_view.children if isinstance(item, ListItem)]
        
        assert sorted(displayed_items_ids) == sorted(expected_unique_ids)

@pytest.mark.asyncio
@patch('cocli.tui.screens.company_list.get_filtered_items_from_fz')
async def test_company_list_search_duplicate_slugs(mock_get_fz_items):
    """Test that searching with duplicate slugs doesn't cause MountError."""
    # Mock get_filtered_items_from_fz to simulate search results
    def mock_get_filtered_items_from_fz_side_effect(*args, **kwargs):
        search_query = kwargs.get("search_query", "").lower()
        if "duplicate" in search_query:
            # Return only the items matching 'duplicate' when search query is 'duplicate'
            return [
                {"name": "Duplicate Company 1", "slug": "duplicate-company", "domain": "duplicate1.com", "type": "company", "unique_id": "duplicate-company"},
                {"name": "Duplicate Company 2", "slug": "duplicate-company", "domain": "duplicate2.com", "type": "company", "unique_id": "duplicate-company-1"},
            ]
        return mock_fz_items # Default case for initial load

    mock_get_fz_items.side_effect = mock_get_filtered_items_from_fz_side_effect
    app = CompanyListTestApp()
    async with app.run_test() as driver:
        company_list_screen = app.get_screen("company_list")
        assert isinstance(company_list_screen, CompanyList)

        list_view = company_list_screen.query_one(ListView)
        # Simulate typing a search query that would include duplicate slugs
        await driver.click("#company_search_input")
        await driver.press("d", "u", "p", "l", "i", "c", "a", "t", "e")
        await driver.pause() # Allow Textual to process the input and update the list

        # Assert that no MountError occurred and the list contains expected items
        displayed_items_ids = [item.id for item in list_view.children if isinstance(item, ListItem)]
        assert sanitize_id("duplicate-company") in displayed_items_ids
        assert sanitize_id("duplicate-company-1") in displayed_items_ids
        assert len(displayed_items_ids) == 2 # Should show both duplicate companies with their unique IDs
