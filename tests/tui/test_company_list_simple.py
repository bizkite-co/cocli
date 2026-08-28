import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult
from pytest_mock import MockerFixture
from cocli.tui.widgets.company_list import CompanyList
from textual.widgets import Input, ListView
from conftest import wait_for_widget

def create_mock_services(results=None):
    mock_search = MagicMock()
    mock_search.return_value = results or []
    return ServiceContainer(search_service=mock_search, sync_search=True), mock_search

@pytest.mark.asyncio
async def test_company_list_mounts():
    services, _ = create_mock_services()
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert company_list_screen is not None


@pytest.mark.asyncio
async def test_company_list_populates():
    results = [
        SearchResult(name="Test Company 1", slug="test-company-1", domain="test1.com", type="company", unique_id="test-company-1", tags=[], display=""),
        SearchResult(name="Test Company 2", slug="test-company-2", domain="test2.com", type="company", unique_id="test-company-2", tags=[], display=""),
    ]
    services, _ = create_mock_services(results)
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        list_view = company_list_screen.query_one("#company_list_view")
        assert list_view.children is not None
        assert len(list_view.children) == 2


@pytest.mark.asyncio
async def test_preview_follows_cursor_from_search_row_without_markdown() -> None:
    """Preview must use the current list index and DuckDB row, not Company.get."""
    results = [
        SearchResult(
            name="Alpha Co",
            slug="alpha-co",
            domain="alpha.com",
            type="company",
            unique_id="alpha-co",
            tags=[],
            display="",
            city="Austin",
            state="TX",
            average_rating=4.8,
            reviews_count=12,
        ),
        SearchResult(
            name="Beta Co",
            slug="beta-co",
            domain="beta.com",
            type="company",
            unique_id="beta-co",
            tags=[],
            display="",
            city="Dallas",
            state="TX",
            average_rating=3.1,
            reviews_count=4,
        ),
    ]
    services, _ = create_mock_services(results)
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        company_list = await wait_for_widget(driver, CompanyList)
        list_view = company_list.query_one("#company_list_view", ListView)
        list_view.index = 0
        first = company_list._highlighted_result()
        assert first is not None and first.slug == "alpha-co"
        preview = company_list._preview_company(first)
        assert preview is not None
        assert preview.slug == "alpha-co"
        assert str(preview.name) == "Alpha Co"
        assert preview.city == "Austin"
        assert preview.average_rating == 4.8

        list_view.index = 1
        second = company_list._highlighted_result()
        assert second is not None and second.slug == "beta-co"
        preview = company_list._preview_company(second)
        assert preview is not None
        assert preview.slug == "beta-co"
        assert preview.city == "Dallas"


@pytest.mark.asyncio
async def test_enter_in_search_leaves_typing_mode_without_selecting() -> None:
    """Enter in the search box must focus the list, not open a company."""
    results = [
        SearchResult(
            name="Alpha Co",
            slug="alpha-co",
            domain="alpha.com",
            type="company",
            unique_id="alpha-co",
            tags=[],
            display="",
        ),
        SearchResult(
            name="Beta Co",
            slug="beta-co",
            domain="beta.com",
            type="company",
            unique_id="beta-co",
            tags=[],
            display="",
        ),
    ]
    services, _ = create_mock_services(results)
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        company_list = await wait_for_widget(driver, CompanyList)
        search_input = company_list.query_one("#company_search_input", Input)
        list_view = company_list.query_one("#company_list_view", ListView)
        search_input.focus()
        await driver.pause(0.1)

        posted: list[object] = []
        original_post = company_list.post_message

        def capture(message: object) -> None:
            posted.append(message)
            return original_post(message)

        company_list.post_message = capture  # type: ignore[method-assign]
        await driver.press("enter")
        await driver.pause(0.1)

        assert list_view.has_focus
        assert not search_input.has_focus
        assert not any(
            isinstance(msg, CompanyList.CompanySelected) for msg in posted
        )

        list_view.index = 1
        await driver.press("enter")
        await driver.pause(0.1)
        assert any(
            isinstance(msg, CompanyList.CompanySelected)
            and getattr(msg, "company_slug", None) == "beta-co"
            for msg in posted
        )


@pytest.mark.asyncio
async def test_company_list_selection_posts_message(mocker: MockerFixture):
    """Test that selecting a company posts a CompanySelected message."""
    results = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    services, _ = create_mock_services(results)
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        await driver.pause(0.5)
        spy = mocker.spy(company_list_screen, "post_message")

        # Move focus to the list view and select the first item
        list_view = company_list_screen.query_one(ListView)
        list_view.focus()
        await driver.pause(0.1)
        list_view.index = 0
        await driver.pause(0.1)
        list_view.action_select_cursor()
        await driver.pause(0.1)
        # Assert that post_message was called with a CompanySelected message
        found_message = False
        for call in spy.call_args_list:
            message = call[0][0]
            if message.__class__.__name__ == "CompanySelected":
                found_message = True
                assert message.company_slug == "test-company"
                break
        assert found_message, "CompanySelected message was not posted"
