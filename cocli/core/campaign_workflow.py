from transitions import Machine
from pathlib import Path
from typing import List, Dict, Any
import toml
import typer

from ..core.config import set_campaign, get_campaign_dir
from rich.console import Console

console = Console()

class CampaignWorkflow:
    states = [
        'idle',
        'import_customers',
        'prospecting_scraping',
        'prospecting_ingesting',
        'prospecting_importing',
        'prospecting_enriching',
        'outreach',
        'completed',
        'failed'
    ]

    def _get_campaign_config_path(self, campaign_name: str) -> Path:
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
            raise typer.Exit(code=1)
        return campaign_dir / "config.toml"

    def _load_current_state(self) -> str:
        if self.config_path.exists():
            config = toml.load(self.config_path)
            return config.get("campaign", {}).get("current_state", "idle")
        return "idle"

    def _save_current_state(self):
        if self.config_path.exists():
            config = toml.load(self.config_path)
        else:
            config = {}
        
        if "campaign" not in config:
            config["campaign"] = {}
        config["campaign"]["current_state"] = self.state
        
        with open(self.config_path, "w") as f:
            toml.dump(config, f)

    def on_enter_state(self, event):
        self._save_current_state()
        console.print(f"[bold green]Campaign '{self.name}' entered state: {self.state}[/bold green]")

    def __init__(self, name: str):
        self.name = name
        self.config_path = self._get_campaign_config_path(name)
        self.state = self._load_current_state()

        transitions: List[Dict[str, Any]] = [
            { 'trigger': 'start_import', 'source': 'idle', 'dest': 'import_customers', 'before': 'set_campaign_context', 'after': 'run_import_customers' },
            { 'trigger': 'start_prospecting', 'source': ['idle', 'import_customers'], 'dest': 'prospecting_scraping', 'before': 'set_campaign_context', 'after': 'run_prospecting_scrape' },
            { 'trigger': 'finish_scraping', 'source': 'prospecting_scraping', 'dest': 'prospecting_ingesting', 'after': 'run_prospecting_ingest' },
            { 'trigger': 'finish_ingesting', 'source': 'prospecting_ingesting', 'dest': 'prospecting_importing', 'after': 'run_prospecting_import' },
            { 'trigger': 'finish_prospecting_import', 'source': 'prospecting_importing', 'dest': 'prospecting_enriching' }, # New sub-state
            { 'trigger': 'finish_enriching', 'source': 'prospecting_enriching', 'dest': 'outreach' }, # Exit prospecting phase
            { 'trigger': 'start_outreach', 'source': ['prospecting_importing', 'outreach'], 'dest': 'outreach' }, # Allow re-entering outreach
            { 'trigger': 'complete_campaign', 'source': '*', 'dest': 'completed' },
            { 'trigger': 'fail_campaign', 'source': '*', 'dest': 'failed', 'after': 'log_failure' }
        ]

        self.machine = Machine(model=self, states=CampaignWorkflow.states, transitions=transitions, initial=self.state)

    def set_campaign_context(self):
        set_campaign(self.name)
        console.print(f"[green]Campaign context set to:[/] [bold]{self.name}[/]")

    def run_import_customers(self):
        console.print(f"[bold blue]Running customer import for campaign: {self.name}[/bold blue]")
        # Placeholder for actual import customer logic
        # This would call a command like cocli import-customers
        # For now, we'll just transition to the next state
        console.print("[bold yellow]Customer import logic not yet implemented. Transitioning to prospecting.[/bold yellow]")
        self.start_prospecting()

    def run_prospecting_scrape(self):
        from ..commands.campaign import scrape_prospects
        console.print(f"[bold blue]Running prospecting scrape for campaign: {self.name}[/bold blue]")
        try:
            scrape_prospects(campaign_name=self.name)
            self.finish_scraping()
        except typer.Exit as e:
            console.print(f"[bold red]Scraping failed: {e.message}[/bold red]")
            self.fail_campaign()
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred during scraping: {e}[/bold red]")
            self.fail_campaign()

    def run_prospecting_ingest(self):
        from ..commands.ingest_google_maps_csv import google_maps_csv_to_google_maps_cache
        console.print(f"[bold blue]Running prospecting ingest for campaign: {self.name}[/bold blue]")
        try:
            google_maps_csv_to_google_maps_cache(campaign_name=self.name)
            self.finish_ingesting()
        except typer.Exit as e:
            console.print(f"[bold red]Ingestion failed: {e.message}[/bold red]")
            self.fail_campaign()
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred during ingestion: {e}[/bold red]")
            self.fail_campaign()

    def run_prospecting_import(self):
        from ..commands.import_companies import google_maps_cache_to_company_files
        console.print(f"[bold blue]Running prospecting import for campaign: {self.name}[/bold blue]")
        try:
            google_maps_cache_to_company_files(campaign_name=self.name)
            self.finish_prospecting_import()
        except typer.Exit as e:
            console.print(f"[bold red]Import failed: {e.message}[/bold red]")
            self.fail_campaign()
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred during import: {e}[/bold red]")
            self.fail_campaign()

    def log_failure(self):
        console.print(f"[bold red]Campaign '{self.name}' failed in state: {self.state}[/bold red]")
        # Here you might add more detailed logging or notification logic