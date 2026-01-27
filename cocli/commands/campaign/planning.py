import typer
import csv
import toml
import logging
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console
from datetime import datetime

from ...core.config import get_campaign_dir, get_people_dir, get_campaign
from ...models.person import Person
from ...core.text_utils import slugify
from ...core.importing import import_prospect
from ...core.prospects_csv_manager import ProspectsIndexManager
from ...core.scrape_index import ScrapeIndex
from ...planning.generate_grid import export_to_kml, DEFAULT_GRID_STEP_DEG, get_campaign_grid_tiles

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)

@app.command(name="import-contacts")
def import_contacts(
    csv_path: Path = typer.Argument(..., help="Path to the CSV file containing contacts."),
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to import contacts into. If not provided, uses the current campaign context."),
) -> None:
    """
    Imports contacts from a CSV file into a campaign.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    contacts_dir = campaign_dir / "contacts"
    contacts_dir.mkdir(exist_ok=True)
    people_dir = get_people_dir()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                person = Person.model_validate(row)
                person_slug = slugify(person.name)
                person_dir = people_dir / person_slug
                person_dir.mkdir(exist_ok=True)

                person_file = person_dir / f"{person_slug}.md"
                with open(person_file, "w") as pf:
                    pf.write("---")
                    yaml.dump(person.model_dump(exclude_none=True), pf, sort_keys=False, default_flow_style=False, allow_unicode=True)
                    pf.write("---")

                symlink_path = contacts_dir / person_slug
                if not symlink_path.exists():
                    symlink_path.symlink_to(person_dir)
                
                console.print(f"[green]Imported contact:{person.name}[/green]") 

            except Exception as e:
                console.print(f"[bold red]Error importing contact: {e}[/bold red]")

@app.command()
def import_prospects(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to import prospects for. If not provided, uses the current campaign context."),
) -> None:
    """
    Imports prospects from a campaign's prospects.csv into the canonical company structure.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    console.print(f"[bold]Importing prospects for campaign: '{campaign_name}'[/bold]")

    csv_manager = ProspectsIndexManager(campaign_name)
    prospects = list(csv_manager.read_all_prospects())

    if not prospects:
        console.print(f"[bold red]No prospects found (or file missing) for campaign: {campaign_name}[/bold red]")
        raise typer.Exit(code=1)

    console.print("[dim]Building map of existing companies...[/dim]")
    new_companies_imported = 0
    
    for prospect_data in prospects:
        new_company = import_prospect(prospect_data, campaign=campaign_name)
        if new_company:
            console.print(f"[green]Imported new prospect:{new_company.name}[/green]") 
            new_companies_imported += 1

    console.print(f"[bold green]Import complete. Added {new_companies_imported} new companies.[/bold green]")

