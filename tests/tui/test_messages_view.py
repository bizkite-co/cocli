"""Messages TUI screen: navigation, per-section rendering, and the
review-before-send flow (the exact frozen body must be shown and sent,
not a fresh re-render)."""

from __future__ import annotations

import pytest

from cocli.tui.app import CocliApp
from cocli.application.services import ServiceContainer
from cocli.tui.widgets.messages_view import MessagesView
from cocli.tui.widgets.follow_up_queue_view import FollowUpQueueView
from cocli.tui.widgets.recent_calls_view import RecentCallListItem, RecentCallsView
from cocli.tui.widgets.recent_emails_view import RecentEmailsView, RecentEmailListItem
from cocli.tui.widgets.target_batches_view import TargetBatchesView
from cocli.tui.widgets.send_log_view import SendLogView, SendLogListItem
from cocli.tui.widgets.unsubscribe_rate_view import UnsubscribeRateView
from textual.widgets import ListView, Label, Static

CAMPAIGN = "test/default"


def _write_pending_batch(
    batch_id: str,
    *,
    slug: str = "acme-financial",
    recipient: str = "bob@acme.test",
    subject: str = "Hi Bob",
    body: str = "Line one\nLine two",
    template_id: str = "t1",
) -> None:
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    index_dir = PendingBatchEntry.get_index_dir(CAMPAIGN)
    index_dir.mkdir(parents=True, exist_ok=True)
    entry = PendingBatchEntry(
        batch_id=batch_id,
        template_id=template_id,
        company_slug=slug,
        recipient=recipient,
        subject=subject,
        body=body,
    )
    with open(index_dir / "pending.usv", "a", encoding="utf-8") as f:
        f.write(entry.to_usv())


@pytest.mark.asyncio
async def test_leader_key_opens_messages_view_with_follow_up_drafts(mock_cocli_env, mocker) -> None:
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)

        assert len(app.query(MessagesView)) == 1
        assert app.query_one("#menu-messages").has_class("active-menu-item")
        assert len(app.query(FollowUpQueueView)) == 1
        assert str(app.query_one("#messages-sidebar").styles.width) == "30"
        assert str(app.query_one("#messages-content").styles.width) == "1fr"


@pytest.mark.asyncio
async def test_messages_section_list_has_real_focus_j_navigates_and_h_stays_put(
    mock_cocli_env, mocker
) -> None:
    """Messages must retain focus and navigation within its section list."""
    from cocli.tui.widgets.company_list import CompanyList

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)

        section_list = app.query_one("#messages-section-list", ListView)
        assert section_list.has_focus
        assert section_list.index == 0
        await pilot.press("j")
        await pilot.pause(0.1)
        assert section_list.index == 1

        await pilot.press("h")
        await pilot.pause(0.2)
        assert len(app.query(MessagesView)) == 1
        assert len(app.query(CompanyList)) == 0
        assert app.query_one("#menu-messages").has_class("active-menu-item")


@pytest.mark.asyncio
async def test_messages_l_navigates_into_follow_up_queue_list(mock_cocli_env, mocker) -> None:
    """Pressing l on Follow-up Drafts in the sidebar moves focus to the queue list, and h returns."""
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)

        section_list = app.query_one("#messages-section-list", ListView)
        assert section_list.has_focus
        assert section_list.index == 0

        await pilot.press("l")
        await pilot.pause(0.2)

        task_list = app.query_one("#fu-queue-list", ListView)
        assert task_list.has_focus

        await pilot.press("h")
        await pilot.pause(0.2)
        assert section_list.has_focus


