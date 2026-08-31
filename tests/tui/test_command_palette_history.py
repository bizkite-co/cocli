import pytest
from cocli.tui.app import CocliApp, CocliCommandProvider
from textual.command import CommandPalette


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
