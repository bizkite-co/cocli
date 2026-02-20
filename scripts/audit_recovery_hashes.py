import sys
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

def audit_recovery(campaign_name: str) -> None:
    data_home = Path(os.environ.get("COCLI_DATA_HOME", Path.home() / ".local/share/cocli_data"))
    checkpoint = data_home / "campaigns" / campaign_name / "recovery" / "indexes" / "google_maps_prospects" / "prospects.checkpoint.usv"
    
    console = Console()
    if not checkpoint.exists():
        console.print(f"[red]Checkpoint not found: {checkpoint}[/red]")
        return

    table = Table(title=f"Recovery Audit: {campaign_name}")
    table.add_column("Place ID", style="dim")
    table.add_column("Hash")
    table.add_column("Name")
    table.add_column("Street")
    table.add_column("Zip")
    table.add_column("Status")

    collisions: dict[str, list[str]] = {}
    total = 0
    missing_hash = 0
    
    with open(checkpoint, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                p = GoogleMapsProspect.from_usv(line)
                total += 1
                
                if not p.company_hash:
                    missing_hash += 1
                else:
                    if p.company_hash in collisions:
                        collisions[p.company_hash].append(p.place_id)
                    else:
                        collisions[p.company_hash] = [p.place_id]
                
                if total <= 20:
                    table.add_row(
                        p.place_id,
                        p.company_hash or "[red]NONE[/red]",
                        p.name[:20],
                        p.street_address[:15] if p.street_address else "[yellow]MISSING[/yellow]",
                        p.zip or "[yellow]MISSING[/yellow]",
                        "[green]OK[/green]"
                    )
            except Exception as e:
                console.print(f"[red]Error parsing line: {e}[/red]")

    console.print(table)
    
    unique_hashes = len(collisions)
    collision_count = sum(len(v) for v in collisions.values() if len(v) > 1)
    
    console.print("\n[bold]Audit Summary:[/bold]")
    console.print(f"Total Records: {total}")
    console.print(f"Unique Hashes: {unique_hashes}")
    console.print(f"Missing Hashes: {missing_hash}")
    console.print(f"Colliding Records: {collision_count}")
    
    if collision_count > 0:
        console.print("\n[red]Top Collisions:[/red]")
        for h, ids in list(collisions.items())[:5]:
            if len(ids) > 1:
                console.print(f"  {h}: {ids}")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "turboship"
    audit_recovery(campaign)
