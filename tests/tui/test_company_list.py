import pytest
from unittest.mock import MagicMock, patch
from cocli.tui.widgets.company_list import CompanyList
from cocli.tui.widgets.company_detail import CompanyDetail
from textual.widgets import ListView
from conftest import wait_for_widget


from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.models.search import SearchResult

# Mock data for the detail screen
mock_detail_data = {
    "company": {"name": "Selected Company", "slug": "selected-company", "domain": "selected.com"},
    "tags": [], "content": "", "website_data": None, "contacts": [], "meetings": [], "notes": []
}

@pytest.mark.asyncio
async def test_company_selection_integration():
    """Test full company selection flow from main menu to detail screen."""
    # Arrange
    mock_search = MagicMock()
    mock_search.return_value = [
        SearchResult(name="Test Company", slug="test-company", domain="test.com", type="company", unique_id="test-company", tags=[], display=""),
    ]
    
    mock_company_service = MagicMock()
    mock_company_service.return_value = mock_detail_data
    
    services = ServiceContainer(
        search_service=mock_search,
        company_service=mock_company_service,
        sync_search=True
    )

    app = CocliApp(services=services, auto_show=False)

    # Act & Assert
    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        await driver.pause(1.0)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        # --- Direct Message Capture ---
        posted_messages = []
        original_post_message = company_list_screen.post_message
        def new_post_message(message):
            posted_messages.append(message)
            return original_post_message(message)
        company_list_screen.post_message = new_post_message
        # ----------------------------

        assert isinstance(company_list_screen, CompanyList)

        # Move focus from the search input to the list view
        list_view = company_list_screen.query_one(ListView)
        list_view.focus()
        await driver.pause(0.1)
        list_view.index = 0
        await driver.pause(0.1)
        list_view.action_select_cursor()
        await driver.pause(0.1)

        assert len(posted_messages) > 0, "No messages were posted"
        assert any(msg.__class__.__name__ == 'CompanySelected' for msg in posted_messages), "CompanySelected message was not posted"

        company_detail = await wait_for_widget(driver, CompanyDetail)
        await driver.pause(0.1)
        assert isinstance(company_detail, CompanyDetail)
        mock_company_service.assert_called_once_with("test-company")


@pytest.mark.asyncio
async def test_selecting_an_unmaterialized_lead_notifies_instead_of_silent_bell():
    """Regression (Mark, 2026-08-31): "several of them show the preview,
    but do not navigate to the detail when I press ENTER or l." Root
    cause: a "lead" in the list can come from raw prospects data
    (google_maps_prospects checkpoint) that was never materialized into a
    companies/<slug>/ directory - get_company_details_for_view() requires
    that directory and returns None otherwise (confirmed ~47% of "All
    Leads" for roadmap have no directory at all). The preview pane never
    hit this - it renders straight from the search result, no filesystem
    lookup - so a lead could preview fine and still fail to open. The old
    handler was `else: self.bell()` with zero logging, indistinguishable
    from a real crash. Now it must notify with a diagnosable message."""
    mock_search = MagicMock()
    mock_search.return_value = [
        SearchResult(
            name="Unmaterialized Lead",
            slug="unmaterialized-lead",
            domain=None,
            type="company",
            unique_id="unmaterialized-lead",
            tags=[],
            display="",
        ),
    ]
    mock_company_service = MagicMock(return_value=None)

    services = ServiceContainer(
        search_service=mock_search,
        company_service=mock_company_service,
        sync_search=True,
    )
    app = CocliApp(services=services, auto_show=False)

    async with app.run_test() as driver:
        await driver.app.action_show_companies()
        await driver.pause(1.0)
        company_list_screen = await wait_for_widget(driver, CompanyList)
        list_view = company_list_screen.query_one(ListView)
        list_view.focus()
        await driver.pause(0.1)
        list_view.index = 0

        with patch.object(driver.app, "notify") as mock_notify:
            list_view.action_select_cursor()
            await driver.pause(0.3)

        mock_notify.assert_called_once()
        assert "unmaterialized-lead" in mock_notify.call_args.args[0]
        assert mock_notify.call_args.kwargs.get("severity") == "warning"
        assert len(driver.app.query(CompanyDetail)) == 0
