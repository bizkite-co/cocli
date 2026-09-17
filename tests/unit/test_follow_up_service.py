"""FollowUpService: schedule now, process when due - "call" folds into
the existing to-call queue, "email" renders into the existing
pending-batch review queue (never auto-sent)."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

from cocli.application.follow_up_service import FollowUpService
from cocli.models.companies.company import Company
from cocli.models.people.person import Person


def _make_company_with_contact(paths_mod: Any, slug: str) -> None:
    company = Company(name="Acme Corp", slug=slug, domain="acme.test", tags=["roadmap"])
    company.save()
    person = Person(name="Edward Miller", email="edward@acme.test", slug="edward-miller")
    person.save()
    contacts_dir = paths_mod.companies.entry(slug).path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / "edward-miller").symlink_to(person.get_local_path())


def test_add_and_list_pending(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = FollowUpService("roadmap")

    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime(2026, 9, 20, tzinfo=UTC),
        format="email",
        template_id="email_02_screenshots.md",
    )
    pending = service.list_pending()
    assert len(pending) == 1
    assert pending[0].format == "email"
    assert pending[0].template_id == "email_02_screenshots.md"


def test_two_follow_ups_for_same_company_both_persist(tmp_path: Any, monkeypatch: Any) -> None:
    """The whole point of not reusing ToCallTask - both must survive."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = FollowUpService("roadmap")

    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime(2026, 9, 20, tzinfo=UTC),
        format="email",
        template_id="t1.md",
    )
    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime(2026, 9, 27, tzinfo=UTC),
        format="call",
    )
    pending = service.list_pending(company_slug="acme-corp")
    assert len(pending) == 2


def test_process_due_call_creates_to_call_task(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths
    from cocli.models.campaigns.queues.to_call import ToCallTask

    monkeypatch.setattr(paths, "root", tmp_path)
    service = FollowUpService("roadmap")
    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
        format="call",
    )

    result = service.process_due()

    assert result.due == 1
    assert result.calls_queued == 1
    assert result.emails_queued == 0
    assert not result.errors
    to_call_task = ToCallTask(company_slug="acme-corp", domain="acme.test", campaign_name="roadmap")
    assert to_call_task.get_local_path().exists()
    # Processed row removed from pending/.
    assert service.list_pending() == []


def test_process_due_email_renders_into_pending_batch_not_sent(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_company_with_contact(paths, "acme-corp")

    service = FollowUpService("roadmap")
    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
        format="email",
        template_id="email_01_pas_hook.md",
    )

    result = service.process_due()

    assert result.emails_queued == 1
    assert not result.errors
    pending_batches = PersonalizedOutreachService("roadmap").list_pending_batches()
    assert len(pending_batches) == 1
    assert pending_batches[0].company_slug == "acme-corp"
    assert pending_batches[0].recipient == "edward@acme.test"
    # Never auto-sent - it's in the review queue only.
    assert service.list_pending() == []


def test_process_due_ignores_not_yet_due_follow_ups(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = FollowUpService("roadmap")
    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) + timedelta(days=7),
        format="call",
    )

    result = service.process_due()

    assert result.due == 0
    assert len(service.list_pending()) == 1


def test_process_due_email_without_template_id_is_an_error_not_a_crash(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_company_with_contact(paths, "acme-corp")
    service = FollowUpService("roadmap")
    service.add_follow_up(
        company_slug="acme-corp",
        domain="acme.test",
        scheduled_at=datetime.now(UTC) - timedelta(days=1),
        format="email",
        template_id=None,
    )

    result = service.process_due()

    assert result.due == 1
    assert result.emails_queued == 0
    assert len(result.errors) == 1
    # Left in place to retry, not silently dropped.
    assert len(service.list_pending()) == 1
