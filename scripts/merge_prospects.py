import pandas as pd
import shutil
from pathlib import Path
import typer
import logging
from rich.console import Console
from cocli.core.config import get_scraped_data_dir, get_campaign_scraped_data_dir

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

@app.command()
def main(campaign_name: str = typer.Argument(..., help="The campaign name to merge prospects for.")) -> None:
    """
    Merges the legacy prospects.csv into the new campaign-specific location.
    """
    # Define paths
    # Old: cocli_data/scraped_data/<campaign>/prospects/prospects.csv
    old_csv_path = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    # New: cocli_data/campaigns/<campaign>/scraped_data/prospects.csv
    new_csv_path = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"

    if not old_csv_path.exists():
        console.print(f"[yellow]No legacy CSV found at {old_csv_path}. Nothing to merge.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Reading legacy CSV from: {old_csv_path}")
    try:
        df_old = pd.read_csv(old_csv_path, low_memory=False)
        console.print(f"Old CSV rows: {len(df_old)}")
    except Exception as e:
        console.print(f"[red]Error reading legacy CSV: {e}[/red]")
        raise typer.Exit(1)

    df_new = pd.DataFrame()
    if new_csv_path.exists():
        console.print(f"Reading new CSV from: {new_csv_path}")
        try:
            df_new = pd.read_csv(new_csv_path, low_memory=False)
            console.print(f"New CSV rows: {len(df_new)}")
        except Exception as e:
            console.print(f"[red]Error reading new CSV: {e}[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"[yellow]Target CSV does not exist yet at {new_csv_path}. It will be created.[/yellow]")
        # Ensure directory exists
        new_csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Concatenate
    console.print("Merging dataframes...")
    df_merged = pd.concat([df_new, df_old], ignore_index=True)
    console.print(f"Total rows before deduplication: {len(df_merged)}")

    # Deduplicate based on Place_ID, keeping the last occurrence (assuming newer is better/fresher)
    console.print("Deduplicating by Place_ID...")
    # Ensure we have Place_ID column before dropping duplicates
    if 'Place_ID' in df_merged.columns:
        df_deduped = df_merged.drop_duplicates(subset=['Place_ID'], keep='last')
    else:
        console.print("[red]Warning: 'Place_ID' column missing. Deduplicating by all columns.[/red]")
        df_deduped = df_merged.drop_duplicates(keep='last')

    console.print(f"Total rows after deduplication: {len(df_deduped)}")

    # Backup the target file before overwriting if it existed
    if new_csv_path.exists():
        backup_path = new_csv_path.with_suffix('.csv.bak')
        shutil.copy(new_csv_path, backup_path)
        console.print(f"Backed up existing target CSV to: {backup_path}")

    # Write to new location
    console.print(f"Writing merged data to: {new_csv_path}")
    df_deduped.to_csv(new_csv_path, index=False)
    
    # Optional: Remove old file?
    # os.remove(old_csv_path)
    console.print("[bold green]Merge complete.[/bold green]")
    console.print(f"[dim]You can manually remove the legacy file: {old_csv_path}[/dim]")

if __name__ == "__main__":
    app()
