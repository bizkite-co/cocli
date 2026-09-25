"""Tests for vim navigation (G, gg, home, end, auto-paging j/k) and search_limit in CompanyList."""

from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from textual.widgets import ListView

from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from conftest import wait_for_widget


def _mock_results(n: int = 10, offset: int = 0) -> list[SearchResult]:
    return [
        SearchResult(
            name=f"Company {i}",
            slug=f"company-{i}",
            domain=f"company{i}.com",
            type="company",
            unique_id=f"company-{i}",
            tags=[],
            display="",
        )
        for i in range(offset + 1, offset + n + 1)
    ]


@pytest.mark.asyncio
async def test_company_list_search_limit_is_500() -> None:
    widget = CompanyList()
    assert widget.search_limit == 500


@pytest.mark.asyncio
async def test_company_list_vim_navigation_g_and_gg() -> None:
    results = _mock_results(10)
    mock_search = MagicMock(return_value=results)
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    app = CocliApp(services=services, auto_show=False)

    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)

        company_list = await wait_for_widget(driver, CompanyList)
        list_view = company_list.query_one("#company_list_view", ListView)
        list_view.focus()
        await driver.pause(0.1)

        assert len(list_view.children) == 10
        assert list_view.index == 0

        # Press 'G' to jump to bottom
        await driver.press("G")
        await driver.pause(0.1)
        assert list_view.index == 9

        # Press 'g' then 'g' within 500ms to jump to top
        await driver.press("g")
        await driver.press("g")
        await driver.pause(0.1)
        assert list_view.index == 0

        # Press 'end' to jump to bottom
        await driver.press("end")
        await driver.pause(0.1)
        assert list_view.index == 9

        # Press 'home' to jump to top
        await driver.press("home")
        await driver.pause(0.1)
        assert list_view.index == 0


@pytest.mark.asyncio
async def test_company_list_auto_paging_j_and_k() -> None:
    def fake_search(*args, limit=500, offset=0, **kwargs):
        # return 5 items per page up to 10 total
        return _mock_results(min(5, max(0, 10 - offset)), offset=offset)

    mock_search = MagicMock(side_effect=fake_search)
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    app = CocliApp(services=services, auto_show=False)

    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)

        company_list = await wait_for_widget(driver, CompanyList)
        company_list.search_limit = 5  # artificially lower limit to test pagination
        company_list.run_search("")
        await driver.pause(0.1)

        list_view = company_list.query_one("#company_list_view", ListView)
        list_view.focus()
        await driver.pause(0.1)

        assert len(list_view.children) == 5
        assert list_view.index == 0
        assert company_list.search_offset == 0

        # Jump to bottom of page 1
        list_view.index = 4
        await driver.pause(0.05)

        # Press 'j' at the bottom of the page -> auto-advances to page 2 (offset=5)
        await driver.press("j")
        await driver.pause(0.1)

        assert company_list.search_offset == 5
        assert list_view.index == 0
        assert str(company_list.filtered_fz_items[0].name) == "Company 6"

        # Press 'k' at index 0 of page 2 -> auto-retreats to page 1 (offset=0)
        await driver.press("k")
        await driver.pause(0.1)

        assert company_list.search_offset == 0
        assert list_view.index == 4
        assert str(company_list.filtered_fz_items[0].name) == "Company 1"
