from transitions import Machine
from pathlib import Path
from typing import List, Dict, Any, cast
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
            return cast(str, config.get("campaign", {}).get("current_state", "idle"))
        return "idle"

    def _save_current_state(self) -> None:
        if self.config_path.exists():
            config = toml.load(self.config_path)
        else:
            config = {}
        
        if "campaign" not in config:
            config["campaign"] = {}
        config["campaign"]["current_state"] = self.state
        
        with open(self.config_path, "w") as f:
            toml.dump(config, f)

    def on_enter_state(self, event: Any) -> None:
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

    def set_campaign_context(self) -> None:
        set_campaign(self.name)
        console.print(f"[green]Campaign context set to:[/] [bold]{self.name}[/]")

    def run_import_customers(self) -> None:
        console.print(f"[bold blue]Running customer import for campaign: {self.name}[/bold blue]")
        # Placeholder for actual import customer logic
        # This would call a command like cocli import-customers
        # For now, we'll just transition to the next state
        console.print("[bold yellow]Customer import logic not yet implemented. Transitioning to prospecting.[/bold yellow]")
        self.start_prospecting()  # type: ignore

    def run_prospecting_scrape(self) -> None:
        from ..commands.campaign import pipeline
        from ..models.company import Company
        from ..core.location_prospects_index import LocationProspectsIndex
        import asyncio
        import toml

        console.print(f"[bold blue]Running prospecting scrape for campaign: {self.name}[/bold blue]")

        campaign_dir = self._get_campaign_config_path(self.name).parent
        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            console.print(f"[bold red]Configuration file not found for campaign '{self.name}'.[/bold red]")
            self.fail_campaign()  # type: ignore
            return

        with open(config_path, "r") as f:
            config = toml.load(f)
        prospecting_config = config.get("prospecting", {})
        locations = prospecting_config.get("locations", [])
        search_phrases = prospecting_config.get("queries", [])
        zoom_out_button_selector = prospecting_config.get("zoom-out-button-selector", "div#zoomOutButton")
        panning_distance_miles = prospecting_config.get("panning-distance-miles", 8)
        initial_zoom_out_level = prospecting_config.get("initial-zoom-out-level", 3)
        omit_zoom_feature = prospecting_config.get("omit-zoom-feature", False)

        if not locations or not search_phrases:
            console.print("[bold red]No locations or queries found in the prospecting configuration.[/bold red]")
            self.fail_campaign()  # type: ignore
            return

        existing_domains = {c.domain for c in Company.get_all() if c.domain}
        location_prospects_index = LocationProspectsIndex(campaign_name=self.name)

        try:
            asyncio.run(
                pipeline(
                    locations=locations,
                    search_phrases=search_phrases,
                    goal_emails=10,  # Default goal, can be made configurable
                    headed=False,
                    devtools=False,
                    campaign_name=self.name,
                    zoom_out_button_selector=zoom_out_button_selector,
                    panning_distance_miles=panning_distance_miles,
                    initial_zoom_out_level=initial_zoom_out_level,
                    omit_zoom_feature=omit_zoom_feature,
                    force=False,
                    ttl_days=30,  # Default, can be made configurable
                    debug=False,
                    existing_domains=existing_domains,
                    console=console,
                    browser_width=2000,
                    browser_height=1500,
                    location_prospects_index=location_prospects_index,
                )
            )
            self.finish_scraping()  # type: ignore
        except typer.Exit:
            console.print("[bold red]Scraping failed.[/bold red]")
            self.fail_campaign()  # type: ignore
        except Exception:
            console.print("[bold red]An unexpected error occurred during scraping.[/bold red]")
            self.fail_campaign()  # type: ignore

    def run_prospecting_ingest(self) -> None:
        from ..commands.ingest_google_maps_csv import google_maps_csv_to_google_maps_cache
        console.print(f"[bold blue]Running prospecting ingest for campaign: {self.name}[/bold blue]")
        try:
            google_maps_csv_to_google_maps_cache(campaign_name=self.name)
            self.finish_ingesting()  # type: ignore
        except typer.Exit:
            self.fail_campaign()  # type: ignore
        except Exception:
            self.fail_campaign()  # type: ignore

    def run_prospecting_import(self) -> None:
        from ..commands.import_companies import google_maps_cache_to_company_files
        console.print(f"[bold blue]Running prospecting import for campaign: {self.name}[/bold blue]")
        try:
            google_maps_cache_to_company_files(campaign_name=self.name)
            self.finish_prospecting_import()  # type: ignore
        except typer.Exit:
            self.fail_campaign()  # type: ignore
        except Exception:
            self.fail_campaign()  # type: ignore

    def log_failure(self) -> None:
        console.print(f"[bold red]Campaign '{self.name}' failed in state: {self.state}[/bold red]")
        # Here you might add more detailed logging or notification logic