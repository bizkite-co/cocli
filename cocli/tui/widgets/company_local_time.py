from __future__ import annotations

import logging
from typing import Any, Optional, Union

from textual.widgets import Static

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.companies.website import Website
from cocli.utils.company_local_time import (
    CompanyPlace,
    format_company_local_now,
    resolve_company_place,
)

logger = logging.getLogger(__name__)


def resolve_place_from_company(
    company: Optional[Union[Company, dict[str, Any]]] = None,
    slug: Optional[str] = None,
) -> CompanyPlace:
    """Resolve a CompanyPlace from either a Company model, a company dict, or a slug."""
    if company is None and slug:
        try:
            company = Company.get(slug)
        except Exception:
            company = None

    if company is None:
        return resolve_company_place()

    company_slug: Optional[str] = slug
    if isinstance(company, Company):
        company_slug = company.slug
        timezone_name = company.timezone
        state = company.state
        city = company.city
        zip_code = company.zip_code
        latitude = company.latitude
        longitude = company.longitude
        address_bits = [
            str(company.street_address or ""),
            str(company.full_address or ""),
            str(company.city or ""),
            str(company.state or ""),
            str(company.zip_code or ""),
        ]
        website_path = company.get_local_path() / "enrichments" / "website.md"
        if website_path.exists():
            try:
                data = Website.read_existing_frontmatter(website_path)
                if data:
                    address_bits.append(str(data.get("address") or ""))
                    address_bits.append(str(data.get("description") or "")[:2000])
            except Exception:
                pass
    else:
        # Dictionary structure (e.g. company_data dict or company_data["company"])
        c_dict = company.get("company", company) if isinstance(company, dict) else {}
        company_slug = c_dict.get("slug") or slug
        timezone_name = c_dict.get("timezone")
        state = c_dict.get("state")
        city = c_dict.get("city")
        zip_code = c_dict.get("zip_code")
        latitude = c_dict.get("latitude")
        longitude = c_dict.get("longitude")
        address_bits = [
            str(c_dict.get("street_address") or ""),
            str(c_dict.get("full_address") or ""),
            str(c_dict.get("city") or ""),
            str(c_dict.get("state") or ""),
            str(c_dict.get("zip_code") or ""),
        ]
        website_data = company.get("website_data") if isinstance(company, dict) else None
        if website_data and isinstance(website_data, dict):
            address_bits.append(str(website_data.get("address") or ""))
            address_bits.append(str(website_data.get("description") or "")[:2000])
        elif company_slug:
            try:
                entry_path = paths.companies.entry(company_slug).path
                website_path = entry_path / "enrichments" / "website.md"
                if website_path.exists():
                    data = Website.read_existing_frontmatter(website_path)
                    if data:
                        address_bits.append(str(data.get("address") or ""))
                        address_bits.append(str(data.get("description") or "")[:2000])
            except Exception:
                pass

    return resolve_company_place(
        timezone_name=timezone_name,
        state=state,
        city=city,
        zip_code=zip_code,
        latitude=latitude,
        longitude=longitude,
        address_text="\n".join(bit for bit in address_bits if bit.strip()),
    )


class CompanyLocalTime(Static):
    """A live-updating widget displaying the current local time and place for a company."""

    DEFAULT_CSS = """
    CompanyLocalTime {
        height: 1;
        color: #00ff00;
        text-style: bold;
    }
    """

    def __init__(
        self,
        company: Optional[Union[Company, dict[str, Any]]] = None,
        slug: Optional[str] = None,
        place: Optional[CompanyPlace] = None,
        id: Optional[str] = "company_local_time",
        classes: Optional[str] = None,
    ):
        if place is not None:
            self._place = place
        else:
            self._place = resolve_place_from_company(company=company, slug=slug)
        initial_markup = self.get_time_markup()
        super().__init__(initial_markup, id=id, classes=classes)

    def set_company(
        self,
        company: Optional[Union[Company, dict[str, Any]]] = None,
        slug: Optional[str] = None,
    ) -> None:
        """Update the target company and refresh the clock display."""
        self._place = resolve_place_from_company(company=company, slug=slug)
        self.tick()

    def set_place(self, place: CompanyPlace) -> None:
        """Explicitly set the CompanyPlace."""
        self._place = place
        self.tick()

    def get_time_markup(self) -> str:
        """Format the company local time with bold green text and location label."""
        stamp = format_company_local_now(place=self._place)
        label = self._place.place_label()
        if label:
            return f"[bold green]{stamp}[/bold green]  ({label})"
        return f"[bold green]{stamp}[/bold green]"

    def on_mount(self) -> None:
        self.set_interval(1.0, self.tick)
        self.tick()

    def tick(self) -> None:
        """Update the label with the current second's timestamp."""
        try:
            self.update(self.get_time_markup())
        except Exception:
            pass
