import csv
import sys
import typer
from typing import Optional
from rich.console import Console
from cocli.core.config import get_campaign_scraped_data_dir, get_campaign, get_campaigns_dir

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. Defaults to current context.")) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    campaign_dir = get_campaigns_dir() / campaign_name
    data_dir = get_campaign_scraped_data_dir(campaign_name)
    csv_path = data_dir / "google_maps_prospects.csv"
    index_dir = campaign_dir / "indexes" / "google_maps_prospects"

    if not csv_path.exists():
        console.print(f"[bold red]Source CSV not found at: {csv_path}[/bold red]")
        sys.exit(1)

    # Create index directory
    index_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Migrating prospects to index: [bold]{index_dir}[/bold]")

    stats = {
        "read": 0,
        "written": 0,
        "missing_id": 0
    }

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            if not fieldnames:
                console.print("[red]CSV file is empty or has no header.[/red]")
                sys.exit(1)

            for row in reader:
                stats["read"] += 1
                place_id = row.get("Place_ID")
                
                if not place_id:
                    stats["missing_id"] += 1
                    continue
                
                # Sanitize filename (though Place_ID is usually safe)
                safe_filename = place_id.replace("/", "_").replace("\\", "_")
                file_path = index_dir / f"{safe_filename}.csv"
                
                with open(file_path, 'w', newline='', encoding='utf-8') as out_f:
                    writer = csv.DictWriter(out_f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerow(row)
                
                stats["written"] += 1

    except Exception as e:
        console.print(f"[bold red]Error during migration: {e}[/bold red]")
        sys.exit(1)

    console.print("\n[bold green]Migration Complete![/bold green]")
    console.print(f"Total Rows Read: {stats['read']}")
    console.print(f"Files Written (Last Write Wins): {stats['written']}")
    console.print(f"Skipped (Missing Place_ID): {stats['missing_id']}")
    console.print(f"Index location: {index_dir}")

if __name__ == "__main__":
    typer.run(main)
