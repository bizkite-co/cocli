from textual.screen import Screen
from textual.widgets import Header, Footer, Static
from textual.containers import VerticalScroll, Horizontal, Container
from rich.markdown import Markdown
from rich.columns import Columns
from rich.panel import Panel as RichPanel
from rich.console import Console as RichConsole
from rich.text import Text

from typing import Dict, Any, List, Tuple, Optional # Added Optional
from pathlib import Path
import datetime

from cocli.models.company import Company
from cocli.models.website import Website
from cocli.models.person import Person
from cocli.models.note import Note
from cocli.renderers.company_view import _render_company_details, _render_contacts_from_data, _render_meetings_from_data, _render_notes_from_data

class CompanyDetailScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back to list"),
        ("q", "app.pop_screen", "Back to list"),
    ]

    def __init__(self, company_data: Dict[str, Any], name: Optional[str] = None, id: Optional[str] = None, classes: Optional[str] = None):
        super().__init__(name=name, id=id, classes=classes)
        self.company_data = company_data

    def compose(self):
        company = Company.model_validate(self.company_data["company"])
        tags = self.company_data["tags"]
        content = self.company_data["content"]
        website_data = Website.model_validate(self.company_data["website_data"]) if self.company_data["website_data"] else None
        contacts_data = self.company_data["contacts"]
        meetings_data = self.company_data["meetings"]
        notes_data = self.company_data["notes"]

        rich_console = RichConsole(force_terminal=True, width=self.app.size.width - 4) # Adjust width for panel padding

        # Render Rich panels using the refactored renderer functions
        details_panel = _render_company_details(company, tags, content, website_data)
        contacts_panel = _render_contacts_from_data(contacts_data)
        meetings_panel, _ = _render_meetings_from_data(meetings_data) # meeting_map is not used in TUI rendering directly
        notes_panel = _render_notes_from_data(notes_data)

        # Convert Rich renderables to Textual Static widgets
        # This is a workaround as Textual does not directly support RichPanel in compose
        # We render the RichPanel to a string and then display it in a Static widget
        
        with rich_console.capture() as capture:
            rich_console.print(details_panel)
        details_static = Static(capture.get(), expand=True)

        with rich_console.capture() as capture:
            rich_console.print(contacts_panel)
        contacts_static = Static(capture.get(), expand=True)

        with rich_console.capture() as capture:
            rich_console.print(meetings_panel)
        meetings_static = Static(capture.get(), expand=True)

        with rich_console.capture() as capture:
            rich_console.print(notes_panel)
        notes_static = Static(capture.get(), expand=True)

        yield Header()
        with VerticalScroll():
            with Horizontal():
                yield details_static
                yield contacts_static
            yield meetings_static
            yield notes_static
        yield Footer()