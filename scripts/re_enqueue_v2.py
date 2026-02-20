import typer
import csv
from rich.console import Console
from rich.progress import track
from typing import Optional
from pathlib import Path

from cocli.core.config import get_campaign
from cocli.core.queue.filesystem import FilesystemEnrichmentQueue
from cocli.models.campaigns.queues.base import QueueMessage

app = typer.Typer()
console = Console()

@app.command()
def main(
    csv_input: str = typer.Argument(..., help="Path to input CSV file, or '-' for stdin"),
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c"),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit number of items. 0 for all."),
) -> None:
    """
    Enqueues items from CSV (file or stdin) to the Filesystem Queue V2.
    """
    if not campaign:
        campaign = get_campaign()
    
    if not campaign:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    # Init Queue
    queue = FilesystemEnrichmentQueue(campaign)
    
    # Read CSV
    lines: list[str] = []
    if csv_input == "-":
        import sys
        lines = sys.stdin.readlines()
    else:
        path = Path(csv_input)
        if not path.exists():
            console.print(f"[red]CSV not found: {path}[/red]")
            raise typer.Exit(1)
        with open(path, "r") as f:
            lines = f.readlines()

    if not lines:
        console.print("[yellow]No input data.[/yellow]")
        raise typer.Exit(0)

    # Parse CSV from lines
    targets = []
    # Use csv.DictReader on the list of lines
    import io
    # Join lines back to string for DictReader (or use StringIO)
    # Be careful if header is missing in a chunk, but usually head includes it.
    # If piping a chunk without header, this fails. 
    # Assumption: User pipes header + data, e.g. `head -n 5 file.csv | ...`
    reader = csv.DictReader(io.StringIO("".join(lines)))
    for row in reader:
        targets.append(row)
    
    console.print(f"Loaded [bold]{len(targets)}[/bold] targets.")
    
    if limit > 0:
        targets = targets[:limit]
        console.print(f"Limiting to first {limit} targets.")

    enqueued_count = 0
    
    for row in track(targets, description="Enqueuing..."):
        # We need domain and slug
        # The CSV has 'slug', 'domain'
        slug = row.get("slug")
        domain = row.get("domain")
        
        if not slug or not domain:
            continue
            
        msg = QueueMessage(
            domain=domain,
            company_slug=slug,
            campaign_name=campaign,
            force_refresh=True, # We want to re-enrich to fix keywords
            ttl_days=30,
            ack_token=None
        )
        
        queue.push(msg)
        enqueued_count += 1

    console.print(f"[green]Success![/green] Enqueued {enqueued_count} items to {queue.queue_name} (V2).")
    console.print(f"Queue location: [bold]{queue.pending_dir}[/bold]")

if __name__ == "__main__":
    app()
