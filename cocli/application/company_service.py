from typing import Dict, Any, Optional
import datetime

from ..models.companies.company import Company
from ..models.people.person import Person
from ..models.companies.note import Note
from ..models.companies.meeting import Meeting
from ..core.website_cache import WebsiteCache # Corrected import

from ..models.companies.website import Website
from ..core.s3_company_manager import S3CompanyManager
import logging

logger = logging.getLogger(__name__)

async def update_company_from_website_data(
    company: Company, 
    website_data: Website, 
    campaign: Optional[Any] = None
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
        logger.info(f"Updating website_url for {company.slug}: {company.website_url} -> {final_url}")
        company.website_url = final_url
        modified = True

    # 2. Handle Email
    if website_data.email and company.email != website_data.email:
        logger.info(f"Updating email for {company.slug}: {company.email} -> {website_data.email}")
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
            logger.warning(f"Failed to save website enrichment locally for {company.slug}: {e}")

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
                logger.info(f"Synced updated company {company.slug} and enrichment to S3")
            except Exception as e:
                logger.warning(f"Failed to sync company update to S3: {e}")

    return modified

    return modified

def get_company_details_for_view(company_slug: str) -> Optional[Dict[str, Any]]:
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
        enrichment_mtime = datetime.datetime.fromtimestamp(enrichment_path.stat().st_mtime, tz=datetime.timezone.utc)
    
    # Load website data using WebsiteCache (legacy fallback)
    website_data = None
    if company.domain:
        website_cache = WebsiteCache()
        website_data = website_cache.get_by_url(company.domain)

    # Load lifecycle data for status display
    lifecycle_dates: Dict[str, Any] = {
        "list_found_at": None, 
        "details_found_at": None, 
        "enqueued_at": None,
        "average_rating": None,
        "reviews_count": None
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
                                    lf.readline() # skip header
                                    for line in lf:
                                        l_parts = line.split(UNIT_SEP)
                                        if len(l_parts) >= 4 and l_parts[0] == place_id:
                                            lifecycle_dates["list_found_at"] = l_parts[1].strip() or None
                                            lifecycle_dates["details_found_at"] = l_parts[2].strip() or None
                                            lifecycle_dates["enqueued_at"] = l_parts[3].strip() or None
                                            break
                            
                            # 2. Look up in prospects index ONLY if still missing
                            if lifecycle_dates["average_rating"] is None:
                                from ..core.prospects_csv_manager import ProspectsIndexManager
                                manager = ProspectsIndexManager(campaign)
                                prospect = manager.get_prospect(place_id)
                                if prospect:
                                    if prospect.average_rating is not None:
                                        lifecycle_dates["average_rating"] = prospect.average_rating
                                    if prospect.reviews_count is not None:
                                        lifecycle_dates["reviews_count"] = prospect.reviews_count
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
                    contacts.append(person.model_dump()) # Convert to dict for generic return

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
                    notes.append(note.model_dump()) # Convert to dict for generic return

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
