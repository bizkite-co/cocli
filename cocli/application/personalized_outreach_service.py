"""Personalized outreach campaign batch selection & email copy generation service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cocli.application.company_service import get_company_details_for_view
from cocli.core.exclusions import ExclusionManager
from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.utils.utm import append_utm_params

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

    def find_eligible_prospects(self, limit: int = 10) -> list[ProspectContactMatch]:
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

            details = get_company_details_for_view(slug)
            if not details:
                continue

            contacts = details.get("contacts") or []
            selected_email: Optional[str] = None
            selected_first_name: Optional[str] = None
            selected_full_name: str = ""
            selected_role: Optional[str] = None

            # First search contacts with explicit first names & emails
            for contact in contacts:
                raw_name = str(contact.get("name") or "").strip()
                email = str(contact.get("email") or "").strip()
                fname = extract_first_name(raw_name)
                if email and fname:
                    selected_email = email
                    selected_first_name = fname
                    selected_full_name = raw_name
                    selected_role = str(contact.get("role") or "")
                    break

            # Fallback if company email exists and a contact has a first name
            if not selected_email and company.email:
                co_email = str(company.email).strip()
                for contact in contacts:
                    raw_name = str(contact.get("name") or "").strip()
                    fname = extract_first_name(raw_name)
                    if fname:
                        selected_email = co_email
                        selected_first_name = fname
                        selected_full_name = raw_name
                        selected_role = str(contact.get("role") or "")
                        break

            if selected_email and selected_first_name:
                company_display_name = str(company.name) if company.name else slug.replace("-", " ").title()
                subject, body = self.generate_copy(
                    first_name=selected_first_name,
                    company_name=company_display_name,
                    company_slug=slug,
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


    def load_template(self, template_name: str = "email_01_pas_hook.md") -> tuple[str, str]:
        """Load email template subject pattern and body content from initiatives/rta/email-sequences/."""
        seq_dir = paths.campaigns / self.campaign_name / "initiatives" / "rta" / "email-sequences"
        template_path = seq_dir / template_name

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
        self, first_name: str, company_name: str, company_slug: str, template_name: str = "email_01_pas_hook.md"
    ) -> tuple[str, str]:
        """Generate outcome-driven, personalized email subject and body with UTM links."""
        subject_template, body_template = self.load_template(template_name)

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

    def render_and_save_draft(self, match: ProspectContactMatch, template_id: str = "email_01_pas_hook") -> Path:
        """Render and save an outreach email draft to disk before sending, maintaining an audit trail."""

        out_dir = (
            paths.campaigns
            / self.campaign_name
            / "initiatives"
            / "rta"
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


