import typer
import csv
import logging
from typing import Dict # Added cast
import toml
from collections import defaultdict
from rich.console import Console

from cocli.core.scrape_index import ScrapeIndex, ScrapedArea
from cocli.core.config import get_campaign_dir, get_campaign_scraped_data_dir, get_campaign

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

def point_in_rect(lat: float, lon: float, bounds: Dict[str, float]) -> bool:
    return (bounds['lat_min'] <= lat <= bounds['lat_max'] and 
            bounds['lon_min'] <= lon <= bounds['lon_max'])

@app.command()
def main(campaign_name_arg: str = typer.Argument(None, help="Campaign name. Defaults to current context.")) -> None:
    """
    Backfills 'items_found' for scraped areas that have 0 items, using local prospects data.
    """
    campaign_name: str
    if not campaign_name_arg:
        current_campaign = get_campaign()
        if not current_campaign:
            console.print("[bold red]Error: No campaign specified and no current context set.[/bold red]")
            raise typer.Exit(1)
        campaign_name = current_campaign
    else:
        campaign_name = campaign_name_arg
    

    console.print(f"[bold]Backfilling item counts for campaign: '{campaign_name}'[/bold]")

    # 1. Load Prospects
    prospects_csv = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"
    if not prospects_csv.exists():
        console.print(f"[red]No prospects.csv found for campaign {campaign_name}[/red]")
        raise typer.Exit(1)

    prospects_by_phrase = defaultdict(list)
    total_prospects = 0
    
    with open(prospects_csv, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            phrase = row.get('Keyword')
            lat_str = row.get('Latitude')
            lon_str = row.get('Longitude')
            
            if phrase and lat_str and lon_str:
                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                    prospects_by_phrase[phrase].append((lat, lon))
                    total_prospects += 1
                except ValueError:
                    continue

    console.print(f"[green]Loaded {total_prospects} prospects across {len(prospects_by_phrase)} phrases.[/green]")

    # 2. Load Scraped Areas for Campaign Phrases
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)
        
    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    search_phrases = config.get("prospecting", {}).get("queries", [])
    
    scrape_index = ScrapeIndex()
    # We load ALL areas for these phrases because we want to update the master index
    # Note: get_all_areas_for_phrases returns a flat list, but we need to group by phrase to save later.
    
    updated_areas_count = 0
    
    for phrase in search_phrases:
        areas = scrape_index._load_areas_for_phrase(phrase)
        if not areas:
            continue
            
        phrase_prospects = prospects_by_phrase.get(phrase, [])
        if not phrase_prospects:
            continue
            
        modified_areas = []
        updates_for_phrase = 0
        
        for area in areas:
            # We only backfill if items_found is 0 
            # (or maybe small numbers? But user said 0 specifically)
            if area.items_found == 0:
                # Count prospects in this box
                # Area bounds keys: lat_min, lat_max, lon_min, lon_max
                count = 0
                bounds = {
                    'lat_min': area.lat_min,
                    'lat_max': area.lat_max,
                    'lon_min': area.lon_min,
                    'lon_max': area.lon_max
                }
                
                for p_lat, p_lon in phrase_prospects:
                    if point_in_rect(p_lat, p_lon, bounds):
                        count += 1
                
                if count > 0:
                    # Create new updated area tuple
                    # ScrapedArea is a NamedTuple, so it's immutable. Replace fields.
                    # Fields: phrase, scrape_date, lat_min, lat_max, lon_min, lon_max, lat_miles, lon_miles, items_found
                    new_area = ScrapedArea(
                        phrase=area.phrase,
                        scrape_date=area.scrape_date,
                        lat_min=area.lat_min,
                        lat_max=area.lat_max,
                        lon_min=area.lon_min,
                        lon_max=area.lon_max,
                        lat_miles=area.lat_miles,
                        lon_miles=area.lon_miles,
                        items_found=count # UPDATE HERE
                    )
                    modified_areas.append(new_area)
                    updates_for_phrase += 1
                else:
                    modified_areas.append(area)
            else:
                modified_areas.append(area)
        
        if updates_for_phrase > 0:
            console.print(f"Updating {updates_for_phrase} areas for phrase '{phrase}'...")
            scrape_index._save_areas_for_phrase(phrase, modified_areas)
            updated_areas_count += updates_for_phrase

    console.print(f"[bold green]Backfill complete. Updated {updated_areas_count} scraped areas.[/bold green]")

if __name__ == "__main__":
    app()
