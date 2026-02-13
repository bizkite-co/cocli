import pytest
from unittest.mock import MagicMock
from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult

@pytest.mark.asyncio
async def test_search_with_injected_service():
    """
    Test that the TUI uses the injected service container instead of 
    relying on global imports and heavy patching.
    """
    # 1. Create a mock search service
    mock_search = MagicMock()
    mock_search.return_value = [
        SearchResult(
            name="Injected Company", 
            slug="injected-slug", 
            type="company", 
            unique_id="injected-slug",
            tags=[],
            display="Injected Company"
        )
    ]
    
    # 2. Create the container with the mock
    services = ServiceContainer(search_service=mock_search, sync_search=True)
    
    # 3. Pass the container to the App
    app = CocliApp(services=services, auto_show=False)
    
    async with app.run_test() as driver:
        # Show companies
        driver.app.action_show_companies()
        await driver.pause(0.1)
        
        # Verify the mock was called by the widget during mount
        # (CompanyList calls it on_mount)
        mock_search.assert_called()
