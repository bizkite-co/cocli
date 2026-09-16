"""InitiativesView: two-level list-above-a-list browser for a campaign's
initiatives/ folder tree, mirroring ApplicationView's Admin pattern
(top nav list + a stacked second list, h/j/k/l navigation)."""

from __future__ import annotations

import pytest
from textual.widgets import ListView

from cocli.application.services import ServiceContainer
from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.initiatives_view import (
    CategoryListItem,
    InitiativeListItem,
    InitiativesView,
    _EmailSequencesPane,
    _FileBrowserPane,
    _TrackingPane,
)

CAMPAIGN = "test/default"


def _make_initiative(campaign: str, initiative: str, categories: dict[str, dict[str, str]]) -> None:
    """categories: {category_name: {relative_file_path: content}}."""
    base = paths.campaigns / campaign / "initiatives" / initiative
    base.mkdir(parents=True, exist_ok=True)
    for category, files in categories.items():
        cat_dir = base / category
        for rel_path, content in files.items():
            file_path = cat_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")


def _write_send_log(campaign: str, entries: list) -> None:
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir(campaign)
    index_dir.mkdir(parents=True, exist_ok=True)
    with open(index_dir / "log.usv", "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_usv())


def _write_ses_events(campaign: str, entries: list) -> None:
    from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

    index_dir = SesEventLogEntry.get_index_dir(campaign)
    index_dir.mkdir(parents=True, exist_ok=True)
    with open(index_dir / "log.usv", "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_usv())


@pytest.mark.asyncio
async def test_initiatives_list_populates_from_folder_names(mock_cocli_env, mocker) -> None:
    _make_initiative(CAMPAIGN, "rta", {"email-sequences": {"t.md": "x"}})
    _make_initiative(CAMPAIGN, "wealth-manager-products", {})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        list_view = widget.query_one("#initiatives_list", ListView)
        names = [i.initiative for i in list_view.children if isinstance(i, InitiativeListItem)]
        assert names == ["rta", "wealth-manager-products"]


@pytest.mark.asyncio
async def test_selecting_initiative_shows_only_existing_categories(mock_cocli_env, mocker) -> None:
    """A second initiative with no category folders yet must show an
    empty categories list, not a hardcoded fixed three."""
    _make_initiative(
        CAMPAIGN,
        "rta",
        {
            "email-sequences": {"t.md": "x"},
            "rendered-outreach": {"acme/t.md": "x"},
            "tracking": {"utm.csv": "x"},
        },
    )
    _make_initiative(CAMPAIGN, "wealth-manager-products", {})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        categories_list = widget.query_one("#categories_list", ListView)

        initiatives_list.focus()
        initiatives_list.index = 0  # rta
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        cats = [c.category for c in categories_list.children if isinstance(c, CategoryListItem)]
        assert cats == ["email-sequences", "rendered-outreach", "tracking"]

        await pilot.press("h")
        await pilot.pause(0.1)
        assert initiatives_list.has_focus
        initiatives_list.index = 1  # wealth-manager-products
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        cats2 = [c.category for c in categories_list.children if isinstance(c, CategoryListItem)]
        assert cats2 == []


@pytest.mark.asyncio
async def test_h_and_l_navigate_between_the_two_lists(mock_cocli_env, mocker) -> None:
    _make_initiative(CAMPAIGN, "rta", {"tracking": {"utm.csv": "x"}})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        categories_list = widget.query_one("#categories_list", ListView)

        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("l")
        await pilot.pause(0.2)
        assert categories_list.has_focus

        await pilot.press("h")
        await pilot.pause(0.1)
        assert initiatives_list.has_focus


@pytest.mark.asyncio
async def test_h_from_content_pane_stops_at_categories_list(mock_cocli_env, mocker) -> None:
    """Regression (2026-09-16): pressing h in the content pane's own file
    list moved focus to categories_list, then - because the pane's on_key
    only called prevent_default(), not stop() - the same keypress kept
    bubbling to InitiativesView's own "h" handler, which saw
    categories_list newly focused and hopped again, straight past it to
    initiatives_list. One "h" must move exactly one level."""
    _make_initiative(CAMPAIGN, "rta", {"rendered-outreach": {"utm.csv": "x"}})

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        categories_list = widget.query_one("#categories_list", ListView)

        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)
        categories_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_FileBrowserPane)
        file_list = pane.query_one("#file_browser_list", ListView)
        file_list.focus()
        await pilot.pause(0.1)
        assert file_list.has_focus

        await pilot.press("h")
        await pilot.pause(0.1)
        assert categories_list.has_focus
        assert not initiatives_list.has_focus

        await pilot.press("h")
        await pilot.pause(0.1)
        assert initiatives_list.has_focus


@pytest.mark.asyncio
async def test_email_sequences_pane_renders_selected_template(mock_cocli_env, mocker) -> None:
    _make_initiative(
        CAMPAIGN,
        "rta",
        {"email-sequences": {"hook.md": '---\nsubject: "Hi {first_name}"\n---\n\nBody for {company_name}'}},
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0  # email-sequences
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_EmailSequencesPane)
        file_list = pane.query_one("#email_sequences_file_list", ListView)
        assert len(file_list.children) == 1
        file_list.focus()
        file_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)

        subject_label = pane.preview.query_one("#template-preview-subject")
        body_static = pane.preview.query_one("#template-preview-body")
        assert "Hi Sample" in str(subject_label.content)
        assert "Body for Sample Co" in str(body_static.content)


