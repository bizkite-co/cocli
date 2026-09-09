from __future__ import annotations

from typing import Any

from cocli.application.personalized_outreach_service import (
    PersonalizedOutreachService,
    extract_first_name,
)
from cocli.models.companies.company import Company
from cocli.models.people.person import Person


def test_extract_first_name() -> None:
    assert extract_first_name("Dr. Alice Smith") == "Alice"
    assert extract_first_name("Bob Jones") == "Bob"
    assert extract_first_name("Ms. Carol Johnson") == "Carol"
    assert extract_first_name("") is None
    assert extract_first_name("123") is None


def test_generate_copy_includes_name_and_utm() -> None:
    service = PersonalizedOutreachService("roadmap")
    subject, body = service.generate_copy(
        first_name="David",
        company_name="Apex Financial",
        company_slug="apex-financial",
    )

    assert "David," in subject
    assert "Apex Financial" in subject
    assert "https://getretirementtaxanalyzer.com?" in body
    assert "utm_source=email_sequence" in body
    assert "utm_campaign=roadmap" in body
    assert "utm_content=apex-financial" in body
    assert "utm_term=david" in body


def test_find_eligible_prospects(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Target Financial",
        slug="target-financial",
        domain="targetfinancial.com",
        email="info@targetfinancial.com",
        tags=["roadmap"],
    )
    company.save()

    person = Person(
        name="Edward Miller",
        email="edward@targetfinancial.com",
        company_name="Target Financial",
        slug="edward-miller",
    )
    person.save()

    # Link contact to company
    contacts_dir = paths.companies.entry("target-financial").path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    symlink = contacts_dir / "edward-miller"
    symlink.symlink_to(person.get_local_path())

    service = PersonalizedOutreachService("roadmap")
    matches = service.find_eligible_prospects(limit=10)

    assert len(matches) == 1
    assert matches[0].company_slug == "target-financial"
    assert matches[0].first_name == "Edward"
    assert matches[0].recipient_email == "edward@targetfinancial.com"
