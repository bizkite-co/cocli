from textual.screen import Screen
from textual.widgets import Header, Footer, Markdown
from textual.app import ComposeResult
from textual.containers import VerticalScroll

from cocli.models.company import Company

class CompanyDetail(Screen[None]):
    """A screen to display the details of a single company."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, company_slug: str, name: str | None = None, id: str | None = None, classes: str | None = None):
        super().__init__(name, id, classes)
        self.company_slug = company_slug
        self.company: Company | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield VerticalScroll(
            Markdown(self.company.description if self.company and self.company.description else "Company not found.", classes="company-description")
        )

    def on_mount(self) -> None:
        self.company = Company.get(self.company_slug)
        if self.company:
            self.sub_title = self.company.name
        else:
            self.sub_title = "Company Not Found"
        self.query_one(Markdown).update(self.company.description if self.company and self.company.description else "Company not found.")
