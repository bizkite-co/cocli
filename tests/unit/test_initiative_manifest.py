"""Tests for InitiativeManifest and FollowUpService.enqueue_initiative."""

from __future__ import annotations

from typing import Any

from cocli.application.follow_up_service import FollowUpService
from cocli.models.campaigns.initiative import (
    InitiativeManifest,
    InitiativeTargetCriteria,
    InitiativeOutreachSpec,
)
from cocli.models.companies.company import Company
from cocli.models.people.person import Person


def _make_company_with_contact(
    paths_mod: Any, slug: str, name: str = "Acme Corp", tags: list[str] | None = None
) -> None:
    company = Company(name=name, slug=slug, domain=f"{slug}.test", tags=tags or ["roadmap"])
    company.save()
    p_slug = f"{slug}-person"
    person = Person(name="Jane Doe", email=f"jane@{slug}.test", slug=p_slug)
    person.save()
    contacts_dir = paths_mod.companies.entry(slug).path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / p_slug).symlink_to(person.get_local_path())


def test_initiative_manifest_serialization(tmp_path: Any) -> None:
    manifest = InitiativeManifest(
        name="testimonials",
        description="Advisor feedback campaign",
        default_template="request_testimonial.md",
        target_criteria=InitiativeTargetCriteria(
            tags=["testimonial-target"],
            company_type="Client",
        ),
        outreach=InitiativeOutreachSpec(
            format="email",
            follow_up_delay_days=1,
            landing_url="https://getretirementtaxanalyzer.com/testimonials/",
            utm_source="email",
            utm_medium="outreach",
            utm_campaign="testimonials",
            utm_content="request_testimonial",
        ),
    )
    manifest_file = tmp_path / "initiative.yaml"
    manifest.save(manifest_file)

    loaded = InitiativeManifest.load(manifest_file)
    assert loaded.name == "testimonials"
    assert loaded.default_template == "request_testimonial.md"
    assert loaded.target_criteria.tags == ["testimonial-target"]
    assert loaded.target_criteria.company_type == "Client"
    assert loaded.outreach.format == "email"
    assert loaded.outreach.follow_up_delay_days == 1
    assert loaded.outreach.utm_campaign == "testimonials"


def test_enqueue_initiative_dry_run_and_execution(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_company_with_contact(paths, "target-one", tags=["roadmap", "testimonial-target", "client"])
    _make_company_with_contact(paths, "target-two", tags=["roadmap", "prospect"])

    # Create initiative.yaml in campaigns/roadmap/initiatives/testimonials/
    init_dir = paths.campaign("roadmap").path / "initiatives" / "testimonials"
    init_dir.mkdir(parents=True, exist_ok=True)
    manifest = InitiativeManifest(
        name="testimonials",
        default_template="request_testimonial.md",
        target_criteria=InitiativeTargetCriteria(tags=["testimonial-target"]),
    )
    manifest.save(init_dir / "initiative.yaml")

    # Add template in initiative email-sequences
    templates_dir = init_dir / "email-sequences"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "request_testimonial.md").write_text(
        "---\nsubject: Quick question\n---\nHi {first_name}, feedback here.",
        encoding="utf-8",
    )

    service = FollowUpService("roadmap")

    # Test dry run
    dry_res = service.enqueue_initiative("testimonials", dry_run=True)
    assert dry_res.enqueued == 1
    assert dry_res.rendered == 0
    assert service.list_pending() == []

    # Test actual execution with render=True
    exec_res = service.enqueue_initiative("testimonials", render=True)
    assert exec_res.enqueued == 1
    assert exec_res.rendered == 1
    assert not exec_res.errors

    # Verify pending batch was created
    from cocli.application.personalized_outreach_service import PersonalizedOutreachService

    outreach = PersonalizedOutreachService("roadmap")
    batches = outreach.list_pending_batches()
    assert len(batches) == 1
    assert batches[0].company_slug == "target-one"
    assert batches[0].initiative == "testimonials"

    # Test idempotency: re-running does not duplicate pending batch entries
    exec_res_2 = service.enqueue_initiative("testimonials", render=True)
    assert exec_res_2.enqueued == 1
    batches_2 = outreach.list_pending_batches()
    assert len(batches_2) == 1
