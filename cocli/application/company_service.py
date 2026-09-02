from __future__ import annotations
from typing import Any, Optional
from pathlib import Path
import datetime

from ..models.companies.company import Company
from ..models.people.person import Person
from ..models.companies.note import Note
from ..models.companies.meeting import Meeting
from ..core.website_cache import WebsiteCache  # Corrected import

from ..models.companies.website import Website
from ..core.s3_company_manager import S3CompanyManager
import logging

logger = logging.getLogger(__name__)


def _read_maps_enrichment_row(path: Path) -> Optional[dict[str, str]]:
    """Parse companies/<slug>/enrichments/google_maps.usv (header or headerless)."""
    from io import StringIO

    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from cocli.utils.usv_utils import USVDictReader

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    first = text.splitlines()[0]
    buf = StringIO(text)
    if first.startswith("ChIJ"):
        reader = USVDictReader(buf, fieldnames=list(GoogleMapsProspect.model_fields.keys()))
    else:
        reader = USVDictReader(buf)
    return next(iter(reader), None)


async def update_company_from_website_data(
    company: Company, website_data: Website, campaign: Optional[Any] = None
) -> bool:
    """
    Updates a Company record with data from a website scrape.
    Handles redirects by updating website_url and ensures clean emails.
    Returns True if the company was modified and saved.
    """
    modified = False

    # 1. Handle Redirects / Website URL
    final_url = str(website_data.url) if website_data.url else None
    if final_url and company.website_url != final_url:
        logger.info(
            f"Updating website_url for {company.slug}: {company.website_url} -> {final_url}"
        )
        company.website_url = final_url
        modified = True

    # 2. Handle Email
    if website_data.email and company.email != website_data.email:
        logger.info(
            f"Updating email for {company.slug}: {company.email} -> {website_data.email}"
        )
        company.email = website_data.email
        modified = True

    # 3. Handle All Emails
    if website_data.all_emails:
        new_emails = sorted(list(set(company.all_emails + website_data.all_emails)))
        if new_emails != company.all_emails:
            company.all_emails = new_emails
            modified = True

    # 4. Handle Tech Stack
    if website_data.tech_stack:
        new_tech = sorted(list(set(company.tech_stack + website_data.tech_stack)))
        if new_tech != company.tech_stack:
            company.tech_stack = new_tech
            modified = True

    # 5. Handle Email Contexts
    if website_data.email_contexts:
        for email, label in website_data.email_contexts.items():
            if label and company.email_contexts.get(email) != label:
                company.email_contexts[email] = label
                modified = True

    # 6. Always save the full Website enrichment locally if we have a slug
    if company.slug:
        try:
            website_data.save(company.slug)
            # Local modification for the company index is already tracked by 'modified' flag,
            # but we always want the enrichment file to be fresh.
        except Exception as e:
            logger.warning(
                f"Failed to save website enrichment locally for {company.slug}: {e}"
            )

    if modified:
        # Save Company Index locally
        company.save()

        # Sync both to S3 if campaign context is provided
        if campaign:
            try:
                s3_manager = S3CompanyManager(campaign=campaign)
                # Sync _index.md
                await s3_manager.save_company_index(company)
                # Sync website.md
                await s3_manager.save_website_enrichment(company.slug, website_data)
                logger.info(
                    f"Synced updated company {company.slug} and enrichment to S3"
                )
            except Exception as e:
                logger.warning(f"Failed to sync company update to S3: {e}")

    return modified


