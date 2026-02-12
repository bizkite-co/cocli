import pytest
from textual.app import App
from textual.widgets import ListView, ListItem
from unittest.mock import MagicMock

from cocli.tui.widgets.person_list import PersonList
from cocli.models.search import SearchResult
from cocli.application.services import ServiceContainer

# Mock data that get_fuzzy_search_results would return for persons
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

    def __init__(self, services=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.services = services or ServiceContainer()

    def on_mount(self) -> None:
        self.push_screen("person_list")

@pytest.mark.asyncio
async def test_person_list_display_people():
    mock_search = MagicMock()
    mock_search.return_value = mock_fz_person_items
    services = ServiceContainer(search_service=mock_search)
    
    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        # Get the PersonList screen
        person_list_screen = app.get_screen("person_list")
        assert isinstance(person_list_screen, PersonList)

        # Allow worker to run
        await driver.pause(0.2)

        # Find the ListView widget
        list_view = person_list_screen.query_one(ListView)
        assert isinstance(list_view, ListView)

        # Assert that the ListView contains the expected person names
        expected_names = [item.name for item in mock_fz_person_items]
        displayed_names = [item.name for item in list_view.children if isinstance(item, ListItem)]
        
        assert sorted(displayed_names) == sorted(expected_names)

@pytest.mark.asyncio
async def test_person_list_search_duplicate_slugs():
    # Mock search_service to simulate search results
    def mock_search_side_effect(*args, **kwargs):
        search_query = kwargs.get("search_query", "").lower()
        if "duplicate" in search_query:
            # Return only the items matching 'duplicate' when search query is 'duplicate'
            return [
                SearchResult(name="Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person", tags=[], display=""),
                SearchResult(name="Another Duplicate Person", slug="duplicate-person", type="person", unique_id="duplicate-person-1", tags=[], display=""),
            ]
        return mock_fz_person_items # Default case for initial load

    mock_search = MagicMock()
    mock_search.side_effect = mock_search_side_effect
    services = ServiceContainer(search_service=mock_search)

    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        person_list_screen = app.get_screen("person_list")
        assert isinstance(person_list_screen, PersonList)

        list_view = person_list_screen.query_one(ListView)
        # Simulate typing a search query that would include duplicate slugs
        await driver.click("#person_search_input")
        await driver.press("d", "u", "p", "l", "i", "c", "a", "t", "e")
        await driver.pause(0.2) # Allow Textual to process the input and update the list

        # Assert that no MountError occurred and the list contains expected items
        displayed_names = [item.name for item in list_view.children if isinstance(item, ListItem)]
        
        assert "Duplicate Person" in displayed_names
        assert "Another Duplicate Person" in displayed_names
        assert len(displayed_names) == 2 
