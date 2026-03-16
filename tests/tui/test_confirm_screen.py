import pytest
from unittest.mock import MagicMock
from cocli.tui.widgets.confirm_screen import ConfirmScreen
from textual.app import ComposeResult
from textual.widgets import Static


@pytest.mark.asyncio
async def test_confirm_screen_y():
    """Test that pressing 'y' on the ConfirmScreen returns True."""
    screen = ConfirmScreen("Test Confirmation?")

    # Test internal state/behavior if possible, or mock the dismiss
    screen.dismiss = MagicMock()

    # Simulate pressing 'y'
    from textual.events import Key

    screen.on_key(Key(key="y", character="y"))

    screen.dismiss.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_confirm_screen_n():
    """Test that pressing 'n' on the ConfirmScreen returns False."""
    screen = ConfirmScreen("Test Confirmation?")

    # Test internal state/behavior if possible, or mock the dismiss
    screen.dismiss = MagicMock()

    # Simulate pressing 'n'
    from textual.events import Key

    screen.on_key(Key(key="n", character="n"))

    screen.dismiss.assert_called_once_with(False)
