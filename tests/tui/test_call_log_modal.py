from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from textual.containers import VerticalScroll

from cocli.core.exclusions import ExclusionManager
from cocli.models.campaigns.queues.to_call import ToCallTask
from cocli.models.companies.company import Company
from cocli.tui.app import CocliApp
from cocli.tui.widgets.call_log_modal import CallLogModal


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_call_log_modal_saves_call_note_and_meeting(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    # Create dummy company
    co = Company(name="Acme Corp", slug="acme-corp", domain="acme.com", phone="555-111-2222")
    co.save()

    # Create pending task
    pending = ToCallTask(company_slug="acme-corp", domain="acme.com", campaign_name="roadmap")
    pending.save()
    assert pending.get_local_path().exists()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="acme-corp", phone="555-111-2222")
        app.push_screen(modal)
        await driver.pause()

        # Check disposition select exists
        disp_select = modal.query_one("#call_disposition")
        assert disp_select is not None

        # Fill notes
        modal.query_one("#call_notes").text = "Spoke with manager, callback scheduled."

        # Save
        await driver.press("ctrl+s")
        await driver.pause()

    # Verify notes/ directory has CallNote
    notes_dir = paths.companies.entry("acme-corp").path / "notes"
    assert notes_dir.exists()
    call_files = list(notes_dir.glob("*-call-*.md"))
    assert len(call_files) == 1
    call_content = call_files[0].read_text()
    assert "disposition: Follow Up Needed" in call_content
    assert "Spoke with manager, callback scheduled." in call_content

    # Verify meetings/ directory has Meeting
    meetings_dir = paths.companies.entry("acme-corp").path / "meetings"
    assert meetings_dir.exists()
    meeting_files = list(meetings_dir.glob("*.md"))
    assert len(meeting_files) == 1


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_call_log_modal_handles_exclusion_disposition(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    co = Company(
        name="Bad Prospect", slug="bad-prospect", domain="badprospect.com", phone="555-999-0000"
    )
    co.save()

    pending = ToCallTask(
        company_slug="bad-prospect", domain="badprospect.com", campaign_name="roadmap"
    )
    pending.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="bad-prospect", phone="555-999-0000")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#call_disposition").value = "Not Interested"
        modal.query_one("#call_notes").text = "Requested to be excluded."

        await driver.press("ctrl+s")
        await driver.pause()

    # Check exclusion manager
    ex_mgr = ExclusionManager("roadmap")
    assert ex_mgr.is_excluded(slug="bad-prospect", domain="badprospect.com")


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_wrong_trade_disposition_uses_shared_mark_invalid_path(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """The new disposition must go through mark_to_call_invalid() - the
    same campaign-wide mechanism as the m,i keybinding - not a bespoke
    exclude call, so it's reversible via m,v and shows up in the "Invalid"
    TUI template regardless of whether the disqualification came from a
    phone call or a list keypress (conversation 2026-09-14)."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.queues.to_call_invalid import ToCallInvalidTask

    monkeypatch.setattr(paths, "root", tmp_path)

    co = Company(
        name="Wrong Trade Co", slug="wrong-trade-co", domain="wrongtrade.com", phone="555-222-3333"
    )
    co.save()

    pending = ToCallTask(
        company_slug="wrong-trade-co", domain="wrongtrade.com", campaign_name="roadmap"
    )
    pending.save()
    pending_path = pending.get_local_path()
    assert pending_path.exists()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="wrong-trade-co", phone="555-222-3333")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#call_disposition").value = "Wrong Trade / No Fit"
        modal.query_one("#call_notes").text = "Doesn't install sheet vinyl at all."

        await driver.press("ctrl+s")
        await driver.pause()

    ex_mgr = ExclusionManager("roadmap")
    assert ex_mgr.is_excluded(slug="wrong-trade-co", domain="wrongtrade.com")

    # Pending file removed outright (not moved to completed/) - same
    # behavior as mark_to_call_invalid via m,i.
    assert not pending_path.exists()

    # Review-pile record exists with the specific reason, same as m,i.
    invalid_task = ToCallInvalidTask(
        company_slug="wrong-trade-co", domain="wrongtrade.com", campaign_name="roadmap"
    )
    assert invalid_task.get_local_path().exists()
    assert "Wrong Trade / No Fit" in invalid_task.get_local_path().read_text()


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_blank_followup_date_means_no_reschedule(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """No checkbox anymore: an empty follow-up date IS "don't reschedule".
    Confirmed 2026-09-14 the checkbox was one more GUI-ish control this
    keyboard-first TUI didn't need."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    co = Company(
        name="No Reschedule Co", slug="no-reschedule-co", domain="noreschedule.com", phone="555-444-5555"
    )
    co.save()
    pending = ToCallTask(
        company_slug="no-reschedule-co", domain="noreschedule.com", campaign_name="roadmap"
    )
    pending.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="no-reschedule-co", phone="555-444-5555")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#callback_date").value = ""
        await driver.press("ctrl+s")
        await driver.pause()

    completed_dir = paths.campaign("roadmap").path / "queues" / "to-call" / "completed"
    assert list(completed_dir.glob("*no-reschedule-co*"))

    pending_dir = paths.campaign("roadmap").path / "queues" / "to-call" / "pending"
    assert not list(pending_dir.glob("*no-reschedule-co*"))


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_right_column_shows_call_reference_files(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """The live-call reference panel (script, phrases, comparison) - the
    layout Mark asked for (2026-09-16): everything existing fits in the
    left column, the right column is call-time reference material."""
    from cocli.core.paths import paths
    from cocli.tui.widgets.call_log_modal import Markdown

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Ref Co", slug="ref-co", domain="ref.test", phone="555-333-4444")
    co.save()

    scripts_dir = paths.campaigns / "roadmap" / "initiatives" / "rta" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "call-opener.md").write_text("# Opener\n\nSay hello.", encoding="utf-8")
    (scripts_dir / "preferred-phrases.md").write_text("# Phrases\n\nUse trajectory.", encoding="utf-8")
    (scripts_dir / "product-comparison.md").write_text("# Comparison\n\neMoney is bigger.", encoding="utf-8")

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        modal = CallLogModal(company_slug="ref-co", phone="555-333-4444")
        app.push_screen(modal)
        await pilot.pause(0.2)

        script_panel = modal.query_one("#call-script-panel", Markdown)
        phrases_panel = modal.query_one("#call-phrases-panel", Markdown)
        comparison_panel = modal.query_one("#call-comparison-panel", Markdown)
        assert "Say hello." in script_panel._markdown
        assert "Use trajectory." in phrases_panel._markdown
        assert "eMoney is bigger." in comparison_panel._markdown

        # Left column still has everything it had before.
        assert modal.query_one("#call_disposition") is not None
        assert modal.query_one("#call_notes") is not None
        assert modal.query_one("#callback_date") is not None
        assert modal.query_one("#followup_template") is not None
        assert modal.query_one("#followup_email_date") is not None

        assert "(555) 333-4444" in str(modal.query_one("#call_phone").content)
        local_time = str(modal.query_one("#company_local_time").content)
        assert "AM" in local_time or "PM" in local_time


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_shift_j_k_scroll_reference_pane_without_leaking_into_notes(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Mark (2026-09-18): shift+j/shift+k should scroll the right-hand
    reference pane down/up - including while call_notes (a TextArea) has
    focus, since that's where typing happens during a live call. Bound
    with priority=True so the TextArea never gets a chance to insert the
    letter as text first."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Scroll Co", slug="scroll-co", domain="scroll.test", phone="555-666-7777")
    co.save()

    scripts_dir = paths.campaigns / "roadmap" / "initiatives" / "rta" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    long_body = "\n\n".join(f"Paragraph {i} of the call opener." for i in range(60))
    (scripts_dir / "call-opener.md").write_text(f"# Opener\n\n{long_body}", encoding="utf-8")
    (scripts_dir / "preferred-phrases.md").write_text("# Phrases", encoding="utf-8")
    (scripts_dir / "product-comparison.md").write_text("# Comparison", encoding="utf-8")

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="scroll-co", phone="555-666-7777")
        app.push_screen(modal)
        await driver.pause(0.2)

        notes = modal.query_one("#call_notes")
        notes.focus()
        assert notes.has_focus

        right_pane = modal.query_one("#call-log-right", VerticalScroll)
        assert right_pane.scroll_target_y == 0

        await driver.press("shift+j")
        await driver.pause()

        assert right_pane.scroll_target_y > 0
        assert notes.text == ""  # the "J" never leaked into the TextArea

        scrolled_down_to = right_pane.scroll_target_y
        await driver.press("shift+k")
        await driver.pause()

        assert right_pane.scroll_target_y < scrolled_down_to
        assert notes.text == ""


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_email_follow_up_scheduled_when_template_picked(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Jimmy Jean case (2026-09-16): a templated email follow-up,
    separate from the call re-queue, must land in the follow-up queue
    for later review/send - not sent automatically, not conflated with
    ToCallTask's callback_at."""
    from cocli.application.follow_up_service import FollowUpService
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Jimmy Jean Insurance", slug="jimmy-jean", domain="jimmyjean.test", phone="555-777-8888")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="jimmy-jean", phone="555-777-8888")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#followup_template").value = "email_02_screenshots.md"
        modal.query_one("#followup_email_date").value = "2026-09-30"
        await driver.press("ctrl+s")
        await driver.pause()

    follow_ups = FollowUpService("roadmap").list_pending(company_slug="jimmy-jean")
    assert len(follow_ups) == 1
    assert follow_ups[0].format == "email"
    assert follow_ups[0].template_id == "email_02_screenshots.md"
    assert follow_ups[0].scheduled_at.strftime("%Y-%m-%d") == "2026-09-30"


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_natural_language_follow_up_dates(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    from cocli.application.follow_up_service import FollowUpService
    from cocli.core.paths import paths
    from cocli.models.campaigns.queues.to_call import ToCallTask as PendingToCall

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="When Co",
        slug="when-co",
        domain="when.test",
        phone="555-888-9999",
        timezone="America/Chicago",
    )
    co.save()
    PendingToCall(company_slug="when-co", domain="when.test", campaign_name="roadmap").save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="when-co", phone="5558889999")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#callback_date").value = "monday"
        modal.query_one("#followup_template").value = "email_02_screenshots.md"
        modal.query_one("#followup_email_date").value = "next week"
        await driver.press("ctrl+s")
        await driver.pause()

    company = Company.get("when-co")
    assert company is not None
    assert company.callback_at is not None
    assert company.callback_at.weekday() == 0
    assert company.callback_at > datetime.now(UTC) - timedelta(seconds=5)

    follow_ups = FollowUpService("roadmap").list_pending(company_slug="when-co")
    assert len(follow_ups) == 1
    assert follow_ups[0].scheduled_at > datetime.now(UTC)


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_call_log_shows_dallas_time_and_known_contacts(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """aquila-shaped record: no timezone/state on the company, Dallas in
    website copy, plus a founder name and office email."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(
        name="Aquila Financial",
        slug="aquila-financial-tax-services",
        domain="aftaxservices.com",
        phone="2148884398",
        street_address="13355 Noel Rd",
        email="info@aftaxservices.com",
    )
    co.save()
    enrich = paths.companies.entry("aquila-financial-tax-services").path / "enrichments"
    enrich.mkdir(parents=True, exist_ok=True)
    (enrich / "website.md").write_text(
        "---\n"
        "url: https://aftaxservices.com/\n"
        "email: info@aftaxservices.com\n"
        "personnel:\n"
        "- name: James Aquila\n"
        "  title: Founder\n"
        "description: |\n"
        "  Located in North Dallas.\n"
        "  Dallas, TX 75240\n"
        "---\n",
        encoding="utf-8",
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(
            company_slug="aquila-financial-tax-services", phone="2148884398"
        )
        app.push_screen(modal)
        await driver.pause(0.2)

        local_time = str(modal.query_one("#company_local_time").content)
        assert "CDT" in local_time or "CST" in local_time
        assert "Dallas" in local_time
        assert "PDT" not in local_time and "PST" not in local_time

        contacts = str(modal.query_one("#call-contacts").content)
        assert "James Aquila" in contacts
        assert "info@aftaxservices.com" in contacts


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_no_email_follow_up_scheduled_by_default(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Leaving the template picker on its default must not silently
    schedule anything."""
    from cocli.application.follow_up_service import FollowUpService
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="No Follow Up Co", slug="no-follow-up-co", domain="nofollowup.test", phone="555-000-1111")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="no-follow-up-co", phone="555-000-1111")
        app.push_screen(modal)
        await driver.pause()

        await driver.press("ctrl+s")
        await driver.pause()

    assert FollowUpService("roadmap").list_pending(company_slug="no-follow-up-co") == []


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_escape_with_empty_notes_dismisses_without_confirmation(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Nothing typed yet - no need to nag for a confirmation."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Empty Co", slug="empty-co", domain="empty.com", phone="555-000-0000")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="empty-co", phone="555-000-0000")
        app.push_screen(modal)
        await driver.pause()

        await driver.press("escape")
        await driver.pause()

        assert app.screen is not modal


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_escape_with_notes_requires_confirmation_before_discarding(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression (2026-09-16): real call notes were lost to an
    unconfirmed instant discard on escape/alt+s during a live call to
    Jimmy Jean Insurance. Declining the confirmation must keep the modal
    open with the typed notes intact."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Notes Co", slug="notes-co", domain="notes.com", phone="555-111-0000")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="notes-co", phone="555-111-0000")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#call_notes").text = "Talked for 20 minutes, very interested."
        await driver.press("escape")
        await driver.pause()

        # Declining must not discard - modal stays open, text intact.
        await driver.press("n")
        await driver.pause()

        assert app.screen is modal
        assert modal.query_one("#call_notes").text == "Talked for 20 minutes, very interested."

        # Confirming discards for real.
        await driver.press("escape")
        await driver.pause()
        await driver.press("y")
        await driver.pause()

        assert app.screen is not modal


@pytest.mark.asyncio
@patch("cocli.tui.widgets.call_log_modal.get_campaign", return_value="roadmap")
async def test_alt_s_while_typing_exits_insert_mode_not_the_screen(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression (2026-09-16, second pass): the app-level alt+s shim's
    first fix routed alt+s through action_cancel() (confirm-before-
    discard) - safer than a blind dismiss, but still wrong. Mark's actual
    ask: alt+s while typing in a TextArea means "exit INSERT mode," i.e.
    stop capturing keys as text, and must never leave the screen at all -
    not even with a confirmation prompt. Only an explicit "escape"/cancel
    gesture should offer to discard."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Alt S Co", slug="alt-s-co", domain="alts.com", phone="555-222-0000")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="alt-s-co", phone="555-222-0000")
        app.push_screen(modal)
        await driver.pause()

        notes = modal.query_one("#call_notes")
        notes.focus()
        notes.text = "Do not lose this."
        await driver.pause()

        await driver.press("alt+s")
        await driver.pause()

        # Still on the same screen - no confirmation dialog, no dismiss.
        assert app.screen is modal
        assert modal.query_one("#call_notes").text == "Do not lose this."
        # Focus moved off the TextArea - that's the "exit insert mode" part.
        assert not notes.has_focus