@pytest.mark.asyncio
async def test_tracking_pane_shows_send_log_scoped_to_this_initiative(mock_cocli_env, mocker) -> None:
    """Tracking is backed by the real send log (SendLogEntry), not raw
    files - and must only show this initiative's own rows, not another
    initiative's, even though today they share one campaign-wide log."""
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    _make_initiative(CAMPAIGN, "rta", {"tracking": {".keep": "x"}})
    _write_send_log(
        CAMPAIGN,
        [
            SendLogEntry(
                batch_id="b1",
                template_id="t1",
                company_slug="acme",
                recipient="bob@acme.test",
                subject="Hi Bob",
                message_id="msg-1",
                status="sent",
                initiative="rta",
            ),
            SendLogEntry(
                batch_id="b1",
                template_id="t1",
                company_slug="bad-co",
                recipient="bad@co.test",
                subject="Hi",
                status="failed",
                error="boom",
                initiative="rta",
            ),
            SendLogEntry(
                batch_id="b2",
                template_id="t2",
                company_slug="other",
                recipient="other@co.test",
                subject="Other initiative",
                status="sent",
                initiative="wealth-manager-products",
            ),
        ],
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0  # tracking (only category present)
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_TrackingPane)
        entry_list = pane.query_one("#tracking_entry_list", ListView)
        assert len(entry_list.children) == 2  # not the wealth-manager-products row
        assert "Sent: 1" in str(pane.stats_label.content)
        assert "Failed: 1" in str(pane.stats_label.content)

        entry_list.focus()
        entry_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)

        body_static = pane.preview.query_one("#tracking-preview-body")
        content = str(body_static.content)
        assert "bob@acme.test" in content or "bad@co.test" in content
        assert "other@co.test" not in content


@pytest.mark.asyncio
async def test_tracking_pane_shows_bounce_complaint_counts_and_marks_the_row(
    mock_cocli_env, mocker
) -> None:
    """Bounce/complaint visibility is the whole point of the SQS
    ingestion pipeline - the Tracking pane must surface it, not just
    sent/failed counts."""
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry
    from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

    _make_initiative(CAMPAIGN, "rta", {"tracking": {".keep": "x"}})
    _write_send_log(
        CAMPAIGN,
        [
            SendLogEntry(
                batch_id="b1",
                template_id="t1",
                company_slug="acme",
                recipient="bob@acme.test",
                subject="Hi Bob",
                message_id="msg-bounced",
                status="sent",
                initiative="rta",
            ),
            SendLogEntry(
                batch_id="b1",
                template_id="t1",
                company_slug="other-co",
                recipient="fine@co.test",
                subject="Hi",
                message_id="msg-fine",
                status="sent",
                initiative="rta",
            ),
        ],
    )
    _write_ses_events(
        CAMPAIGN,
        [
            SesEventLogEntry(
                event_type="BOUNCE",
                message_id="msg-bounced",
                recipient="bob@acme.test",
                sub_type="Permanent",
            ),
        ],
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_TrackingPane)
        assert "Bounced: 1" in str(pane.stats_label.content)
        assert "Complaints: 0" in str(pane.stats_label.content)

        from cocli.tui.widgets.initiatives_view import TrackingListItem

        items = list(pane.entry_list.children)
        bounced_item = next(i for i in items if isinstance(i, TrackingListItem) and i.entry.message_id == "msg-bounced")
        fine_item = next(i for i in items if isinstance(i, TrackingListItem) and i.entry.message_id == "msg-fine")
        assert bounced_item.event_type == "BOUNCE"
        assert fine_item.event_type is None


@pytest.mark.asyncio
async def test_tracking_pane_l_opens_the_highlighted_entrys_company(mock_cocli_env, mocker) -> None:
    """A sent-email record is only useful if you can jump from it to the
    company it was sent to - mirrors the h/j/k/l vim convention already
    used throughout this screen (l = drill deeper)."""
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    _make_initiative(CAMPAIGN, "rta", {"tracking": {".keep": "x"}})
    _write_send_log(
        CAMPAIGN,
        [
            SendLogEntry(
                batch_id="b1",
                template_id="t1",
                company_slug="acme-financial",
                recipient="bob@acme.test",
                subject="Hi Bob",
                status="sent",
                initiative="rta",
            ),
        ],
    )

    app = CocliApp(services=ServiceContainer(campaign_name=CAMPAIGN), auto_show=False)
    async with app.run_test() as pilot:
        widget = InitiativesView()
        await app.main_content.mount(widget)
        await pilot.pause(0.2)

        initiatives_list = widget.query_one("#initiatives_list", ListView)
        initiatives_list.focus()
        initiatives_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        categories_list = widget.query_one("#categories_list", ListView)
        categories_list.index = 0
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.2)

        pane = widget.query_one(_TrackingPane)
        entry_list = pane.query_one("#tracking_entry_list", ListView)
        entry_list.focus()
        entry_list.index = 0
        await pilot.pause(0.1)

        mock_open = mocker.patch.object(app, "open_company_detail")
        await pilot.press("l")
        await pilot.pause(0.1)

        mock_open.assert_called_once_with("acme-financial")
