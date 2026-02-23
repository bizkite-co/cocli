# POLICY: frictionless-data-policy-enforcement
import pytest
from textual.widgets import Input
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_list import CompanyList

@pytest.mark.asyncio
async def test_search_input_not_hijacked_by_shortcuts():
    """
    Verifies that typing characters that match shortcuts (f, r, s, a) 
    into the search input does NOT trigger those shortcuts.
    """
    app = CocliApp()
    async with app.run_test() as pilot:
        # 1. Ensure we are on the companies tab
        await pilot.press("c") 
        
        # 2. Focus the search input
        # Press 's' to focus search (this is our shortcut)
        await pilot.press("s")
        assert app.focused.id == "company_search_input"
        
        # 3. Simulate typing "fire" 
        # 'f' is Toggle Actionable, 'r' is Toggle Recent
        # We want to make sure the search input gets the keys AND the filter doesn't toggle
        
        company_list = app.query_one(CompanyList)
        # Ensure we know the starting state
        company_list.filter_contact = True 
        initial_filter_state = company_list.filter_contact
        
        # Type letters individually to ensure they go to the focused widget
        for char in "fire":
            await pilot.press(char)
        
        # 4. Verify the input value is exactly "fire"
        search_input = app.query_one("#company_search_input", Input)
        assert search_input.value == "fire", f"Search input hijacked! Value is '{search_input.value}' instead of 'fire'"
        
        # 5. Verify the filter state hasn't changed
        assert company_list.filter_contact == initial_filter_state, "Shortcut 'f' was triggered while typing!"
