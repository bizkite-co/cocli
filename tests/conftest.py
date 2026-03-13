import os
import tempfile
import sys
import asyncio
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch as module_patch

import pytest
from textual.app import Screen
from textual.widget import Widget
from typer.testing import CliRunner
from playwright.async_api import async_playwright

# GLOBAL ISOLATION: Set this BEFORE any cocli imports
# This ensures the DataPaths singleton initializes to a safe temp location
_TEST_DATA_HOME = Path(tempfile.gettempdir()) / "cocli_test_data"
os.environ["COCLI_DATA_HOME"] = str(_TEST_DATA_HOME)

# DISABLE Zeroconf/Gossip globally for ALL tests
# Prevent any zeroconf background activity
sys.modules['zeroconf'] = MagicMock()
# Mock Gossip Bridge components before they are imported by anything else
# Use a mock object with heartbeats attribute to support TUI tests
mock_bridge = MagicMock()
mock_bridge.heartbeats = {}
module_patch('cocli.core.gossip_bridge.bridge', mock_bridge).start()
module_patch('cocli.core.gossip_bridge.GossipBridge', MagicMock()).start()
# Also stub start/stop on the class level if anything tries to instantiate it
module_patch('cocli.core.gossip_bridge.GossipBridge.start', lambda x: None).start()
module_patch('cocli.core.gossip_bridge.GossipBridge.stop', lambda x: None).start()
module_patch('cocli.core.gossip_bridge.Zeroconf', MagicMock()).start()
module_patch('cocli.core.gossip_bridge.ServiceBrowser', MagicMock()).start()

@pytest.fixture(scope="session")
def runner():
    return CliRunner()

@pytest.fixture(scope="session")
def cli_app():
    # Lazy import to satisfy lint while maintaining isolation
    main_mod = importlib.import_module("cocli.main")
    return main_mod.app

def get_op_secret(op_path):
    """Fetches a secret from 1Password using unified utility."""
    from cocli.utils.op_utils import get_op_secret as unified_get_secret
    secret = unified_get_secret(op_path)
    if not secret:
        raise Exception(f"Failed to read secret from 1Password: {op_path}")
    return secret

@pytest.fixture(scope="session")
def campaign_config():
    config_mod = importlib.import_module("cocli.core.config")
    return config_mod.load_campaign_config("roadmap")

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
            # If selector is provided, use it. Try exact match first, then broader query.
            if selector:
                # First try direct query on the app
                node = None
                try:
                    # Look for the exact selector
                    results = driver.app.query(selector)
                    if results:
                        node = results.first()
                except Exception:
                    pass
                
                # If not found, try searching children of parent_widget if provided
                if not node and parent_widget:
                    try:
                        results = parent_widget.query(selector)
                        if results:
                            node = results.first()
                    except Exception:
                        pass
                
                # If found, check type
                if node and isinstance(node, widget_type):
                    return node
            else:
                # No selector, search by type
                query = widget_type.__name__
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
    paths_mod = importlib.import_module("cocli.core.paths")
    mocker.patch.object(paths_mod.paths, 'root', cocli_base_dir)
    
    # Also redirect COCLI_CONFIG_HOME via environment
    os.environ["COCLI_CONFIG_HOME"] = str(cocli_base_dir / "config")
    
    # 3. Mock Configuration
    # Ensure get_campaign returns a predictable value ('test/default')
    # We use a nested name to verify namespace awareness in tests
    test_campaign_name = "test/default"
    config_mod = importlib.import_module("cocli.core.config")
    mocker.patch.object(config_mod, 'get_campaign', return_value=test_campaign_name)
    
    search_mod = importlib.import_module("cocli.application.search_service")
    mocker.patch.object(search_mod, 'get_campaign', return_value=test_campaign_name)
    
    # Also patch cache getters to ensure they use our temp dir logic (via paths)
    cache_mod = importlib.import_module("cocli.core.cache")
    mocker.patch.object(cache_mod, 'get_cocli_base_dir', return_value=cocli_base_dir)
    
    # Ensure config path points to temp
    mocker.patch.object(config_mod, 'get_config_dir', return_value=cocli_base_dir / "config")
    
    return cocli_base_dir
