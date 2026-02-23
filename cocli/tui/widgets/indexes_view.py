# POLICY: frictionless-data-policy-enforcement
from typing import Any, Optional, TYPE_CHECKING, cast
import logging
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static
from rich.table import Table


if TYPE_CHECKING:
    from ..app import CocliApp

logger = logging.getLogger(__name__)

INDEXES_METADATA = {
    "gm_prospects": {
        "label": "Google Maps Prospects",
        "description": "Consolidated index of all scraped Google Maps leads.",
        "model": "GoogleMapsProspect"
    },
    "email_index": {
        "label": "Email Index",
        "description": "Unified index of all discovered email addresses.",
        "model": "EmailEntry"
    },
    "domain_index": {
        "label": "Domain Index",
        "description": "Index mapping domains to company discovery status.",
        "model": "DomainEntry"
    },
    "lifecycle": {
        "label": "Lifecycle Index",
        "description": "Tracks scrape and enrichment timestamps for all entities.",
        "model": "LifecycleEntry"
    },
    "exclusions": {
        "label": "Exclusion Index",
        "description": "Global and campaign-specific ignore lists.",
        "model": "ExclusionEntry"
    }
}

class IndexSelection(ListView):
    """Sidebar list for selecting an index to view."""
    def compose(self) -> ComposeResult:
        for idx_id, meta in INDEXES_METADATA.items():
            yield ListItem(Label(meta['label']), id=f"idx_{idx_id}")

class IndexDetail(VerticalScroll):
    """Detailed view for a specific system index."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_index: Optional[str] = None
        self.can_focus = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="index_header"):
            yield Label("Select an index to view details.", id="index_title")
        
        with Vertical(classes="panel", id="index_info_panel"):
            yield Label("INDEX METADATA", classes="panel-header")
            yield Static(id="index_info_content", classes="panel-content")

    def update_detail(self, index_id: str) -> None:
        meta = INDEXES_METADATA.get(index_id)
        if not meta:
            return
        
        self.active_index = index_id
        self.query_one("#index_title", Label).update(f"INDEX: {meta['label'].upper()}")
        
        app = cast("CocliApp", self.app)
        campaign = app.services.reporting_service.campaign_name
        
        # Fetch Stats from Service
        stats = app.services.reporting_service.get_index_stats(campaign)
        idx_stats = stats.get(index_id, {"count": 0, "path": "N/A"})
        
        # Metadata Table
        info_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        info_table.add_column("Key", style="dim cyan", width=20)
        info_table.add_column("Value", style="white")
        
        info_table.add_row("Description", meta['description'])
        info_table.add_row("Model Class", meta['model'])
        info_table.add_row("Record Count", str(idx_stats['count']))
        info_table.add_row("Local Path", f"[bold green]data/{idx_stats['path']}[/]")
        
        self.query_one("#index_info_content", Static).update(info_table)
