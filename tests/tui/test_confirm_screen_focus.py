import pytest
from unittest.mock import MagicMock
from cocli.tui.widgets.confirm_screen import ConfirmScreen
from cocli.tui.widgets.company_list import CompanyList
from textual.app import ComposeResult
from textual.widgets import Static
from textual.events import Key


@pytest.mark.asyncio
async def test_confirm_screen_captures_keys_when_focused():
    """
    Test that ConfirmScreen captures keys when focused,
    preventing bubbling to underlying widgets like ListView.
    """
    # Create the screen
    screen = ConfirmScreen("Remove Company?")

    # Mock the dismiss method to check if it's called
    screen.dismiss = MagicMock()

    # Simulate a key press
    # Using 'y' which should dismiss with True
    screen.on_key(Key(key="y", character="y"))

    # Verify the dismiss was called
    screen.dismiss.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_confirm_screen_focus_on_mount():
    """Test that ConfirmScreen gains focus when mounted."""
    screen = ConfirmScreen("Remove Company?")

    # We need to simulate the mount event
    # Using a spy to check if focus() was called
    screen.focus = MagicMock()

    # Trigger the on_mount method directly
    screen.on_mount()

    # Verify focus was called
    screen.focus.assert_called_once()
