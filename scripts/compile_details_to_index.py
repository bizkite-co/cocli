import json
import logging
import typer
from rich.console import Console
from rich.progress import track
from cocli.core.paths import paths
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.google_maps_raw import GoogleMapsRawResult
from cocli.core.prospects_csv_manager import ProspectsIndexManager

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)

JUNK_NAMES = ["home", "homepage", "home page", "recovery task"]

def is_junk_name(name: str) -> bool:
    if not name:
        return True
    lower_name = name.lower()
    return any(j in lower_name for j in JUNK_NAMES)

@app.command()
def main(
    campaign_name: str,
    limit: int = typer.Option(0, "--limit", help="Limit number of files processed."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't write to index.")
) -> None:
    """
    Consolidates completed gm-details JSON files into the campaign's prospect index.
    This recovers the 'Gold Source' names and addresses found by workers.
    """
    campaign_path = paths.campaign(campaign_name)
    completed_dir = campaign_path.queue("gm-details").completed
    
    if not completed_dir.exists():
        console.print(f"[red]Completed queue directory not found: {completed_dir}[/red]")
        return

    json_files = list(completed_dir.glob("*.json"))
    if limit > 0:
        json_files = json_files[:limit]

    console.print(f"Found [bold]{len(json_files)}[/bold] completed detail files for [bold]{campaign_name}[/bold].")
    
    manager = ProspectsIndexManager(campaign_name)
    count = 0
    skipped = 0
    junk = 0

    for json_path in track(json_files, description="Compiling details..."):
        try:
            data = json.loads(json_path.read_text())
            
            # The JSON from details-worker is often a raw result or a model dump
            # We need to map it back to a GoogleMapsProspect
            place_id = data.get("place_id") or data.get("Place_ID")
            name = data.get("name") or data.get("Name")
            
            if not name or is_junk_name(name):
                junk += 1
                continue

            # Map raw fields if necessary (some older JSONs might be raw)
            raw = GoogleMapsRawResult(
                Place_ID=place_id,
                Name=name,
                Full_Address=data.get("full_address") or data.get("Full_Address", ""),
                Website=data.get("website") or data.get("Website", ""),
                Phone_1=data.get("phone") or data.get("Phone", ""),
                processed_by=data.get("processed_by", "details-compiler")
            )
            
            prospect = GoogleMapsProspect.from_raw(raw)
            
            # Merge with any other fields in the JSON
            prospect_dict = prospect.model_dump()
            for k, v in data.items():
                if k in prospect_dict and v and not prospect_dict[k]:
                    prospect_dict[k] = v
            
            final_prospect = GoogleMapsProspect.model_validate(prospect_dict)

            if not dry_run:
                manager.append_prospect(final_prospect)
            
            count += 1
        except Exception as e:
            logger.error(f"Failed to process {json_path.name}: {e}")
            skipped += 1

    console.print("\n[bold green]Compilation Complete![/bold green]")
    console.print(f"Index updates: {count}")
    console.print(f"Skipped (Junk name): {junk}")
    console.print(f"Errors: {skipped}")
    
    if not dry_run:
        console.print("[yellow]Next step: Run 'cocli campaign sync-index-to-folders' to restore names.[/yellow]")

if __name__ == "__main__":
    app()
