"""`/` opens a filter row only while typing. Enter stamps the query on the header."""

from __future__ import annotations

import pytest
from textual.widgets import Label, ListView

from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.inputs import CocliSearchInput
from cocli.tui.widgets.list_filter import ListFilterState, applied_header
from cocli.tui.widgets.person_list import PersonList
from tests.tui.test_person_list import PersonListTestApp
from unittest.mock import MagicMock


def _header_text(label: Label) -> str:
    return str(label.content)


def test_applied_header_shows_the_query_only_after_commit() -> None:
    state = ListFilterState()
    state.committed = "acme"
    state.editing = True
    assert applied_header("SEARCH (2 results)", state) == "SEARCH (2 results)"
    state.editing = False
    assert applied_header("SEARCH (2 results)", state) == "SEARCH (2 results)  /acme"


@pytest.mark.asyncio
async def test_slash_hides_until_open_and_enter_marks_the_filter() -> None:
    services = ServiceContainer(
        search_service=MagicMock(
            return_value=[
                SearchResult(
                    name="Acme",
                    slug="acme",
                    type="company",
                    unique_id="acme",
                    tags=[],
                    display="",
                )
            ]
        ),
        sync_search=True,
    )
    app = CocliApp(services=services, auto_show=False)
    async with app.run_test() as driver:
        await app.action_show_companies()
        await driver.pause(0.3)
        company_list = app.query_one(CompanyList)
        search = company_list.query_one("#company_search_input", CocliSearchInput)
        header = company_list.query_one("#search_header", Label)
        assert not search.display

        company_list.query_one("#company_list_view", ListView).focus()
        await driver.pause(0.05)
        await driver.press("/")
        assert search.display
        assert search.has_focus
        await driver.press("a", "c", "m", "e")
        assert "/acme" not in _header_text(header)

        await driver.press("enter")
        assert not search.display
        assert "/acme" in _header_text(header)

        await driver.press("/")
        await driver.press("z")
        assert search.value == "z"
        await driver.press("escape")
        assert search.value == "acme"
        assert not search.display
        assert "/acme" in _header_text(header)
        assert "/z" not in _header_text(header)

        await driver.press("/")
        await driver.press("/")
        assert search.value == "/"


@pytest.mark.asyncio
async def test_person_slash_filter_uses_the_same_commit_rule() -> None:
    services = ServiceContainer(search_service=MagicMock(return_value=[]), sync_search=True)
    app = PersonListTestApp(services=services)
    async with app.run_test() as driver:
        await driver.pause(0.1)
        person_list = app.query_one(PersonList)
        search = person_list.query_one("#person_search_input", CocliSearchInput)
        header = person_list.query_one("#person_list_header", Label)
        assert not search.display

        await driver.press("/")
        await driver.press("b", "e", "n")
        assert "/ben" not in _header_text(header)
        await driver.press("enter")
        assert not search.display
        assert "/ben" in _header_text(header)
