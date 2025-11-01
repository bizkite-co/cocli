import pytest
from unittest.mock import patch
from cocli.tui.app import CocliApp
from cocli.tui.screens.company_list import CompanyList
from cocli.models.search import SearchResult
from pytest_mock import MockerFixture


@pytest.mark.asyncio
@patch('cocli.tui.screens.company_list.get_filtered_items_from_fz')
async def test_company_list_mounts(mock_get_fz_items):
    """Test that the CompanyList screen can be mounted."""
    mock_get_fz_items.return_value = []
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.app.push_screen(CompanyList())
        await driver.pause()
        assert isinstance(app.screen, CompanyList)


@pytest.mark.asyncio
@patch('cocli.tui.screens.company_list.get_filtered_items_from_fz')
async def test_company_list_populates(mock_get_fz_items):
    """Test that the CompanyList screen populates the list view."""
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company 1", slug="test-company-1", domain="test1.com", type="company", unique_id="test-company-1", tags=[], display=""),
        SearchResult(name="Test Company 2", slug="test-company-2", domain="test2.com", type="company", unique_id="test-company-2", tags=[], display=""),
    ]
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.app.push_screen(CompanyList())
        await driver.pause()
        list_view = app.screen.query_one("#company_list_view")
        assert list_view.children is not None
        assert len(list_view.children) == 2


@pytest.mark.asyncio
@patch('cocli.tui.screens.company_list.get_filtered_items_from_fz')
async def test_company_list_selection_posts_message(mock_get_fz_items, mocker: MockerFixture):
    """Test that selecting a company posts a CompanySelected message."""
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    app = CocliApp()
    async with app.run_test() as driver:
        company_list_screen = CompanyList()
        spy = mocker.spy(company_list_screen, "post_message")

        await driver.app.push_screen(company_list_screen)
        await driver.pause()

        # Move focus to the list view and select the first item
        await driver.press("tab")
        await driver.press("down")
        await driver.press("enter")
        await driver.pause()

        # Assert that post_message was called with a CompanySelected message
        found_message = False
        for call in spy.call_args_list:
            message = call[0][0]
            if message.__class__.__name__ == "CompanySelected":
                found_message = True
                assert message.company_slug == "test-company"
                break
        assert found_message, "CompanySelected message was not posted"