def get_company_details_for_view(company_slug: str) -> Optional[dict[str, Any]]:
    """
    Retrieves all necessary data for displaying a company's detailed view.

    Args:
        company_slug: The slug of the company to retrieve details for.

    Returns:
        A dictionary containing company details, contacts, meetings, notes,
        and website data, or None if the company is not found.
    """
    from ..core.paths import paths

    entry = paths.companies.entry(company_slug)

    if not entry.exists():
        return None

    company = Company.from_directory(entry.path)
    if not company:
        return None

    index_path = entry.index
    tags_path = entry.tags
    meetings_dir = entry / "meetings"
    contacts_dir = entry / "contacts"
    notes_dir = entry / "notes"

    # Load tags
    tags = []
    if tags_path.exists():
        tags = tags_path.read_text().strip().splitlines()

    # Load markdown content from _index.md
    content = ""
    if index_path.exists():
        file_content = index_path.read_text()
        if file_content.startswith("---") and "---" in file_content[3:]:
            _, _, content = file_content.split("---", 2)
        else:
            content = file_content

    # Load website data (enrichment)
    enrichment_path = entry.enrichment("website")
    enrichment_mtime = None
    if enrichment_path.exists():
        enrichment_mtime = datetime.datetime.fromtimestamp(
            enrichment_path.stat().st_mtime, tz=datetime.timezone.utc
        )

    maps_receipt = entry / "enrichments" / "google_maps.usv"
    maps_row = (
        _read_maps_enrichment_row(maps_receipt) if maps_receipt.exists() else None
    )

    # Load website data using WebsiteCache (legacy fallback)
    website_data = None
    view_domain = company.domain or (
        (maps_row.get("domain") or "").strip() if maps_row else None
    )
    if view_domain:
        website_cache = WebsiteCache()
        website_data = website_cache.get_by_url(view_domain)

    # Load lifecycle data for status display
    lifecycle_dates: dict[str, Any] = {
        "list_found_at": None,
        "details_found_at": None,
        "enqueued_at": None,
        "average_rating": None,
        "reviews_count": None,
    }
    from ..core.config import get_campaign

    campaign = get_campaign()
    if maps_row:
        try:
            rating_val = (maps_row.get("average_rating") or "").strip()
            reviews_val = (maps_row.get("reviews_count") or "").strip()
            if rating_val:
                lifecycle_dates["average_rating"] = float(rating_val)
            if reviews_val:
                lifecycle_dates["reviews_count"] = int(float(reviews_val))
            details_at = (maps_row.get("updated_at") or "").strip()
            if details_at:
                lifecycle_dates["details_found_at"] = details_at
        except (TypeError, ValueError) as e:
            logger.warning(f"Error parsing maps receipt for {company_slug}: {e}")

    if campaign:
        try:
            from cocli.core.constants import UNIT_SEP

            place_id = ""
            if maps_row:
                place_id = (maps_row.get("place_id") or "").strip()
            if not place_id and company.place_id:
                place_id = str(company.place_id)

            lifecycle_path = paths.campaign(campaign).lifecycle
            if place_id and lifecycle_path.exists():
                with open(lifecycle_path, "r", encoding="utf-8") as lf:
                    lf.readline()  # skip header
                    for line in lf:
                        l_parts = line.split(UNIT_SEP)
                        if len(l_parts) >= 4 and l_parts[0] == place_id:
                            lifecycle_dates["list_found_at"] = (
                                l_parts[1].strip() or None
                            )
                            lifecycle_dates["details_found_at"] = (
                                l_parts[2].strip() or None
                            ) or lifecycle_dates["details_found_at"]
                            lifecycle_dates["enqueued_at"] = (
                                l_parts[3].strip() or None
                            )
                            break

            if (
                place_id
                and (
                    lifecycle_dates["average_rating"] is None
                    or lifecycle_dates["reviews_count"] is None
                )
            ):
                try:
                    from ..core.prospects_csv_manager import (
                        ProspectsIndexManager,
                    )

                    manager = ProspectsIndexManager(campaign)
                    prospect = manager.get_prospect(place_id)
                    if prospect:
                        if (
                            lifecycle_dates["average_rating"] is None
                            and prospect.average_rating is not None
                        ):
                            lifecycle_dates["average_rating"] = (
                                prospect.average_rating
                            )
                        if (
                            lifecycle_dates["reviews_count"] is None
                            and prospect.reviews_count is not None
                        ):
                            lifecycle_dates["reviews_count"] = (
                                prospect.reviews_count
                            )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error reading maps receipt for {company_slug}: {e}")

    # Load contacts
    contacts = []
    if contacts_dir.exists():
        for contact_symlink in sorted(contacts_dir.iterdir()):
            if contact_symlink.is_symlink():
                person_dir = contact_symlink.resolve()
                person = Person.from_directory(person_dir)
                if person:
                    contacts.append(
                        person.model_dump()
                    )  # Convert to dict for generic return

    # Load meetings
    meetings = []
    if meetings_dir.exists():
        for meeting_file in sorted(meetings_dir.iterdir()):
            if meeting_file.is_file() and meeting_file.suffix == ".md":
                meeting = Meeting.from_file(meeting_file)
                if meeting:
                    m_data = meeting.model_dump()
                    m_data["datetime_utc"] = meeting.timestamp.isoformat()
                    m_data["file_path"] = str(meeting_file)
                    meetings.append(m_data)

    # Load notes
    notes = []
    if notes_dir.exists():
        for note_file in sorted(notes_dir.iterdir()):
            if note_file.is_file() and note_file.suffix == ".md":
                note = Note.from_file(note_file)
                if note:
                    n_data = note.model_dump()
                    n_data["file_path"] = str(note_file)
                    notes.append(n_data)  # Convert to dict for generic return

    comp_dict = company.model_dump()

    # Merge lifecycle data - PRIORITIZE ENRICHMENT over disk/index
    # This ensures manual scrapes are immediately visible in the TUI.
    for key, val in lifecycle_dates.items():
        if val is not None:
            comp_dict[key] = val

    if maps_row:
        enrich_domain = (maps_row.get("domain") or "").strip()
        if enrich_domain and not comp_dict.get("domain"):
            comp_dict["domain"] = enrich_domain
        enrich_website = (maps_row.get("website") or "").strip()
        if enrich_website and not comp_dict.get("website_url"):
            comp_dict["website_url"] = enrich_website
        enrich_gmb = (maps_row.get("gmb_url") or "").strip()
        if enrich_gmb and "google.com/maps" in enrich_gmb and "query=google" not in enrich_gmb:
            comp_dict["gmb_url"] = enrich_gmb
        elif comp_dict.get("gmb_url") and "query=google" in str(comp_dict["gmb_url"]):
            from ..utils.google_maps_url import google_maps_url

            rebuilt = google_maps_url(
                place_id=comp_dict.get("place_id"),
                name=comp_dict.get("name"),
                street_address=comp_dict.get("street_address"),
                city=comp_dict.get("city"),
            )
            if rebuilt:
                comp_dict["gmb_url"] = rebuilt

    return {
        "company": comp_dict,
        "tags": tags,
        "content": content,
        "website_data": website_data.model_dump() if website_data else None,
        "enrichment_path": str(enrichment_path) if enrichment_path.exists() else None,
        "enrichment_mtime": enrichment_mtime.isoformat() if enrichment_mtime else None,
        "contacts": contacts,
        "meetings": meetings,
        "notes": notes,
    }


