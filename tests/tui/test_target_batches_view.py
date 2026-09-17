"""TargetBatchesView's edit action - "add my own text on top of the
template, then send" (Mark, 2026-09-16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from textual.widgets import ListView

from cocli.application.personalized_outreach_service import PersonalizedOutreachService
from cocli.core.paths import paths
from cocli.tui.app import CocliApp
from cocli.tui.widgets.edit_pending_entry_modal import EditPendingEntryModal
from cocli.tui.widgets.target_batches_view import TargetBatchesView


def _freeze_one_batch(
    tmp_path: Any, monkeypatch: Any, template_id: str = "email_01_pas_hook.md"
) -> str:
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
    return service.freeze_batch(limit=10, template_id=template_id)


def _write_layout_template() -> None:
    """Assumes paths.root is already isolated (call after _freeze_one_batch,
    which is what actually monkeypatches it)."""
    templates_dir = paths.campaigns / "roadmap" / "email-templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "email_02_product_overview.md").write_text(
        "---\n"
        "subject_templates:\n"
        "  - '{first_name}, take a look'\n"
        "layout: email_02_product_overview.njk\n"
        "---\n"
        "Hi {first_name},\n\nCheck out {landing_url}.\n",
        encoding="utf-8",
    )
    (templates_dir / "email_02_product_overview.njk").write_text(
        "<html><body>{{ content | safe }}</body></html>", encoding="utf-8"
    )


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


@pytest.mark.asyncio
async def test_open_preview_warns_for_plain_text_template(tmp_path: Any, monkeypatch: Any) -> None:
    """A plain-text .md template (no `layout:`) has no HTML to preview -
    "o" must say so rather than silently doing nothing."""
    from unittest.mock import patch

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

        with patch.object(app, "notify") as mock_notify:
            await pilot.press("o")
            await pilot.pause(0.1)

    assert any("No HTML preview" in call.args[0] for call in mock_notify.call_args_list)


@pytest.mark.asyncio
async def test_open_preview_materializes_draft_and_opens_html(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """"o" on an entry frozen via "New Batch" (no rendered-outreach file
    yet, unlike a follow-up) must still work - it materializes the draft
    on the fly, renders the HTML, and opens it."""
    from unittest.mock import patch

    from cocli.application.services import ServiceContainer

    _freeze_one_batch(tmp_path, monkeypatch, template_id="email_02_product_overview.md")
    _write_layout_template()

    app = CocliApp(services=ServiceContainer(campaign_name="roadmap"), auto_show=False)
    async with app.run_test() as pilot:
        view = TargetBatchesView()
        await app.query_one("#app_content").mount(view)
        await pilot.pause(0.2)

        list_view = view.query_one(ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause(0.1)

        with patch("cocli.utils.open_url.open_url", return_value=True) as mock_open_url:
            await pilot.press("o")
            await pilot.pause(0.1)

    mock_open_url.assert_called_once()
    opened_path = mock_open_url.call_args.args[0]
    assert opened_path.endswith("email_02_product_overview.html")
    assert Path(opened_path).exists()
