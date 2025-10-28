from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from cocli.models.company import Company
from cocli.utils.textual_utils import sanitize_id # New import

class CompanyList(Screen[None]):
    """A screen to display a list of companies."""

    def compose(self) -> ComposeResult:
        companies = Company.get_all()
        # Sort by company name, but use slug for ID
        sorted_companies = sorted(companies, key=lambda c: c.name)

        yield Label("Companies")
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(company.name), id=sanitize_id(company.slug)) for company in sorted_companies]
            )
