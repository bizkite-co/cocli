import pytest

from textual.widgets import Header
from unittest.mock import patch
from cocli.tui.app import CocliApp
from cocli.tui.widgets.prospect_menu import ProspectMenu
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.person_list import PersonList
from cocli.tui.widgets.campaign_selection import CampaignSelection
from conftest import wait_for_widget, wait_for_screen

@pytest.mark.asyncio
async def test_header_is_visible():
    """Test that the Header widget is visible on app startup."""
    app = CocliApp()
    async with app.run_test() as driver:
        header = await wait_for_widget(driver, Header)
        assert isinstance(header, Header)
        assert header.visible

@pytest.mark.asyncio
async def test_leader_a_shows_campaigns():
    """Test that Leader+a shows the CampaignSelection widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "a")
        campaign_selection = await wait_for_widget(driver, CampaignSelection)
        assert isinstance(campaign_selection, CampaignSelection)

@pytest.mark.asyncio
async def test_leader_p_shows_people():
    """Test that Leader+p shows the PersonList widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "p")
        person_list = await wait_for_widget(driver, PersonList)
        assert isinstance(person_list, PersonList)

@pytest.mark.asyncio
@patch('cocli.tui.widgets.company_list.get_fuzzy_search_results')
async def test_leader_c_shows_companies(mock_get_fz_items):
    """Test that Leader+c shows the CompanyList widget."""
    mock_get_fz_items.return_value = [] # Provide an empty list or a mock SearchResult
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "c")
        company_list = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list, CompanyList)

@pytest.mark.asyncio
async def test_leader_s_shows_prospects():
    """Test that Leader+s shows the ProspectMenu widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("space", "s")
        prospect_menu = await wait_for_screen(driver, ProspectMenu)
        assert isinstance(prospect_menu, ProspectMenu)
