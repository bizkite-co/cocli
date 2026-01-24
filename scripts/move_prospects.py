import shutil
import typer
from rich.console import Console

from cocli.core.config import get_scraped_data_dir, get_campaign_scraped_data_dir, get_all_campaign_dirs

app = typer.Typer()
console = Console()

@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without executing them.")
) -> None:
    """
    Moves prospects.csv files from the old location to the new campaign-specific location for all campaigns.
    This assumes no new data was written to the new location for these campaigns.
    """
    console.print("[bold blue]Starting prospects.csv file movement...[/bold blue]")

    legacy_base_dir = get_scraped_data_dir() # This is ~/.local/share/data/scraped_data

    for campaign_dir in get_all_campaign_dirs():
        campaign_name = campaign_dir.name # campaign_dir is already the new campaigns/<slug> path
        
        old_prospects_path = legacy_base_dir / campaign_name / "prospects" / "prospects.csv"
        new_prospects_dir = get_campaign_scraped_data_dir(campaign_name) # This creates the new dir if it doesn't exist
        new_prospects_path = new_prospects_dir / "prospects.csv"

        if old_prospects_path.exists():
            console.print(f"Processing campaign: [bold]{campaign_name}[/bold]")
            if new_prospects_path.exists():
                console.print(f"  [yellow]Warning:[/yellow] New prospects.csv already exists at [dim]{new_prospects_path}[/dim]. Skipping move for [bold]{campaign_name}[/bold] to avoid overwriting. Manual merge may be required if data is different.")
                continue # Skip to next campaign
            
            console.print(f"  Moving {old_prospects_path} -> {new_prospects_path}")
            if not dry_run:
                try:
                    shutil.move(str(old_prospects_path), str(new_prospects_path))
                    console.print(f"  [green]Successfully moved prospects.csv for [bold]{campaign_name}[/bold][/green]")

                    # Clean up old empty directories
                    try:
                        old_prospects_path.parent.rmdir() # remove 'prospects' dir
                        old_prospects_path.parent.parent.rmdir() # remove campaign_name dir from old scraped_data
                        console.print(f"  [dim]Cleaned up legacy directories for [bold]{campaign_name}[/bold][/dim]")
                    except OSError as e:
                        console.print(f"  [yellow]Warning:[/yellow] Could not remove old directories for [bold]{campaign_name}[/bold] (might not be empty): {e}")

                except Exception as e:
                    console.print(f"  [bold red]Error moving prospects.csv for [bold]{campaign_name}[/bold]: {e}[/bold red]")
            else:
                console.print(f"  [dim]Dry run: Would move {old_prospects_path} to {new_prospects_path}[/dim]")
        else:
            console.print(f"  [dim]No legacy prospects.csv found for [bold]{campaign_name}[/bold] at {old_prospects_path}[/dim]")

    console.print("[bold blue]Prospects.csv file movement complete.[/bold blue]")

if __name__ == "__main__":
    app()
