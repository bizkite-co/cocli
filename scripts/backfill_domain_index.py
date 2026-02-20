import typer
import yaml
from pathlib import Path
from typing import Optional, Iterable, List
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign
from cocli.core.domain_index_manager import DomainIndexManager
from cocli.models.campaigns.campaign import Campaign as CampaignModel
from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
from datetime import datetime, timezone

import logging

app = typer.Typer()
console = Console()

def setup_logging(campaign_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"backfill_domains_{campaign_name}_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    return log_file

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name to backfill."),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit the number of companies processed (for testing)."),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Specific company slug to process.")
) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    log_file = setup_logging(campaign_name)
    console.print(f"Backfilling domains for [bold]{campaign_name}[/bold]")
    if limit:
        console.print(f"Testing with limit: [yellow]{limit}[/yellow]")
    if company:
        console.print(f"Processing specific company: [cyan]{company}[/cyan]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    companies_dir = get_companies_dir()
    campaign = CampaignModel.load(campaign_name)
    domain_manager = DomainIndexManager(campaign)
    
    # We'll use the campaign's tag to filter companies
    from cocli.core.config import load_campaign_config
    config = load_campaign_config(campaign_name)
    tag = config.get("campaign", {}).get("tag") or campaign_name
    
    added_count = 0
    processed_count = 0
    
    targets: Iterable[Path]
    if company:
        targets = [companies_dir / company]
    else:
        targets = companies_dir.iterdir()

    # Use iterdir() directly to avoid loading all paths into memory at once
    for company_path in track(targets, description=f"Backfilling domains for {campaign_name}..."):
        if not company_path.is_dir():
            continue
            
        if not company and limit and processed_count >= limit:
            break
            
        # 1. Check if company belongs to campaign (Fast tag check)
        tags_path = company_path / "tags.lst"
        tags: List[str] = []
        if not tags_path.exists():
            continue
            
        try:
            tags = tags_path.read_text().splitlines()
            if tag not in [t.strip() for t in tags]:
                continue
        except Exception:
            continue

        processed_count += 1

        # 2. Check for website enrichment
        website_md = company_path / "enrichments" / "website.md"
        if not website_md.exists():
            continue
            
        try:
            content = website_md.read_text()
            from cocli.core.text_utils import parse_frontmatter
            frontmatter_str = parse_frontmatter(content)
            if not frontmatter_str:
                continue
                
            # Aggressive Clean: Strip !!python/object tags that safe_load can't handle
            import re
            cleaned_yaml = re.sub(r'!!python/object/new:cocli\.models\.[a-z_]+\.[A-Za-z]+', '', frontmatter_str)
            # Also clean up the 'args:' lines if they remain
            cleaned_yaml = re.sub(r'args:\s*\[([^\]]+)\]', r'\1', cleaned_yaml)

            try:
                data = yaml.safe_load(cleaned_yaml)
            except Exception:
                from cocli.utils.yaml_utils import resilient_safe_load
                data = resilient_safe_load(frontmatter_str)

            if not data:
                continue
                
            domain = data.get("domain") or company_path.name
            
            # Map Website data to WebsiteDomainCsv model
            # (Basic fields needed for the index)
            record = WebsiteDomainCsv(
                domain=domain,
                company_name=data.get("company_name") or company_path.name,
                is_email_provider=data.get("is_email_provider", False),
                updated_at=data.get("updated_at") or datetime.now(timezone.utc),
                tags=tags # Keep campaign tags
            )
            
            domain_manager.add_or_update(record)
            added_count += 1
            
        except Exception as e:
            logging.error(f"Error processing {company_path.name}: {e}")

    # 3. Compact the domain index
    console.print("Compacting domain index...")
    domain_manager.compact_inbox()

    console.print(f"[bold green]Backfill complete! Added {added_count} domains to index for {campaign_name}.[/bold green]")

if __name__ == "__main__":
    app()
