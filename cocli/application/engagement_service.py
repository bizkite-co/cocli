"""Multi-channel signal ingestion & consolidated engagement event log service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.companies.note import Note
from cocli.models.engagement import EngagementEvent

logger = logging.getLogger(__name__)

USV_HEADER = (
    "timestamp\x1fcampaign\x1fcompany_slug\x1fevent_type\x1fsource\x1futm_content\x1fdetails\n"
)


class EngagementService:
    def __init__(self, campaign_name: str) -> None:
        self.campaign_name = campaign_name

    def log_path(self) -> Path:
        p = paths.campaign(self.campaign_name).path / "logs" / "engagement_events.usv"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(USV_HEADER, encoding="utf-8")
        return p

    def record_event(self, event: EngagementEvent) -> Path:
        """Appends an event to the campaign's engagement USV log and updates company tags/status."""
        path = self.log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(event.to_usv_row())

        slug = event.company_slug or event.utm_content
        if slug:
            company = Company.get(slug)
            if company:
                tags = list(company.tags or [])
                event_tag = f"engagement:{event.event_type}"
                if event_tag not in tags:
                    tags.append(event_tag)
                if event.event_type == "email_reply" and "email-replied" not in tags:
                    tags.append("email-replied")
                company.tags = tags
                company.save(rebuild_cache=False)

        logger.info(
            "Recorded engagement event %s for %s (%s)",
            event.event_type,
            slug or "unknown",
            self.campaign_name,
        )
        return path

    def ingest_telemetry(self, payload: dict[str, Any]) -> EngagementEvent:
        """
        Ingest a GTM or web landing page telemetry payload linked via UTM campaign tokens.
        Payload keys expected: event_type, utm_source, utm_medium, utm_campaign, utm_content/company_slug, utm_term.
        """
        campaign = payload.get("utm_campaign") or self.campaign_name
        company_slug = payload.get("company_slug") or payload.get("utm_content")
        event_type = payload.get("event_type") or payload.get("event") or "page_view"

        event = EngagementEvent(
            campaign_name=campaign,
            company_slug=company_slug,
            event_type=event_type,
            source=payload.get("source", "gtm"),
            utm_source=payload.get("utm_source"),
            utm_medium=payload.get("utm_medium"),
            utm_campaign=campaign,
            utm_content=company_slug,
            utm_term=payload.get("utm_term"),
            details=payload.get("details") or {},
        )
        self.record_event(event)

        # If high-intent event (cta_click, calculator_interactive_use, demo_video_start), file a note
        if company_slug and event_type in (
            "cta_click",
            "calculator_interactive_use",
            "demo_video_start",
        ):
            notes_dir = paths.companies.entry(company_slug).path / "notes"
            note = Note(
                title=f"Landing Page Activity: {event_type}",
                content=f"Prospect triggered {event_type} on getretirementtaxanalyzer.com via UTM sequence.\nUTM Source: {event.utm_source}\nUTM Medium: {event.utm_medium}",
            )
            note.to_file(notes_dir)

        return event
