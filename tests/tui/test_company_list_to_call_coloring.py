"""End-to-end: CompanyList's to-call view actually renders overdue/due-soon
rows with color, and leaves other filtered views (and never-scheduled
rows) uncolored (Mark, 2026-09-17)."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock

import pytest
from rich.text import Text
from textual.widgets import Label, ListView

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList
from cocli.models.search import SearchResult
from conftest import wait_for_widget


def _result(slug: str, callback_at: str | None) -> SearchResult:
    return SearchResult(
        type="company",
        name=slug.replace("-", " ").title(),
        slug=slug,
        display=slug,
        unique_id=slug,
        to_call_callback_at=callback_at,
    )


@pytest.mark.asyncio
async def test_to_call_view_colors_overdue_and_due_soon_rows() -> None:
    overdue = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    due_soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    mock_results = [
        _result("never-called-co", None),
        _result("overdue-co", overdue),
        _result("due-soon-co", due_soon),
    ]

    app = CocliApp(auto_show=False)
    app.services.search_service = MagicMock(return_value=mock_results)
    app.services.sync_search = True

    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")

        company_list_widget = await wait_for_widget(driver, CompanyList)
        company_list_widget.apply_template("tpl_to_call")
        company_list_widget.update_company_list_view()
        await driver.pause(0.1)

        list_view = company_list_widget.query_one("#company_list_view", ListView)
        renderables = {}
        for item in list_view.children:
            label = item.query_one(Label)
            renderables[getattr(item, "name")] = label._Static__content

        never_called = renderables["Never Called Co"]
        overdue_r = renderables["Overdue Co"]
        due_soon_r = renderables["Due Soon Co"]

        assert not isinstance(never_called, Text) or never_called.style == ""
        assert isinstance(overdue_r, Text) and overdue_r.style == "bold orange1"
        assert isinstance(due_soon_r, Text) and due_soon_r.style == "bold yellow"


@pytest.mark.asyncio
async def test_tpl_to_call_resets_sort_recent_so_the_dedicated_sort_actually_runs() -> None:
    """Mark, 2026-10-08: "we have tried to update the to-call list
    several times" - every earlier fix to search_service.py's dedicated
    to-call ORDER BY (testimonial-target tier, then priority, then
    most-overdue-first) was correct but never took effect: sort_recent
    defaults True from __init__ and nothing reset it for this template,
    so run_search()'s "sort_by = self.current_sort or ('recent' if
    self.sort_recent else None)" evaluated to "recent" instead of None,
    silently routing into an earlier, unrelated branch (plain
    last_modified DESC) every single time the to-call template was
    opened - confirmed live: that produced the exact order Mark saw
    (testimonial-target companies buried near the bottom, no overdue-
    first behavior at all)."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")

        company_list_widget = await wait_for_widget(driver, CompanyList)
        company_list_widget.sort_recent = True  # the pre-existing default
        company_list_widget.apply_template("tpl_to_call")

        assert company_list_widget.sort_recent is False
        assert company_list_widget.current_sort is None


@pytest.mark.asyncio
async def test_tpl_to_call_search_is_not_sorted_by_recent() -> None:
    """Same bug, exercised through the real search call: confirms
    run_search() actually passes sort_by=None (not "recent") to
    fuzzy_search() once the to-call template is applied."""
    app = CocliApp(auto_show=False)
    app.services.sync_search = True
    captured: dict[str, object] = {}

    def _fake_search_service(**kwargs: object) -> list:
        captured.update(kwargs)
        return []

    app.services.search_service = _fake_search_service

    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")

        company_list_widget = await wait_for_widget(driver, CompanyList)
        company_list_widget.apply_template("tpl_to_call")
        company_list_widget.run_search("")

        assert captured.get("sort_by") is None
        assert captured.get("filters") == {"to_call": True}


@pytest.mark.asyncio
async def test_non_to_call_view_never_colors_rows() -> None:
    """A company that happens to also be on the to-call queue must not
    show colored in an unrelated filtered/plain search view - coloring is
    scoped to the to-call view specifically."""
    overdue = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    mock_results = [_result("overdue-co", overdue)]

    app = CocliApp(auto_show=False)
    app.services.search_service = MagicMock(return_value=mock_results)
    app.services.sync_search = True

    async with app.run_test() as driver:
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")

        company_list_widget = await wait_for_widget(driver, CompanyList)
        company_list_widget.apply_template("tpl_all")
        company_list_widget.update_company_list_view()
        await driver.pause(0.1)

        list_view = company_list_widget.query_one("#company_list_view", ListView)
        label = list_view.children[0].query_one(Label)
        assert not isinstance(label._Static__content, Text)
