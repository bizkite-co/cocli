import typer
import csv
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import track

from cocli.models.target_location import TargetLocation
from cocli.core.scrape_index import ScrapeIndex
from cocli.core.saturation_calculator import calculate_saturation_score
from cocli.core.config import get_campaign_dir

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer()

@app.command()
def main(
    campaign_name: str = typer.Argument(..., help="Name of the campaign."),
    csv_filename: str = typer.Option("target_locations.csv", "--csv", help="Filename of the target locations CSV within the campaign directory."),
    max_proximity: float = typer.Option(20.0, "--proximity", help="Max proximity in miles to consider for saturation."),
) -> None:
    """
    Calculates saturation scores for target locations based on scraped areas
    and updates the target locations CSV file.
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    csv_path = campaign_dir / csv_filename
    if not csv_path.exists():
        console.print(f"[bold red]CSV file not found: {csv_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Loading scraped areas...[/bold blue]")
    scrape_index = ScrapeIndex()
    scraped_areas = scrape_index.get_all_scraped_areas()
    console.print(f"Loaded {len(scraped_areas)} scraped areas.")

    console.print(f"[bold blue]Processing target locations from {csv_path.name}...[/bold blue]")
    
    updated_rows = []
    headers = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames) if reader.fieldnames else []
        
        # Ensure saturation_score is in headers
        if "saturation_score" not in headers:
            headers.append("saturation_score")
        
        # Ensure company_slug is in headers if we populate it (optional for now)
        if "company_slug" not in headers:
            headers.append("company_slug")

        rows = list(reader)
        for row in track(rows, description="Calculating scores..."):
            try:
                # Validate/Parse with Pydantic
                # We need to handle potential type conversions or defaults handled by Pydantic
                # Using 'construct' or 'model_validate'
                # Note: TargetLocation expects 'lat', 'lon' as floats. CSV gives strings.
                
                # We can't pass extra fields if extra='ignore'. 
                # So we filter or rely on Pydantic to ignore.
                target = TargetLocation.model_validate(row)
                
                # Calculate Score
                score = calculate_saturation_score(target, scraped_areas, max_proximity=max_proximity)
                target.saturation_score = round(score, 2)
                
                # Update row dict with new values
                # We use model_dump to get serialized values (rounded lat/lon)
                dumped = target.model_dump(by_alias=True)
                
                # Merge back into row to preserve any extra fields not in model (if any exist and we want to keep them)
                # But our model config says extra='ignore', so model_validate dropped them.
                # If we want to preserve unknown columns, we should have used a different approach.
                # Assuming the CSV structure is controlled by us and matches the model + extras we know.
                # User said: "preserve all existing columns".
                # My model defined all known columns. 
                # If there are truly unknown columns, I should update the model to extra='allow'.
                
                # Let's check model config again. I set extra='ignore'.
                # I should probably update model to extra='allow' in a previous step to be safe, 
                # or just merge `dumped` into `row`.
                row.update(dumped)
                updated_rows.append(row)
                
            except Exception as e:
                logger.error(f"Error processing row {row.get('name', 'UNKNOWN')}: {e}")
                updated_rows.append(row) # Keep original row if failure?

    # Write back
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(updated_rows)

    console.print(f"[bold green]Updated {len(updated_rows)} locations in {csv_path.name}[/bold green]")

if __name__ == "__main__":
    app()
