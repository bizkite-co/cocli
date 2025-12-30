import typer
import csv
from pathlib import Path
from typing import Optional
from cocli.core.config import get_companies_dir, get_campaign
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def main(
    csv_path: Path = typer.Argument(..., help="Path to the historical email CSV to compare against."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name. Defaults to current context.")
):
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    manager = ProspectsIndexManager(campaign_name)
    
    # Load all current prospect slugs/domains
    current_prospect_slugs = set()
    for prospect in manager.read_all_prospects():
        if prospect.company_slug:
            current_prospect_slugs.add(prospect.company_slug)
        if prospect.Name:
            current_prospect_slugs.add(slugify(prospect.Name))
        if prospect.Domain:
            current_prospect_slugs.add(slugify(prospect.Domain))
            
    missing_count = 0
    folder_missing = 0
    email_missing_in_folder = 0
    not_in_prospect_index = 0
    total_in_csv = 0
    
    console.print(f"Comparing [bold cyan]{csv_path}[/bold cyan] to current state of [bold cyan]{campaign_name}[/bold cyan]...")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_in_csv += 1
            domain = row['domain']
            if not domain:
                continue
                
            slug = slugify(domain)
            company_path = companies_dir / slug
            
            # Check folder
            if not company_path.exists():
                folder_missing += 1
                missing_count += 1
                continue
                
            # Check email in _index.md
            index_path = company_path / "_index.md"
            has_email = False
            if index_path.exists():
                content = index_path.read_text()
                if "email: " in content and "email: null" not in content and "email: ''" not in content:
                    has_email = True
            
            if not has_email:
                email_missing_in_folder += 1
                missing_count += 1
                continue
                
            # Check if in current prospect index
            if slug not in current_prospect_slugs:
                not_in_prospect_index += 1
                missing_count += 1
                
    console.print(f"Total processed from CSV: [bold]{total_in_csv}[/bold]")
    console.print(f"Folders missing: [bold red]{folder_missing}[/bold red]")
    console.print(f"Emails missing in _index.md (but folder exists): [bold yellow]{email_missing_in_folder}[/bold yellow]")
    console.print(f"Exist and have email, but NOT in prospect index: [bold blue]{not_in_prospect_index}[/bold blue]")
    console.print(f"Still accounted for: [bold green]{total_in_csv - missing_count}[/bold green]")

if __name__ == "__main__":
    app()