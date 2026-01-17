import csv
import yaml
import os
from pathlib import Path
from rich.console import Console
from rich.progress import track

from cocli.core.config import get_campaign_dir, get_companies_dir, get_cocli_base_dir

console = Console()

def cleanup_roadmap_contamination(dry_run: bool = True):
    campaign_name = "roadmap"
    contaminated_keywords = {"floor", "flooring", "carpet", "rug", "tile", "vinyl", "laminate", "contractor"}
    valid_phrases = {"wealth manager", "financial advisor", "financial planner", "pacific life", "financial analyst"}
    
    companies_dir = get_companies_dir()
    campaign_dir = get_campaign_dir(campaign_name)
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"
    email_index_dir = campaign_dir / "indexes" / "emails"
    
    removed_count = 0
    
    # 1. Audit and Prune Companies Directory
    console.print(f"[bold blue]Step 1: Pruning tags in companies directory (Dry Run: {dry_run})[/bold blue]")
    for company_dir in track(list(companies_dir.iterdir()), description="Auditing companies..."):
        if not company_dir.is_dir():
            continue
            
        tags_file = company_dir / "tags.lst"
        if not tags_file.exists():
            continue
            
        tags = tags_file.read_text().splitlines()
        if campaign_name not in [t.strip() for t in tags]:
            continue
            
        # Check for contamination
        is_contaminated = False
        reason = ""
        
        # Check name/slug
        if any(kw in company_dir.name.lower() for kw in contaminated_keywords):
            is_contaminated = True
            reason = f"Slug contains contaminated keyword: {company_dir.name}"
            
        # Check metadata
        if not is_contaminated:
            index_md = company_dir / "_index.md"
            if index_md.exists():
                try:
                    parts = index_md.read_text().split("---")
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        name = data.get("name", "").lower()
                        if any(kw in name for kw in contaminated_keywords):
                            is_contaminated = True
                            reason = f"Name contains contaminated keyword: {name}"
                        
                        tech_stack = data.get("tech_stack", [])
                        if any(any(kw in str(t).lower() for kw in contaminated_keywords) for t in tech_stack):
                            is_contaminated = True
                            reason = f"Tech stack contains contamination: {tech_stack}"
                except Exception:
                    pass

        if is_contaminated:
            console.print(f"[yellow]Flagged {company_dir.name}:[/yellow] {reason}")
            if not dry_run:
                new_tags = [t.strip() for t in tags if t.strip() != campaign_name]
                if new_tags:
                    tags_file.write_text("\n".join(new_tags) + "\n")
                else:
                    tags_file.unlink() # Delete if no tags left
            removed_count += 1

    # 2. Prune Google Maps Prospect Index
    console.print(f"\n[bold blue]Step 2: Pruning GM Prospect Index (Dry Run: {dry_run})[/bold blue]")
    if prospects_dir.exists():
        for file_path in prospects_dir.glob("*.csv"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("Name", "").lower()
                        keyword = row.get("Keyword", "").lower()
                        
                        is_contaminated = any(kw in name for kw in contaminated_keywords)
                        
                        if is_contaminated:
                            console.print(f"[yellow]Removing from GM Index:[/yellow] {name} ({file_path.name})")
                            if not dry_run:
                                file_path.unlink()
            except Exception:
                pass

    # 3. Prune Email Index
    console.print(f"\n[bold blue]Step 3: Pruning Email Index (Dry Run: {dry_run})[/bold blue]")
    if email_index_dir.exists():
        for domain_dir in email_index_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            
            domain = domain_dir.name
            if any(kw in domain.lower() for kw in contaminated_keywords):
                console.print(f"[yellow]Removing from Email Index:[/yellow] {domain}")
                if not dry_run:
                    import shutil
                    shutil.rmtree(domain_dir)

    console.print(f"\n[bold green]Cleanup complete. {removed_count} companies processed.[/bold green]")
    if dry_run:
        console.print("[yellow]Note: This was a DRY RUN. No files were modified.[/yellow]")

if __name__ == "__main__":
    import sys
    dry_run = "--fix" not in sys.argv
    cleanup_roadmap_contamination(dry_run=dry_run)
