from typing import Dict, Any, Optional
import re
import datetime

from ..models.company import Company
from ..models.person import Person
from ..models.note import Note
from ..core.config import get_companies_dir
from ..core.website_cache import WebsiteCache # Corrected import

def get_company_details_for_view(company_slug: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves all necessary data for displaying a company's detailed view.

    Args:
        company_slug: The slug of the company to retrieve details for.

    Returns:
        A dictionary containing company details, contacts, meetings, notes,
        and website data, or None if the company is not found.
    """
    companies_dir = get_companies_dir()
    selected_company_dir = companies_dir / company_slug

    if not selected_company_dir.exists():
        return None

    company = Company.from_directory(selected_company_dir)
    if not company:
        return None

    index_path = selected_company_dir / "_index.md"
    tags_path = selected_company_dir / "tags.lst"
    meetings_dir = selected_company_dir / "meetings"
    contacts_dir = selected_company_dir / "contacts"
    notes_dir = selected_company_dir / "notes"

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

    # Load website data using WebsiteCache
    website_data = None
    if company.domain:
        website_cache = WebsiteCache()
        website_data = website_cache.get_by_url(company.domain)

    # Load contacts
    contacts = []
    if contacts_dir.exists():
        for contact_symlink in contacts_dir.iterdir():
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
        for note_file in notes_dir.iterdir():
            if note_file.is_file() and note_file.suffix == ".md":
                note = Note.from_file(note_file)
                if note:
                    notes.append(note.model_dump()) # Convert to dict for generic return

    return {
        "company": company.model_dump(),
        "tags": tags,
        "content": content,
        "website_data": website_data.model_dump() if website_data else None,
        "contacts": contacts,
        "meetings": meetings,
        "notes": notes,
    }