@pytest.mark.asyncio
async def test_messages_recent_calls_lists_logged_phone_calls(mock_cocli_env, mocker) -> None:
    from datetime import UTC, datetime, timedelta

    from cocli.core.paths import paths
    from cocli.models.companies.company import Company
    from cocli.models.companies.meeting import Meeting
    from cocli.tui.widgets.company_detail import CompanyDetail

    company = Company(name="Friday Caller", slug="friday-caller", tags=[CAMPAIGN])
    company.save()
    meetings_dir = paths.companies.entry(company.slug).path / "meetings"
    Meeting(
        timestamp=datetime.now(UTC) - timedelta(days=2),
        title="Logged Call: Interested",
        type="phone-call",
        content="Asked for an email with the product overview.",
    ).to_file(meetings_dir)
    Meeting(
        timestamp=datetime.now(UTC) - timedelta(days=3),
        title="Logged Call: Follow-up",
        type="phone-call",
        content="Requested a call next week.",
    ).to_file(meetings_dir)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.05)
        await pilot.press("space")
        await pilot.press("m")
        await pilot.pause(0.05)
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert len(app.query(RecentCallsView)) == 1
        call_list = app.query_one("#recent-call-list", ListView)
        assert len(call_list.children) == 2
        assert call_list.has_focus
        assert call_list.index == 0
        assert isinstance(call_list.children[0], RecentCallListItem)
        assert call_list.children[0].call.company_slug == "friday-caller"
        preview = app.query_one("#recent-call-preview-body", Static)
        assert "Asked for an email with the product overview." in str(preview.content)

        await pilot.press("j")
        await pilot.pause(0.05)
        assert "Requested a call next week." in str(preview.content)
        assert "Company Activity:" in str(preview.content)

        # Test f key in RecentCallsView opens EnqueueFollowUpModal
        await pilot.press("f")
        await pilot.pause(0.05)
        from cocli.tui.widgets.enqueue_follow_up_modal import EnqueueFollowUpModal

        assert isinstance(app.screen, EnqueueFollowUpModal)

        # Submit follow-up modal
        await pilot.press("ctrl+s")
        await pilot.pause(0.05)
        assert not isinstance(app.screen, EnqueueFollowUpModal)

        from cocli.application.follow_up_service import FollowUpService

        pending = FollowUpService(CAMPAIGN).list_pending("friday-caller")
        assert len(pending) == 1
        assert pending[0].company_slug == "friday-caller"

        # Open CompanyDetail
        await pilot.press("l")
        await pilot.pause(0.05)
        assert len(app.query(CompanyDetail)) == 1

        # Test f key in CompanyDetail also opens EnqueueFollowUpModal
        await pilot.press("f")
        await pilot.pause(0.05)
        assert isinstance(app.screen, EnqueueFollowUpModal)
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert not isinstance(app.screen, EnqueueFollowUpModal)

        await pilot.press("h")
        await pilot.pause(0.2)
        assert len(app.query(RecentCallsView)) == 1
        assert call_list.has_focus


@pytest.mark.asyncio
async def test_target_batches_shows_full_rendered_body_on_selection(mock_cocli_env, mocker) -> None:
    _write_pending_batch("batch-1", body="Line one\nLine two")

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = TargetBatchesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#target-batch-list", ListView)
        assert len(list_view.children) == 1
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)

        body_text = widget.query_one("#batch-preview-body").content
        # The exact frozen content, with real newlines restored - not the
        # USV-sanitized "<br>" form, and not a re-rendered value.
        assert "<br>" not in str(body_text)
        assert "Line one" in str(body_text)
        assert "Line two" in str(body_text)



@pytest.mark.asyncio
async def test_follow_up_queue_view_lists_pending_tasks(mock_cocli_env, mocker) -> None:
    """FollowUpQueueView should list items from queues/follow-up/pending/."""
    from datetime import UTC, datetime, timedelta
    from cocli.application.follow_up_service import FollowUpService
    from cocli.tui.widgets.follow_up_queue_view import FollowUpQueueListItem

    FollowUpService(CAMPAIGN).add_follow_up(
        company_slug="acme-financial",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) + timedelta(days=5),
        format="email",
        template_id="t1",
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = FollowUpQueueView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        task_list = widget.query_one("#fu-queue-list", ListView)
        assert len(task_list.children) == 1
        assert isinstance(task_list.children[0], FollowUpQueueListItem)
        assert task_list.children[0].follow_up.company_slug == "acme-financial"
        assert task_list.children[0].follow_up.template_id == "t1"


@pytest.mark.asyncio
async def test_follow_up_queue_view_prepare_due_follow_ups(mock_cocli_env, mocker) -> None:
    """P key on FollowUpQueueView calls FollowUpService.process_due()."""
    from cocli.application.follow_up_service import ProcessFollowUpsResult

    process_due = mocker.patch(
        "cocli.application.follow_up_service.FollowUpService.process_due",
        return_value=ProcessFollowUpsResult(due=1, emails_queued=1),
    )
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = FollowUpQueueView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        widget.task_list.focus()
        await pilot.press("P")
        await pilot.pause(0.2)

    process_due.assert_called_once_with()


