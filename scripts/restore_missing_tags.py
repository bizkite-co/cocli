import csv
from pathlib import Path
from rich.console import Console
from rich.progress import track
from cocli.core.text_utils import slugify

console = Console()

def restore_tags(campaign_name: str = "turboship") -> None:
    data_home = Path("/home/mstouffer/repos/company-cli/cocli_data")
    companies_dir = data_home / "companies"
    campaign_dir = data_home / "campaigns" / campaign_name
    
    # 1. Load the Prospect Index (The ultimate list of what belongs to this campaign)
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"
    if not prospects_dir.exists():
        console.print(f"[red]Error: Prospects index not found at {prospects_dir}[/red]")
        return

    target_slugs = set()
    console.print(f"[bold]Loading prospect index for {campaign_name}...[/bold]")
    for csv_file in prospects_dir.glob("*.csv"):
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    domain = row.get('Domain')
                    if domain:
                        target_slugs.add(slugify(domain))
        except Exception:
            pass
    
    console.print(f"Found {len(target_slugs)} unique businesses in the prospect index.")

    # 2. Cross-reference with companies on disk
    console.print("[bold]Restoring missing tags...[/bold]")
    restored_count = 0
    
    for slug in track(target_slugs, description="Checking companies..."):
        company_path = companies_dir / slug
        if company_path.exists() and company_path.is_dir():
            tags_path = company_path / "tags.lst"
            
            # Check if tag is missing
            current_tags = []
            if tags_path.exists():
                current_tags = tags_path.read_text().strip().splitlines()
            
            if campaign_name not in current_tags:
                current_tags.append(campaign_name)
                if "prospect" not in current_tags:
                    current_tags.append("prospect")
                
                # Write back to tags.lst
                with open(tags_path, "w") as f:
                    f.write("\n".join(sorted(list(set(current_tags)))))
                
                restored_count += 1

    console.print("\n[bold green]Success![/bold green]")
    console.print(f"  • Restored {campaign_name} tag to [bold]{restored_count}[/bold] companies.")
    console.print("  • These companies will now appear in your next 'make report'.")

if __name__ == "__main__":
    restore_tags()
