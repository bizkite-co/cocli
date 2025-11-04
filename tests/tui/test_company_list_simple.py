import pytest
from unittest.mock import patch
from cocli.tui.app import CocliApp

from cocli.models.search import SearchResult
from pytest_mock import MockerFixture
from cocli.tui.widgets.company_list import CompanyList
from textual.widgets import ListView
from conftest import wait_for_widget


@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_company_list_mounts(mock_get_fz_items):
    app = CocliApp()
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("alt+c")
        await driver.pause()
        company_list_screen = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list_screen, CompanyList)


@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_company_list_populates(mock_get_fz_items):
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company 1", slug="test-company-1", domain="test1.com", type="company", unique_id="test-company-1", tags=[], display=""),
        SearchResult(name="Test Company 2", slug="test-company-2", domain="test2.com", type="company", unique_id="test-company-2", tags=[], display=""),
    ]
    app = CocliApp()
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("alt+c")
        await driver.pause()
        company_list_screen = await wait_for_widget(driver, CompanyList)
        list_view = company_list_screen.query_one("#company_list_view")
        assert list_view.children is not None
        assert len(list_view.children) == 2


@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_list.get_filtered_items_from_fz')
async def test_company_list_selection_posts_message(mock_get_fz_items, mocker: MockerFixture):
    """Test that selecting a company posts a CompanySelected message."""
    mock_get_fz_items.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    app = CocliApp()
    async with app.run_test() as driver:
        # Select 'Companies' using the hotkey
        await driver.press("alt+c")
        await driver.pause()
        company_list_screen = await wait_for_widget(driver, CompanyList)
        spy = mocker.spy(company_list_screen, "post_message")

        # Move focus to the list view and select the first item
        company_list_screen.query_one(ListView).focus()
        await driver.pause()
        await driver.press("down")
        await driver.press("l")
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