@pytest.mark.asyncio
async def test_follow_up_queue_view_prepare_selected_task(mock_cocli_env, mocker) -> None:
    """p key on FollowUpQueueView calls FollowUpService.process_task() for selected item."""
    from datetime import UTC, datetime, timedelta
    from cocli.application.follow_up_service import FollowUpService

    FollowUpService(CAMPAIGN).add_follow_up(
        company_slug="acme-financial",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) + timedelta(days=5),
        format="email",
        template_id="t1",
    )
    process_task = mocker.patch(
        "cocli.application.follow_up_service.FollowUpService.process_task",
        return_value=None,
    )
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = FollowUpQueueView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        widget.task_list.focus()
        await pilot.press("p")
        await pilot.pause(0.2)

    process_task.assert_called_once()
    assert process_task.call_args[0][0].company_slug == "acme-financial"



@pytest.mark.asyncio
async def test_send_batch_flow_sends_and_clears_pending(mock_cocli_env, mocker) -> None:
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    _write_pending_batch("batch-1", slug="acme-financial", recipient="bob@acme.test")

    class _FakeSentResult:
        message_id = "fake-msg-id"

    class _FakeEmailService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def send(self, request: object) -> _FakeSentResult:
            return _FakeSentResult()

    mocker.patch("cocli.core.config.load_campaign_config", return_value={})
    mocker.patch("cocli.application.email_service.EmailService", _FakeEmailService)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = TargetBatchesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#target-batch-list", ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.3)

        service = PersonalizedOutreachService(CAMPAIGN)
        assert service.list_pending_batches() == []

        log_path = SendLogEntry.get_index_dir(CAMPAIGN) / "log.usv"
        entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
        assert len(entries) == 1
        assert entries[0].status == "sent"
        assert entries[0].company_slug == "acme-financial"


@pytest.mark.asyncio
async def test_send_all_batches_flow_sends_all_pending(mock_cocli_env, mocker) -> None:
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    _write_pending_batch("batch-1", slug="acme-1", recipient="bob1@acme.test")
    _write_pending_batch("batch-2", slug="acme-2", recipient="bob2@acme.test")

    class _FakeSentResult:
        message_id = "fake-msg-id"

    class _FakeEmailService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def send(self, request: object) -> _FakeSentResult:
            return _FakeSentResult()

    mocker.patch("cocli.core.config.load_campaign_config", return_value={})
    mocker.patch("cocli.application.email_service.EmailService", _FakeEmailService)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = TargetBatchesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#target-batch-list", ListView)
        list_view.focus()
        await pilot.press("S")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.3)

        service = PersonalizedOutreachService(CAMPAIGN)
        assert service.list_pending_batches() == []

        log_path = SendLogEntry.get_index_dir(CAMPAIGN) / "log.usv"
        entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
        assert len(entries) == 2



@pytest.mark.asyncio
async def test_discard_batch_removes_without_sending(mock_cocli_env, mocker) -> None:
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    _write_pending_batch("batch-1")

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = TargetBatchesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#target-batch-list", ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        await pilot.press("d")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.2)

        service = PersonalizedOutreachService(CAMPAIGN)
        assert service.list_pending_batches() == []


@pytest.mark.asyncio
async def test_send_log_section_lists_sent_entries(mock_cocli_env, mocker) -> None:
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir(CAMPAIGN)
    index_dir.mkdir(parents=True, exist_ok=True)
    entry = SendLogEntry(
        batch_id="b1", template_id="t1", company_slug="acme-financial",
        recipient="bob@acme.test", subject="Hi Bob", status="sent", message_id="msg-1",
    )
    with open(index_dir / "log.usv", "w", encoding="utf-8") as f:
        f.write(entry.to_usv())

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = SendLogView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#send-log-list", ListView)
        assert len(list_view.children) == 1
        assert isinstance(list_view.children[0], SendLogListItem)
        assert list_view.children[0].entry.company_slug == "acme-financial"


