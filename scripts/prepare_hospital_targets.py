import csv
import math
import re
import typer
from pathlib import Path
from rich.console import Console
from rich.progress import track
from fuzzywuzzy import fuzz # type: ignore

# Setup
app = typer.Typer()
console = Console()

def meters_to_latlon(x: float, y: float) -> tuple[float, float]:
    """Converts Web Mercator (EPSG:3857) meters to Lat/Lon (EPSG:4326)."""
    lon = (x / 20037508.34) * 180
    lat = (y / 20037508.34) * 180
    lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
    return lat, lon

def parse_markdown_beds(md_path: Path) -> list[dict]:
    """Extracts {name, beds} from the markdown list."""
    hospitals = []
    with open(md_path, 'r') as f:
        for line in f:
            # Match: * Hospital Name (Location): 1,234 beds
            match = re.search(r'\*\s+(.*?)(?:\(.*\))?:\s+([\d,]+)\s+beds', line)
            if match:
                name = match.group(1).strip()
                beds = int(match.group(2).replace(',', ''))
                hospitals.append({"name": name, "beds": beds})
    return hospitals

@app.command()
def main(
    csv_path: Path = typer.Argument(..., help="Path to Structures...csv"),
    md_path: Path = typer.Argument(..., help="Path to largest-hospitals.md"),
    output_path: Path = typer.Argument(..., help="Path to save target_locations.csv"),
):
    """
    Merges Hospital CSV with Bed counts and converts coordinates to Lat/Lon.
    """
    if not csv_path.exists() or not md_path.exists():
        console.print("[bold red]Input files not found.[/bold red]")
        raise typer.Exit(1)

    # 1. Load Beds (High Value Targets)
    high_value_list = parse_markdown_beds(md_path)
    console.print(f"Loaded {len(high_value_list)} high-value hospitals from Markdown.")

    # 2. Stream CSV and Match
    matched_targets = []
    
    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        rows = list(reader) # Load all to memory (5k rows is fine)
    
    console.print(f"Loaded {len(rows)} rows from CSV. Matching...")

    # We only care about the high value ones for now? 
    # Or do we want ALL hospitals, but prioritized?
    # Let's try to find matches for our high_value_list in the CSV to get their coords.
    
    for target in track(high_value_list, description="Matching hospitals..."):
        best_match = None
        best_score = 0
        
        target_name_clean = target['name'].lower().replace('hospital', '').replace('center', '').strip()

        for row in rows:
            row_name = row['Name']
            row_name_clean = row_name.lower().replace('hospital', '').replace('center', '').strip()
            
            # Simple checks first
            if target_name_clean in row_name_clean:
                score = 90
            else:
                score = fuzz.token_set_ratio(target['name'], row['Name'])
            
            if score > best_score:
                best_score = score
                best_match = row
        
        if best_score > 85 and best_match:
            # Found a match!
            try:
                x = float(best_match['x'])
                y = float(best_match['y'])
                lat, lon = meters_to_latlon(x, y)
                
                matched_targets.append({
                    "name": target['name'], # Use our clean name
                    "csv_name": best_match['Name'],
                    "beds": target['beds'],
                    "lat": lat,
                    "lon": lon,
                    "city": best_match['City'],
                    "state": best_match['State']
                })
            except ValueError:
                pass
        else:
            # console.print(f"[dim]No match for {target['name']} (Best: {best_score})[/dim]")
            pass

    # 3. Save
    matched_targets.sort(key=lambda x: x['beds'], reverse=True)
    
    with open(output_path, 'w', newline='') as f:
        fieldnames = ["name", "beds", "lat", "lon", "city", "state", "csv_name"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_targets)

    console.print(f"[bold green]Successfully generated targets for {len(matched_targets)} hospitals.[/bold green]")
    console.print(f"Saved to: {output_path}")

if __name__ == "__main__":
    app()
