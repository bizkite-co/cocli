import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.columns import Columns

from tzlocal import get_localzone
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




def display_company_view(console: Console, company_data: Dict[str, Any]) -> None:
    console.clear()

    company = Company.model_validate(company_data["company"])
    tags = company_data["tags"]
    content = company_data["content"]
    website_data = Website.model_validate(company_data["website_data"]) if company_data["website_data"] else None
    contacts_data = company_data["contacts"]
    meetings_data = company_data["meetings"]
    notes_data = company_data["notes"]

    if not company.slug:
        console.print("[bold red]Error: Company slug is missing.[/]")
        return

    # Render components
    details_panel = _render_company_details(company, tags, content, website_data)
    contacts_panel = _render_contacts_from_data(contacts_data)
    meetings_panel, meeting_map = _render_meetings_from_data(meetings_data)
    notes_panel = _render_notes_from_data(notes_data)

    # Display layout
    top_columns = Columns([details_panel, contacts_panel], expand=True, equal=True)
    console.print(top_columns)
    console.print(meetings_panel)
    console.print(notes_panel)

def _render_contacts_from_data(contacts_data: List[Dict[str, Any]]) -> Panel:
    """Renders a list of contacts from pre-fetched data."""
    if not contacts_data:
        return Panel("No contacts found.", title="Contacts", border_style="blue")

    contact_panels = []
    for contact_dict in contacts_data:
        person = Person.model_validate(contact_dict)
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

def _render_meetings_from_data(meetings_data: List[Dict[str, Any]]) -> Tuple[Panel, Dict[int, Path]]:
    """Renders upcoming and recent meetings from pre-fetched data."""
    next_meetings = []
    recent_meetings = []

    now_local = datetime.datetime.now(get_localzone())
    six_months_ago_local = now_local - datetime.timedelta(days=180)

    for meeting_dict in meetings_data:
        meeting_datetime_utc = datetime.datetime.fromisoformat(meeting_dict["datetime_utc"])
        meeting_title = meeting_dict["title"]
        meeting_file_path = Path(meeting_dict["file_path"])

        local_tz = get_localzone()
        meeting_datetime_local = meeting_datetime_utc.astimezone(local_tz)

        if meeting_datetime_local > now_local:
            next_meetings.append((meeting_datetime_local, meeting_file_path, meeting_title))
        elif meeting_datetime_local >= six_months_ago_local:
            recent_meetings.append((meeting_datetime_local, meeting_file_path, meeting_title))

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

def _render_notes_from_data(notes_data: List[Dict[str, Any]]) -> Panel:
    """Renders the most recent three notes from pre-fetched data."""
    notes = [Note.model_validate(n) for n in notes_data]
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