@app.command(name="generate-grid")
def generate_grid(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. If not provided, uses the current campaign context."),
    proximity_miles: float = typer.Option(10.0, "--proximity", help="Radius in miles to generate grid around each target location."),
) -> None:
    """
    Generates a 0.1-degree aligned scrape grid for each target location in the campaign.
    Exports KML and JSON plans to the campaign's exports/ directory.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    # Load Config
    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    prospecting_config = config.get("prospecting", {})

    # Use proximity from config if not provided on CLI
    if proximity_miles == 10.0 and "proximity" in prospecting_config:
        proximity_miles = float(prospecting_config["proximity"])

    console.print(f"[bold]Generating planning grids for campaign: '{campaign_name}' (Radius: {proximity_miles} mi)[/bold]")

    target_locations_csv = prospecting_config.get("target-locations-csv")

    target_locations: List[Dict[str, Any]] = []
    if target_locations_csv:
        csv_path = Path(target_locations_csv)
        if not csv_path.is_absolute():
            csv_path = campaign_dir / csv_path
        
        if csv_path.exists():
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Try various field names
                        name = row.get("name") or row.get("city")
                        lat = row.get("lat")
                        lon = row.get("lon")
                        
                        if name and lat and lon and lat.strip() and lon.strip():
                            target_locations.append({
                                "name": str(name),
                                "lat": float(lat),
                                "lon": float(lon)
                            })
                if target_locations:
                    console.print(f"[green]Loaded {len(target_locations)} target locations from {csv_path.name}[/green]")
            except Exception as e:
                logger.error(f"Error reading target locations CSV: {e}")
                # Don't raise, try fallback to 'locations' list

    # Fallback to geocoding the 'locations' list if needed
    config_locations = prospecting_config.get("locations", [])
    if config_locations:
        from geopy.geocoders import Nominatim # type: ignore
        from geopy.exc import GeocoderServiceError # type: ignore
        geolocator = Nominatim(user_agent="cocli")
        
        for loc_name in config_locations:
            # Skip if already loaded from CSV
            if any(loc["name"] == loc_name for loc in target_locations):
                continue
                
            try:
                console.print(f"[dim]Geocoding: {loc_name}...[/dim]")
                location = geolocator.geocode(loc_name)
                if location:
                    target_locations.append({
                        "name": loc_name,
                        "lat": location.latitude,
                        "lon": location.longitude
                    })
                    console.print(f"[green]  Found: {location.latitude}, {location.longitude}[/green]")
                else:
                    console.print(f"[yellow]  Could not geocode: {loc_name}[/yellow]")
            except GeocoderServiceError as e:
                console.print(f"[red]  Geocoding error for {loc_name}: {e}[/red]")

    if not target_locations:
        console.print("[yellow]No valid target locations found.[/yellow]")
        return

    export_dir = campaign_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    unique_tiles = get_campaign_grid_tiles(campaign_name, target_locations=target_locations)
    kml_path = export_dir / "target-areas.kml"
    
    export_to_kml(unique_tiles, str(kml_path), f"{campaign_name} - All Targets", color="08ffffff")
    
    console.print("[bold green]Grid generation complete.[/bold green]")
    console.print(f"  Tiles: {len(unique_tiles)}")

@app.command(name="coverage-gap")
def coverage_gap(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. If not provided, uses the current campaign context."),
    output_csv: Optional[Path] = typer.Option(None, "--output", help="Path to save the CSV report."),
) -> None:
    """
    Generates a report matching every target area to its most recent scrape date.
    Helps identify gaps in campaign coverage.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
        if campaign_name is None:
            logger.error("Error: No campaign name provided and no campaign context is set.")
            raise typer.Exit(code=1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(1)

    target_tiles = get_campaign_grid_tiles(campaign_name)
    if not target_tiles:
         console.print(f"[bold red]No target tiles found for campaign '{campaign_name}'.[/bold red]")
         raise typer.Exit(1)
    
    console.print(f"[bold]Analyzing coverage for {len(target_tiles)} target tiles in '{campaign_name}'...[/bold]")

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    search_phrases = config.get("prospecting", {}).get("queries", [])
    
    scrape_index = ScrapeIndex()
    report_data = []
    scraped_count = 0
    
    for tile in target_tiles:
        lat = tile.get("center_lat") or tile.get("center", {}).get("lat")
        lon = tile.get("center_lon") or tile.get("center", {}).get("lon")
        tile_id = tile.get("id")
        
        if lat is None or lon is None:
            continue
            
        step = DEFAULT_GRID_STEP_DEG
        half_step = step / 2.0
        bounds = {
            "lat_min": float(lat) - half_step,
            "lat_max": float(lat) + half_step,
            "lon_min": float(lon) - half_step,
            "lon_max": float(lon) + half_step
        }
        
        latest_date: Optional[datetime] = None
        matching_phrase: Optional[str] = None
        
        for phrase in search_phrases:
            match = scrape_index.is_area_scraped(phrase, bounds, overlap_threshold_percent=90.0)
            if match:
                scraped_area, _ = match
                if latest_date is None or scraped_area.scrape_date > latest_date:
                    latest_date = scraped_area.scrape_date
                    matching_phrase = phrase
        
        if latest_date:
            scraped_count += 1
            
        report_data.append({
            "tile_id": tile_id,
            "latitude": lat,
            "longitude": lon,
            "status": "SCRAPED" if latest_date else "MISSING",
            "last_scrape": latest_date.strftime('%Y-%m-%d %H:%M') if latest_date else "N/A",
            "phrase": matching_phrase or "N/A"
        })

    import pandas as pd
    df = pd.DataFrame(report_data)
    coverage_pct = (scraped_count / len(target_tiles)) * 100 if target_tiles else 0
    console.print(f"Coverage: [bold cyan]{scraped_count}/{len(target_tiles)}[/bold cyan] tiles ([bold]{coverage_pct:.1f}%[/bold])")

    if output_csv:
        df.to_csv(output_csv, index=False)
        console.print(f"[green]Report saved to: {output_csv}[/green]")
    else:
        missing = df[df["status"] == "MISSING"].head(10)
        if not missing.empty:
            console.print("\n[yellow]Example Missing Tiles:[/yellow]")
            console.print(missing[["tile_id", "latitude", "longitude"]])
