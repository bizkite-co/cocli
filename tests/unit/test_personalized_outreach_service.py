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
        self.sent_requests: list[Any] = []

    def send(self, request: Any) -> _FakeEmailResult:
        self.sent_to.append(request.to_address)
        self.sent_requests.append(request)
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


def _make_eligible_prospect(
    paths: Any,
    *,
    slug: str = "acme-financial",
    company_name: str = "Acme Financial",
    first_name: str = "Bob",
    email_addr: str = "bob@acme.test",
) -> None:
    """Same setup shape as test_find_eligible_prospects above: a company
    tagged for the campaign, with a linked contact having a real first
    name and email - the minimum find_eligible_prospects() needs."""
    company = Company(
        name=company_name,
        slug=slug,
        domain=f"{slug}.test",
        email=email_addr,
        tags=["roadmap"],
    )
    company.save()

    person_slug = f"{first_name.lower()}-{slug}"
    person = Person(
        name=f"{first_name} Smith",
        email=email_addr,
        company_name=company_name,
        slug=person_slug,
    )
    person.save()

    contacts_dir = paths.companies.entry(slug).path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / person_slug).symlink_to(person.get_local_path())


def test_freeze_batch_writes_rendered_pending_entries(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    pending = service.list_pending_batches()
    assert len(pending) == 1
    assert pending[0].batch_id == batch_id
    assert pending[0].template_id == "email_01_pas_hook.md"
    assert pending[0].company_slug == "acme-financial"
    assert pending[0].recipient == "bob@acme.test"
    # Fully rendered, not a raw template - no unresolved placeholders left.
    assert "{first_name}" not in pending[0].subject
    assert "Bob" in pending[0].subject


def test_freeze_batch_raises_on_bad_template_placeholder(tmp_path: Any, monkeypatch: Any) -> None:
    """A template bug must surface at freeze time, not after a batch has
    already been queued for review or send."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    template_dir = paths.campaigns / "roadmap" / "email-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "broken.md").write_text(
        '---\nsubject: "Hi {first_name}"\n---\n\nSee {this_field_does_not_exist}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("roadmap")
    import pytest

    with pytest.raises(KeyError):
        service.freeze_batch(limit=10, template_id="broken.md")

    assert service.list_pending_batches() == []


def test_send_pending_batch_sends_and_removes_only_that_batch(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    # An unrelated pending batch must survive untouched.
    other_index_dir = PendingBatchEntry.get_index_dir("roadmap")
    with open(other_index_dir / "pending.usv", "a", encoding="utf-8") as f:
        f.write(
            PendingBatchEntry(
                batch_id="other-batch",
                template_id="t2",
                company_slug="other-co",
                recipient="other@co.test",
                subject="Other subject",
                body="Other body",
            ).to_usv()
        )

    fake_email_service = _FakeEmailService()
    result = service.send_pending_batch(batch_id, email_service=fake_email_service)

    assert result.sent == 1
    assert result.failed == 0
    assert fake_email_service.sent_to == ["bob@acme.test"]

    remaining = service.list_pending_batches()
    assert [e.batch_id for e in remaining] == ["other-batch"]

    log_path = SendLogEntry.get_index_dir("roadmap") / "log.usv"
    sent_entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert len(sent_entries) == 1
    assert sent_entries[0].company_slug == "acme-financial"
    assert sent_entries[0].status == "sent"


def test_send_pending_batch_restores_real_newlines_in_body(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """PendingBatchEntry.to_usv() sanitizes newlines to '<br>' for USV
    storage - the actual sent email must see real newlines back, not
    literal '<br>' text (that would itself be exactly the kind of
    send-time flaw the review step exists to catch)."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    fake_email_service = _FakeEmailService()
    service.send_pending_batch(batch_id, email_service=fake_email_service)

    sent_body = fake_email_service.sent_requests[0].body
    assert "<br>" not in sent_body
    assert "\n" in sent_body


def test_discard_pending_batch_removes_without_sending(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    fake_email_service = _FakeEmailService()
    service.discard_pending_batch(batch_id)

    assert service.list_pending_batches() == []
    assert fake_email_service.sent_to == []


def test_compute_unsubscribe_rate(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.application.personalized_outreach_service import compute_unsubscribe_rate
    from cocli.core.exclusions import ExclusionManager
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    monkeypatch.setattr(paths, "root", tmp_path)

    index_dir = SendLogEntry.get_index_dir("roadmap")
    index_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        SendLogEntry(
            batch_id="b1", template_id="t1", company_slug=f"co-{i}",
            recipient=f"co{i}@test.com", subject="Hi", status="sent",
        )
        for i in range(4)
    ] + [
        SendLogEntry(
            batch_id="b1", template_id="t1", company_slug="co-failed",
            recipient="failed@test.com", subject="Hi", status="failed", error="boom",
        )
    ]
    with open(index_dir / "log.usv", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_usv())

    ExclusionManager("roadmap").add_exclusion(
        slug="co-1", domain="co1@test.com", reason="unsubscribe:COMPLAINT"
    )
    ExclusionManager("roadmap").add_exclusion(
        slug="co-wrong-trade", domain="wrong@test.com", reason="to-call-nonconforming"
    )

    stats = compute_unsubscribe_rate("roadmap")

    assert stats.sent_count == 4
    assert stats.unsubscribed_count == 1
    assert stats.rate == 0.25
