from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from cocli.application.call_history_service import ConnectedCallInfo
from cocli.models.companies.company import Company
from cocli.tui.app import CocliApp
from cocli.tui.widgets.email_send_modal import EmailSendModal
from cocli.tui.widgets.inputs import CocliInput
from textual.widgets import TextArea


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_send_modal.get_campaign", return_value="roadmap")
async def test_email_send_modal_prepopulates_and_displays_call_context(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="Higginbotham Financial",
        slug="higginbotham-financial",
        domain="higginbotham.com",
        email="mitch@higginbotham.com",
    )
    co.save()

    fake_call = ConnectedCallInfo(
        call_date=None,  # type: ignore[arg-type]
        call_date_str="10/14",
        contact_name="Mitch",
        notes_snippet="Spoke to Mitch about Roth conversion tool",
    )

    with (
        patch(
            "cocli.tui.widgets.email_send_modal.find_recent_connected_call",
            return_value=fake_call,
        ),
        patch(
            "cocli.application.personalized_outreach_service.PersonalizedOutreachService.generate_copy",
            return_value=("Hi Mitch, feedback", "Hi Mitch,\n\nHere is the tool link."),
        ),
    ):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            modal = EmailSendModal(
                company_slug="higginbotham-financial",
                contact_name="Mitch Gaylord",
                recipient_email="mitch@higginbotham.com",
                template_id="request_testimonial.md",
                initiative="testimonials",
            )
            app.push_screen(modal)
            await pilot.pause(0.2)

            subject_input = modal.query_one("#email-send-subject", CocliInput)
            assert "10/14" in subject_input.value

            body_area = modal.query_one("#email-send-body", TextArea)
            assert "10/14" in body_area.text


@pytest.mark.asyncio
@patch("cocli.tui.widgets.email_send_modal.get_campaign", return_value="roadmap")
async def test_email_send_modal_send_now_calls_service_with_edited_content(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.application.personalized_outreach_service import SendBatchResult

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="Higginbotham Financial",
        slug="higginbotham-financial",
        domain="higginbotham.com",
        email="mitch@higginbotham.com",
    )
    co.save()

    send_now_called: list[dict[str, Any]] = []

    def _fake_send_now(self: Any, company_slug: str, **kwargs: Any) -> SendBatchResult:
        send_now_called.append({"slug": company_slug, **kwargs})
        return SendBatchResult(batch_id="test-batch", sent=1, failed=0)

    with (
        patch("cocli.tui.widgets.email_send_modal.find_recent_connected_call", return_value=None),
        patch(
            "cocli.application.personalized_outreach_service.PersonalizedOutreachService.send_now",
            _fake_send_now,
        ),
    ):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            modal = EmailSendModal(
                company_slug="higginbotham-financial",
                contact_name="Mitch Gaylord",
                recipient_email="mitch@higginbotham.com",
                template_id="request_testimonial.md",
                initiative="testimonials",
                subject="Initial Subject",
                body="Initial Body",
            )
            app.push_screen(modal)
            await pilot.pause(0.2)

            # Edit subject and body
            subject_input = modal.query_one("#email-send-subject", CocliInput)
            subject_input.value = "Custom Tailored Subject for Mitch"

            body_area = modal.query_one("#email-send-body", TextArea)
            body_area.text = "Customized body text for Mitch."

            # Send via F4
            await pilot.press("f4")
            await pilot.pause(0.3)

            assert app.screen is not modal

    assert len(send_now_called) == 1
    assert send_now_called[0]["subject"] == "Custom Tailored Subject for Mitch"
    assert send_now_called[0]["body"] == "Customized body text for Mitch."
    assert send_now_called[0]["recipient_email"] == "mitch@higginbotham.com"
