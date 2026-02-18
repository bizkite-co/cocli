import typer
import yaml
from typing import Optional
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign
from cocli.core.email_index_manager import EmailIndexManager
from cocli.core.text_utils import is_valid_email
from cocli.models.email import EmailEntry

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name to backfill. If not provided, scans all companies for the campaign tag.")) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    email_manager = EmailIndexManager(campaign_name)
    
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    added_count = 0
    
    for company_path in track(company_paths, description=f"Backfilling emails for {campaign_name}..."):
        # Check if company belongs to campaign
        tags_path = company_path / "tags.lst"
        is_member = False
        if tags_path.exists():
            tags = tags_path.read_text().strip().splitlines()
            if campaign_name in tags:
                is_member = True
        
        if not is_member:
            continue
            
        emails = set()
        domain = company_path.name # Default
        
        # 1. Check _index.md
        index_md = company_path / "_index.md"
        if index_md.exists():
            try:
                content = index_md.read_text()
                from cocli.core.text_utils import parse_frontmatter
                frontmatter_str = parse_frontmatter(content)
                if frontmatter_str:
                    data = yaml.safe_load(frontmatter_str)
                    if data:
                        domain = data.get("domain") or domain
                        e = data.get("email")
                        if e and e not in ["null", "''", ""]:
                            emails.add(e)
            except Exception:
                pass

        # 2. Check website.md
        website_md = company_path / "enrichments" / "website.md"
        if website_md.exists():
            try:
                content = website_md.read_text()
                from cocli.core.text_utils import parse_frontmatter
                frontmatter_str = parse_frontmatter(content)
                if frontmatter_str:
                    data = yaml.safe_load(frontmatter_str)
                    if data:
                        domain = data.get("domain") or domain
                        e = data.get("email")
                        if e and e not in ["null", "''", ""]:
                            emails.add(e)
                        
                        all_emails = data.get("all_emails", [])
                        for e in all_emails:
                            if e and e not in ["null", "''", ""]:
                                emails.add(e)

                        personnel = data.get("personnel", [])
                        for p in personnel:
                            if isinstance(p, dict) and p.get("email"):
                                emails.add(p["email"])
            except Exception:
                pass

        for email in emails:
            if not is_valid_email(email):
                continue
            entry = EmailEntry(
                email=email,
                domain=domain,
                company_slug=company_path.name,
                source="backfill",
                tags=[campaign_name]
            )
            if email_manager.add_email(entry):
                added_count += 1

    # Compact the index to move from inbox to shards
    email_manager.compact()

    console.print(f"[bold green]Backfill complete! Added {added_count} email entries to index for {campaign_name}.[/bold green]")

if __name__ == "__main__":
    app()