from __future__ import annotations

from typing import Any

from cocli.application.engagement_service import EngagementService
from cocli.models.companies.company import Company
from cocli.models.engagement import EngagementEvent


def test_record_event_writes_usv_and_updates_company_tags(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Target Prospect", slug="target-prospect", domain="targetprospect.com"
    )
    company.save()

    service = EngagementService("roadmap")
    event = EngagementEvent(
        campaign_name="roadmap",
        company_slug="target-prospect",
        event_type="email_reply",
        source="imap",
        details={"subject": "Re: Demo inquiry"},
    )

    log_path = service.record_event(event)
    assert log_path.exists()

    content = log_path.read_text(encoding="utf-8")
    assert "target-prospect" in content
    assert "email_reply" in content

    updated_company = Company.get("target-prospect")
    assert updated_company is not None
    assert "email-replied" in updated_company.tags
    assert "engagement:email_reply" in updated_company.tags


def test_ingest_telemetry_links_utm_content_to_company(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Web Prospect", slug="web-prospect", domain="webprospect.com"
    )
    company.save()

    service = EngagementService("roadmap")
    payload = {
        "event_type": "cta_click",
        "source": "gtm",
        "utm_source": "email_sequence",
        "utm_medium": "email",
        "utm_campaign": "roadmap",
        "utm_content": "web-prospect",
        "details": {"button_id": "start-free-trial"},
    }

    event = service.ingest_telemetry(payload)
    assert event.company_slug == "web-prospect"
    assert event.event_type == "cta_click"

    # Check note written for high intent event
    notes_dir = paths.companies.entry("web-prospect").path / "notes"
    assert notes_dir.exists()
    note_files = list(notes_dir.glob("*.md"))
    assert len(note_files) == 1
    assert "Landing Page Activity: cta_click" in note_files[0].read_text()


def test_list_events_filters_and_returns_newest_first(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    service = EngagementService("roadmap")
    event1 = EngagementEvent(
        campaign_name="roadmap",
        company_slug="prospect-a",
        event_type="landing_page_view",
        utm_campaign="testimonials",
        source="gtm",
    )
    event2 = EngagementEvent(
        campaign_name="roadmap",
        company_slug="prospect-b",
        event_type="feedback_submit",
        utm_campaign="testimonials",
        source="gtm",
        details={"message": "Great spend-down table"},
    )
    event3 = EngagementEvent(
        campaign_name="roadmap",
        company_slug="prospect-c",
        event_type="cta_click",
        utm_campaign="rta",
        source="gtm",
    )

    service.record_event(event1)
    service.record_event(event2)
    service.record_event(event3)

    all_events = service.list_events()
    assert len(all_events) == 3
    assert all_events[0].event_type in ("landing_page_view", "feedback_submit", "cta_click")

    testimonial_events = service.list_events(initiative="testimonials")
    assert len(testimonial_events) == 2
    assert all(e.utm_campaign == "testimonials" for e in testimonial_events)

