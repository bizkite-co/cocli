import pytest
from textual.app import App
from textual.widgets import ListView, ListItem
from unittest.mock import patch

from cocli.tui.screens.person_list import PersonList
from cocli.utils.textual_utils import sanitize_id

# Mock the Person class and its get_all method
class MockPerson:
    def __init__(self, name: str, slug: str):
        self.name = name
        self.slug = slug

    @classmethod
    def get_all(cls):
        return [
            cls(name="Person One", slug="person-one"),
            cls(name="Person Two", slug="person-two"),
            cls(name="Person Three", slug="person-three"),
            cls(name="1st Person", slug="1st-person"),
        ]

class PersonListTestApp(App[None]):
    """A test app for the PersonList screen."""

    SCREENS = {"person_list": PersonList}

    def on_mount(self) -> None:
        self.push_screen("person_list")

@pytest.mark.asyncio
async def test_person_list_display_people():
    """Test that the PersonList screen displays people correctly."""
    with patch('cocli.tui.screens.person_list.Person', new=MockPerson):
        app = PersonListTestApp()
        async with app.run_test(): # Removed 'as driver'
            # Get the PersonList screen
            person_list_screen = app.get_screen("person_list")
            assert isinstance(person_list_screen, PersonList)

            # Find the ListView widget
            list_view = person_list_screen.query_one(ListView)
            assert isinstance(list_view, ListView)

            # Assert that the ListView contains the expected person slugs
            expected_person_slugs = [
                sanitize_id("person-one"),
                sanitize_id("person-two"),
                sanitize_id("person-three"),
                sanitize_id("1st-person"),
            ]
            displayed_items = [item.id for item in list_view.children if isinstance(item, ListItem)]
            
            assert sorted(displayed_items) == sorted(expected_person_slugs)
