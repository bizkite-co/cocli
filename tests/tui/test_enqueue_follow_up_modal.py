from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from cocli.application.follow_up_service import FollowUpService
from cocli.models.companies.company import Company
from cocli.tui.app import CocliApp

# Deliberately NOT imported at module level: importing EnqueueFollowUpModal
# here would bind its `get_campaign` name to whatever cocli.core.config.
# get_campaign currently is at pytest COLLECTION time (before any test's
# mocker.patch has run) - and since Python caches modules, every later
# lazy import of this module elsewhere in the suite (e.g.
# test_messages_view.py's f-key test) would then reuse that same,
# permanently-unpatched binding instead of picking up its own mock.
# Importing lazily inside each test function, like the rest of the
# suite does, avoids disturbing that import-order-sensitive behavior.


@pytest.mark.asyncio
@patch("cocli.tui.widgets.enqueue_follow_up_modal.get_campaign", return_value="roadmap")
async def test_f4_sends_immediately_and_dismisses_without_scheduling(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.tui.widgets.enqueue_follow_up_modal import EnqueueFollowUpModal
    """Mark, 2026-10-09: "a function that calls each of the already
    existing steps in sequence, with automatic approval" - F4 here is the
    same express lane as Call Log's F4, but since this modal's whole
    purpose is schedule-or-send (not log-a-call-and-incidentally-email),
    a successful send dismisses it like Ctrl+S does; nothing gets
    scheduled on the follow-up queue."""
    from cocli.application.personalized_outreach_service import (
        PersonalizedOutreachService,
        ProspectContactMatch,
        SendBatchResult,
    )
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="Send Now Co",
        slug="send-now-co",
        domain="sendnow.test",
        email="contact@sendnow.test",
    )
    co.save()

    fake_match = ProspectContactMatch(
        company_slug="send-now-co",
        company_name="Send Now Co",
        recipient_email="contact@sendnow.test",
        contact_name="Pat Contact",
        first_name="Pat",
        role=None,
        subject="",
        body="",
    )

    send_calls: list[Any] = []

    def _fake_send_batch(self: Any, matches: Any, **kwargs: Any) -> Any:
        send_calls.append((matches, kwargs))
        return SendBatchResult(batch_id="test-batch", sent=len(matches), failed=0)

    with (
        patch.object(
            PersonalizedOutreachService, "find_contact_for_company", return_value=fake_match
        ),
        patch.object(
            PersonalizedOutreachService,
            "generate_copy",
            return_value=("Subject line", "Body text"),
        ),
        patch.object(PersonalizedOutreachService, "send_batch", _fake_send_batch),
    ):
        app = CocliApp(auto_show=False)
        async with app.run_test() as pilot:
            modal = EnqueueFollowUpModal(company_slug="send-now-co")
            app.push_screen(modal)
            await pilot.pause(0.2)

            await pilot.press("f4")
            await pilot.pause(0.3)

            assert app.screen is not modal

    assert len(send_calls) == 1
    sent_matches, _sent_kwargs = send_calls[0]
    assert sent_matches[0].recipient_email == "contact@sendnow.test"
    assert FollowUpService("roadmap").list_pending(company_slug="send-now-co") == []


@pytest.mark.asyncio
@patch("cocli.tui.widgets.enqueue_follow_up_modal.get_campaign", return_value="roadmap")
async def test_f4_with_no_template_warns_and_does_not_send(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.tui.widgets.enqueue_follow_up_modal import EnqueueFollowUpModal
    from cocli.tui.widgets.search_select import SearchSelect

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="No Template Co", slug="no-template-co", domain="notemplate.test")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = EnqueueFollowUpModal(company_slug="no-template-co")
        app.push_screen(modal)
        await pilot.pause(0.2)

        modal.query_one("#followup_template", SearchSelect).value = ""
        await pilot.press("f4")
        await pilot.pause(0.2)

        assert app.screen is modal


@pytest.mark.asyncio
@patch("cocli.tui.widgets.enqueue_follow_up_modal.get_campaign", return_value="roadmap")
async def test_f3_opens_email_send_modal(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.tui.widgets.email_send_modal import EmailSendModal
    from cocli.tui.widgets.enqueue_follow_up_modal import EnqueueFollowUpModal

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="Edit Send Co",
        slug="edit-send-co",
        domain="editsend.test",
        email="contact@editsend.test",
    )
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = EnqueueFollowUpModal(company_slug="edit-send-co")
        app.push_screen(modal)
        await pilot.pause(0.2)

        await pilot.press("f3")
        await pilot.pause(0.2)

        # Active screen should now be EmailSendModal
        assert isinstance(app.screen, EmailSendModal)
        assert app.screen.company_slug == "edit-send-co"

