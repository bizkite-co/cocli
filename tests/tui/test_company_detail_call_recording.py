from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail


@pytest.fixture
def mock_company_data():
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com",
        },
        "contacts": [],
        "meetings": [],
        "notes": [],
        "activity": [],
        "website_data": None,
        "tags": [],
    }


async def _mount(app: CocliApp, pilot, company_data):
    detail = CompanyDetail(company_data)
    await app.query_one("#app_content").mount(detail)
    await pilot.pause()
    return detail


@pytest.mark.asyncio
@patch.object(CompanyDetail, "action_play_recording")
async def test_pressing_L_on_activity_table_dispatches_play_recording(
    mock_action, mock_company_data
):
    """Regression test: a Binding on ActivityTable with no matching
    action_<name> method anywhere on the widget silently does nothing -
    Textual does not fall back to an ancestor's method automatically. Every
    new ActivityTable binding needs an explicit forwarder (see
    action_reply_email) or the keypress is a silent no-op."""
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)
        detail.activity_table.focus()
        await pilot.pause()

        await pilot.press("L")
        await pilot.pause()

        mock_action.assert_called_once()


@pytest.mark.asyncio
@patch.object(CompanyDetail, "action_transcribe_recording")
async def test_pressing_T_on_activity_table_dispatches_transcribe_recording(
    mock_action, mock_company_data
):
    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)
        detail.activity_table.focus()
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        mock_action.assert_called_once()


@pytest.mark.asyncio
async def test_play_recording_warns_when_no_recording_on_selected_call(
    mock_company_data,
):
    from cocli.models.companies.activity import CompanyActivity
    from datetime import datetime, UTC

    mock_company_data["activity"] = [
        CompanyActivity(
            timestamp=datetime.now(UTC),
            activity_type="call",
            icon="📞",
            title="Logged call",
            preview="[Call]",
            content="",
            file_path=None,
            metadata={"disposition": "Connected", "phone": "+15551234567"},
            is_scheduled=False,
        )
    ]

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = await _mount(app, pilot, mock_company_data)
        detail.refresh_activity_data()
        await pilot.pause()

        with patch("cocli.tui.widgets.company_detail.open_local_path") as mock_open:
            detail.action_play_recording()
            mock_open.assert_not_called()


@pytest.mark.asyncio
async def test_mounting_company_detail_does_not_auto_sync_recordings_under_pytest(
    mock_company_data,
):
    """Regression guard: AUTO_SYNC_RECORDINGS_ON_OPEN must never fire during
    tests. Twilio credential resolution (including op:// 1Password lookups)
    happens before calling_provider's PYTEST_CURRENT_TEST short-circuit, so
    without this guard, every test mounting CompanyDetail on a dev machine
    with real Twilio config configured could trigger live API calls or
    1Password/Windows Hello prompts."""
    with patch(
        "cocli.application.call_recording_service.sync_twilio_recordings"
    ) as mock_sync:
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            await _mount(app, pilot, mock_company_data)
            await pilot.pause()

        mock_sync.assert_not_called()


@pytest.mark.asyncio
@patch("cocli.application.call_recording_service.sync_twilio_recordings")
async def test_pressing_S_syncs_recordings_and_refreshes_activity(
    mock_sync, mock_company_data
):
    from cocli.application.call_recording_service import SyncRecordingsResult

    mock_sync.return_value = SyncRecordingsResult(synced_count=2, matched_count=2)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await _mount(app, pilot, mock_company_data)

        with patch(
            "cocli.application.services.ServiceContainer.get_company_details",
            return_value=mock_company_data,
        ) as mock_refresh:
            await pilot.press("S")
            await pilot.pause()

        mock_sync.assert_called_once()
        mock_refresh.assert_called_once_with("test-co")
