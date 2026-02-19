from textual.app import ComposeResult
from textual.containers import Horizontal, Container
from textual.widgets import ListView
from textual import on, events

from .template_list import TemplateList
from .company_list import CompanyList
from .company_preview import CompanyPreview

class CompanySearchView(Container):
    """
    A three-column view for company search.
    Column 1: Templates
    Column 2: Search/Company List
    Column 3: Company Preview
    """

    BINDINGS = [
        ("t", "focus_template", "Focus Templates"),
        ("c", "focus_companies", "Focus Companies"),
        ("s", "focus_search", "Search"),
    ]

    def __init__(
        self, 
        template_list: TemplateList, 
        company_list: CompanyList, 
        company_preview: CompanyPreview,
        name: str | None = None, 
        id: str | None = None, 
        classes: str | None = None
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.template_list = template_list
        self.company_list = company_list
        self.company_preview = company_preview

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self.template_list
            yield self.company_list
            yield self.company_preview

    @on(TemplateList.TemplateSelected)
    def on_template_selected(self, message: TemplateList.TemplateSelected) -> None:
        self.company_list.apply_template(message.template_id)
        self.action_focus_companies()

    @on(CompanyList.CompanyHighlighted)
    def on_company_highlighted(self, message: CompanyList.CompanyHighlighted) -> None:
        self.company_preview.update_preview(message.company)

    def action_focus_template(self) -> None:
        self.template_list.focus_list()

    def action_focus_companies(self) -> None:
        self.company_list.query_one("#company_list_view").focus()

    def action_focus_search(self) -> None:
        self.company_list.action_focus_search()

    def on_key(self, event: events.Key) -> None:
        if event.key == "h":
            if self.company_list.has_focus_within:
                self.template_list.focus_list()
                event.prevent_default()
            elif self.company_preview.has_focus_within:
                self.action_focus_companies()
                event.prevent_default()
        elif event.key == "l":
            if self.template_list.has_focus_within:
                # Trigger selection which will apply template and move focus
                self.template_list.query_one(ListView).action_select_cursor()
                event.prevent_default()
            elif self.company_list.has_focus_within:
                self.company_preview.focus()
                event.prevent_default()
