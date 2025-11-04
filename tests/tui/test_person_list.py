import pytest
from textual.app import App
from textual.widgets import ListView, ListItem
from unittest.mock import patch

from cocli.tui.widgets.person_list import PersonList
from cocli.utils.textual_utils import sanitize_id # Re-added for sanitizing expected IDs
from cocli.models.search import SearchResult

# Mock data that get_filtered_items_from_fz would return for persons
mock_fz_person_items = [
    SearchResult(name="Person One", slug="person-one", type="person", unique_id="person-one", tags=[], display=""),
    SearchResult(name="Person Two", slug="person-two", type="person", unique_id="person-two", tags=[], display=""),
    SearchResult(name="Person Three", slug="person-three", type="person", unique_id="person-three", tags=[], display=""),
    SearchResult(name="1st Person", slug="1st-person", type="person", unique_id="_1st-person", tags=[], display=""),
    SearchResult(name="Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person", tags=[], display=""),
    SearchResult(name="Another Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person-1", tags=[], display=""),
]

class PersonListTestApp(App[None]):
    """A test app for the PersonList screen."""

    SCREENS = {"person_list": PersonList}

    def on_mount(self) -> None:
        self.push_screen("person_list")

@pytest.mark.asyncio
@patch('cocli.tui.widgets.person_list.get_filtered_items_from_fz')
async def test_person_list_display_people(mock_get_fz_items):
    mock_get_fz_items.return_value = mock_fz_person_items # Return all mock items
    app = PersonListTestApp()
    async with app.run_test():
        # Get the PersonList screen
        person_list_screen = app.get_screen("person_list")
        assert isinstance(person_list_screen, PersonList)

        # Find the ListView widget
        list_view = person_list_screen.query_one(ListView)
        assert isinstance(list_view, ListView)

        # Assert that the ListView contains the expected person unique_ids
        expected_unique_ids = [sanitize_id(item.unique_id) for item in mock_fz_person_items]
        displayed_items = [item.id for item in list_view.children if isinstance(item, ListItem)]
        
        assert sorted(displayed_items) == sorted(expected_unique_ids)

@pytest.mark.asyncio
@patch('cocli.tui.widgets.person_list.get_filtered_items_from_fz')
async def test_person_list_search_duplicate_slugs(mock_get_fz_items):
    # Mock get_filtered_items_from_fz to simulate search results
    def mock_get_filtered_items_from_fz_side_effect(*args, **kwargs):
        search_query = kwargs.get("search_query", "").lower()
        if "duplicate" in search_query:
            # Return only the items matching 'duplicate' when search query is 'duplicate'
            return [
                SearchResult(name="Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person", tags=[], display=""),
                SearchResult(name="Another Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person-1", tags=[], display=""),
            ]
        return mock_fz_person_items # Default case for initial load

    mock_get_fz_items.side_effect = mock_get_filtered_items_from_fz_side_effect

    app = PersonListTestApp()
    async with app.run_test() as driver:
        person_list_screen = app.get_screen("person_list")
        assert isinstance(person_list_screen, PersonList)

        list_view = person_list_screen.query_one(ListView)
        # Simulate typing a search query that would include duplicate slugs
        await driver.click("#person_search_input")
        await driver.press("d", "u", "p", "l", "i", "c", "a", "t", "e")
        await driver.pause() # Allow Textual to process the input and update the list

        # Assert that no MountError occurred and the list contains expected items
        displayed_items_ids = [item.id for item in list_view.children if isinstance(item, ListItem)]
        assert sanitize_id("duplicate-person") in displayed_items_ids
        assert sanitize_id("duplicate-person-1") in displayed_items_ids
        assert len(displayed_items_ids) == 2 # Should show both duplicate persons with their unique IDs
