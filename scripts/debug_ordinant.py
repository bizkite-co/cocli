import hashlib
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.sharding import get_domain_shard

from typing import Tuple

app = typer.Typer()
console = Console()

def get_legacy_info(domain: str, slug: str) -> Tuple[str, str]:
    raw_id = f"{slug}_{domain}"
    legacy_id = hashlib.md5(raw_id.encode()).hexdigest()
    legacy_shard = legacy_id[0]
    return legacy_id, legacy_shard

@app.command()
def check(
    domain: str = typer.Argument(..., help="The domain to check."),
    slug: str = typer.Option("placeholder-slug", "--slug", "-s", help="The company slug (required for legacy path calculation).")
) -> None:
    """
    Shows the transition from Legacy to Gold Standard Ordinants for a domain.
    """
    legacy_id, legacy_shard = get_legacy_info(domain, slug)
    gold_shard = get_domain_shard(domain)
    gold_id = domain

    table = Table(title=f"Ordinant Mapping: {domain}")
    table.add_column("System", style="cyan")
    table.add_column("Shard", style="magenta")
    table.add_column("Task ID (Directory)", style="green")
    table.add_column("Logic", style="yellow")

    table.add_row(
        "Legacy", 
        legacy_shard, 
        legacy_id, 
        f"md5('{slug}_{domain}')[0]"
    )
    table.add_row(
        "Gold Standard", 
        gold_shard, 
        gold_id, 
        f"sha256('{domain}')[:2]"
    )

    console.print(table)
    
    console.print("\n[bold]S3 Path Comparison:[/bold]")
    console.print(f"[red]OLD:[/red] .../enrichment/pending/{legacy_shard}/{legacy_id}/task.json")
    console.print(f"[green]NEW:[/green] .../enrichment/pending/{gold_shard}/{gold_id}/task.json")

if __name__ == "__main__":
    app()
