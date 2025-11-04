import pytest

from textual.widgets import Header
from cocli.tui.app import CocliApp
from cocli.tui.widgets.prospect_menu import ProspectMenu
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.person_list import PersonList
from cocli.tui.widgets.campaign_selection import CampaignSelection
from conftest import wait_for_widget

@pytest.mark.asyncio
async def test_header_is_visible():
    """Test that the Header widget is visible on app startup."""
    app = CocliApp()
    async with app.run_test() as driver:
        header = await wait_for_widget(driver, Header)
        assert isinstance(header, Header)
        assert header.visible

@pytest.mark.asyncio
async def test_alt_shift_c_shows_campaigns():
    """Test that Alt+Shift+c shows the CampaignSelection widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("alt+shift+c")
        await driver.pause()
        campaign_selection = await wait_for_widget(driver, CampaignSelection)
        assert isinstance(campaign_selection, CampaignSelection)

@pytest.mark.asyncio
async def test_alt_shift_p_shows_people():
    """Test that Alt+Shift+p shows the PersonList widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("alt+shift+p")
        await driver.pause()
        person_list = await wait_for_widget(driver, PersonList)
        assert isinstance(person_list, PersonList)

@pytest.mark.asyncio
async def test_alt_c_shows_companies():
    """Test that Alt+c shows the CompanyList widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("alt+c")
        await driver.pause()
        company_list = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list, CompanyList)

@pytest.mark.asyncio
async def test_alt_p_shows_prospects():
    """Test that Alt+p shows the ProspectMenu widget."""
    app = CocliApp()
    async with app.run_test() as driver:
        await driver.press("alt+p")
        await driver.pause()
        prospect_menu = await wait_for_widget(driver, ProspectMenu)
        assert isinstance(prospect_menu, ProspectMenu)