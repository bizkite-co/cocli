from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

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
async def test_alt_s_with_notes_requires_confirmation_not_blind_dismiss(
    _mock_campaign: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """The app-level alt+s "universal escape" shim (app.py) used to call
    dismiss(None) directly on any modal it didn't specifically recognize -
    bypassing CallLogModal's own confirmation entirely. It must route
    through action_cancel() instead."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    co = Company(name="Alt S Co", slug="alt-s-co", domain="alts.com", phone="555-222-0000")
    co.save()

    app = CocliApp(auto_show=False)
    async with app.run_test() as driver:
        modal = CallLogModal(company_slug="alt-s-co", phone="555-222-0000")
        app.push_screen(modal)
        await driver.pause()

        modal.query_one("#call_notes").text = "Do not lose this."
        await driver.press("alt+s")
        await driver.pause()

        # A confirmation dialog, not an immediate blind dismiss.
        from cocli.tui.widgets.confirm_screen import ConfirmScreen

        assert isinstance(app.screen, ConfirmScreen)

        await driver.press("n")
        await driver.pause()

        # Declining returns to the modal with notes intact.
        assert app.screen is modal
        assert modal.query_one("#call_notes").text == "Do not lose this."
