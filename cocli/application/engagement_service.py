"""Multi-channel signal ingestion & consolidated engagement event log service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

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

        # If high-intent event, file a note on the sovereign company
        if company_slug and event_type in (
            "cta_click",
            "calculator_interactive_use",
            "demo_video_start",
            "feedback_submit",
            "link_click",
        ):
            notes_dir = paths.companies.entry(company_slug).path / "notes"
            details = payload.get("details") or {}
            feedback_msg = details.get("message") or payload.get("message") or ""
            note_content = (
                f"Prospect triggered {event_type} on getretirementtaxanalyzer.com via UTM sequence.\n"
                f"UTM Source: {event.utm_source}\nUTM Medium: {event.utm_medium}\n"
            )
            if feedback_msg:
                note_content += f"\nSubmitted Feedback:\n{feedback_msg}\n"
            note = Note(
                title=f"Landing Page Activity: {event_type}",
                content=note_content,
            )
            note.to_file(notes_dir)

        return event

    def list_events(self, initiative: Optional[str] = None) -> list[EngagementEvent]:
        """Read and return engagement events from USV log, optionally filtered by initiative, newest first."""
        path = self.log_path()
        if not path.exists():
            return []

        events: list[EngagementEvent] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[1:]:  # skip header
                line = line.strip()
                if not line:
                    continue
                evt = EngagementEvent.from_usv_row(line)
                if evt:
                    if initiative:
                        # Match by utm_campaign, utm_content, or event campaign
                        evt_initiative = (evt.utm_campaign or "").lower()
                        if evt_initiative and evt_initiative != initiative.lower():
                            continue
                    events.append(evt)
        except Exception as exc:
            logger.warning("Error reading engagement log %s: %s", path, exc)

        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    def _match_initiative_recipients_by_first_name(
        self, initiative: str, first_name: str
    ) -> list[str]:
        """Slugs of this initiative's rendered-outreach recipients whose
        first name (the convention's second-to-last slug segment, e.g.
        "calibrate-wealth-partners-dave-halvorson" -> "dave") matches
        `first_name`. May return more than one slug - first names aren't
        guaranteed unique across recipients, so callers must not silently
        pick one when this returns more than one match."""
        outreach_dir = (
            paths.campaign(self.campaign_name).path
            / "initiatives"
            / initiative
            / "rendered-outreach"
        )
        if not outreach_dir.is_dir():
            return []
        target = first_name.strip().lower()
        matches = []
        for entry in outreach_dir.iterdir():
            if not entry.is_dir():
                continue
            parts = entry.name.split("-")
            if len(parts) >= 2 and parts[-2].lower() == target:
                matches.append(entry.name)
        return matches

    def pull_from_ga4(
        self,
        property_id: Optional[str] = None,
        initiative: Optional[str] = None,
        days: int = 7,
    ) -> list[EngagementEvent]:
        """Query Google Analytics 4 for recent campaign sessions with company/person attribution,
        and append new hits to the campaign's engagement USV log."""
        try:
            from gtm_telemetry_wizard.config import TelemetryConfig
            from gtm_telemetry_wizard.service import TelemetryProvider
        except ImportError as exc:
            raise RuntimeError(
                "gtm_telemetry_wizard package is not installed; cannot pull GA4 telemetry."
            ) from exc

        # TelemetryProvider() with no config defaults to loading a
        # `telemetry.toml` from the current working directory - a separate
        # mechanism that was never actually wired to cocli's own campaign
        # config. Build it explicitly from cocli_config.toml instead, so the
        # ga4_measurement_id/container_id already configured per-campaign is
        # what gets used (ga4_property_id can then be auto-discovered from
        # ga4_measurement_id via the Analytics Admin API if not set).
        from cocli.core.config import load_campaign_config

        campaign_cfg = load_campaign_config(self.campaign_name)
        ga_cfg = campaign_cfg.get("google_analytics", {}) or {}
        gtm_cfg = campaign_cfg.get("gtm", {}) or {}
        telemetry_config = TelemetryConfig(
            campaign_name=self.campaign_name,
            ga4_measurement_id=ga_cfg.get("ga4_measurement_id"),
            ga4_property_id=ga_cfg.get("ga4_property_id") or property_id,
            container_id=gtm_cfg.get("container_id"),
            gtm_container_api_id=gtm_cfg.get("gtm_container_api_id"),
            analytics_account_id=ga_cfg.get("analytics_account_id"),
            gtm_account_id=gtm_cfg.get("gtm_account_id"),
        )

        provider = TelemetryProvider(config=telemetry_config)
        campaign_filter = initiative or self.campaign_name
        try:
            report = provider.query_analytics(
                property_id=property_id,
                campaign=campaign_filter,
                days=days,
            )
        except Exception as exc:
            # Deliberately not swallowed into a log-only warning + return [] -
            # that made every failure (auth, config, a stale/incompatible
            # gtm_telemetry_wizard install, network) look identical to "ran
            # fine, found 0 events" in the TUI. Let it propagate so the
            # caller's existing `except Exception as exc: notify(f"GA4 pull
            # failed: {exc}")` actually shows the real reason.
            #
            # gtm_telemetry_wizard's ConfigurationError carries the
            # actionable fix as a separate `.solution` attribute, not part
            # of str(exc) - duck-typed here (not imported) to avoid a hard
            # dependency on that exception type's exact class.
            solution = getattr(exc, "solution", None)
            message = f"Failed to query GA4 Data API: {exc}"
            if solution:
                message = f"{message} ({solution})"
            logger.error(message)
            raise RuntimeError(message) from exc

        dim_headers = [d.get("name", "") for d in report.get("dimensionHeaders", [])]
        metric_headers = [m.get("name", "") for m in report.get("metricHeaders", [])]

        existing_events = self.list_events(initiative=initiative)
        seen_keys = {
            (
                e.company_slug,
                e.utm_campaign,
                (e.details or {}).get("page_path"),
                e.utm_term,
            )
            for e in existing_events
        }

        new_events: list[EngagementEvent] = []
        for row in report.get("rows", []):
            d_vals = [v.get("value", "") for v in row.get("dimensionValues", [])]
            m_vals = [v.get("value", "0") for v in row.get("metricValues", [])]
            dims = dict(zip(dim_headers, d_vals))
            metrics = dict(zip(metric_headers, m_vals))

            ad_content = dims.get("sessionManualAdContent")
            if ad_content == "(not set)":
                ad_content = None
            term = dims.get("sessionManualTerm")
            if term == "(not set)":
                term = None

            # Which UTM param actually identifies the company depends on how
            # the outreach link was built: personalized_outreach_service.py
            # injects the real company slug into utm_content. But the
            # request_testimonial.md template (and possibly others) bakes a
            # fixed CTA label into utm_content ("request_testimonial" for
            # every recipient) and puts the person's bare first name in
            # utm_term instead - so utm_content there is never a company at
            # all. Trust utm_content only when it actually resolves to a
            # real company; otherwise fall back to matching utm_term's first
            # name against this initiative's known outreach recipients.
            co_slug: Optional[str] = ad_content if ad_content and Company.get(ad_content) else None
            ambiguous_term_match = False
            if not co_slug and term and initiative:
                candidates = self._match_initiative_recipients_by_first_name(initiative, term)
                if len(candidates) == 1:
                    co_slug = candidates[0]
                elif len(candidates) > 1:
                    ambiguous_term_match = True

            page_path = dims.get("pagePath")
            camp = dims.get("sessionCampaignName") or campaign_filter

            fingerprint = (co_slug, camp, page_path, term)
            if fingerprint in seen_keys:
                continue

            details: dict[str, Any] = {
                "page_path": page_path,
                "sessions": int(metrics.get("sessions", 0)),
                "screen_page_views": int(metrics.get("screenPageViews", 0)),
                "active_users": int(metrics.get("activeUsers", 0)),
            }
            if ad_content and ad_content != co_slug:
                details["link_label"] = ad_content
            if ambiguous_term_match:
                details["ambiguous_first_name"] = term

            event = EngagementEvent(
                campaign_name=camp,
                company_slug=co_slug,
                event_type="link_click",
                source="ga4",
                utm_source="email",
                utm_medium="outreach",
                utm_campaign=camp,
                utm_content=ad_content,
                utm_term=term,
                details=details,
            )
            self.record_event(event)
            if co_slug:
                try:
                    notes_dir = paths.companies.entry(co_slug).path / "notes"
                    if notes_dir.parent.exists():
                        person_info = f" ({term})" if term else ""
                        note_content = (
                            f"Prospect{person_info} clicked outreach link and visited {page_path or 'landing page'} via UTM sequence.\n"
                            f"Source: GA4 Data API\nCampaign: {camp}\n"
                        )
                        note = Note(
                            title="Landing Page Activity: link_click",
                            content=note_content,
                        )
                        note.to_file(notes_dir)
                except Exception as note_err:
                    logger.warning("Could not record note for %s: %s", co_slug, note_err)

            seen_keys.add(fingerprint)
            new_events.append(event)

        return new_events

    def pull_cta_clicks(
        self, property_id: Optional[str] = None, initiative: Optional[str] = None, days: int = 7
    ) -> list[EngagementEvent]:
        """Pull event-level GA4 data for the cta_click custom event: which
        specific button was clicked, on which page - the granularity
        pull_from_ga4()'s session-level pull can't see, since that only
        knows a session happened, not which button within it was
        pressed. Requires the `button_label` event-scoped custom
        dimension to already be registered on the GA4 property (see
        GoogleTelemetryProvider.register_event_custom_dimension) -
        registration doesn't backfill past events, only ones recorded
        after it existed.
        """
        from cocli.application.telemetry_service import GoogleTelemetryProvider
        from cocli.core.config import load_campaign_config

        campaign_cfg = load_campaign_config(self.campaign_name)
        ga_cfg = campaign_cfg.get("google_analytics", {}) or {}
        p_id = property_id or ga_cfg.get("ga4_property_id")
        if not p_id:
            raise RuntimeError(
                "Missing GA4 numeric property ID. Pass property_id, or set "
                "google_analytics.ga4_property_id in this campaign's config.toml."
            )

        provider = GoogleTelemetryProvider(self.campaign_name)
        rows = provider.query_cta_clicks(str(p_id), days=days)

        existing_events = self.list_events(initiative=initiative)
        seen_keys = {
            (e.company_slug, (e.details or {}).get("button_label"), (e.details or {}).get("page_path"), e.utm_term)
            for e in existing_events
            if e.event_type == "cta_click"
        }

        new_events: list[EngagementEvent] = []
        for row in rows:
            page_path = row.get("pagePath")
            button_label = row.get("customEvent:button_label") or ""
            ad_content = row.get("sessionManualAdContent")
            if ad_content == "(not set)":
                ad_content = None
            term = row.get("sessionManualTerm")
            if term == "(not set)":
                term = None
            event_count = int(row.get("eventCount", "0") or 0)

            co_slug: Optional[str] = ad_content if ad_content and Company.get(ad_content) else None
            if not co_slug and term and initiative:
                candidates = self._match_initiative_recipients_by_first_name(initiative, term)
                if len(candidates) == 1:
                    co_slug = candidates[0]

            fingerprint = (co_slug, button_label, page_path, term)
            if fingerprint in seen_keys:
                continue

            event = EngagementEvent(
                campaign_name=initiative or self.campaign_name,
                company_slug=co_slug,
                event_type="cta_click",
                source="ga4",
                utm_content=ad_content,
                utm_term=term,
                details={
                    "button_label": button_label,
                    "page_path": page_path,
                    "event_count": event_count,
                },
            )
            self.record_event(event)
            seen_keys.add(fingerprint)
            new_events.append(event)

        return new_events

    def _find_company_by_email(self, email: str) -> Optional[str]:
        """Look up a company slug by email via the compact company_cache.usv
        index (slug|name|type|domain|email|...), not a per-company
        _index.md scan. A first version of this scanned every company's
        _index.md individually via Company.get() - at ~40k companies that
        took long enough to make `cocli telemetry process-testimonials`
        look hung. The cache is one file, already built for exactly this
        kind of fast lookup (see cocli/core/cache.py). Falls back to
        rebuilding the cache once if it's missing/stale, same as
        get_cached_items() already does elsewhere.

        Testimonial submissions carry a real work email, a far more
        reliable identifier than the first-name-only utm_term GA4 clicks
        are limited to.
        """
        from cocli.core.cache import build_cache, get_cache_path, is_cache_valid

        target = email.strip().lower()
        if not target:
            return None

        if not is_cache_valid(campaign=self.campaign_name):
            try:
                build_cache(campaign=self.campaign_name)
            except Exception as exc:
                logger.warning("Could not build company cache for email lookup: %s", exc)
                return None

        cache_file = get_cache_path(campaign=self.campaign_name) / "company_cache.usv"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\x1f")
                    if len(parts) <= 4:
                        continue
                    if parts[4].strip().lower() == target:
                        return parts[0]
        except OSError as exc:
            logger.warning("Could not read company cache for email lookup: %s", exc)
        return None

    def process_testimonial_submissions(self, initiative: Optional[str] = None) -> list[EngagementEvent]:
        """Process pending testimonial-form submissions (JSON files synced
        down from S3 via `cocli smart-sync` - see
        cdk_scraper_deployment/testimonials_stack.py, which replaced
        formsubmit.co after it was confirmed to silently drop every
        submission) into the engagement log plus a company note carrying
        the full testimonial text, then move each to completed/ as a
        witness receipt - the same pending/completed lifecycle gm-details
        tasks already use (see docs/data-management/directory-data-structure.md).
        """
        import json as jsonlib

        queue_dir = paths.campaign(self.campaign_name).path / "queues" / "testimonials"
        pending_dir = queue_dir / "pending"
        completed_dir = queue_dir / "completed"

        if not pending_dir.is_dir():
            return []
        completed_dir.mkdir(parents=True, exist_ok=True)

        # Moving pending -> completed only updates the LOCAL mirror. A
        # generic `aws s3 sync` (unlike `cocli smart-sync`, which tracks
        # .smart_sync_state.json) doesn't know a pending/ object was
        # already consumed and will re-download it on the next run,
        # causing it to be reprocessed - confirmed empirically (a
        # already-processed test submission came back and got a second,
        # duplicate engagement log entry). Delete the S3 source object
        # once local processing succeeds so it can never come back.
        s3_client = None
        bucket_name = None
        try:
            from cocli.core.config import load_campaign_config
            from cocli.core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

            config = load_campaign_config(self.campaign_name)
            bucket_name = get_data_bucket_name(config, self.campaign_name)
            s3_client = get_s3_client(session=get_boto3_session(config))
        except Exception as exc:
            logger.debug("S3 cleanup unavailable (local-only campaign?): %s", exc)

        new_events: list[EngagementEvent] = []
        for task_file in sorted(pending_dir.glob("*.json")):
            try:
                data = jsonlib.loads(task_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse testimonial task %s: %s", task_file, exc)
                continue

            email = str(data.get("email") or "").strip()
            name = str(data.get("name") or "").strip()
            message = str(data.get("message") or "")
            utm_term = str(data.get("utm_term") or "").strip()
            camp = str(data.get("utm_campaign") or self.campaign_name)

            co_slug = self._find_company_by_email(email) if email else None
            if not co_slug and utm_term and initiative:
                candidates = self._match_initiative_recipients_by_first_name(initiative, utm_term)
                if len(candidates) == 1:
                    co_slug = candidates[0]

            event = EngagementEvent(
                campaign_name=camp,
                company_slug=co_slug,
                event_type="testimonial_submitted",
                source="webhook",
                utm_source=str(data.get("utm_source") or ""),
                utm_medium=str(data.get("utm_medium") or ""),
                utm_campaign=camp,
                utm_content=str(data.get("utm_content") or ""),
                utm_term=utm_term,
                details={
                    "name": name,
                    "firm": data.get("firm"),
                    "email": email,
                    "message": message,
                    "permission_to_quote": data.get("permission_to_quote"),
                    "page_url": data.get("page_url"),
                },
            )
            self.record_event(event)
            new_events.append(event)

            if co_slug:
                try:
                    notes_dir = paths.companies.entry(co_slug).path / "notes"
                    if notes_dir.parent.exists():
                        note_content = (
                            f"Firm: {data.get('firm') or ''}\n"
                            f"Email: {email}\n"
                            f"Permission to quote: {data.get('permission_to_quote') or ''}\n\n"
                            f"{message}"
                        )
                        note = Note(
                            title=f"Testimonial Submitted: {name or email or 'Unknown'}",
                            content=note_content,
                        )
                        note.to_file(notes_dir)
                except Exception as note_err:
                    logger.warning("Could not record testimonial note for %s: %s", co_slug, note_err)
            else:
                logger.info(
                    "Testimonial submission %s could not be matched to a company (email=%s, term=%s)",
                    task_file.name, email, utm_term,
                )

            task_file.replace(completed_dir / task_file.name)

            if s3_client and bucket_name:
                s3_key = f"{paths.s3.campaign(self.campaign_name).queue('testimonials').pending()}{task_file.name}"
                try:
                    s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
                except Exception as exc:
                    logger.warning(
                        "Processed %s locally but could not delete its S3 source (%s) - "
                        "it will be re-downloaded and reprocessed on the next sync: %s",
                        task_file.name, s3_key, exc,
                    )

        return new_events

    def list_form_submissions(
        self, queue_names: tuple[str, ...] = ("testimonials", "signups"), since_days: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """List raw form submissions across one or more S3-backed intake
        queues (see cdk_scraper_deployment/testimonials_stack.py's
        FormIntakeStack), both pending/ (not yet processed by e.g.
        `process-testimonials`) and completed/ (already processed) -
        reading straight from S3 so this reflects reality even if
        `cocli smart-sync` hasn't been run locally. Read-only: never
        moves, deletes, or processes anything.

        Each result dict is the submission's own JSON plus "_queue"
        ("testimonials"/"signups") and "_status" ("pending"/"completed").
        Sorted newest first. `since_days=None` returns everything.
        """
        import json as jsonlib
        import time

        cutoff = time.time() - (since_days * 86400) if since_days is not None else None
        results: list[dict[str, Any]] = []

        s3_client = None
        bucket_name = None
        try:
            from cocli.core.config import load_campaign_config
            from cocli.core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

            config = load_campaign_config(self.campaign_name)
            bucket_name = get_data_bucket_name(config, self.campaign_name)
            s3_client = get_s3_client(session=get_boto3_session(config))
        except Exception as exc:
            logger.debug("S3 access unavailable for list_form_submissions (local-only campaign?): %s", exc)

        for queue_name in queue_names:
            for status in ("pending", "completed"):
                if status == "pending":
                    prefix = paths.s3.campaign(self.campaign_name).queue(queue_name).pending()
                else:
                    prefix = f"campaigns/{self.campaign_name}/queues/{queue_name}/completed/"
                if s3_client and bucket_name:
                    try:
                        paginator = s3_client.get_paginator("list_objects_v2")
                        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                            for obj in page.get("Contents", []):
                                key = obj["Key"]
                                if not key.endswith(".json"):
                                    continue
                                try:
                                    body = s3_client.get_object(Bucket=bucket_name, Key=key)["Body"].read()
                                    item = jsonlib.loads(body)
                                except Exception as exc:
                                    logger.warning("Could not read/parse %s: %s", key, exc)
                                    continue
                                received_at = item.get("received_at")
                                if cutoff is not None and (received_at is None or received_at < cutoff):
                                    continue
                                item["_queue"] = queue_name
                                item["_status"] = status
                                results.append(item)
                    except Exception as exc:
                        logger.warning("Could not list S3 queue %s/%s: %s", queue_name, status, exc)
                else:
                    # Local-only fallback (no S3 access this session) -
                    # reads whatever's already synced to the local mirror.
                    local_dir = paths.campaign(self.campaign_name).path / "queues" / queue_name / status
                    if not local_dir.is_dir():
                        continue
                    for task_file in local_dir.glob("*.json"):
                        try:
                            item = jsonlib.loads(task_file.read_text(encoding="utf-8"))
                        except Exception as exc:
                            logger.warning("Could not parse %s: %s", task_file, exc)
                            continue
                        received_at = item.get("received_at")
                        if cutoff is not None and (received_at is None or received_at < cutoff):
                            continue
                        item["_queue"] = queue_name
                        item["_status"] = status
                        results.append(item)

        results.sort(key=lambda item: item.get("received_at") or 0, reverse=True)
        return results

