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
