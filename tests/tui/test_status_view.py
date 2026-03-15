# POLICY: frictionless-data-policy-enforcement
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from cocli.tui.widgets.status_view import StatusView

class StatusTestApp(App):
    """A minimal app to test StatusView."""
    def compose(self) -> ComposeResult:
        yield StatusView(id="view_status")

@pytest.mark.asyncio
async def test_status_view_hydration(mocker):
    """
    Verify that StatusView correctly hydrates and displays Data Root and S3 Remote.
    """
    app = StatusTestApp()
    
    # Mock reporting service
    mock_env = {
        "campaign": "test-campaign",
        "context": "test-context",
        "strategy": "Mock Strategy",
        "strategy_details": ["Detail 1"],
        "data_root": "/mock/data/root",
        "s3_data_root": "s3://mock-bucket"
    }
    
    mock_services = mocker.Mock()
    mock_services.reporting_service.campaign_name = "test-campaign"
    mock_services.reporting_service.get_environment_status.return_value = mock_env
    mock_services.reporting_service.load_cached_report.return_value = None
    app.services = mock_services
    
    async with app.run_test() as pilot:
        view = app.query_one("#view_status", StatusView)
        
        # Wait for hydration worker
        import time
        start = time.time()
        while view.status_data is None and time.time() - start < 5:
            await pilot.pause(0.2)
            
        assert view.status_data == mock_env
        
        # Verify "Loading" message is gone
        body = view.query_one("#status_body")
        for child in body.children:
            if isinstance(child, Static):
                # Using hasattr/getattr for robustness across Textual versions
                content = str(getattr(child, "renderable", getattr(child, "_renderable", "")))
                if "Loading" in content:
                    pytest.fail("Loading message still present after hydration")
        
        assert len(body.children) >= 1
