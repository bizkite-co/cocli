from textual.app import ComposeResult
from textual.containers import Horizontal, Container
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
        # Use call_after_refresh to ensure focus happens AFTER the company_list 
        # has reacted to the template change (e.g. started loading)
        self.call_after_refresh(self.action_focus_companies)

    @on(CompanyList.CompanyHighlighted)
    def on_company_highlighted(self, message: CompanyList.CompanyHighlighted) -> None:
        self.company_preview.update_preview(message.company)

    def action_focus_template(self) -> None:
        self.template_list.focus_list()

    def action_reset_view(self) -> None:
        """Fully resets the search view and returns to template selection."""
        # Suppress input-changed events during reset to prevent focus stealing
        self.company_list._ignoring_input_change = True
        try:
            from textual.widgets import Input
            search_input = self.company_list.query_one("#company_search_input", Input)
            search_input.value = ""
        finally:
            self.company_list._ignoring_input_change = False
        
        self.template_list.focus_list()

    def action_focus_companies(self) -> None:
        self.company_list.query_one("#company_list_view").focus()

    def action_focus_search(self) -> None:
        self.company_list.action_focus_search()

    def on_key(self, event: events.Key) -> None:
        if event.key == "h":
            if self.company_list.query_one("#company_list_view").has_focus:
                self.template_list.focus_list()
                event.stop()
                event.prevent_default()
                return
            elif self.template_list.query_one("#template_list").has_focus:
                # Already at the trunk of this view, let it bubble if needed
                pass
        elif event.key == "l":
            if self.template_list.has_focus_within:
                # Trigger selection which will apply template and move focus
                from textual.widgets import ListView
                self.template_list.query_one(ListView).action_select_cursor()
                event.prevent_default()
            elif self.company_list.query_one("#company_list_view").has_focus:
                # Enter detail view
                self.company_list.query_one("#company_list_view").action_select_cursor() # type: ignore
                event.prevent_default()
