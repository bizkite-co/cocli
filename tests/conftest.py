import pytest
import asyncio
from textual.widget import Widget
from textual.css.query import NoMatches
from typer.testing import CliRunner
from cocli.main import app
from textual.screen import Screen

@pytest.fixture(scope="session")
def runner():
    return CliRunner()

@pytest.fixture(scope="session")
def cli_app():
    return app

async def wait_for_widget(driver, widget_type: type[Widget], timeout: float = 30.0) -> Widget:
    """Waits for a widget of the given type to appear in the DOM or be the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        # Check if it's the active screen
        if issubclass(widget_type, Screen) and isinstance(driver.app.screen, widget_type):
            return driver.app.screen
        try:
            return driver.app.query_one(widget_type)
        except NoMatches:
            await asyncio.sleep(0.01) # Give Textual a chance to update the DOM
    raise TimeoutError(f"Widget of type {widget_type.__name__} did not appear within {timeout} seconds")

async def wait_for_screen(driver, screen_type: type[Screen], timeout: float = 30.0) -> Screen:
    """Waits for a screen of the given type to become the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        if isinstance(driver.app.screen, screen_type):
            return driver.app.screen
        await asyncio.sleep(0.01) # Give Textual a chance to update the screen stack
    raise TimeoutError(f"Screen of type {screen_type.__name__} did not become active within {timeout} seconds")