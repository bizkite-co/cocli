from __future__ import annotations

import json
import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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


def test_pull_from_ga4_raises_when_gtm_telemetry_wizard_not_installed(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression test: a missing/broken gtm_telemetry_wizard install must
    surface as a real error, not get logged-and-swallowed into an empty
    list that looks identical to 'ran fine, found nothing' in the TUI."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    monkeypatch.setitem(sys.modules, "gtm_telemetry_wizard", None)
    monkeypatch.setitem(sys.modules, "gtm_telemetry_wizard.service", None)

    service = EngagementService("roadmap")
    with pytest.raises(RuntimeError, match="not installed"):
        service.pull_from_ga4(initiative="testimonials")


def test_pull_from_ga4_raises_when_query_analytics_fails(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression test for the actual bug hit in production: a stale
    gtm-telemetry-wizard install missing query_analytics() raised
    AttributeError, which pull_from_ga4 used to catch, log as a warning,
    and hide behind `return []` - the TUI then reported "Pulled 0 new GA4
    signal(s)" for every failure, indistinguishable from real success."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    # Import the real package first so gtm_telemetry_wizard/__init__.py's
    # eager `from .cli import app` (which itself imports .config and
    # .service) has already resolved and cached in sys.modules. Without
    # this, patching sys.modules["gtm_telemetry_wizard.service"] below would
    # make the FIRST import of any gtm_telemetry_wizard submodule (e.g. our
    # own `from gtm_telemetry_wizard.config import TelemetryConfig`)
    # re-trigger that package init using the incomplete fake .service
    # module, raising an unrelated ImportError instead of exercising the
    # AttributeError path this test is actually about.
    import gtm_telemetry_wizard.service  # noqa: F401

    fake_module = ModuleType("gtm_telemetry_wizard.service")
    fake_provider_cls = MagicMock()
    fake_provider_instance = fake_provider_cls.return_value
    fake_provider_instance.query_analytics.side_effect = AttributeError(
        "'TelemetryProvider' object has no attribute 'query_analytics'"
    )
    fake_module.TelemetryProvider = fake_provider_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"gtm_telemetry_wizard.service": fake_module}):
        service = EngagementService("roadmap")
        with pytest.raises(RuntimeError, match="Failed to query GA4 Data API"):
            service.pull_from_ga4(initiative="testimonials")