def backfill_missing_companies_from_prospects(
    campaign_name: str, dry_run: bool = True, min_hours_since_last_run: Optional[float] = None
) -> dict[str, Any]:
    """
    Materializes companies/<slug> directories for prospects that exist in a
    campaign's prospects checkpoint but were never compiled into a company
    record (Mark, 2026-08-31 - ~6,055 of 27,049 roadmap prospect slugs had
    no companies/<slug> dir; the TUI's detail view requires that directory
    to exist, so these leads previewed but wouldn't open). Uses the same
    field mapping as op_compile_to_call's create-from-prospect path
    (name/phone/rating/reviews/address/domain). Tags every created company
    with campaign_name (op_compile_to_call's own create path was found to
    skip this, leaving created companies invisible to
    audit_campaign_integrity) plus a dated backfill marker, since nothing
    else records how a company record was created.

    min_hours_since_last_run (2026-09-01): for a login-triggered scheduled
    run (systemd OnStartupSec=, fires every login) rather than a fixed
    calendar schedule - Mark wants "run shortly after login, but only if
    it's actually been a while," and is fine with it not running for days
    if he isn't logged in. systemd's Persistent= (the disk-backed "catch up
    a missed run" mechanism) explicitly only applies to OnCalendar= timers
    per systemd.timer(5), not the monotonic OnStartupSec=/OnUnitActiveSec=
    needed for login-triggering, and it was unclear whether
    OnUnitActiveSec='s own state survives a full user-manager restart
    (logout with no lingering) - so the staleness check lives here instead,
    against an explicit marker file, rather than relying on systemd
    internals that weren't verifiable. Only checked/updated for a real
    (non-dry-run) execute - a dry-run inspection should always show live
    state.
    """
    import datetime as _datetime
    import time as _time

    from ..core.paths import paths
    from ..core.prospects_csv_manager import ProspectsIndexManager
    from ..core.utils import create_company_files
    from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    from ..models.company_name import CompanyName

    marker_path = paths.campaign(campaign_name).path / ".backfill-from-prospects-last-run"
    if not dry_run and min_hours_since_last_run is not None and marker_path.exists():
        hours_since = (_time.time() - marker_path.stat().st_mtime) / 3600
        if hours_since < min_hours_since_last_run:
            return {
                "campaign_name": campaign_name,
                "skipped_stale_check": True,
                "hours_since_last_run": round(hours_since, 2),
                "min_hours_since_last_run": min_hours_since_last_run,
                "dry_run": dry_run,
            }

    companies_dir = paths.companies.path
    # A bare directory isn't a real company record: the enrichment worker's
    # Website.save() creates companies/<slug>/enrichments/ as a side effect
    # of mkdir(parents=True) for slugs that don't have a company yet (126
    # such shells found in production, 2026-08-31), leaving no _index.md.
    # Company.from_directory() already treats that the same as "not found"
    # (get_company_details_for_view -> None), so those slugs need the same
    # backfill as ones with no directory at all.
    existing_slugs = (
        {p.name for p in companies_dir.iterdir() if p.is_dir() and (p / "_index.md").exists()}
        if companies_dir.exists()
        else set()
    )

    manager = ProspectsIndexManager(campaign_name)

    # Last-write-wins per slug: read_all_prospects() yields the cold
    # checkpoint first, then hotter WAL entries - a later entry for the
    # same slug is the fresher record.
    prospects_by_slug: dict[str, GoogleMapsProspect] = {}
    for prospect in manager.read_all_prospects():
        if not prospect.slug or prospect.slug in existing_slugs:
            continue
        prospects_by_slug[prospect.slug] = prospect

    backfill_tag = f"backfilled-from-prospects-{_datetime.date.today().isoformat()}"
    created_slugs = []
    for slug, prospect in prospects_by_slug.items():
        company_name = (
            str(prospect.name).strip("\"'")
            if prospect.name
            else slug.replace("-", " ").title()
        )
        company = Company(
            name=CompanyName(company_name),
            slug=slug,
            phone_1=prospect.phone,
            phone_number=prospect.phone,
            average_rating=prospect.average_rating,
            reviews_count=prospect.reviews_count,
            street_address=prospect.street_address,
            city=prospect.city,
            state=prospect.state,
            zip_code=prospect.zip,
            domain=prospect.domain,
            tags=[backfill_tag],
            campaigns=[campaign_name],
        )
        if not dry_run:
            create_company_files(company, company.get_local_path(), rebuild_cache=False)
        created_slugs.append(slug)

    if not dry_run and created_slugs:
        from ..core.cache import build_cache

        build_cache(campaign=campaign_name)

    if not dry_run:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(_datetime.datetime.now(_datetime.UTC).isoformat())

    return {
        "campaign_name": campaign_name,
        "skipped_stale_check": False,
        "existing_company_count": len(existing_slugs),
        "missing_count": len(created_slugs),
        "created_count": 0 if dry_run else len(created_slugs),
        "dry_run": dry_run,
        "tag": backfill_tag,
        "slugs": created_slugs,
    }


