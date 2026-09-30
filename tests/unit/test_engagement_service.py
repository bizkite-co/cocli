from __future__ import annotations

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