def test_pull_from_ga4_includes_configuration_error_solution_hint(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """gtm_telemetry_wizard's ConfigurationError carries its actionable fix
    in a separate `.solution` attribute, not in str(exc) - e.g. raising it
    bare for a missing ga4_property_id gave the user "Missing GA4 numeric
    property ID." with no indication of how to actually fix it."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    # See comment in test_pull_from_ga4_raises_when_query_analytics_fails.
    import gtm_telemetry_wizard.service  # noqa: F401

    class FakeConfigurationError(ValueError):
        def __init__(self) -> None:
            super().__init__("Missing GA4 numeric property ID.")
            self.solution = (
                "Specify --property-id, set `ga4_property_id` in "
                "telemetry.toml, or export GA4_PROPERTY_ID."
            )

    fake_module = ModuleType("gtm_telemetry_wizard.service")
    fake_provider_cls = MagicMock()
    fake_provider_instance = fake_provider_cls.return_value
    fake_provider_instance.query_analytics.side_effect = FakeConfigurationError()
    fake_module.TelemetryProvider = fake_provider_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"gtm_telemetry_wizard.service": fake_module}):
        service = EngagementService("roadmap")
        with pytest.raises(RuntimeError, match="set `ga4_property_id` in telemetry.toml"):
            service.pull_from_ga4(initiative="testimonials")


def test_pull_cta_clicks_requires_a_property_id(tmp_path: Any, monkeypatch: Any) -> None:
    """Built from the 2026-10-01 incident where the first successful
    cta_click pull required manually passing --property-id each time -
    without a configured ga4_property_id, this must fail with an
    actionable message rather than call the Data API with None."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    service = EngagementService("roadmap")
    with pytest.raises(RuntimeError, match="Missing GA4 numeric property ID"):
        service.pull_cta_clicks()


def test_pull_cta_clicks_captures_button_label_in_event_details(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The actual point of this feature: a cta_click row from GA4 (with
    the button_label event-scoped custom dimension populated) must
    become an EngagementEvent whose details carry that label - the
    session-level pull (pull_from_ga4) can only ever say a page was
    visited, never which button was pressed."""
    from cocli.core.paths import paths
    from cocli.application.telemetry_service import GoogleTelemetryProvider

    monkeypatch.setattr(paths, "root", tmp_path)

    fake_rows = [
        {
            "pagePath": "/signup/",
            "customEvent:button_label": "Request a Callback",
            "sessionManualAdContent": "(not set)",
            "sessionManualTerm": "(not set)",
            "eventCount": "3",
        }
    ]
    with patch.object(GoogleTelemetryProvider, "query_cta_clicks", return_value=fake_rows):
        service = EngagementService("roadmap")
        new_events = service.pull_cta_clicks(property_id="510155544")

    assert len(new_events) == 1
    event = new_events[0]
    assert event.event_type == "cta_click"
    assert event.source == "ga4"
    assert event.details["button_label"] == "Request a Callback"
    assert event.details["page_path"] == "/signup/"
    assert event.details["event_count"] == 3
    assert event.company_slug is None  # (not set) ad_content/term - no attribution possible


def test_pull_cta_clicks_deduplicates_against_already_recorded_events(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Re-running the pull (e.g. a scheduled poll) must not duplicate an
    already-recorded click with the same company/button/page/term
    fingerprint - matches the dedup behavior pull_from_ga4 already has
    for link_click."""
    from cocli.core.paths import paths
    from cocli.application.telemetry_service import GoogleTelemetryProvider

    monkeypatch.setattr(paths, "root", tmp_path)

    fake_rows = [
        {
            "pagePath": "/signup/",
            "customEvent:button_label": "Request a Callback",
            "sessionManualAdContent": "(not set)",
            "sessionManualTerm": "(not set)",
            "eventCount": "1",
        }
    ]
    with patch.object(GoogleTelemetryProvider, "query_cta_clicks", return_value=fake_rows):
        service = EngagementService("roadmap")
        first_pull = service.pull_cta_clicks(property_id="510155544")
        assert len(first_pull) == 1

        second_pull = service.pull_cta_clicks(property_id="510155544")
        assert len(second_pull) == 0


def test_process_testimonial_submissions_reads_directly_from_s3(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The actual 2026-10-02 bug this replaces: `cocli smart-sync queues`
    never covered the testimonials queue (only map-tile/gm-list/
    gm-details/enrichment are in its loop), so a local pending/ file
    never existed unless someone manually `aws s3 cp`'d it down first -
    undocumented, and the method silently returned [] regardless of what
    was actually sitting in S3. This must process directly from S3, with
    no local pending/ file ever required."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    submission = {
        "id": "abc123",
        "name": "Jane Advisor",
        "email": "jane@example.com",
        "message": "Great tool, saved us hours.",
        "utm_campaign": "testimonials",
    }

    fake_body = MagicMock()
    fake_body.read.return_value = json.dumps(submission).encode("utf-8")

    fake_paginator = MagicMock()
    fake_paginator.paginate.return_value = [
        {"Contents": [{"Key": "campaigns/roadmap/queues/testimonials/pending/abc123.json"}]}
    ]

    fake_s3_client = MagicMock()
    fake_s3_client.get_paginator.return_value = fake_paginator
    fake_s3_client.get_object.return_value = {"Body": fake_body}

    with patch(
        "cocli.core.config.load_campaign_config", return_value={}
    ), patch(
        "cocli.core.reporting.get_data_bucket_name", return_value="fake-bucket"
    ), patch(
        "cocli.core.reporting.get_boto3_session", return_value=MagicMock()
    ), patch(
        "cocli.core.reporting.get_s3_client", return_value=fake_s3_client
    ):
        service = EngagementService("roadmap")
        # No local pending/ directory is ever created - proving the S3
        # path doesn't depend on one existing.
        new_events = service.process_testimonial_submissions()

    assert len(new_events) == 1
    assert new_events[0].details["message"] == "Great tool, saved us hours."

    fake_s3_client.delete_object.assert_called_once_with(
        Bucket="fake-bucket",
        Key="campaigns/roadmap/queues/testimonials/pending/abc123.json",
    )

    completed_witness = (
        paths.campaign("roadmap").path / "queues" / "testimonials" / "completed" / "abc123.json"
    )
    assert completed_witness.exists()


def test_process_testimonial_submissions_falls_back_to_local_pending_dir(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """When S3 access genuinely isn't configured (a local-only/dev
    campaign), fall back to draining whatever's already sitting in the
    local pending/ mirror, rather than silently doing nothing."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    queue_dir = paths.campaign("roadmap").path / "queues" / "testimonials" / "pending"
    queue_dir.mkdir(parents=True)
    (queue_dir / "local1.json").write_text(
        json.dumps({"name": "Local Only", "email": "local@example.com", "message": "Local fallback works"}),
        encoding="utf-8",
    )

    with patch(
        "cocli.core.config.load_campaign_config", side_effect=Exception("no AWS config")
    ):
        service = EngagementService("roadmap")
        new_events = service.process_testimonial_submissions()

    assert len(new_events) == 1
    assert new_events[0].details["message"] == "Local fallback works"
    assert not (queue_dir / "local1.json").exists()
    assert (paths.campaign("roadmap").path / "queues" / "testimonials" / "completed" / "local1.json").exists()


def test_process_unsubscribe_requests_resolves_guid_to_the_real_recipient_and_excludes_them(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The actual point of today's build (Mark, 2026-10-03): the Lambda
    this request came from never saw a plaintext email address, only a
    guid - resolving it to the real recipient (via the SendRecord that
    guid's own send already created) and applying the suppression both
    happen here, locally."""
    from cocli.core.paths import paths
    from cocli.core.exclusions import ExclusionManager
    from cocli.models.send_record import SendRecord
    from datetime import datetime, UTC

    monkeypatch.setattr(paths, "root", tmp_path)

    SendRecord(
        guid="guid-abc",
        campaign_name="roadmap",
        initiative="rta",
        company_slug="acme-co",
        template_id="email_02_product_overview.md",
        recipient_email="bob@acme.test",
        subject="Hi Bob",
        sent_at=datetime(2026, 10, 1, tzinfo=UTC),
    ).save()

    queue_dir = paths.campaign("roadmap").path / "queues" / "unsubscribes" / "pending"
    queue_dir.mkdir(parents=True)
    (queue_dir / "req1.json").write_text(
        json.dumps({"guid": "guid-abc", "reason": "too many emails"}), encoding="utf-8"
    )

    with patch("cocli.core.config.load_campaign_config", side_effect=Exception("no AWS config")):
        service = EngagementService("roadmap")
        unsubscribed = service.process_unsubscribe_requests()

    assert unsubscribed == ["bob@acme.test"]

    record = SendRecord.get("roadmap", "guid-abc")
    assert record is not None
    assert record.unsubscribed_at is not None
    assert record.unsubscribe_reason == "too many emails"

    exclusions = ExclusionManager("roadmap").list_exclusions()
    assert any(e.domain == "bob@acme.test" for e in exclusions)

    assert not (queue_dir / "req1.json").exists()
    assert (paths.campaign("roadmap").path / "queues" / "unsubscribes" / "completed" / "req1.json").exists()


def test_process_unsubscribe_requests_skips_unknown_guid_without_crashing(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A guid with no matching SendRecord (e.g. pre-dates this feature,
    or was tampered with) must not crash the whole batch - just logged
    and skipped, matching testimonials' unmatched-entry handling."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    queue_dir = paths.campaign("roadmap").path / "queues" / "unsubscribes" / "pending"
    queue_dir.mkdir(parents=True)
    (queue_dir / "req1.json").write_text(json.dumps({"guid": "no-such-guid"}), encoding="utf-8")

    with patch("cocli.core.config.load_campaign_config", side_effect=Exception("no AWS config")):
        service = EngagementService("roadmap")
        unsubscribed = service.process_unsubscribe_requests()

    assert unsubscribed == []
    # Still marked completed - an unresolvable request shouldn't be
    # retried forever.
    assert (paths.campaign("roadmap").path / "queues" / "unsubscribes" / "completed" / "req1.json").exists()

