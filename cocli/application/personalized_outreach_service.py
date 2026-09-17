"""Personalized outreach campaign batch selection & email copy generation service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from cocli.application.company_service import get_company_details_for_view
from cocli.core.exclusions import ExclusionManager
from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.utils.utm import append_utm_params

if TYPE_CHECKING:
    from cocli.application.email_service import EmailService
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry
    from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

logger = logging.getLogger(__name__)

DEFAULT_LANDING_URL = "https://getretirementtaxanalyzer.com"


@dataclass
class ProspectContactMatch:
    company_slug: str
    company_name: str
    recipient_email: str
    contact_name: str
    first_name: str
    role: Optional[str]
    subject: str
    body: str


@dataclass
class SendBatchResult:
    batch_id: str
    sent: int = 0
    failed: int = 0


@dataclass
class UnsubscribeRateStats:
    sent_count: int
    unsubscribed_count: int

    @property
    def rate(self) -> float:
        """Unsubscribed / sent, as a fraction. 0.0 when nothing has been sent
        (rather than dividing by zero) - there's no rate to report yet."""
        if self.sent_count == 0:
            return 0.0
        return self.unsubscribed_count / self.sent_count


def extract_first_name(full_name_or_str: str) -> Optional[str]:
    """Extract a clean human first name from a contact name string."""
    if not full_name_or_str:
        return None
    cleaned = full_name_or_str.strip()
    for prefix in ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof."):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    parts = [p for p in cleaned.split() if p and len(p) > 1]
    if not parts:
        return None
    candidate = parts[0]
    if candidate.isalpha():
        return candidate.capitalize()
    return None


def resolve_company_name(person: Any) -> str:
    generic_domains = ("gmail", "hotmail", "yahoo", "aol", "me", "icloud", "outlook", "rocketmail")
    co_name = str(person.company_name or "").strip()
    if co_name and co_name.lower() not in generic_domains:
        return co_name
    if person.email and "@" in str(person.email):
        domain = str(person.email).split("@")[-1]
        domain_name = domain.split(".")[0].replace("-", " ").title()
        if domain_name.lower() not in generic_domains:
            return domain_name
    return co_name or str(person.name or "Your Firm")


