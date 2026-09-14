"""SearchSelect: keyboard-only filterable single-select, not a GUI dropdown.

Built to replace Textual's Select widget in call_log_modal.py - this TUI's
convention is an always-visible, keyboard-navigable list, not a collapsed
popup menu. See conversation 2026-09-14.
"""

from __future__ import annotations

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.search_select import SearchSelect

CHOICES = [
    ("Follow Up Needed", "Follow Up Needed"),
    ("Interested / Qualified", "Interested"),
    ("Not Interested", "Not Interested"),
    ("Wrong Trade / No Fit", "Wrong Trade / No Fit"),
    ("Bad Number", "Bad Number"),
]


@pytest.mark.asyncio
async def test_initial_value_is_highlighted() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test():
        widget = SearchSelect(CHOICES, initial_value="Not Interested", id="ds")
        await app.query_one("#app_content").mount(widget)
        assert widget.value == "Not Interested"


@pytest.mark.asyncio
async def test_typing_filters_the_visible_list() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        widget = SearchSelect(CHOICES, id="ds")
        await app.query_one("#app_content").mount(widget)
        await pilot.pause()
        widget.focus_filter()
        await pilot.pause()

        await pilot.press(*"trade")
        await pilot.pause()

        assert widget._filtered == [("Wrong Trade / No Fit", "Wrong Trade / No Fit")]


@pytest.mark.asyncio
async def test_enter_selects_the_highlighted_choice() -> None:
    """Checking widget.value (set synchronously in _select_current before
    the message posts) rather than capturing the Selected message itself -
    overriding post_message on a live widget instance breaks Textual's own
    internal message loop and hangs the test app, it isn't just a hook
    point for consumer messages."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        widget = SearchSelect(CHOICES, id="ds")
        await app.query_one("#app_content").mount(widget)
        await pilot.pause()
        widget.focus_filter()
        await pilot.pause()

        await pilot.press(*"bad")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert widget.value == "Bad Number"


@pytest.mark.asyncio
async def test_down_arrow_moves_selection_without_typing() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        widget = SearchSelect(CHOICES, id="ds")
        await app.query_one("#app_content").mount(widget)
        await pilot.pause()
        widget.focus_filter()
        await pilot.pause()

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        assert widget.value == "Interested"


@pytest.mark.asyncio
async def test_empty_filter_result_does_not_crash_on_enter() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        widget = SearchSelect(CHOICES, id="ds")
        await app.query_one("#app_content").mount(widget)
        await pilot.pause()
        widget.focus_filter()
        await pilot.pause()

        await pilot.press(*"zzzzz")
        await pilot.pause()
        assert widget._filtered == []

        await pilot.press("enter")
        await pilot.pause()
