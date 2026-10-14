from unittest.mock import patch

import pytest
from textual.command import CommandPalette

from cocli.tui.app import CocliApp, CocliCommandProvider
from cocli.tui.calling_palette import CallingCommandResult
from cocli.tui.widgets.confirm_screen import ConfirmScreen
from cocli.tui.widgets.content_viewer_modal import ContentViewerModal


async def _provider(app: CocliApp) -> CocliCommandProvider:
    palette = app.screen
    assert isinstance(palette, CommandPalette)
    return next(p for p in palette._providers if isinstance(p, CocliCommandProvider))


@pytest.mark.asyncio
async def test_palette_search_finds_sync_messages() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.05)
        provider = await _provider(app)
        hits = [hit.text async for hit in provider.search("sync-messages")]
        assert "calling sync-messages" in hits
        hits = [hit.text async for hit in provider.search("calling phone-status")]
        assert "calling phone-status" in hits


@pytest.mark.asyncio
async def test_palette_sync_messages_notifies_the_result() -> None:
    app = CocliApp(auto_show=False)

    def fake(_action_id: str) -> CallingCommandResult:
        return CallingCommandResult("Synced 2 SMS messages (1 matched, 1 in inbox).")

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.05)
        with patch("cocli.tui.calling_palette.execute_calling_command", fake):
            with patch.object(app, "notify") as mock_notify:
                await pilot.press(*"calling sync-messages")
                await pilot.pause(0.05)
                await pilot.press("enter")
                await pilot.pause(0.4)
        messages = [call.args[0] for call in mock_notify.call_args_list]
        assert any("Synced 2 SMS" in message for message in messages)


@pytest.mark.asyncio
async def test_palette_test_sms_asks_before_sending() -> None:
    app = CocliApp(auto_show=False)

    def fake(_action_id: str) -> CallingCommandResult:
        raise AssertionError("test-sms ran without confirmation")

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.05)
        with patch("cocli.tui.calling_palette.execute_calling_command", fake):
            await pilot.press(*"calling test-sms")
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.press("n")
            await pilot.pause(0.2)
        assert not isinstance(app.screen, ConfirmScreen)


@pytest.mark.asyncio
async def test_palette_set_twilio_shows_the_cli_form() -> None:
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.05)
        await pilot.press(*"calling set-twilio")
        await pilot.pause(0.05)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ContentViewerModal)
        content = app.screen.query_one("#viewer_content")
        assert "set-twilio" in str(content.render())
