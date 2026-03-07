import os
import tempfile
from pathlib import Path

# GLOBAL ISOLATION: Set this BEFORE any cocli imports
# This ensures the DataPaths singleton initializes to a safe temp location
_TEST_DATA_HOME = Path(tempfile.gettempdir()) / "cocli_test_data"
os.environ["COCLI_DATA_HOME"] = str(_TEST_DATA_HOME)

import asyncio  # noqa: E402
import subprocess  # noqa: E402
from textual.app import Screen  # noqa: E402
from textual.widget import Widget  # noqa: E402
  # noqa: E402
from typer.testing import CliRunner  # noqa: E402
import pytest  # noqa: E402
from cocli.main import app  # noqa: E402
from cocli.core.config import load_campaign_config  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402


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

async def wait_for_screen(driver, screen_type: type[Screen], timeout: float = 5.0) -> Screen:
    """Waits for a screen of the given type to become the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        if isinstance(driver.app.screen, screen_type):
            return driver.app.screen
        await asyncio.sleep(0.01) # Give Textual a chance to update the screen stack
    raise TimeoutError(f"Screen of type {screen_type.__name__} did not become active within {timeout} seconds")

async def wait_for_widget(driver, widget_type: type[Widget], selector: str | None = None, parent_widget: Widget | None = None, timeout: float = 5.0) -> Widget:
    """Waits for a widget of the given type to appear in the DOM or be the active screen."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        # Check if it's the active screen
        if issubclass(widget_type, Screen) and isinstance(driver.app.screen, widget_type):
            return driver.app.screen
        try:
            # If selector is provided, use it (optionally with type)
            # If no selector, use just the type name
            if selector:
                query = selector
            else:
                query = widget_type.__name__
            
            if parent_widget:
                # Use query() + first() to be more robust than query_one()
                results = parent_widget.query(query)
                if results:
                    node = results.first()
                    if isinstance(node, widget_type):
                        return node
            else:
                results = driver.app.query(query)
                if results:
                    node = results.first()
                    if isinstance(node, widget_type):
                        return node
        except Exception:
            pass
        
        await asyncio.sleep(0.01) # Give Textual a chance to update the DOM
    raise TimeoutError(f"Widget of type {widget_type.__name__} with selector '{selector}' did not appear within {timeout} seconds")

async def wait_for_campaign_detail_update(detail_widget, timeout: float = 5.0):
    """Waits for the CampaignDetail widget to have its campaign attribute set."""
    expires = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < expires:
        if detail_widget.campaign is not None:
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"CampaignDetail widget did not update its campaign within {timeout} seconds")

@pytest.fixture
def mock_cocli_env(tmp_path, mocker):
    """
    Sets up a completely isolated cocli environment in a temporary directory.
    Redirects global paths and mocks campaign configuration.
    """
    # 1. Create Directory Structure
    cocli_base_dir = tmp_path / "cocli"
    cocli_base_dir.mkdir()
    
    (cocli_base_dir / "companies").mkdir()
    (cocli_base_dir / "people").mkdir()
    (cocli_base_dir / "campaigns").mkdir()
    (cocli_base_dir / "config").mkdir()

    # Create a visual watermark company in the test environment
    test_company_dir = cocli_base_dir / "companies" / "test-company"
    test_company_dir.mkdir()
    (test_company_dir / "_index.md").write_text("---\nname: TEST-COMPANY\ntags: [test]\n---")

    # 2. Redirect Global Paths
    # We patch the 'root' property of the 'paths' singleton
    from cocli.core.paths import paths
    mocker.patch.object(paths, 'root', cocli_base_dir)
    
    # 3. Mock Configuration
    # Ensure get_campaign returns a predictable value ('test/default')
    # We use a nested name to verify namespace awareness in tests
    test_campaign_name = "test/default"
    mocker.patch('cocli.core.config.get_campaign', return_value=test_campaign_name)
    mocker.patch('cocli.application.search_service.get_campaign', return_value=test_campaign_name)
    
    # Also patch cache getters to ensure they use our temp dir logic (via paths)
    mocker.patch('cocli.core.cache.get_cocli_base_dir', return_value=cocli_base_dir)
    
    # Ensure config path points to temp
    mocker.patch('cocli.core.config.get_config_dir', return_value=cocli_base_dir / "config")
    
    return cocli_base_dir
    
    return cocli_base_dir
