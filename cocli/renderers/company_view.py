import datetime
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.columns import Columns

from pytz import timezone
from tzlocal import get_localzone
from ..core.config import get_companies_dir
from ..models.company import Company
from ..models.website import Website
from ..models.person import Person
from ..models.note import Note

def _render_company_details(company: Company, tags: List[str], content: str, website_data: Optional[Website]) -> Panel:
    """Renders company details, including tags, services, and markdown content."""
    output = ""

    if content.strip():
        output += f"\n{content.strip()}\n"

    for key, value in company.model_dump().items():
        if value is None or key == "name":
            continue

        key_str = key.replace('_', ' ').title()
        if key == "domain" and isinstance(value, str):
            output += f"- {key_str}: [{value}](http://{value})\n"
        elif key == "phone_number" and isinstance(value, str):
            output += f"- {key_str}: {value} (Press 'p' to call)\n"
        else:
            output += f"- {key_str}: {value}\n"

    if tags:
        output += f"- Tags: {', '.join(tags)}\n"

    if website_data and website_data.services:
        output += f"- Services: {', '.join(website_data.services)}\n"

    return Panel(Markdown(output), title="Company Details", border_style="green")

def _render_contacts(contacts_dir: Path) -> Panel:
    """Renders a list of contacts with more details."""
    if not contacts_dir.exists():
        return Panel("No contacts found.", title="Contacts", border_style="blue")

    contact_panels = []
    for contact_symlink in contacts_dir.iterdir():
        if contact_symlink.is_symlink():
            person_dir = contact_symlink.resolve()
            person = Person.from_directory(person_dir)
            if person:
                contact_details = f"[bold]{person.name}[/bold]\n"
                if person.role:
                    contact_details += f"Role: {person.role}\n"
                if person.email:
                    contact_details += f"Email: {person.email}\n"
                if person.phone:
                    contact_details += f"Phone: {person.phone}"
                contact_panels.append(Panel(contact_details, title=person.name, border_style="blue"))

    if not contact_panels:
        return Panel("No contacts found.", title="Contacts", border_style="blue")

    return Panel(Columns(contact_panels, expand=True, equal=True), title="Contacts", border_style="blue")


def _render_meetings(meetings_dir: Path) -> Tuple[Panel, Dict[int, Path]]:
    """Renders upcoming and recent meetings."""
    next_meetings = []
    recent_meetings = []

    if meetings_dir.exists():
        now_local = datetime.datetime.now(get_localzone())
        six_months_ago_local = now_local - datetime.timedelta(days=180)

        for meeting_file in sorted(meetings_dir.iterdir()):
            if meeting_file.is_file() and meeting_file.suffix == ".md":
                try:
                    match = re.match(r"^(\d{4}-\d{2}-\d{2}(?:T\d{4}Z)?)-?(.*)\.md$", meeting_file.name)
                    if not match:
                        continue

                    datetime_str = match.group(1)
                    title_slug = match.group(2)

                    if 'T' in datetime_str and datetime_str.endswith('Z'):
                        meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H%MZ').replace(tzinfo=timezone('UTC'))
                    else:
                        meeting_datetime_utc = datetime.datetime.strptime(datetime_str, '%Y-%m-%d').replace(tzinfo=timezone('UTC'))

                    local_tz = get_localzone()
                    meeting_datetime_local = meeting_datetime_utc.astimezone(local_tz)
                    meeting_title = title_slug.replace("-", " ") if title_slug else "Untitled Meeting"

                    if meeting_datetime_local > now_local:
                        next_meetings.append((meeting_datetime_local, meeting_file, meeting_title))
                    elif meeting_datetime_local >= six_months_ago_local:
                        recent_meetings.append((meeting_datetime_local, meeting_file, meeting_title))
                except (ValueError, IndexError):
                    pass

    next_meetings.sort(key=lambda x: x[0])
    recent_meetings.sort(key=lambda x: x[0], reverse=True)

    all_displayable_meetings = []
    meeting_counter = 1
    output = ""

    output += "## Next Meetings\n\n"
    if next_meetings:
        for dt, file, title in next_meetings:
            output += f"- {meeting_counter}. {dt.strftime('%Y-%m-%d %H:%M %Z')}: [{title}]({file.name})\n"
            all_displayable_meetings.append((meeting_counter, file))
            meeting_counter += 1
    else:
        output += "No upcoming meetings found.\n"

    output += "\n---\n\n## Recent Meetings\n\n"
    if recent_meetings:
        for dt, file, title in recent_meetings:
            output += f"- {meeting_counter}. {dt.strftime('%Y-%m-%d %H:%M %Z')}: [{title}]({file.name})\n"
            all_displayable_meetings.append((meeting_counter, file))
            meeting_counter += 1
    else:
        output += "No recent meetings found.\n"

    meeting_map = {num: file for num, file in all_displayable_meetings}
    return Panel(Markdown(output), title="Meetings", border_style="magenta"), meeting_map

def _render_notes(notes_dir: Path) -> Panel:
    """Renders the most recent three notes."""
    notes = []
    if notes_dir.exists():
        for note_file in notes_dir.iterdir():
            if note_file.is_file() and note_file.suffix == ".md":
                note = Note.from_file(note_file)
                if note:
                    notes.append(note)

    notes.sort(key=lambda n: n.timestamp, reverse=True)

    output = ""
    if notes:
        for i, note in enumerate(notes[:3]): # Display only the most recent 3 notes
            output += f"[bold]{note.timestamp.strftime('%Y-%m-%d %H:%M')}[/bold] - [bold]{note.title}[/bold]\n"
            output += f"{note.content}\n\n"
            if i < len(notes[:3]) - 1:
                output += "---\n\n" # Separator between notes
    else:
        output = "No notes found."

    return Panel(Markdown(output), title="Recent Notes", border_style="cyan")


def display_company_view(console: Console, company: Company, website_data: Optional[Website]):
    console.clear()

    if not company.slug:
        console.print("[bold red]Error: Company slug is missing.[/]")
        return

    selected_company_dir = get_companies_dir() / company.slug

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

    # Render components
    details_panel = _render_company_details(company, tags, content, website_data)
    contacts_panel = _render_contacts(contacts_dir)
    meetings_panel, meeting_map = _render_meetings(meetings_dir)
    notes_panel = _render_notes(notes_dir)

    # Display layout
    top_columns = Columns([details_panel, contacts_panel], expand=True, equal=True)
    console.print(top_columns)
    console.print(meetings_panel)
    console.print(notes_panel)

    return meeting_map
