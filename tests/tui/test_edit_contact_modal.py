"""Contacts panel: the real contact editor (Mark, 2026-10-09), replacing
the former "Edit Contact coming soon" stub, plus the "w" profile-page
open action and the refusal to edit non-Person-backed rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.people.person import Person
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_detail import CompanyDetail
from cocli.tui.widgets.edit_contact_modal import EditContactModal


def _link_contact(company_slug: str, person: Person) -> None:
    person.save()
    contacts_dir = paths.companies.entry(company_slug).path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / person.slug).symlink_to(person.get_local_path())


@pytest.mark.asyncio
async def test_edit_item_opens_editor_and_save_updates_the_contact(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Higginbotham - Mitch Gaylord", slug="higginbotham-mitch-gaylord"
    )
    company.save()
    person = Person(
        name="Mitch Gaylord",
        slug="mitch-gaylord",
        email="mgaylord@higginbotham.com",
        phone="18007282374",
    )
    _link_contact("higginbotham-mitch-gaylord", person)

    from cocli.application.company_service import get_company_details_for_view

    company_data = get_company_details_for_view("higginbotham-mitch-gaylord")
    assert company_data is not None

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.contacts_table.focus()
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()

        assert isinstance(app.screen, EditContactModal)
        assert app.screen.query_one("#edit_contact_phone").value == "+1 (800) 728-2374"

        app.screen.query_one("#edit_contact_phone").value = "19494907817"
        app.screen.query_one("#edit_contact_profile_url").value = (
            "https://www.higginbotham.com/team/mitchell-gaylord/"
        )
        app.screen.query_one("#edit_contact_linkedin_url").value = (
            "https://www.linkedin.com/in/mitchell-gaylord/"
        )
        await pilot.press("ctrl+s")
        await pilot.pause()

        assert not isinstance(app.screen, EditContactModal)

    updated = Person.get("mitch-gaylord")
    assert updated is not None
    assert updated.phone is not None
    assert str(updated.phone) == "19494907817"
    assert updated.profile_url == "https://www.higginbotham.com/team/mitchell-gaylord/"
    assert updated.linkedin_url == "https://www.linkedin.com/in/mitchell-gaylord/"

    # The in-memory contacts list (used by action_call_company) reflects
    # the edit without needing to reopen Company Detail.
    refreshed_contact = detail.company_data["contacts"][0]
    assert refreshed_contact.get("phone") == "19494907817"


@pytest.mark.asyncio
async def test_edit_item_refuses_for_a_website_scraped_row_with_no_slug(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company = Company(name="Scraped Co", slug="scraped-co")
    company.save()

    company_data = {
        "company": {"name": "Scraped Co", "slug": "scraped-co"},
        "contacts": [{"name": "Website Lead", "email": "lead@scraped.test", "role": "website"}],
        "meetings": [],
        "notes": [],
        "website_data": None,
        "tags": [],
        "enrichment_path": None,
    }

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.contacts_table.focus()
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()

        assert not isinstance(app.screen, EditContactModal)


@pytest.mark.asyncio
async def test_open_profile_opens_browser_when_set(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company = Company(name="Profile Co", slug="profile-co")
    company.save()
    person = Person(
        name="Has Profile", slug="has-profile", profile_url="https://example.test/team/has-profile/"
    )
    _link_contact("profile-co", person)

    from cocli.application.company_service import get_company_details_for_view

    company_data = get_company_details_for_view("profile-co")
    assert company_data is not None

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.contacts_table.focus()
        await pilot.pause()

        with patch(
            "cocli.tui.widgets.company_detail.open_url", return_value=True
        ) as mock_open:
            await pilot.press("w")
            await pilot.pause()

        mock_open.assert_called_once_with("https://example.test/team/has-profile/")


@pytest.mark.asyncio
async def test_open_profile_warns_when_not_set(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(paths, "root", tmp_path)
    company = Company(name="No Profile Co", slug="no-profile-co")
    company.save()
    person = Person(name="No Profile", slug="no-profile")
    _link_contact("no-profile-co", person)

    from cocli.application.company_service import get_company_details_for_view

    company_data = get_company_details_for_view("no-profile-co")
    assert company_data is not None

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        detail = CompanyDetail(company_data)
        await app.query_one("#app_content").mount(detail)
        await pilot.pause()

        detail.contacts_table.focus()
        await pilot.pause()

        with patch("cocli.tui.widgets.company_detail.open_url") as mock_open:
            await pilot.press("w")
            await pilot.pause()

        mock_open.assert_not_called()
