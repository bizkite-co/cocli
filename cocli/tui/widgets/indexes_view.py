# POLICY: frictionless-data-policy-enforcement
from typing import Any, Optional, TYPE_CHECKING, cast
import logging
import json
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Label, ListView, ListItem, Static
from rich.table import Table
from rich.panel import Panel
from ...core.paths import paths


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
        "description": "[bold yellow][shared][/bold yellow] Index mapping domains to company discovery status.",
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
        with Horizontal(id="index_header", classes="pane-header"):
            yield Label("Select an index to view details.", id="index_title")
        
        with Vertical(classes="panel", id="index_info_panel"):
            yield Label("INDEX METADATA", classes="panel-header")
            yield Static(id="index_info_content", classes="panel-content")
        
        yield Vertical(id="index_dynamic_content")

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

        # 2. Dynamic Sections (Schema, Execution Journal)
        dynamic_content = self.query_one("#index_dynamic_content", Vertical)
        dynamic_content.remove_children()

        # A. Execution Journal (Merges Plan + Latest Run)
        try:
            # Determine Op and Index context
            idx_name = index_id.replace("idx_", "").replace("email_index", "emails").replace("gm_prospects", "google_maps_prospects")
            op_id = f"op_compact_{index_id.replace('idx_', '').replace('gm_', '').replace('_index', '')}"
            op = app.services.operation_service.get_details(op_id)
            
            run_dir = paths.campaign(campaign).index(idx_name).runs
            latest_run: Optional[Path] = None
            if run_dir.exists():
                runs = sorted([p for p in run_dir.glob("*.usv")], key=lambda p: p.name, reverse=True)
                if runs:
                    latest_run = runs[0]

            if op and op.steps:
                # Load latest statuses if log exists
                step_statuses = {}
                step_details = {}
                if latest_run:
                    from cocli.core.constants import UNIT_SEP
                    with open(latest_run, "r") as f:
                        next(f) # Skip header
                        for line in f:
                            if UNIT_SEP in line:
                                parts = line.strip().split(UNIT_SEP)
                                if len(parts) >= 3:
                                    s_name, s_status, s_det = parts[1], parts[2], parts[3] if len(parts)>3 else ""
                                    step_statuses[s_name] = s_status
                                    step_details[s_name] = s_det

                journal_table = Table(box=None, show_header=True, padding=(0, 1))
                journal_table.add_column("Step", style="white", width=25)
                journal_table.add_column("Status", style="bold", width=12)
                journal_table.add_column("Notes", style="dim")
                
                for step in op.steps:
                    status = step_statuses.get(step.name, "pending")
                    details = step_details.get(step.name, "")
                    
                    if status == "success":
                        marker = "[green]✔ success[/]"
                    elif status == "failed":
                        marker = "[red]✘ failed[/]"
                    else:
                        marker = "[dim]○ pending[/]"
                    
                    journal_table.add_row(step.description, marker, details)
                
                title = "Execution Journal"
                if latest_run:
                    title += f" (Last Run: {latest_run.stem.split('_')[0]})"
                
                dynamic_content.mount(Static(Panel(journal_table, title=title, border_style="blue" if latest_run else "yellow")))
            else:
                dynamic_content.mount(Static(Panel("No maintenance operations defined for this index.", title="Execution Journal", border_style="dim")))
        except Exception as e:
            logger.error(f"Error loading journal: {e}")
            dynamic_content.mount(Static(Panel(f"Failed to load journal: {e}", title="Execution Journal", border_style="red")))

        # B. Schema (Datapackage Fields)
        try:
            # Derive DP path
            dp_path = paths.root / idx_stats.get('path', '').replace(idx_stats.get('path', '').split('/')[-1], 'datapackage.json')
            if not dp_path.exists() and "google_maps_prospects" in str(dp_path):
                 dp_path = paths.campaign(campaign).index("google_maps_prospects").datapackage
            
            if dp_path.exists():
                with open(dp_path, "r") as f:
                    dp = json.load(f)
                    fields = dp.get("resources", [{}])[0].get("schema", {}).get("fields", [])
                    schema_table = Table(box=None, padding=(0, 1), show_header=True)
                    schema_table.add_column("Field", style="bold white")
                    schema_table.add_column("Type", style="dim cyan")
                    schema_table.add_column("Description", style="dim")
                    for field in fields[:15]:
                        schema_table.add_row(field.get("name"), field.get("type"), field.get("description", ""))
                    if len(fields) > 15:
                        schema_table.add_row("...", f"+{len(fields)-15} more fields", "")
                    dynamic_content.mount(Static(Panel(schema_table, title="Schema (datapackage.json)", border_style="dim white")))
        except Exception:
            pass
