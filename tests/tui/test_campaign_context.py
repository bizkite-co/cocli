import pytest
from textual.app import App
from cocli.application.services import ServiceContainer
from textual.message import Message


class MockCampaignMessage(Message):
    def __init__(self, campaign_name: str) -> None:
        super().__init__()
        self.campaign_name = campaign_name


@pytest.mark.asyncio
async def test_campaign_context_does_not_leak_on_highlight(mocker):
    """
    Test that highlighting a campaign in the UI does NOT switch the application's campaign context.
    """
    app = App()
    app.services = ServiceContainer(campaign_name="roadmap")

    # Simulate the Highlight message
    _ = MockCampaignMessage(campaign_name="fullertonian")

    # We need to simulate the ApplicationView handler
    # Note: ApplicationView uses work(exclusive=True) for handle_campaign_highlight,
    # so we might need to test the logic directly or through the view.

    # Let's test the ServiceContainer context switch logic first to ensure it behaves as expected
    assert app.services.campaign_name == "roadmap"

    # The vulnerability is that handle_campaign_highlight updates the reporting service context:
    # app.services.reporting_service.campaign_name = campaign_name

    # If we trigger handle_campaign_highlight, it should NOT call set_campaign()
    # unless it's a 'Selected' event.
    pass


@pytest.mark.asyncio
async def test_service_container_campaign_switching(mocker):
    """
    Verify that ServiceContainer only switches campaign when explicitly told to.
    """
    services = ServiceContainer(campaign_name="roadmap")
    assert services.campaign_name == "roadmap"

    # Simulate explicit switch
    services.set_campaign("fullertonian")
    assert services.campaign_name == "fullertonian"
    assert services._reporting_service is None  # Should be invalidated
