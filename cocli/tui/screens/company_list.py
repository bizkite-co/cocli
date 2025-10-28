from textual.screen import Screen
from textual.widgets import ListView, ListItem, Label, Input # New import Input
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message

from cocli.models.company import Company
from cocli.utils.textual_utils import sanitize_id

class CompanyList(Screen[None]):
    """A screen to display a list of companies."""

    class CompanySelected(Message):
        """Posted when a company is selected from the list."""
        def __init__(self, company_slug: str) -> None:
            super().__init__()
            self.company_slug = company_slug

    def __init__(self, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.all_companies = list(Company.get_all()) # Store all companies
        self.filtered_companies = self.all_companies # Initialize filtered list

    def compose(self) -> ComposeResult:
        yield Label("Companies")
        yield Input(placeholder="Search companies...", id="company_search_input") # Add search input
        with VerticalScroll():
            yield ListView(
                *[ListItem(Label(company.name), id=sanitize_id(company.slug)) for company in self.filtered_companies], # Use filtered_companies
                id="company_list_view"
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Called when the search input changes."""
        search_query = event.value.lower()
        self.filtered_companies = [
            company for company in self.all_companies
            if search_query in company.name.lower() or \
               (company.domain and search_query in company.domain.lower()) or \
               (company.slug and search_query in company.slug.lower())
        ]
        self.update_company_list_view()

    def update_company_list_view(self) -> None:
        """Updates the ListView with filtered companies."""
        list_view = self.query_one("#company_list_view", ListView)
        list_view.clear()
        for company in self.filtered_companies:
            list_view.append(ListItem(Label(company.name), id=sanitize_id(company.slug)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when a company is selected from the list."""
        if event.item.id:
            self.post_message(self.CompanySelected(event.item.id))
