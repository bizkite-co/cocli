from textual.binding import Binding
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


def test_ctrl_c_copies_instead_of_navigating_back() -> None:
    """Ctrl+C used to be bound to Back, so nothing in the TUI could be copied."""
    mapped: list[tuple[str, str]] = []
    for binding in CocliApp.BINDINGS:
        if isinstance(binding, Binding):
            mapped.append((binding.key, binding.action))
        else:
            mapped.append((str(binding[0]), str(binding[1])))
    assert ("ctrl+c", "copy_text") in mapped
    assert ("ctrl+c", "navigate_up") not in mapped


@pytest.mark.asyncio
async def test_right_click_copies_textual_selection() -> None:
    """Windows Terminal two-finger tap is a right-click. With mouse tracking
    on, WT does not copy that itself — the app has to."""
    from unittest.mock import patch

    from textual.events import MouseUp

    app = CocliApp(services=create_mock_services(), auto_show=False)
    async with app.run_test():
        with patch.object(app, "_selected_text_for_copy", return_value="555-123-4567"), patch.object(
            app, "copy_to_clipboard"
        ) as copy:
            event = MouseUp(None, 1, 1, 0, 0, 3, False, False, False)
            app.on_mouse_up(event)
            copy.assert_called_once_with("555-123-4567")

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