def backfill_campaigns_from_tags(*, dry_run: bool = True) -> dict[str, Any]:
    """Move known campaign names out of company.tags into company.campaigns.

    A company can belong to more than one campaign; tags stay for labels
    like backfilled-from-prospects-*, not for campaign membership.
    """
    from ..core.config import get_all_campaign_dirs

    known = {d.name for d in get_all_campaign_dirs()}
    moved = 0
    scanned = 0
    slugs: list[str] = []
    by_campaign: dict[str, int] = {name: 0 for name in known}
    for company in Company.get_all():
        scanned += 1
        if scanned % 500 == 0:
            logger.info(
                "backfill_campaigns_from_tags: scanned %s, matched %s",
                scanned,
                moved,
            )
        if company is None:
            continue
        hit = [t for t in (company.tags or []) if t in known]
        if not hit:
            continue
        for name in hit:
            company.add_to_campaign(name)
            by_campaign[name] = by_campaign.get(name, 0) + 1
        if not dry_run:
            company.save(rebuild_cache=False)
        moved += 1
        slugs.append(company.slug)
    return {
        "dry_run": dry_run,
        "known_campaigns": sorted(known),
        "scanned": scanned,
        "companies_updated": moved,
        "by_campaign": {k: v for k, v in sorted(by_campaign.items()) if v},
        "slugs": slugs,
    }
