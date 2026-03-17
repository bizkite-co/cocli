import pytest
from unittest.mock import MagicMock
from textual.app import App, ComposeResult
from textual.widgets import ListView, ListItem, Label
from cocli.tui.widgets.confirm_screen import ConfirmScreen


# Mocking the app structure to test event propagation
class MockApp(App):
    def compose(self) -> ComposeResult:
        self.list_view = ListView(ListItem(Label("Item")), id="company_list_view")
        yield self.list_view


@pytest.mark.asyncio
async def test_modal_prevents_propagation_to_list():
    """
    Test that when a ConfirmScreen is active,
    pressing 'y' does NOT trigger actions in the ListView.
    """
    app = MockApp()

    # We need to simulate the app running to have a DOM
    async with app.run_test() as pilot:
        # Get reference to the list view
        list_view = app.query_one("#company_list_view", ListView)

        # Verify initial focus
        list_view.focus()
        assert list_view.has_focus

        # Push the modal
        modal = ConfirmScreen("Remove?")
        await pilot.app.push_screen(modal)

        # Wait for the screen to be mounted
        await pilot.pause()

        # Access the modal screen
        screen = pilot.app.screen

        # Verify that the dialog inside the screen has focus
        dialog = screen.query_one("#confirm-dialog")
        dialog.focus()
        await pilot.pause()
        assert dialog.has_focus

        # Spy on list_view.action_select_cursor or similar to check if it's called
        list_view.action_select_cursor = MagicMock()

        # Simulate pressing 'y'
        await pilot.press("y")

        # Verify the modal dismissed, and list view was NOT acted upon
        # Screen is dismissed when push_screen returns.
        # Since we are using push_screen in tests, we check if screen is still active.
        assert app.screen is not screen
        list_view.action_select_cursor.assert_not_called()
