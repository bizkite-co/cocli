# POLICY: frictionless-data-policy-enforcement
import pytest
from cocli.tui.app import CocliApp, CocliCommandProvider
from textual.command import CommandPalette

@pytest.mark.asyncio
async def test_command_palette_history_order(mocker):
    """
    Verify:
    1. Command palette shows 5 items by default (empty query).
    2. Using a command moves it to the top.
    """
    app = CocliApp(auto_show=False)
    
    # Pre-set history to known state
    app.command_history = ["Show People", "Show Companies", "Show Events", "Show Application", "Create Task"]
    
    async with app.run_test() as pilot:
        # 1. Open palette
        await pilot.press("ctrl+p")
        await pilot.pause(0.5)
        
        assert isinstance(app.screen, CommandPalette)
        palette = app.screen
        provider = next(p for p in palette._providers if isinstance(p, CocliCommandProvider))
        
        # Manually trigger search to inspect hits (Textual async generator)
        hits = []
        async for hit in provider.search(""):
            hits.append(hit)
            
        assert len(hits) >= 5
        # Top hit should be 'Show People' based on our preset history
        # (Hit score is 1.0, and they are yielded in order)
        # Note: Hit.command is the wrapped function
        # We check the display text via Hit.match_display
        assert "Show People" in str(hits[0].match_display)
        assert "Show Companies" in str(hits[1].match_display)

        # 2. Record a command use
        app.record_command("Create Task")
        assert app.command_history[0] == "Create Task"
        
        # 3. Check new order
        hits = []
        async for hit in provider.search(""):
            hits.append(hit)
        
        assert "Create Task" in str(hits[0].match_display)
        assert "Show People" in str(hits[1].match_display)