class PersonalizedOutreachService:

    def __init__(self, campaign_name: str = "roadmap") -> None:
        self.campaign_name = campaign_name
        self.exclusion_mgr = ExclusionManager(campaign_name)

    def find_eligible_prospects(
        self,
        limit: int = 10,
        template_name: str = "email_01_pas_hook.md",
        initiative: str = "rta",
    ) -> list[ProspectContactMatch]:
        """Find campaign companies having valid email addresses and contact first names."""
        matches: list[ProspectContactMatch] = []
        companies_dir = paths.companies.ensure()

        if not companies_dir.exists():
            return matches

        for index_file in sorted(companies_dir.glob("*/_index.md")):
            if len(matches) >= limit:
                break
            slug = index_file.parent.name
            company = Company.get(slug)
            if not company or not company.belongs_to_campaign(self.campaign_name):
                continue

            if self.exclusion_mgr.is_excluded(slug=company.slug, domain=company.domain):
                continue

            selected = self._select_company_contact(company)
            if selected:
                selected_email, selected_first_name, selected_full_name, selected_role = selected
                company_display_name = str(company.name) if company.name else slug.replace("-", " ").title()
                subject, body = self.generate_copy(
                    first_name=selected_first_name,
                    company_name=company_display_name,
                    company_slug=slug,
                    template_name=template_name,
                    initiative=initiative,
                )
                matches.append(
                    ProspectContactMatch(
                        company_slug=slug,
                        company_name=company_display_name,
                        recipient_email=selected_email,
                        contact_name=selected_full_name,
                        first_name=selected_first_name,
                        role=selected_role,
                        subject=subject,
                        body=body,
                    )
                )

        # Fallback to scanning paths.people if more matches needed
        if len(matches) < limit and paths.people.path.exists():
            from cocli.models.people.person import Person
            seen_slugs = {m.company_slug for m in matches}
            seen_emails = {m.recipient_email.lower() for m in matches}

            for person_dir in sorted(paths.people.path.glob("*")):
                if len(matches) >= limit:
                    break
                person = Person.from_directory(person_dir)
                if not person or not person.email or not person.name:
                    continue

                email_str = str(person.email).strip().lower()
                if email_str in seen_emails:
                    continue

                fname = extract_first_name(str(person.name))
                if not fname:
                    continue

                co_name = resolve_company_name(person)
                co_slug = person_dir.name

                if co_slug in seen_slugs:
                    continue

                if self.exclusion_mgr.is_excluded(slug=co_slug, domain=email_str):
                    continue

                seen_slugs.add(co_slug)
                seen_emails.add(email_str)

                subject, body = self.generate_copy(
                    first_name=fname,
                    company_name=co_name,
                    company_slug=co_slug,
                    template_name=template_name,
                    initiative=initiative,
                )
                matches.append(
                    ProspectContactMatch(
                        company_slug=co_slug,
                        company_name=co_name,
                        recipient_email=email_str,
                        contact_name=str(person.name),
                        first_name=fname,
                        role=person.role,
                        subject=subject,
                        body=body,
                    )
                )

        return matches

    def _select_company_contact(
        self, company: Company
    ) -> Optional[tuple[str, str, str, Optional[str]]]:
        """Extracted from find_eligible_prospects() (2026-09-16) so a
        single-company lookup (FollowUpService, rendering a due email
        follow-up) can reuse the exact same contact-selection rules
        instead of duplicating them. Returns
        (email, first_name, full_name, role) or None if nothing usable."""
        details = get_company_details_for_view(company.slug)
        if not details:
            return None
        contacts = details.get("contacts") or []

        for contact in contacts:
            raw_name = str(contact.get("name") or "").strip()
            email = str(contact.get("email") or "").strip()
            fname = extract_first_name(raw_name)
            if email and fname:
                return email, fname, raw_name, str(contact.get("role") or "")

        if company.email:
            co_email = str(company.email).strip()
            for contact in contacts:
                raw_name = str(contact.get("name") or "").strip()
                fname = extract_first_name(raw_name)
                if fname:
                    return co_email, fname, raw_name, str(contact.get("role") or "")

        return None

    def find_contact_for_company(self, company_slug: str) -> Optional[ProspectContactMatch]:
        """Single-company version of find_eligible_prospects() with no
        template rendering - just resolves who/what to send to. Used by
        FollowUpService to render a due email follow-up for one specific
        company rather than scanning the whole campaign for candidates."""
        company = Company.get(company_slug)
        if not company:
            return None
        selected = self._select_company_contact(company)
        if not selected:
            return None
        email, first_name, full_name, role = selected
        company_display_name = str(company.name) if company.name else company_slug.replace("-", " ").title()
        return ProspectContactMatch(
            company_slug=company_slug,
            company_name=company_display_name,
            recipient_email=email,
            contact_name=full_name,
            first_name=first_name,
            role=role,
            subject="",
            body="",
        )

    def list_templates(self) -> list[str]:
        """Filenames available via load_template()'s fallback chain -
        generic dir first, then the roadmap/RTA-specific dir - deduplicated
        and sorted for stable display."""
        generic_dir = paths.campaigns / self.campaign_name / "email-templates"
        rta_dir = paths.campaigns / self.campaign_name / "initiatives" / "rta" / "email-sequences"
        names: set[str] = set()
        for d in (generic_dir, rta_dir):
            if d.exists():
                names.update(p.name for p in d.glob("*.md"))
        return sorted(names)

    _INITIATIVE_CATEGORIES = ("email-sequences", "rendered-outreach", "tracking")

    def _initiatives_dir(self) -> Path:
        return paths.campaigns / self.campaign_name / "initiatives"

    def list_initiatives(self) -> list[str]:
        """Initiative names - literally the subdirectory names under
        campaigns/<c>/initiatives/ (e.g. "rta", "wealth-manager-products"),
        not an abstraction over them - the Messages Initiatives browser is
        meant to read the real folder structure directly."""
        root = self._initiatives_dir()
        if not root.exists():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_dir())

    def list_initiative_categories(self, initiative: str) -> list[str]:
        """Whichever of email-sequences/rendered-outreach/tracking actually
        exist for this initiative, in that fixed preferred order - not
        every initiative has all three (e.g. wealth-manager-products has
        none yet), so this must not hardcode all three as always present."""
        base = self._initiatives_dir() / initiative
        return [c for c in self._INITIATIVE_CATEGORIES if (base / c).is_dir()]

    def list_initiative_templates(self, initiative: str) -> list[str]:
        """*.md filenames directly under this initiative's own
        email-sequences/ dir - a literal folder listing, deliberately not
        merged with the campaign-generic email-templates/ dir (that merge
        is list_templates()'s job, used by the CLI batch commands)."""
        d = self._initiatives_dir() / initiative / "email-sequences"
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.glob("*.md"))

    def list_category_files(self, initiative: str, category: str) -> list[Path]:
        """Every file under this initiative/category, recursively - covers
        both flat categories (tracking/) and nested ones
        (rendered-outreach/<company-slug>/*.md) uniformly."""
        base = self._initiatives_dir() / initiative / category
        if not base.is_dir():
            return []
        return sorted(p for p in base.rglob("*") if p.is_file())

    def load_template(
        self, template_name: str = "email_01_pas_hook.md", initiative: str = "rta"
    ) -> tuple[str, str]:
        """Load email template subject pattern and body content.

        Checks campaigns/<c>/email-templates/ first (campaign-generic
        location) then falls back to
        campaigns/<c>/initiatives/<initiative>/email-sequences/ (the
        original roadmap/RTA-specific location, left in place rather than
        moved) so other campaigns can add templates without needing an
        initiative directory of their own. `initiative` defaults to "rta"
        so every existing caller (prepare-batch, send-batch, freeze_batch)
        keeps resolving exactly as before - it's only a real parameter (not
        still a hardcoded literal) so the Messages TUI's Initiatives
        browser can render a template from *whichever* initiative the
        user actually has selected, not always "rta".
        """
        generic_dir = paths.campaigns / self.campaign_name / "email-templates"
        initiative_dir = (
            paths.campaigns / self.campaign_name / "initiatives" / initiative / "email-sequences"
        )
        template_path = generic_dir / template_name
        if not template_path.exists():
            template_path = initiative_dir / template_name

        default_subject = "{first_name}, a 30-year spend-down view your clients will instantly understand"
        default_body = (
            "Hi {first_name},\n\n"
            "When evaluating retirement tax strategies for high-income clients, showing how tax-qualified "
            "vs. non-qualified assets deplete over a 30-year horizon is often the single most convincing moment in a client review.\n\n"
            "Patchwork spreadsheets and generic planning software usually fail at showing integrated tax drag, RMD impacts, "
            "and withdrawal sequencing in a clean, visual format that clients easily grasp.\n\n"
            "We built the Retirement Tax Analyzer ({landing_url}) to give financial advisors a 30-year integrated spend-down table "
            "that answers 'how long does the money last?' in seconds.\n\n"
            "Would you be open to a quick look to see how it can elevate your client review meetings?\n\n"
            "Best regards,\n"
            "The Retirement Tax Analyzer Team\n\n"
            "---\n"
            'If you prefer not to receive future communications, reply "unsubscribe" to this email or visit {landing_url}/unsubscribe\n'
        )

        if not template_path.exists():
            return default_subject, default_body

        try:
            content = template_path.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml

                    meta = yaml.safe_load(parts[1]) or {}
                    subjects = meta.get("subject_templates") or []
                    if subjects:
                        subject = str(subjects[0])
                    elif meta.get("subject"):
                        subject = str(meta.get("subject"))
                    else:
                        subject = default_subject
                    body = parts[2].strip()
                    return subject, body
            return default_subject, content
        except Exception as err:
            logger.warning("Error loading email template %s: %s", template_path, err)
            return default_subject, default_body

    def generate_copy(
        self,
        first_name: str,
        company_name: str,
        company_slug: str,
        template_name: str = "email_01_pas_hook.md",
        initiative: str = "rta",
    ) -> tuple[str, str]:
        """Generate outcome-driven, personalized email subject and body with UTM links."""
        subject_template, body_template = self.load_template(template_name, initiative=initiative)

        clean_co_name = company_name.split("-")[0].strip() if "-" in company_name else company_name

        subject = subject_template.format(
            first_name=first_name,
            company_name=clean_co_name,
            landing_url=DEFAULT_LANDING_URL,
        )

        raw_body = body_template.format(
            first_name=first_name,
            company_name=clean_co_name,
            landing_url=DEFAULT_LANDING_URL,
        )

        body_with_utm = append_utm_params(
            raw_body,
            campaign=self.campaign_name,
            company_slug=company_slug,
            source="email_sequence",
            medium="email",
            term=first_name.lower(),
        )

        return subject, body_with_utm

    def render_and_save_draft(
        self,
        match: ProspectContactMatch,
        template_id: str = "email_01_pas_hook",
        initiative: str = "rta",
    ) -> Path:
        """Render and save an outreach email draft to disk before sending, maintaining an audit trail."""

        out_dir = (
            paths.campaigns
            / self.campaign_name
            / "initiatives"
            / initiative
            / "rendered-outreach"
            / match.company_slug
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file: Path = out_dir / f"{template_id}.md"

        frontmatter = (
            f"---\n"
            f"template_id: {template_id}\n"
            f"company_slug: {match.company_slug}\n"
            f"company_name: {match.company_name}\n"
            f"recipient_email: {match.recipient_email}\n"
            f"contact_name: {match.contact_name}\n"
            f"first_name: {match.first_name}\n"
            f"subject: \"{match.subject}\"\n"
            f"---\n\n"
        )

        out_file.write_text(frontmatter + match.body, encoding="utf-8")
        return out_file

    def send_batch(
        self,
        matches: list[ProspectContactMatch],
        *,
        template_id: str,
        email_service: "EmailService",
        initiative: str = "rta",
    ) -> SendBatchResult:
        """Actually sends a batch (as opposed to prepare-batch/render_and_save_draft,
        which only render drafts to disk).

        Isolates each recipient's send in its own try/except so one failure
        doesn't abort the run - the same discipline as
        index_service.IndexService.requeue_enrichment_gaps, built after a
        set -e-style batch lost already-completed work partway through.
        Appends one SendLogEntry per attempt to the campaign's structured
        send log - the replacement for scattered per-company EmailNote
        markdown files as the source of truth for "was this actually sent."
        """
        from datetime import datetime, UTC

        from cocli.models.campaigns.indexes.email_send_log import SendLogEntry
        from cocli.models.mail import SendMailRequest

        # Microsecond precision: two send_batch() calls in quick succession
        # (e.g. back-to-back CLI runs, or two tests in the same process)
        # must not collide on batch_id - second-granularity did.
        batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        index_dir = SendLogEntry.get_index_dir(self.campaign_name)
        index_dir.mkdir(parents=True, exist_ok=True)
        log_path = index_dir / "log.usv"

        result = SendBatchResult(batch_id=batch_id)
        entries: list[SendLogEntry] = []
        for match in matches:
            try:
                send_result = email_service.send(
                    SendMailRequest(
                        to_address=match.recipient_email,
                        subject=match.subject,
                        body=match.body,
                        company_slug=match.company_slug,
                    )
                )
                entries.append(
                    SendLogEntry(
                        batch_id=batch_id,
                        template_id=template_id,
                        company_slug=match.company_slug,
                        recipient=match.recipient_email,
                        subject=match.subject,
                        message_id=send_result.message_id,
                        status="sent",
                        initiative=initiative,
                    )
                )
                result.sent += 1
            except Exception as exc:
                logger.warning(
                    "send_batch: failed to send to %s (%s): %s",
                    match.recipient_email,
                    match.company_slug,
                    exc,
                )
                entries.append(
                    SendLogEntry(
                        batch_id=batch_id,
                        template_id=template_id,
                        company_slug=match.company_slug,
                        recipient=match.recipient_email,
                        subject=match.subject,
                        status="failed",
                        error=str(exc),
                        initiative=initiative,
                    )
                )
                result.failed += 1

        with open(log_path, "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.to_usv())
        SendLogEntry.save_datapackage(index_dir, "email_send_log", "log.usv")

        return result

    def freeze_batch(self, *, limit: int, template_id: str, initiative: str = "rta") -> str:
        """Selects and fully renders a batch, then writes it to
        indexes/email-pending-batch/pending.usv before it is ever
        sendable - a bad template placeholder raises here (from
        find_eligible_prospects -> generate_copy -> str.format()), not
        after a batch has already been queued for review or send.

        Returns the new batch_id.
        """
        from datetime import datetime, UTC

        from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        matches = self.find_eligible_prospects(limit=limit, template_name=template_id, initiative=initiative)

        batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        entries = [
            PendingBatchEntry(
                batch_id=batch_id,
                template_id=template_id,
                company_slug=match.company_slug,
                recipient=match.recipient_email,
                subject=match.subject,
                body=match.body,
                initiative=initiative,
            )
            for match in matches
        ]
        self.append_pending_batch_entries(entries)
        return batch_id

    def append_pending_batch_entries(self, entries: list["PendingBatchEntry"]) -> None:
        """Shared tail of freeze_batch() - also used by FollowUpService
        to queue a single due email follow-up as a "batch of one" that
        shows up in TargetBatchesView for review like any other batch."""
        from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        index_dir = PendingBatchEntry.get_index_dir(self.campaign_name)
        index_dir.mkdir(parents=True, exist_ok=True)
        with open(index_dir / "pending.usv", "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.to_usv())
        PendingBatchEntry.save_datapackage(index_dir, "email_pending_batch", "pending.usv")

    def list_pending_batches(self) -> list["PendingBatchEntry"]:
        """All rows across all not-yet-sent-or-discarded batches, current
        state only (a sent/discarded batch's rows are removed, not kept)."""
        from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        pending_path = PendingBatchEntry.get_index_dir(self.campaign_name) / "pending.usv"
        if not pending_path.exists():
            return []
        return [
            PendingBatchEntry.from_usv(line)
            for line in pending_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    def entry_to_match(entry: "PendingBatchEntry") -> ProspectContactMatch:
        """PendingBatchEntry.to_usv() sanitizes newlines to '<br>' (the
        same lossy encoding every USV string field uses, base.py's
        to_usv()) - reversed here, once, so both the review preview and
        the actual sent email see real line breaks instead of literal
        '<br>' text. This is the one place that conversion happens; don't
        duplicate it."""
        return ProspectContactMatch(
            company_slug=entry.company_slug,
            company_name=entry.company_slug,
            recipient_email=entry.recipient,
            contact_name="",
            first_name="",
            role=None,
            subject=entry.subject.replace("<br>", "\n"),
            body=entry.body.replace("<br>", "\n"),
        )

    def update_pending_entry(
        self, batch_id: str, company_slug: str, *, subject: str, body: str
    ) -> bool:
        """Overwrites one pending batch row's rendered subject/body in
        place - the "add my own text on top of the template, then send"
        step Mark asked for (2026-09-16), rather than requiring every
        follow-up to be either a raw template or hand-composed from
        scratch. Returns False if no matching row was found."""
        entries = self.list_pending_batches()
        found = False
        for entry in entries:
            if entry.batch_id == batch_id and entry.company_slug == company_slug:
                entry.subject = subject
                entry.body = body
                found = True
        if found:
            self._rewrite_pending(entries)
        return found

    def send_pending_batch(self, batch_id: str, *, email_service: "EmailService") -> SendBatchResult:
        """Sends exactly the frozen rows for batch_id (not a fresh
        find_eligible_prospects() re-render - what was reviewed is what
        gets sent), then removes only that batch_id's rows from
        pending.usv so it can't be sent twice."""
        all_entries = self.list_pending_batches()
        batch_entries = [e for e in all_entries if e.batch_id == batch_id]
        remaining = [e for e in all_entries if e.batch_id != batch_id]

        if not batch_entries:
            return SendBatchResult(batch_id=batch_id, sent=0, failed=0)

        matches = [self.entry_to_match(e) for e in batch_entries]
        result = self.send_batch(
            matches,
            template_id=batch_entries[0].template_id,
            email_service=email_service,
            initiative=batch_entries[0].initiative,
        )

        self._rewrite_pending(remaining)
        return result

    def discard_pending_batch(self, batch_id: str) -> None:
        """Drops batch_id's rows from pending.usv without sending - e.g.
        review caught a flaw in the rendered content."""
        remaining = [e for e in self.list_pending_batches() if e.batch_id != batch_id]
        self._rewrite_pending(remaining)

    def _rewrite_pending(self, entries: list["PendingBatchEntry"]) -> None:
        from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

        index_dir = PendingBatchEntry.get_index_dir(self.campaign_name)
        index_dir.mkdir(parents=True, exist_ok=True)
        pending_path = index_dir / "pending.usv"
        pending_path.write_text("".join(e.to_usv() for e in entries), encoding="utf-8")

    def list_send_log(self, initiative: Optional[str] = None) -> list["SendLogEntry"]:
        """Every attempt (sent or failed) across every batch, newest first -
        the Messages screen's per-initiative Tracking pane's data source.
        Rows written before `initiative` existed default to "rta" (the
        field's own default), which is factually correct for every entry
        written before this feature - roadmap only had one initiative
        with an email-sequences/ dir at the time."""
        from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

        log_path = SendLogEntry.get_index_dir(self.campaign_name) / "log.usv"
        if not log_path.exists():
            return []
        entries = [
            SendLogEntry.from_usv(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if initiative is not None:
            entries = [e for e in entries if e.initiative == initiative]
        return sorted(entries, key=lambda e: e.sent_at, reverse=True)

    def list_ses_events(self, initiative: Optional[str] = None) -> list["SesEventLogEntry"]:
        """Bounce/complaint events (EmailEventsService.poll()'s output),
        newest first. The event log itself doesn't record which
        initiative a message belonged to (see ses_event_log.py) - joined
        here against this initiative's own send log by message_id,
        instead of denormalizing initiative onto the event at ingestion
        time, matching compute_unsubscribe_rate()'s existing
        compute-over-existing-data convention."""
        from cocli.models.campaigns.indexes.ses_event_log import SesEventLogEntry

        log_path = SesEventLogEntry.get_index_dir(self.campaign_name) / "log.usv"
        if not log_path.exists():
            return []
        entries = [
            SesEventLogEntry.from_usv(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if initiative is not None:
            message_ids = {e.message_id for e in self.list_send_log(initiative) if e.message_id}
            entries = [e for e in entries if e.message_id in message_ids]
        return sorted(entries, key=lambda e: e.occurred_at, reverse=True)


def compute_unsubscribe_rate(campaign_name: str) -> UnsubscribeRateStats:
    """Sent count from the send log, unsubscribed count from exclusions
    tagged by `cocli email unsubscribe` (reason "unsubscribe:<REASON>",
    commands/email.py) - a pure computation over existing data, no new
    storage."""
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir(campaign_name)
    log_path = index_dir / "log.usv"
    sent_count = 0
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                if SendLogEntry.from_usv(line).status == "sent":
                    sent_count += 1
            except Exception:
                continue

    unsubscribed_count = sum(
        1
        for exc in ExclusionManager(campaign_name).list_exclusions()
        if (exc.reason or "").startswith("unsubscribe:")
    )

    return UnsubscribeRateStats(sent_count=sent_count, unsubscribed_count=unsubscribed_count)


