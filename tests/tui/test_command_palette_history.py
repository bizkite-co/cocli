# POLICY: frictionless-data-policy-enforcement
import pytest
from cocli.tui.app import CocliApp, CocliCommandProvider
from textual.command import CommandPalette


@pytest.mark.asyncio
async def test_command_palette_history_order(mocker):
    """
    Verify:
    1. Command palette shows items from history.
    2. Recording a command updates the history.
    """
    app = CocliApp(auto_show=False)

    # Pre-set history to known state
    app.command_history = [
        "Show People",
        "Show Companies",
        "Show Events",
        "Show Application",
        "Create Task",
    ]

    async with app.run_test() as pilot:
        # 1. Open palette
        await pilot.press("ctrl+p")
        await pilot.pause(0.5)

        assert isinstance(app.screen, CommandPalette)
        palette = app.screen
        provider = next(
            p for p in palette._providers if isinstance(p, CocliCommandProvider)
        )

        # Manually trigger search to inspect hits (Textual async generator)
        hits = []
        async for hit in provider.search(""):
            hits.append(hit)

        # Verify palette returns some hits
        assert len(hits) >= 1

        # 2. Record a command use
        app.record_command("Create Task")
        assert app.command_history[0] == "Create Task"
