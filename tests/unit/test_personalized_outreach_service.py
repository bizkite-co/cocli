from __future__ import annotations

from typing import Any

from cocli.application.personalized_outreach_service import (
    ProspectContactMatch,
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
    assert len(subject) > 15
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


class _FakeEmailResult:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class _FakeEmailService:
    """Stand-in for EmailService.send() - raises for recipients in fail_for
    so per-recipient isolation can be exercised without SES/1Password."""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.sent_to: list[str] = []

    def send(self, request: Any) -> _FakeEmailResult:
        self.sent_to.append(request.to_address)
        if request.to_address in self.fail_for:
            raise RuntimeError("SES boom")
        return _FakeEmailResult(message_id=f"msg-{request.to_address}")


def _match(slug: str, email: str, subject: str = "Hi") -> ProspectContactMatch:
    return ProspectContactMatch(
        company_slug=slug,
        company_name=slug.replace("-", " ").title(),
        recipient_email=email,
        contact_name="Contact Person",
        first_name="Contact",
        role=None,
        subject=subject,
        body=f"body for {slug}",
    )


def test_send_batch_isolates_per_recipient_failures(tmp_path: Any, monkeypatch: Any) -> None:
    """One failing recipient must not stop the others from being attempted
    and logged - same isolation discipline as requeue_enrichment_gaps."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    matches = [_match("good-co", "good@co.test"), _match("bad-co", "bad@co.test")]
    fake_email_service = _FakeEmailService(fail_for={"bad@co.test"})

    service = PersonalizedOutreachService("roadmap")
    result = service.send_batch(
        matches, template_id="email_01_pas_hook.md", email_service=fake_email_service
    )

    assert result.sent == 1
    assert result.failed == 1
    assert fake_email_service.sent_to == ["good@co.test", "bad@co.test"]

    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir("roadmap")
    log_path = index_dir / "log.usv"
    entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    by_slug = {e.company_slug: e for e in entries}

    assert by_slug["good-co"].status == "sent"
    assert by_slug["good-co"].message_id == "msg-good@co.test"
    assert by_slug["good-co"].batch_id == result.batch_id

    assert by_slug["bad-co"].status == "failed"
    assert by_slug["bad-co"].error is not None
    assert by_slug["bad-co"].batch_id == result.batch_id

    assert (index_dir / "datapackage.json").exists()


def test_send_batch_appends_across_calls(tmp_path: Any, monkeypatch: Any) -> None:
    """Each send_batch() call is a new batch_id but must append to, not
    overwrite, prior batches' rows in the same log."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")

    first = service.send_batch(
        [_match("first-co", "first@co.test")],
        template_id="t1",
        email_service=_FakeEmailService(),
    )
    second = service.send_batch(
        [_match("second-co", "second@co.test")],
        template_id="t1",
        email_service=_FakeEmailService(),
    )

    assert first.batch_id != second.batch_id

    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    log_path = SendLogEntry.get_index_dir("roadmap") / "log.usv"
    entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert {e.company_slug for e in entries} == {"first-co", "second-co"}


def test_load_template_prefers_generic_dir_over_rta_dir(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    generic_dir = paths.campaigns / "turboship" / "email-templates"
    generic_dir.mkdir(parents=True)
    (generic_dir / "welcome.md").write_text(
        '---\nsubject: "Generic {first_name}"\n---\n\nGeneric body {landing_url}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("turboship")
    subject, body = service.load_template("welcome.md")

    assert subject == "Generic {first_name}"
    assert "Generic body" in body


def test_load_template_falls_back_to_rta_dir_when_generic_absent(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    rta_dir = paths.campaigns / "roadmap" / "initiatives" / "rta" / "email-sequences"
    rta_dir.mkdir(parents=True)
    (rta_dir / "legacy.md").write_text(
        '---\nsubject: "Legacy {first_name}"\n---\n\nLegacy body {landing_url}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("roadmap")
    subject, body = service.load_template("legacy.md")

    assert subject == "Legacy {first_name}"
    assert "Legacy body" in body
