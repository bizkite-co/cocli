from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.markup import escape
from cocli.models.company import Company

class CompanyPreview(VerticalScroll):
    """A widget to display a preview of a company."""

    def update_preview(self, company: Company) -> None:
        """Update the preview with the given company."""
        self.remove_children()
        self.mount(
            Static(f"[b]Name:[/b] {escape(company.name)}"),
            Static(f"[b]Domain:[/b] {escape(str(company.domain))}"),
            Static(f"[b]Type:[/b] {escape(company.type)}"),
            Static(f"[b]Tags:[/b] {escape(', '.join(company.tags))}"),
            Static(f"\n[b]Description:[/b]\n{escape(str(company.description))}"),
        )