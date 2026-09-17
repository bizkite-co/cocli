"""TargetBatchesView's edit action - "add my own text on top of the
template, then send" (Mark, 2026-09-16)."""

from __future__ import annotations

from typing import Any

import pytest
from textual.widgets import ListView

from cocli.application.personalized_outreach_service import PersonalizedOutreachService
from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.edit_pending_entry_modal import EditPendingEntryModal
from cocli.tui.widgets.target_batches_view import TargetBatchesView


def _freeze_one_batch(tmp_path: Any, monkeypatch: Any) -> str:
    from cocli.models.companies.company import Company
    from cocli.models.people.person import Person

    monkeypatch.setattr(paths, "root", tmp_path)
    company = Company(name="Acme Corp", slug="acme-corp", domain="acme.test", tags=["roadmap"])
    company.save()
    person = Person(name="Edward Miller", email="edward@acme.test", slug="edward-miller")
    person.save()
    contacts_dir = paths.companies.entry("acme-corp").path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / "edward-miller").symlink_to(person.get_local_path())

    service = PersonalizedOutreachService("roadmap")
    return service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")


@pytest.mark.asyncio
async def test_e_opens_edit_modal_prefilled_with_rendered_draft(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.application.services import ServiceContainer

    _freeze_one_batch(tmp_path, monkeypatch)

    app = CocliApp(services=ServiceContainer(campaign_name="roadmap"), auto_show=False)
    async with app.run_test() as pilot:
        view = TargetBatchesView()
        await app.query_one("#app_content").mount(view)
        await pilot.pause(0.2)

        list_view = view.query_one(ListView)
        assert len(list_view.children) == 1
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        await pilot.press("e")
        await pilot.pause(0.2)

        assert isinstance(app.screen, EditPendingEntryModal)
        subject_value = app.screen.query_one("#edit-pending-subject").value
        assert "David" not in subject_value  # sanity: not a stale/empty field
        assert subject_value


@pytest.mark.asyncio
async def test_edit_and_save_persists_to_pending_batch(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.application.services import ServiceContainer

    _freeze_one_batch(tmp_path, monkeypatch)

    app = CocliApp(services=ServiceContainer(campaign_name="roadmap"), auto_show=False)
    async with app.run_test() as pilot:
        view = TargetBatchesView()
        await app.query_one("#app_content").mount(view)
        await pilot.pause(0.2)

        list_view = view.query_one(ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        await pilot.press("e")
        await pilot.pause(0.2)
        assert isinstance(app.screen, EditPendingEntryModal)

        app.screen.query_one("#edit-pending-subject").value = "My custom subject"
        app.screen.query_one("#edit-pending-body").text = "Personal note.\n\nRest of body."
        await pilot.press("ctrl+s")
        await pilot.pause(0.2)

        assert not isinstance(app.screen, EditPendingEntryModal)

    entries = PersonalizedOutreachService("roadmap").list_pending_batches()
    assert len(entries) == 1
    assert entries[0].subject == "My custom subject"
    assert "Personal note." in entries[0].body.replace("<br>", "\n")


@pytest.mark.asyncio
async def test_edit_cancel_does_not_touch_the_pending_entry(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.application.services import ServiceContainer

    _freeze_one_batch(tmp_path, monkeypatch)
    original = PersonalizedOutreachService("roadmap").list_pending_batches()[0]

    app = CocliApp(services=ServiceContainer(campaign_name="roadmap"), auto_show=False)
    async with app.run_test() as pilot:
        view = TargetBatchesView()
        await app.query_one("#app_content").mount(view)
        await pilot.pause(0.2)

        list_view = view.query_one(ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        await pilot.press("e")
        await pilot.pause(0.2)
        assert isinstance(app.screen, EditPendingEntryModal)

        app.screen.query_one("#edit-pending-subject").value = "Should not be saved"
        await pilot.press("escape")
        await pilot.pause(0.2)

        assert not isinstance(app.screen, EditPendingEntryModal)

    entries = PersonalizedOutreachService("roadmap").list_pending_batches()
    assert entries[0].subject == original.subject
