from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail, NotesTable
from cocli.tui.widgets.email_compose_modal import EmailComposeModal


@pytest.fixture
def mock_company_data() -> dict[str, Any]:
    return {
        "company": {
            "name": "Test Co",
            "slug": "test-co",
            "domain": "test.com",
            "email": "client@test.com",
        },
        "notes": [
            {
                "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
                "title": "Email received: Hello",
                "content": "- From: client@test.com\n- To: mark@example.com\n\nHi there",
                "file_path": "/tmp/note1.md",
            }
        ],
        "contacts": [{"name": "Pat", "role": "Owner", "email": "pat@test.com"}],
        "meetings": [],
        "tags": [],
    }


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_compose_modal.load_campaign_config")
@patch("cocli.tui.widgets.email_compose_modal.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_compose_email_opens_modal(
    mock_get_details: Any,
    _mock_campaign: Any,
    mock_config: Any,
    mock_company_data: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_config.return_value = {
        "email": {"from_address": "mark@getretirementtaxanalyzer.com"},
        "aws": {"profile": "westmonroe-support"},
    }
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        to_input = app.screen.query_one("#email-to")
        assert "client@test.com" in str(to_input.value)
        from_label = app.screen.query_one("#email-from")
        from_text = str(getattr(from_label, "content", getattr(from_label, "renderable", "")))
        assert "mark@getretirementtaxanalyzer.com" in from_text


@pytest.mark.asyncio
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_reply_email_prefills_from_note(
    mock_get_details: Any, mock_company_data: dict[str, Any], tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause(0.1)
        app.query_one("#panel-activity").focus()
        await driver.pause(0.1)
        await driver.press("i")
        assert app.query_one(NotesTable).has_focus
        await driver.press("r")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        assert "client@test.com" in str(app.screen.query_one("#email-to").value)
        assert str(app.screen.query_one("#email-subject").value).startswith("Re:")
        assert "Hi there" in app.screen.query_one("#email-body").text


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_compose_modal.Boto3SesSender")
@patch("cocli.tui.widgets.email_compose_modal.load_campaign_config")
@patch("cocli.tui.widgets.email_compose_modal.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_compose_send_dismisses_modal(
    mock_get_details: Any,
    _mock_campaign: Any,
    mock_config: Any,
    mock_ses: Any,
    mock_company_data: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    from cocli.core.paths import paths
    from cocli.models.mail import SendMailResult

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_config.return_value = {
        "email": {"from_address": "mark@getretirementtaxanalyzer.com"},
        "aws": {"profile": "westmonroe-support"},
    }
    sender = mock_ses.return_value
    sender.send_email.return_value = "ses-1"
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        app.screen.query_one("#email-subject").value = "Hello"
        app.screen.query_one("#email-body").text = "Body text"
        with patch(
            "cocli.application.email_service.EmailService.send",
            return_value=SendMailResult(
                message_id="ses-1",
                to_address="client@test.com",
                subject="Hello",
                note_written=True,
                company_slug="test-co",
            ),
        ):
            await driver.press("ctrl+s")
            await driver.pause()
        assert not isinstance(app.screen, EmailComposeModal)


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_compose_modal.Boto3SesSender")
@patch("cocli.tui.widgets.email_compose_modal.load_campaign_config")
@patch("cocli.tui.widgets.email_compose_modal.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_compose_send_via_ctrl_enter(
    mock_get_details: Any,
    _mock_campaign: Any,
    mock_config: Any,
    mock_ses: Any,
    mock_company_data: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    from cocli.core.paths import paths
    from cocli.models.mail import SendMailResult

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_config.return_value = {
        "email": {"from_address": "mark@getretirementtaxanalyzer.com"},
        "aws": {"profile": "westmonroe-support"},
    }
    sender = mock_ses.return_value
    sender.send_email.return_value = "ses-1"
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        app.screen.query_one("#email-subject").value = "Hello"
        app.screen.query_one("#email-body").text = "Body text"
        with patch(
            "cocli.application.email_service.EmailService.send",
            return_value=SendMailResult(
                message_id="ses-1",
                to_address="client@test.com",
                subject="Hello",
                note_written=True,
                company_slug="test-co",
            ),
        ):
            await driver.press("ctrl+enter")
            await driver.pause()
        assert not isinstance(app.screen, EmailComposeModal)


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_compose_modal.load_campaign_config")
@patch("cocli.tui.widgets.email_compose_modal.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_escape_with_drafted_body_requires_confirmation(
    mock_get_details: Any,
    _mock_campaign: Any,
    mock_config: Any,
    mock_company_data: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Regression (2026-09-16): same fix as CallLogModal - a drafted
    email must not be silently discarded by escape/alt+s."""
    from cocli.core.paths import paths
    from cocli.tui.widgets.confirm_screen import ConfirmScreen

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_config.return_value = {
        "email": {"from_address": "mark@getretirementtaxanalyzer.com"},
        "aws": {"profile": "westmonroe-support"},
    }
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        modal = app.screen
        modal.query_one("#email-body").text = "Please don't lose this draft."

        await driver.press("escape")
        await driver.pause()

        assert isinstance(app.screen, ConfirmScreen)
        await driver.press("n")
        await driver.pause()

        assert app.screen is modal
        assert modal.query_one("#email-body").text == "Please don't lose this draft."


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_compose_modal.load_campaign_config")
@patch("cocli.tui.widgets.email_compose_modal.get_campaign", return_value="roadmap")
@patch("cocli.application.company_service.get_company_details_for_view")
async def test_alt_s_while_typing_body_exits_insert_mode_not_the_screen(
    mock_get_details: Any,
    _mock_campaign: Any,
    mock_config: Any,
    mock_company_data: dict[str, Any],
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Same fix as CallLogModal (2026-09-16, second pass): alt+s while
    the email body TextArea is focused must exit INSERT mode (defocus),
    not offer to discard the draft - that's what "on all the screens"
    means for this app-level shim."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    mock_get_details.return_value = mock_company_data
    mock_config.return_value = {
        "email": {"from_address": "mark@getretirementtaxanalyzer.com"},
        "aws": {"profile": "westmonroe-support"},
    }
    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        detail = CompanyDetail(mock_company_data)
        await app.query_one("#app_content").mount(detail)
        await driver.pause()
        await driver.press("C")
        await driver.pause()
        assert isinstance(app.screen, EmailComposeModal)
        modal = app.screen
        body = modal.query_one("#email-body")
        body.focus()
        body.text = "Please don't lose this draft."
        await driver.pause()

        await driver.press("alt+s")
        await driver.pause()

        assert app.screen is modal
        assert modal.query_one("#email-body").text == "Please don't lose this draft."
        assert not body.has_focus
