import datetime
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

from pytz import timezone
from tzlocal import get_localzone

def _render_company_details(frontmatter_data: dict, tags: List[str], content: str) -> Panel:
    """Renders company details, including tags, and markdown content."""
    output = ""
    for key, value in frontmatter_data.items():
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

    if content.strip():
        output += f"\n{content.strip()}\n"

    return Panel(Markdown(output), title="Company Details", border_style="green")

def _render_contacts(contacts_dir: Path) -> Panel:
    """Renders a list of contacts in two columns."""
    if not contacts_dir.exists():
        return Panel("No contacts found.", title="Contacts", border_style="blue")

    contacts = [f.name for f in contacts_dir.iterdir() if f.is_file()]
    if not contacts:
        return Panel("No contacts found.", title="Contacts", border_style="blue")

    contact_renderables = [Text(contact) for contact in sorted(contacts)]
    
    # Use rich.Columns for a multi-column layout
    columns = Columns(contact_renderables, equal=True, expand=True)
    return Panel(columns, title="Contacts", border_style="blue")


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


def display_company_view(console: Console, company_name: str, selected_company_dir: Path, frontmatter_data: dict):
    console.clear() 
    
    index_path = selected_company_dir / "_index.md"
    tags_path = selected_company_dir / "tags.lst"
    meetings_dir = selected_company_dir / "meetings"
    contacts_dir = selected_company_dir / "contacts"

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
    details_panel = _render_company_details(frontmatter_data, tags, content)
    contacts_panel = _render_contacts(contacts_dir)
    meetings_panel, meeting_map = _render_meetings(meetings_dir)

    # Display layout
    console.print(details_panel)
    console.print(contacts_panel)
    console.print(meetings_panel)

    return meeting_map
