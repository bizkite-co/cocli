import pytest
import asyncio
from textual.widget import Widget
from textual.css.query import NoMatches
from typer.testing import CliRunner
from cocli.main import app

@pytest.fixture(scope="session")
def runner():
    return CliRunner()

@pytest.fixture(scope="session")
def cli_app():
    return app

async def wait_for_widget(driver, widget_type: type[Widget], timeout: float = 5.0) -> Widget:
    """Waits for a widget of the given type to appear in the DOM."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        try:
            return driver.app.query_one(widget_type)
        except NoMatches:
            await driver.pause(0.01) # Give Textual a chance to update the DOM
    raise TimeoutError(f"Widget of type {widget_type.__name__} did not appear within {timeout} seconds")