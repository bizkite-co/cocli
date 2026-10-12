import pytest
from textual.app import App
from textual.widgets import ListView, ListItem, Markdown
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

from textual.app import ComposeResult


class PersonListTestApp(App[None]):
    """A test app for the PersonList container."""

    def __init__(self, services=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.services = services or ServiceContainer()
        self.auto_show = False
        self.person_list = PersonList()

    def compose(self) -> ComposeResult:
        yield self.person_list


@pytest.mark.asyncio
async def test_person_list_display_people():
    mock_search = MagicMock()
    mock_search.return_value = mock_fz_person_items
    services = ServiceContainer(search_service=mock_search, sync_search=True)

    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        # Get the PersonList widget
        person_list_screen = app.person_list
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
    services = ServiceContainer(search_service=mock_search, sync_search=True)

    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        person_list_screen = app.person_list
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


def _person(index: int) -> SearchResult:
    return SearchResult(
        name=f"Person {index:02d}",
        slug=f"person-{index:02d}",
        type="person",
        unique_id=f"person-{index:02d}",
        tags=[],
        display="",
    )


class _KeyApp(PersonListTestApp):
    def __init__(self, services=None, *args, **kwargs):
        super().__init__(services=services, *args, **kwargs)
        self.opened: list[str] = []

    def on_person_list_person_selected(self, message: PersonList.PersonSelected) -> None:
        self.opened.append(message.person_slug)


@pytest.mark.asyncio
async def test_person_list_is_not_capped_at_twenty() -> None:
    people = [_person(i) for i in range(25)]
    services = ServiceContainer(search_service=MagicMock(return_value=people), sync_search=True)
    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        await driver.pause(0.2)
        list_view = app.person_list.query_one(ListView)
        assert len(list_view.children) == 25


@pytest.mark.asyncio
async def test_person_list_vim_keys_search_move_and_open() -> None:
    services = ServiceContainer(
        search_service=MagicMock(return_value=mock_fz_person_items),
        sync_search=True,
    )
    app = _KeyApp(services=services)
    async with app.run_test() as driver:
        await driver.pause(0.2)
        list_view = app.person_list.query_one("#person_list_view", ListView)
        assert list_view.has_focus
        assert list_view.index == 0

        await driver.press("j")
        assert list_view.index == 1
        await driver.press("k")
        assert list_view.index == 0

        await driver.press("s")
        assert app.person_list.query_one("#person_search_input").has_focus

        await driver.press("escape")
        assert list_view.has_focus

        await driver.press("j")
        await driver.press("l")
        assert app.opened == ["person-two"]


@pytest.mark.asyncio
async def test_h_returns_from_person_detail_to_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """h on a person record returns to the people list.

    The list stays mounted but hidden, and it used to keep focus. Back then
    treated that hidden list as the current screen and left the record up.
    """
    from cocli.models.company_name import CompanyName
    from cocli.models.people.person import Person
    from cocli.tui.app import CocliApp
    from cocli.tui.widgets.person_detail import PersonDetail

    person = Person(
        name=CompanyName("Richard Bendes"),
        slug="richard-bendes",
        role="Austin branch",
        linkedin_url="https://www.linkedin.com/in/richard-bendes-36630462/",
    )
    services = ServiceContainer(
        search_service=MagicMock(
            return_value=[
                SearchResult(
                    name="Richard Bendes",
                    slug="richard-bendes",
                    type="person",
                    unique_id="richard-bendes",
                    tags=[],
                    display="",
                )
            ]
        ),
        sync_search=True,
    )
    app = CocliApp(services=services, auto_show=False)
    monkeypatch.setattr(Person, "get", classmethod(lambda cls, slug: person))
    async with app.run_test() as driver:
        await app.action_show_people()
        await driver.pause(0.2)
        await driver.press("l")
        await driver.pause(0.2)
        detail = app.query_one(PersonDetail)
        assert detail.display
        source = detail.query_one("#person-description", Markdown).source
        assert "Person not found." not in source
        assert "\n\n**Role:**" in source
        await driver.press("h")
        await driver.pause(0.4)
        assert not any(widget.display for widget in app.query(PersonDetail))
        assert app.query_one(PersonList).display
