import asyncio
import subprocess
from textual.app import Screen
from textual.widget import Widget
from textual.css.query import NoMatches
from typer.testing import CliRunner
import pytest
from cocli.main import app
from cocli.core.config import load_campaign_config
from playwright.async_api import async_playwright


@pytest.fixture(scope="session")
def runner():
    return CliRunner()

@pytest.fixture(scope="session")
def cli_app():
    return app

def get_op_secret(op_path):
    """Fetches a secret from 1Password CLI."""
    result = subprocess.run(["op", "read", op_path], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to read secret from OP: {result.stderr}")
    return result.stdout.strip()

@pytest.fixture(scope="session")
def campaign_config():
    return load_campaign_config("roadmap")

@pytest.fixture(scope="session")
def auth_creds(campaign_config):
    aws_config = campaign_config.get("aws", {})
    username_path = aws_config.get("cocli_op_test_username")
    password_path = aws_config.get("cocli_op_test_password")
    
    if not username_path or not password_path:
        pytest.skip("OP test credentials paths not found in config.")
        
    username = get_op_secret(username_path)
    password = get_op_secret(password_path)
    return {"username": username, "password": password}

@pytest.fixture
async def page():
    """Fixture that provides a playwright page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        yield page
        await browser.close()

@pytest.fixture
def visible_locator():
    """Fixture that returns a helper to find the visible element among multiple matches."""
    async def _locator(page, selector):
        loc = page.locator(selector)
        count = await loc.count()
        for i in range(count):
            element = loc.nth(i)
            if await element.is_visible():
                return element
        return loc.first
    return _locator

async def wait_for_screen(driver, screen_type: type[Screen], timeout: float = 60.0) -> Screen:
    """Waits for a screen of the given type to become the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        if isinstance(driver.app.screen, screen_type):
            return driver.app.screen
        await asyncio.sleep(0.01) # Give Textual a chance to update the screen stack
    raise TimeoutError(f"Screen of type {screen_type.__name__} did not become active within {timeout} seconds")

async def wait_for_widget(driver, widget_type: type[Widget], selector: str | None = None, parent_widget: Widget | None = None, timeout: float = 60.0) -> Widget:
    """Waits for a widget of the given type to appear in the DOM or be the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        # Check if it's the active screen
        if issubclass(widget_type, Screen) and isinstance(driver.app.screen, widget_type):
            return driver.app.screen
        try:
            query = f"{widget_type.__name__}{selector or ''}"
            if parent_widget:
                return parent_widget.query_one(query, widget_type)
            else:
                return driver.app.query_one(query, widget_type)
        except NoMatches:
            await asyncio.sleep(0.01) # Give Textual a chance to update the DOM
    raise TimeoutError(f"Widget of type {widget_type.__name__} with selector '{selector}' did not appear within {timeout} seconds")

async def wait_for_campaign_detail_update(detail_widget, timeout: float = 60.0):
    """Waits for the CampaignDetail widget to have its campaign attribute set."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        if detail_widget.campaign is not None:
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"CampaignDetail widget did not update its campaign within {timeout} seconds")
