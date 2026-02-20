import typer
import csv
from rich.console import Console
from rich.progress import track
from typing import Optional
from pathlib import Path

from cocli.core.config import get_campaign, get_campaign_exports_dir
from cocli.models.companies.company import Company

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Path to output CSV file. Defaults to campaign exports."),
) -> None:
    """
    Lists all prospects in a campaign that are missing emails and saves them to a CSV.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    if output is None:
        exports_dir = get_campaign_exports_dir(campaign_name)
        output = exports_dir / "prospects_missing_emails.csv"

    console.print(f"[bold]Finding prospects missing emails for campaign: {campaign_name}[/bold]")
    
    all_companies = Company.get_all()
    missing_emails = []
    
    for company in track(all_companies, description="Scanning companies..."):
        # Check if part of the campaign
        if campaign_name not in company.tags:
            continue
            
        # Check if email is missing
        if not company.email:
            # We also need a domain to be useful for re-scraping
            if company.domain:
                missing_emails.append({
                    "name": company.name,
                    "slug": company.slug,
                    "domain": company.domain
                })

    if not missing_emails:
        console.print("[yellow]No prospects missing emails found.[/yellow]")
        return

    console.print(f"Found [bold green]{len(missing_emails)}[/bold green] prospects missing emails.")

    # Write to CSV
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "slug", "domain"])
        writer.writeheader()
        writer.writerows(missing_emails)

    console.print(f"List saved to: [bold]{output}[/bold]")

if __name__ == "__main__":
    app()
