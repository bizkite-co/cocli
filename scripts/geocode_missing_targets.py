import toml
import csv
from pathlib import Path
from geopy.geocoders import Nominatim  # type: ignore
from geopy.exc import GeocoderServiceError  # type: ignore
from rich.console import Console
import sys

console = Console()

def geocode_missing(campaign_name: str = "turboship") -> None:
    data_home = Path("/home/mstouffer/repos/company-cli/data")
    campaign_dir = data_home / "campaigns" / campaign_name
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        return

    with open(config_path, "r") as f:
        config = toml.load(f)
    
    prospecting = config.get("prospecting", {})
    locations = prospecting.get("locations", [])
    target_csv_name = prospecting.get("target-locations-csv", "target_locations.csv")
    csv_path = campaign_dir / target_csv_name

    if not locations:
        console.print("[yellow]No locations found in config.toml to geocode.[/yellow]")
        return

    # Load existing CSV to avoid duplicates
    existing_names = set()
    fieldnames = ["name", "beds", "lat", "lon", "city", "state", "csv_name", "saturation_score", "company_slug"]
    rows = []
    
    if csv_path.exists():
        with open(csv_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames) if reader.fieldnames else fieldnames
            for row in reader:
                existing_names.add(row["name"])
                rows.append(row)

    geolocator = Nominatim(user_agent="cocli_geocoder")
    new_locations_added = 0

    for loc_name in locations:
        if loc_name in existing_names:
            console.print(f"[dim]Skipping {loc_name}, already in CSV.[/dim]")
            continue
        
        try:
            console.print(f"Geocoding: [bold cyan]{loc_name}[/bold cyan]...")
            location = geolocator.geocode(loc_name)
            if location:
                # Try to parse city/state
                city = loc_name.split(",")[0].strip()
                state = loc_name.split(",")[1].strip() if "," in loc_name else ""
                
                new_row = {fn: "" for fn in fieldnames}
                new_row.update({
                    "name": loc_name,
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "city": city,
                    "state": state
                })
                rows.append(new_row)
                new_locations_added += 1
                console.print(f"  [green]Found: {location.latitude}, {location.longitude}[/green]")
            else:
                console.print(f"  [yellow]Could not find coordinates for {loc_name}[/yellow]")
        except GeocoderServiceError as e:
            console.print(f"  [red]Error geocoding {loc_name}: {e}[/red]")

    if new_locations_added > 0:
        # Save CSV
        rows.sort(key=lambda x: x["name"])
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        # Remove from config.toml
        # config["prospecting"]["locations"] = [] # Optional: clear it?
        # with open(config_path, "w") as f:
        #     toml.dump(config, f)
            
        console.print(f"[bold green]Successfully added {new_locations_added} locations to {csv_path.name}[/bold green]")
    else:
        console.print("[yellow]No new locations were added.[/yellow]")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "turboship"
    geocode_missing(campaign)
