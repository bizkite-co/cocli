"""Personalized outreach campaign batch selection & email copy generation service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

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

        return matches

    def generate_copy(
        self, first_name: str, company_name: str, company_slug: str
    ) -> tuple[str, str]:
        """Generate high-converting, personalized email subject and body with UTM links."""
        subject = f"{first_name}, retirement tax analysis for {company_name}"

        base_body = (
            f"Hi {first_name},\n\n"
            f"I was reviewing {company_name}'s client services and wanted to reach out directly. "
            f"When evaluating retirement tax strategies for high-income clients, calculating the exact impact of "
            f"tax-qualified vs. non-qualified assets is often one of the most compelling conversations you can have.\n\n"
            f"We built the Retirement Tax Analyzer ({DEFAULT_LANDING_URL}) to help advisory teams "
            f"visually model complex retirement distribution scenarios, tax brackets, and passive income strategies in seconds.\n\n"
            f"Would you be open to a quick 5-minute look to see how it can streamline your client reviews?\n\n"
            f"Best regards,\n"
            f"The Retirement Tax Analyzer Team\n"
        )

        body_with_utm = append_utm_params(
            base_body,
            campaign=self.campaign_name,
            company_slug=company_slug,
            source="email_sequence",
            medium="email",
            term=first_name.lower(),
        )

        return subject, body_with_utm
