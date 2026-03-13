from textual.widgets import Label
import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp, MenuBar
from cocli.application.services import ServiceContainer
from cocli.tui.widgets.application_view import ApplicationView
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.person_list import PersonList
from conftest import wait_for_widget

def create_mock_services():
    mock_search = MagicMock()
    mock_search.return_value = []
    return ServiceContainer(search_service=mock_search, sync_search=True)

@pytest.mark.asyncio
async def test_header_is_visible():
    """Test that the MenuBar widget is visible on app startup."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await driver.pause(0.5)
        menu_bar = await wait_for_widget(driver, MenuBar)
        assert isinstance(menu_bar, MenuBar)
        assert menu_bar.visible

@pytest.mark.asyncio
async def test_leader_a_shows_application():
    """Test that Leader+a shows the ApplicationView widget."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await driver.pause(0.5)
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("a")
        await driver.pause(0.1)
        application_view = await wait_for_widget(driver, ApplicationView)
        assert isinstance(application_view, ApplicationView)

@pytest.mark.asyncio
async def test_leader_p_shows_people():
    """Test that Leader+p shows the PersonList widget."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await driver.pause(0.5)
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("p")
        await driver.pause(0.1)
        person_list = await wait_for_widget(driver, PersonList)
        assert isinstance(person_list, PersonList)

@pytest.mark.asyncio
async def test_leader_c_shows_companies():
    """Test that Leader+c shows the CompanyList widget."""
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await driver.pause(0.5)
        # Already there, but let's press anyway to verify the binding
        await driver.press("space")
        await driver.pause(0.1)
        await driver.press("c")
        await driver.pause(0.1)
        company_list = await wait_for_widget(driver, CompanyList)
        assert isinstance(company_list, CompanyList)

@pytest.mark.asyncio
async def test_campaign_override_display(monkeypatch):
    """Test that campaign override is indicated in the MenuBar with rich markup."""
    monkeypatch.setenv("COCLI_CAMPAIGN", "test_override")
    
    # We need to ensure ServiceContainer picks it up
    # In real app, it calls get_campaign() which reads the env var.
    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test() as driver:
        await driver.pause(0.5)
        menu_bar = await wait_for_widget(driver, MenuBar)
        
        # Find the application label in the menu bar
        app_label = menu_bar.query_one("#menu-application", Label)
        
        # In Textual, Static content is private
        markup = str(getattr(app_label, "_Static__content", ""))
        
        assert "test_override" in markup
        assert "bold white on blue" in markup
