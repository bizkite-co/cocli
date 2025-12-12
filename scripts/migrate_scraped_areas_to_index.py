
import csv
import json
import logging
import math
from pathlib import Path
from datetime import datetime, UTC
import typer
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_scraped_areas_index_dir

app = typer.Typer()
console = Console()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_grid_key(lat: float, lon: float) -> str:
    """Returns the grid key for spatial partitioning (1x1 degree) using floor."""
    return f"lat{math.floor(lat)}_lon{math.floor(lon)}"

def migrate_phrase_csv(csv_path: Path, phrase_slug: str) -> int:
    """Migrates a single phrase CSV to the new index structure."""
    
    base_dir = get_scraped_areas_index_dir()
    phrase_dir = base_dir / phrase_slug
    phrase_dir.mkdir(parents=True, exist_ok=True)
    
    count = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Parse data
                scrape_date_str = row['scrape_date']
                try:
                    scrape_date = datetime.fromisoformat(scrape_date_str)
                    if scrape_date.tzinfo is None:
                        scrape_date = scrape_date.replace(tzinfo=UTC)
                except ValueError:
                    scrape_date = datetime.now(UTC)

                lat_min = float(row['lat_min'])
                lat_max = float(row['lat_max'])
                lon_min = float(row['lon_min'])
                lon_max = float(row['lon_max'])
                lat_miles = float(row['lat_miles'])
                lon_miles = float(row['lon_miles'])
                items_found = int(row.get('items_found', 0))

                # Partition by bottom-left corner
                grid_key = get_grid_key(lat_min, lon_min)
                grid_dir = phrase_dir / grid_key
                grid_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename with bounds for "metadata-only" scanning
                # Format: {lat_min}_{lat_max}_{lon_min}_{lon_max}.json
                # We use 5 decimal places for ~1m precision
                filename = f"{lat_min:.5f}_{lat_max:.5f}_{lon_min:.5f}_{lon_max:.5f}.json"
                file_path = grid_dir / filename
                
                # Construct JSON payload
                data = {
                    "phrase": phrase_slug,
                    "scrape_date": scrape_date.isoformat(),
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                    "lat_miles": lat_miles,
                    "lon_miles": lon_miles,
                    "items_found": items_found
                }
                
                with open(file_path, 'w', encoding='utf-8') as outfile:
                    json.dump(data, outfile)
                
                count += 1
                
            except Exception as e:
                logger.error(f"Error migrating row in {csv_path.name}: {e}")
                continue
                
    return count

@app.command()
def main(delete_old: bool = False) -> None:
    """
    Migrates scraped_areas CSVs to partitioned JSON files.
    Structure: indexes/scraped_areas/{phrase}/lat{int}_lon{int}/{bounds}.json
    """
    index_dir = get_scraped_areas_index_dir()
    
    # Only migrate CSVs
    csv_files = list(index_dir.glob("*.csv"))
    console.print(f"Found {len(csv_files)} CSV files to migrate in {index_dir}")
    
    total_records = 0
    
    for csv_file in track(csv_files, description="Migrating CSVs..."):
        if csv_file.name == "wilderness_areas.csv":
            phrase_slug = "wilderness"
        else:
            phrase_slug = csv_file.stem 
        
        records = migrate_phrase_csv(csv_file, phrase_slug)
        total_records += records
        console.print(f"  Migrated {csv_file.name}: {records} records")
        
        if delete_old:
            csv_file.unlink()
            console.print(f"  Deleted {csv_file.name}")

    console.print(f"[bold green]Migration Complete! Total records: {total_records}[/bold green]")

if __name__ == "__main__":
    app()
