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
