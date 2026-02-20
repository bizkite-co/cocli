import typer
import json
from rich.console import Console
from rich.progress import track

from typing import Optional
from cocli.core.config import get_companies_dir, get_cocli_base_dir, get_campaign
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.base import QueueMessage

app = typer.Typer()
console = Console()

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-queueing even if marked as failed."),
) -> None:
    """
    Finds companies that have no enrichment data (website.md) and are not currently in the queue.
    Pushes them to the enrichment queue.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold]Gap Analysis for campaign: {campaign_name}[/bold]")
    
    # 1. Identify Queued Domains
    # In cloud mode, we can't easily list all pending domains without polling the whole queue
    # which is destructive. However, we can check our local 'queues/' folder if it exists.
    queue_base = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment"
    queued_domains = set()
    
    # Check pending, processing, and failed (unless forcing retry of failed)
    dirs_to_check = ["pending", "processing"]
    if not force:
        dirs_to_check.append("failed")
        
    for status in dirs_to_check:
        d = queue_base / status
        if d.exists():
            for f in d.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    if "domain" in data:
                        queued_domains.add(data["domain"])
                except Exception:
                    pass
    
    console.print(f"Found {len(queued_domains)} domains currently in local queues ({', '.join(dirs_to_check)}).")

    # 2. Scan Companies
    companies_dir = get_companies_dir()
    
    missing_count = 0
    requeued_count = 0
    queue_manager = get_queue_manager("enrichment", use_cloud=True, campaign_name=campaign_name)
    
    # Get all folders
    company_folders = [f for f in companies_dir.iterdir() if f.is_dir()]
    
    for folder in track(company_folders, description="Scanning companies..."):
        # Check if website.md exists
        website_md = folder / "enrichments" / "website.md"
        if website_md.exists():
            continue # Already enriched (success or empty)
            
        # If missing, check if we can identify the domain
        # Try reading _index.md
        domain = None
        slug = folder.name
        
        index_md = folder / "_index.md"
        if index_md.exists():
            try:
                # Quick parse without yaml overhead
                content = index_md.read_text()
                import yaml
                # split by ---
                parts = content.split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    domain = data.get("domain")
            except Exception:
                pass
        
        # Fallback: infer domain from slug? 
        # e.g. 'google-com' -> 'google.com'. 
        # Risky, but better than nothing if _index.md is corrupt.
        if not domain:
            # Try to reconstruction from slug
            # This is heuristic.
            domain = slug.replace("-", ".", 1) # crude
            # Let's rely on _index.md for now. If missing/corrupt, maybe we skip?
            # Or we assume the folder name IS the slug which IS the domain-ish.
            continue

        if domain in queued_domains:
            continue
            
        # Found a gap!
        missing_count += 1
        
        # Push to queue
        msg = QueueMessage(
            domain=domain,
            company_slug=slug,
            campaign_name=campaign_name,
            force_refresh=False,
            ttl_days=30,
            ack_token=None,
        )
        queue_manager.push(msg)
        requeued_count += 1
        queued_domains.add(domain) # Prevent dupes in loop

    console.print("[bold green]Gap Analysis Complete.[/bold green]")
    console.print(f"Missing Enrichments: {missing_count}")
    console.print(f"Re-queued Tasks: {requeued_count}")

if __name__ == "__main__":
    app()
