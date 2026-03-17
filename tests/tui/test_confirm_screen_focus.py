import pytest
from unittest.mock import MagicMock
from cocli.tui.widgets.confirm_screen import ConfirmScreen
from textual.app import App


@pytest.mark.asyncio
async def test_confirm_screen_captures_keys_when_focused():
    """Test that ConfirmScreen captures keys when focused."""
    app = App()
    async with app.run_test() as pilot:
        screen = ConfirmScreen("Remove Company?")
        await pilot.app.push_screen(screen)

        # Mock the dismiss method
        screen.dismiss = MagicMock()

        # Simulate 'y'
        await pilot.press("y")

        # Verify
        screen.dismiss.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_confirm_screen_focus_on_mount():
    """Test that ConfirmScreen gains focus when mounted."""
    app = App()
    async with app.run_test() as pilot:
        screen = ConfirmScreen("Remove Company?")

        # Push the modal
        await pilot.app.push_screen(screen)
        await pilot.pause()

        dialog = screen.query_one("#confirm-dialog")
        dialog.focus = MagicMock()

        # Trigger on_mount
        screen.on_mount()

        # Verify focus was called
        dialog.focus.assert_called_once()
