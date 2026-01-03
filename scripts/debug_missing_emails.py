import yaml
import logging
from pathlib import Path
from typing import Set
from rich.console import Console
from cocli.core.config import get_companies_dir, get_campaign

console = Console()

def debug_emails(campaign_name="turboship"):
    companies_dir = get_companies_dir()
    
    all_disk_emails = set()
    campaign_emails = set()
    missing_tag_emails = [] # Emails found in companies that SHOULD have the tag but don't
    
    # 1. Find every unique email on disk
    console.print("[bold]Scanning all company files for emails...[/bold]")
    for company_path in companies_dir.iterdir():
        if not company_path.is_dir(): continue
        
        email = None
        # Check _index.md
        index_md = company_path / "_index.md"
        if index_md.exists():
            try:
                parts = index_md.read_text().split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    if data and data.get("email"):
                        email = data.get("email")
            except: pass
            
        # Check website.md if index failed
        if not email:
            web_md = company_path / "enrichments" / "website.md"
            if web_md.exists():
                try:
                    parts = web_md.read_text().split("---")
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        if data and data.get("email"):
                            email = data.get("email")
                except: pass
        
        if email and "@" in str(email):
            all_disk_emails.add(email)
            
            # Check tags
            tags_path = company_path / "tags.lst"
            tags = []
            if tags_path.exists():
                tags = tags_path.read_text().strip().splitlines()
            
            if campaign_name in tags:
                campaign_emails.add(email)
            else:
                missing_tag_emails.append({
                    "slug": company_path.name,
                    "email": email,
                    "tags": tags
                })

    console.print(f"\n[bold]Data Integrity Report:[/bold]")
    console.print(f"  • Total unique emails on disk: [green]{len(all_disk_emails)}[/green]")
    console.print(f"  • Emails with '{campaign_name}' tag: [blue]{len(campaign_emails)}[/blue]")
    console.print(f"  • Potential '{campaign_name}' emails missing tag: [yellow]{len(missing_tag_emails)}[/yellow]")
    
    if missing_tag_emails:
        console.print("\n[bold red]Top 10 untagged companies with emails:[/bold red]")
        for item in missing_tag_emails[:10]:
            console.print(f"    - {item['slug']}: {item['email']} (Tags: {item['tags']})")

if __name__ == "__main__":
    debug_emails()
