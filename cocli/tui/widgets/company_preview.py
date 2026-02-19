from typing import Any
from textual.widgets import Static, Label
from textual.containers import VerticalScroll, Container, Horizontal
from rich.markup import escape
from cocli.models.company import Company
from textual.app import ComposeResult
from .phone import Phone
from .email import Email

class CompanyPreview(Container):
    """A widget to display a preview of a company."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Capture initial widgets to mount in preview_content later
        self._initial_widgets = args
        super().__init__(**kwargs)
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield Label("PREVIEW", id="preview_header", classes="pane-header")
        yield VerticalScroll(id="preview_content")

    def on_mount(self) -> None:
        if self._initial_widgets:
            content = self.query_one("#preview_content", VerticalScroll)
            content.mount(*self._initial_widgets)

    def update_preview(self, company: Company) -> None:
        """Update the preview with the given company."""
        content = self.query_one("#preview_content", VerticalScroll)
        content.remove_children()
        
        # Location info
        location = f"{company.city or 'N/A'}, {company.state or 'N/A'}"
        
        # Rating info
        rating_str = f"{company.average_rating or 'N/A'} ({company.reviews_count or 0} reviews)"

        # Lifecycle dates
        scraped_at = company.list_found_at.strftime('%Y-%m-%d') if company.list_found_at else "N/A"
        details_at = company.details_found_at.strftime('%Y-%m-%d') if company.details_found_at else "N/A"
        
        if company.last_enriched:
            enriched_str = f"[bold green]{company.last_enriched.strftime('%Y-%m-%d')}[/]"
        else:
            enriched_str = "[bold yellow]No[/]"

        content.mount(
            Static(f"[b]Name:[/b] {escape(company.name)}"),
            Static(f"[b]Domain:[/b] {escape(str(company.domain or 'N/A'))}"),
            Static(f"[b]Type:[/b] {escape(company.type)}"),
            Static(f"[b]Location:[/b] {escape(location)}"),
            Static(f"[b]Rating:[/b] {escape(rating_str)}"),
            Horizontal(
                Label("[b]Phone:[/b] "),
                Phone(company.phone_number),
                classes="preview-line"
            ),
            Horizontal(
                Label("[b]Email:[/b] "),
                Email(company.email),
                classes="preview-line"
            ),
            Static(f"[b]Scraped:[/b] {scraped_at}"),
            Static(f"[b]Details:[/b] {details_at}"),
            Static(f"[b]Enriched:[/b] {enriched_str}"),
            Static(f"[b]Tags:[/b] {escape(', '.join(company.tags))}"),
            Static(f"\n[b]Description:[/b]\n{escape(str(company.description or ''))}"),
        )