@pytest.mark.asyncio
async def test_unsubscribe_rate_shows_computed_rate(mock_cocli_env, mocker) -> None:
    from cocli.core.exclusions import ExclusionManager
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir(CAMPAIGN)
    index_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        SendLogEntry(
            batch_id="b1", template_id="t1", company_slug=f"co-{i}",
            recipient=f"co{i}@test.com", subject="Hi", status="sent",
        )
        for i in range(4)
    ]
    with open(index_dir / "log.usv", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_usv())
    ExclusionManager(CAMPAIGN).add_exclusion(
        slug="co-1", domain="co1@test.com", reason="unsubscribe:COMPLAINT"
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = UnsubscribeRateView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        sent_label = widget.query_one("#unsubscribe-rate-sent", Label)
        rate_label = widget.query_one("#unsubscribe-rate-rate", Label)
        assert "4" in str(sent_label.content)
        assert "25.0%" in str(rate_label.content)


@pytest.mark.asyncio
async def test_recent_emails_view_shows_inbound_and_outbound_with_content_and_no_year(
    mock_cocli_env, mocker
) -> None:
    from datetime import UTC, datetime, timedelta
    from cocli.core.paths import paths
    from cocli.models.companies.company import Company
    from cocli.models.companies.email_note import EmailNote

    company = Company(name="Acme Corp", slug="acme-corp", tags=[CAMPAIGN])
    company.save()
    notes_dir = paths.companies.entry(company.slug).path / "notes"

    EmailNote(
        timestamp=datetime.now(UTC) - timedelta(hours=2),
        title="Proposal for Widget",
        type="email",
        direction="sent",
        from_address="sales@ourco.com",
        to_addresses=["ceo@acmecorp.com"],
        content="Here is our detailed proposal for the widget contract.",
    ).to_file(notes_dir)

    EmailNote(
        timestamp=datetime.now(UTC) - timedelta(hours=1),
        title="Re: Proposal for Widget",
        type="email",
        direction="received",
        from_address="ceo@acmecorp.com",
        to_addresses=["sales@ourco.com"],
        content="We received your proposal and would love to move forward.",
    ).to_file(notes_dir)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = RecentEmailsView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#send-log-list", ListView)
        assert len(list_view.children) == 2
        assert isinstance(list_view.children[0], RecentEmailListItem)

        # Newest first: received email should be index 0
        first_item = list_view.children[0]
        assert first_item.email.direction == "received"
        assert "Re: Proposal for Widget" in first_item.email.title
        assert first_item.email.company_slug == "acme-corp"

        # Check rendered label in list view: [RCVD], no year in date, and content snippet
        rendered_label = first_item.query_one(Label).content
        label_text = str(rendered_label)
        assert "RCVD" in label_text
        assert "2026" not in label_text
        assert "We received your proposal" in label_text

        # Second item is sent
        second_item = list_view.children[1]
        assert second_item.email.direction == "sent"
        assert "Proposal for Widget" in second_item.email.title
        second_label_text = str(second_item.query_one(Label).content)
        assert "SENT" in second_label_text
        assert "2026" not in second_label_text
        assert "Here is our detailed proposal" in second_label_text

        # Detail view shows full content body and metadata
        body_text = str(widget.query_one("#send-log-detail-body", Static).content)
        assert "We received your proposal and would love to move forward." in body_text
        assert "acme-corp" in body_text
        assert "ceo@acmecorp.com" in body_text
        assert "2026-" not in body_text


@pytest.mark.asyncio
async def test_recent_calls_view_shows_sms_and_calls_with_no_year(
    mock_cocli_env, mocker
) -> None:
    from datetime import UTC, datetime, timedelta
    from cocli.core.paths import paths
    from cocli.models.companies.company import Company
    from cocli.models.companies.meeting import Meeting
    from cocli.models.companies.sms_note import SmsNote

    company = Company(name="Beta Industries", slug="beta-industries", tags=[CAMPAIGN])
    company.save()

    meetings_dir = paths.companies.entry(company.slug).path / "meetings"
    Meeting(
        timestamp=datetime.now(UTC) - timedelta(hours=3),
        title="Intro call with founder",
        type="phone-call",
        content="Great intro conversation.",
    ).to_file(meetings_dir)

    notes_dir = paths.companies.entry(company.slug).path / "notes"
    SmsNote(
        timestamp=datetime.now(UTC) - timedelta(hours=1),
        title="SMS from founder",
        direction="inbound",
        from_phone="+17145551234",
        to_phone="+17144514350",
        content="Hey, can you send over the deck?",
    ).to_file(notes_dir)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = RecentCallsView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        call_list = widget.query_one("#recent-call-list", ListView)
        assert len(call_list.children) == 2

        # First item is newest (the inbound SMS)
        first_item = call_list.children[0]
        assert first_item.call.item_type == "sms"
        first_label = str(first_item.query_one(Label).content)
        assert "💬" in first_label
        assert "INBOUND" in first_label
        assert "2026" not in first_label

        # Preview of first item shows SMS content
        preview_text = str(widget.query_one("#recent-call-preview-body", Static).content)
        assert "Hey, can you send over the deck?" in preview_text
        assert "2026-" not in preview_text

        # Second item is phone call
        second_item = call_list.children[1]
        assert second_item.call.item_type == "call"
        second_label = str(second_item.query_one(Label).content)
        assert "📞" in second_label
        assert "2026" not in second_label


@pytest.mark.asyncio
async def test_messages_view_recent_emails_right_below_recent_calls(
    mock_cocli_env, mocker
) -> None:
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)

        section_list = app.query_one("#messages-section-list", ListView)
        items = list(section_list.children)
        assert len(items) == 5
        assert items[0].section == "follow-ups"
        assert items[1].section == "batch-emails"
        assert items[2].section == "recent-calls"
        assert items[2].label == "Recent Calls & SMS"
        assert items[3].section == "recent-emails"
        assert items[3].label == "Recent Emails"
        assert items[4].section == "initiatives"

        # Navigate down to Recent Emails (index 3)
        await pilot.press("j")  # index 1
        await pilot.press("j")  # index 2 (recent-calls)
        await pilot.press("j")  # index 3 (recent-emails)
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert len(app.query(RecentEmailsView)) == 1


