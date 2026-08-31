import pytest
from cocli.tui.app import CocliApp, CocliCommandProvider
from cocli.tui.widgets.application_view import ApplicationView
from textual.command import CommandPalette
from textual.widgets import ListView


@pytest.mark.asyncio
async def test_command_palette_shows_hits_before_typing():
    """Regression (Mark, 2026-08-31): Ctrl+P opened to a blank list every
    time - CocliCommandProvider only implemented search(), but Textual's
    CommandPalette shows discover() results before any typing and only
    switches to search() once there's a query
    (textual/command.py: `hits = self.search(query) if query else
    self.discover()`)."""
    app = CocliApp(auto_show=False)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)

        assert isinstance(app.screen, CommandPalette)
        palette = app.screen
        provider = next(
            p for p in palette._providers if isinstance(p, CocliCommandProvider)
        )

        discovered = [hit async for hit in provider.discover()]
        assert len(discovered) >= 1

        option_list = palette.query_one("OptionList")
        assert option_list.option_count >= 1


@pytest.mark.asyncio
async def test_running_a_command_moves_it_to_the_top_of_mru():
    app = CocliApp(auto_show=False)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)

        palette = app.screen
        provider = next(
            p for p in palette._providers if isinstance(p, CocliCommandProvider)
        )

        before = [hit.text for hit in [h async for h in provider.discover()]]
        assert before[0] != "Show Events"

        app.update_command_mru("Show Events")

        after = [hit.text for hit in [h async for h in provider.discover()]]
        assert after[0] == "Show Events"


@pytest.mark.asyncio
async def test_alt_s_closes_the_command_palette():
    """Regression (Mark, 2026-08-31): "alt+s doesn't escape from ^p. It's
    supposed to be a general keymap for escape." Confirmed: plain escape
    already closed the palette (Textual's own CommandPalette binding), but
    alt+s (and meta+s) didn't - CocliApp's own alt+s BINDING
    (action_navigate_up) never gets a chance to fire while a pushed Screen
    like CommandPalette is active, since Textual's screens don't forward
    unmatched keys up to the App's BINDINGS. CommandPalette has no idea
    about cocli's alt+s-as-escape convention, so the keypress was
    previously just silently swallowed."""
    app = CocliApp(auto_show=False)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)
        assert isinstance(app.screen, CommandPalette)

        await pilot.press("alt+s")
        await pilot.pause(0.3)
        assert not isinstance(app.screen, CommandPalette)


@pytest.mark.asyncio
async def test_palette_finds_to_call_operation_and_navigates_to_it():
    """Regression (Mark, 2026-08-31): "I still don't see anything in the
    ^p for 'to-call', or 'call'." The 9-command hand-picked list never
    included OperationService's registry at all - op_compile_to_call (the
    To-Call queue's purge+reload) is now in there, and selecting it
    navigates to ApplicationView's Operations panel with that exact
    operation highlighted and focused, rather than executing it blind
    (several operations take parameters - limit/purge for this one - that
    the palette has no UI to set)."""
    app = CocliApp(auto_show=False)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)
        palette = app.screen
        provider = next(
            p for p in palette._providers if isinstance(p, CocliCommandProvider)
        )

        for query in ("to-call", "call"):
            hits = [h.text for h in [hit async for hit in provider.search(query)]]
            assert any("To-Call" in h for h in hits), f"query={query!r} hits={hits}"

        for ch in "to-call":
            await pilot.press(ch)
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.5)

        assert not isinstance(app.screen, CommandPalette)
        app_view = app.query_one(ApplicationView)
        list_view = app_view.query_one("#sidebar_operations", ListView)
        highlighted = list_view.highlighted_child
        assert highlighted is not None and highlighted.id == "op_compile_to_call"
        assert app.focused is list_view
