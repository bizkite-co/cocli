from typing import Dict, Any, Optional
import re
import datetime

from ..models.companies.company import Company
from ..models.people.person import Person
from ..models.companies.note import Note
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
                try:
                    match = re.match(r"^(\d{4}-\d{2}-\d{2}(?:T\d{4}Z)?)-?(.*)\.md$", meeting_file.name)
                    if not match:
                        continue

                    datetime_str = match.group(1)
                    title_slug = match.group(2)

                    if 'T' in datetime_str and datetime_str.endswith('Z'):
                        meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H%MZ').replace(tzinfo=datetime.timezone.utc)
                    else:
                        meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)

                    meeting_title = title_slug.replace("-", " ") if title_slug else "Untitled Meeting"
                    
                    meetings.append({
                        "datetime_utc": meeting_datetime_utc.isoformat(),
                        "title": meeting_title,
                        "file_path": str(meeting_file)
                    })
                except (ValueError, IndexError):
                    pass
    
    # Load notes
    notes = []
    if notes_dir.exists():
        for note_file in sorted(notes_dir.iterdir()):
            if note_file.is_file() and note_file.suffix == ".md":
                note = Note.from_file(note_file)
                if note:
                    notes.append(note.model_dump()) # Convert to dict for generic return

    return {
        "company": company.model_dump(),
        "tags": tags,
        "content": content,
        "website_data": website_data.model_dump() if website_data else None,
        "enrichment_path": str(enrichment_path) if enrichment_path.exists() else None,
        "enrichment_mtime": enrichment_mtime.isoformat() if enrichment_mtime else None,
        "contacts": contacts,
        "meetings": meetings,
        "notes": notes,
    }
