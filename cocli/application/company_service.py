from __future__ import annotations
from typing import Any, Optional
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

    # Load website data using WebsiteCache (legacy fallback)
    website_data = None
    if company.domain:
        website_cache = WebsiteCache()
        website_data = website_cache.get_by_url(company.domain)

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
    if campaign:
        maps_receipt = entry / "enrichments" / "google_maps.usv"
        if maps_receipt.exists():
            try:
                from cocli.core.constants import UNIT_SEP

                with open(maps_receipt, "r", encoding="utf-8") as rf:
                    # Check if the first line is a header (contains 'created_at' or 'Place_ID')
                    # or if it's already the data (starts with 'ChIJ')
                    first_line = rf.readline()
                    data_line = None
                    if first_line.startswith("ChIJ"):
                        data_line = first_line
                    else:
                        data_line = rf.readline()

                    if data_line:
                        parts = data_line.split(UNIT_SEP)
                        if len(parts) > 25 and parts[0].startswith("ChIJ"):
                            place_id = parts[0]
                            # Rating is at index 25, reviews at 24
                            rating_val = parts[25].strip()
                            reviews_val = parts[24].strip()

                            if rating_val:
                                lifecycle_dates["average_rating"] = float(rating_val)
                            if reviews_val:
                                lifecycle_dates["reviews_count"] = int(reviews_val)

                            # Extract details_at from index 5 (updated_at)
                            if len(parts) > 5:
                                details_at = parts[5].strip()
                                if details_at:
                                    lifecycle_dates["details_found_at"] = details_at

                            # 1. Look up in lifecycle.usv
                            lifecycle_path = paths.campaign(campaign).lifecycle
                            if lifecycle_path.exists():
                                with open(lifecycle_path, "r", encoding="utf-8") as lf:
                                    # Header: place_id, scraped_at, details_at, enqueued_at, enriched_at
                                    lf.readline()  # skip header
                                    for line in lf:
                                        l_parts = line.split(UNIT_SEP)
                                        if len(l_parts) >= 4 and l_parts[0] == place_id:
                                            lifecycle_dates["list_found_at"] = (
                                                l_parts[1].strip() or None
                                            )
                                            lifecycle_dates["details_found_at"] = (
                                                l_parts[2].strip() or None
                                            )
                                            lifecycle_dates["enqueued_at"] = (
                                                l_parts[3].strip() or None
                                            )
                                            break

                            # 2. Look up in prospects index if missing
                            if (
                                lifecycle_dates["average_rating"] is None
                                or lifecycle_dates["reviews_count"] is None
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
    slugs: list[str] = []
    for company in Company.get_all():
        if company is None:
            continue
        hit = [t for t in (company.tags or []) if t in known]
        if not hit:
            continue
        for name in hit:
            company.add_to_campaign(name)
        if not dry_run:
            company.save(rebuild_cache=False)
        moved += 1
        slugs.append(company.slug)
    return {
        "dry_run": dry_run,
        "known_campaigns": sorted(known),
        "companies_updated": moved,
        "slugs": slugs,
    }
