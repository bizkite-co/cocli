from cocli.core.prospects_csv_manager import ProspectsIndexManager
from rich.console import Console
from rich.table import Table

def debug_hashes(campaign_name: str) -> None:
    manager = ProspectsIndexManager(campaign_name)
    console = Console()
    
    table = Table(title=f"Hash Diagnostic: {campaign_name}")
    table.add_column("Place ID", style="dim")
    table.add_column("Hash")
    table.add_column("Name")
    table.add_column("Street")
    table.add_column("Zip")
    table.add_column("Full Address", style="dim")

    count = 0
    for p in manager.read_all_prospects():
        table.add_row(
            p.place_id or "",
            p.company_hash or "[red]NONE[/red]",
            p.name or "",
            p.street_address or "[yellow]MISSING[/yellow]",
            p.zip or "[yellow]MISSING[/yellow]",
            (p.full_address or "")[:30] + "..." if p.full_address else ""
        )
        count += 1
        if count >= 30:
            break
            
    console.print(table)

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    debug_hashes(campaign)