@pytest.mark.asyncio
async def test_messages_view_drilldown_and_return_from_recent_emails(
    mock_cocli_env, mocker
) -> None:
    from datetime import UTC, datetime, timedelta
    from cocli.core.paths import paths
    from cocli.models.companies.company import Company
    from cocli.models.companies.email_note import EmailNote
    from cocli.tui.widgets.company_detail import CompanyDetail

    company = Company(name="Acme Corp", slug="acme-corp", tags=[CAMPAIGN])
    company.save()
    notes_dir = paths.companies.entry(company.slug).path / "notes"
    EmailNote(
        timestamp=datetime.now(UTC) - timedelta(hours=1),
        title="Email from client",
        direction="received",
        sender="client@acme.test",
        recipient="me@test.local",
        content="Great proposal!",
    ).to_file(notes_dir)

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.press("m")
        await pilot.pause(0.2)

        # Select Recent Emails (index 3)
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("j")
        await pilot.press("enter")
        await pilot.pause(0.2)

        assert len(app.query(RecentEmailsView)) == 1
        list_view = app.query_one("#send-log-list", ListView)
        assert len(list_view.children) == 1
        assert list_view.has_focus

        # Press 'l' to open CompanyDetail
        await pilot.press("l")
        await pilot.pause(0.2)
        assert len(app.query(CompanyDetail)) == 1

        # Press 'h' to return to Recent Emails
        await pilot.press("h")
        await pilot.pause(0.2)

        # Should return smoothly without NoMatches crash
        assert len(app.query(RecentEmailsView)) == 1
        list_view_after = app.query_one("#send-log-list", ListView)
        assert list_view_after.has_focus


@pytest.mark.asyncio
async def test_messages_view_action_focus_when_unmounted(mock_cocli_env, mocker) -> None:
    """Invoking focus on an unmounted messages section switches to it safely without crashing."""
    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        await pilot.press("space")
        await pilot.press("m")
        await pilot.pause(0.2)

        mv = app.query_one(MessagesView)
        # Initially FollowUpQueueView is mounted
        assert len(app.query(RecentCallsView)) == 0

        # Calling action_focus_recent_calls() should mount RecentCallsView without raising NoMatches
        mv.action_focus_recent_calls()
        await pilot.pause(0.2)
        assert len(app.query(RecentCallsView)) == 1

        # Now calling action_focus_recent_emails() should mount RecentEmailsView without raising NoMatches
        mv.action_focus_recent_emails()
        await pilot.pause(0.2)
        assert len(app.query(RecentEmailsView)) == 1


