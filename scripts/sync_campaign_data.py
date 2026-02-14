import typer
import logging
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaigns_dir
from cocli.models.company import Company
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.utils.usv_utils import USVDictWriter
from pathlib import Path
from typing import Optional
from datetime import datetime

app = typer.Typer()
console = Console()

def setup_file_logging(script_name: str) -> Path:
    """Configures logging to a timestamped file in .logs/"""
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{script_name}_{timestamp}.log"
    
    # Configure standard logging to only go to the file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file)
        ],
        force=True # Override any previous config
    )
    return log_file

@app.command()
def index_to_folders(
    campaign_name: str = typer.Argument(..., help="Campaign name to sync."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't save changes.")
) -> None:
    """
    Ensures every entry in the Google Maps index has a corresponding folder and _index.md.
    Updates missing place_id, gmb_url, and tags without overwriting existing enrichment data.
    """
    log_file = setup_file_logging(f"sync_index_{campaign_name}")
    logger = logging.getLogger("sync")
    
    console.print(f"Starting sync for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    manager = ProspectsIndexManager(campaign_name)
    companies_dir = get_companies_dir()
    
    created_count = 0
    updated_count = 0
    tagged_count = 0
    
    prospects = list(manager.read_all_prospects())
    logger.info(f"Loaded {len(prospects)} prospects from index.")

    from cocli.models.google_maps_prospect import GoogleMapsProspect

    for prospect in track(prospects, description="Syncing Index -> Folders"):
        if not prospect.company_slug:
            logger.warning(f"Skipping prospect with missing slug: {prospect.place_id}")
            continue
            
        slug = prospect.company_slug
        company_dir = companies_dir / slug
        
        # 1. Ensure directory exists
        if not company_dir.exists():
            logger.info(f"Creating directory: {slug}")
            if not dry_run:
                company_dir.mkdir(parents=True, exist_ok=True)
            created_count += 1
            
        # 2. Load or create company object
        company_obj = Company.get(slug)
        is_new = False
        if not company_obj:
            logger.info(f"Creating NEW company record: {slug}")
            company_obj = Company(
                name=prospect.name or slug,
                slug=slug,
                tags=[campaign_name]
            )
            is_new = True
        
        updated = False
        
        # 3. Merge missing identity data
        if not company_obj.place_id and prospect.place_id:
            logger.info(f"Adding missing place_id to {slug}: {prospect.place_id}")
            company_obj.place_id = prospect.place_id
            updated = True
            
        if company_obj.latitude is None and prospect.latitude:
            logger.info(f"Adding missing latitude to {slug}: {prospect.latitude}")
            company_obj.latitude = prospect.latitude
            updated = True
            
        if company_obj.longitude is None and prospect.longitude:
            logger.info(f"Adding missing longitude to {slug}: {prospect.longitude}")
            company_obj.longitude = prospect.longitude
            updated = True
            
        if company_obj.name == slug and prospect.name:
            logger.info(f"Setting proper name for {slug}: {prospect.name}")
            company_obj.name = prospect.name
            updated = True

        if is_new:
            logger.info(f"Company {slug} is NEW")
        elif updated:
            logger.info(f"Company {slug} was UPDATED")
            
        # 4. Ensure campaign tag
        if campaign_name not in company_obj.tags:
            logger.info(f"Adding campaign tag '{campaign_name}' to {slug}")
            company_obj.tags.append(campaign_name)
            updated = True
            tagged_count += 1
            
        # 5. Recover search phrase if possible (keyword in prospect model)
        if prospect.keyword and prospect.keyword not in company_obj.tags:
            logger.info(f"Adding discovery tag '{prospect.keyword}' to {slug}")
            company_obj.tags.append(prospect.keyword)
            updated = True

        if (updated or is_new) and not dry_run:
            company_obj.save(email_sync=False)
            if not is_new:
                updated_count += 1

        # 6. Provenance: Save the original Maps data as an enrichment source
        if not dry_run:
            enrich_dir = company_dir / "enrichments"
            enrich_dir.mkdir(exist_ok=True)
            maps_usv = enrich_dir / "google_maps.usv"
            
            # Always update the receipt to match the latest index state
            with open(maps_usv, 'w', encoding='utf-8') as f:
                fieldnames = list(GoogleMapsProspect.model_fields.keys())
                writer = USVDictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(prospect.model_dump(mode="json"))

    console.print("\n[bold green]Sync Complete![/bold green]")
    console.print(f"Folders Created: {created_count}")
    console.print(f"Companies Updated: {updated_count}")
    console.print(f"Campaign Tags Added: {tagged_count}")
    logger.info("Sync process finished successfully.")

@app.command()
def folders_to_index(
    campaign_name: str = typer.Argument(..., help="Campaign name to sync."),
    output_missing: Optional[Path] = typer.Option(None, "--output", "-o", help="File to save slugs not in index.")
) -> None:
    """
    Checks every folder with the campaign tag and ensures it exists in the prospect index.
    Logs missing slugs to a USV for recovery.
    """
    log_file = setup_file_logging(f"sync_folders_{campaign_name}")
    logger = logging.getLogger("sync")
    
    console.print(f"Verifying folders for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    manager = ProspectsIndexManager(campaign_name)
    
    if output_missing is None:
        campaign_dir = get_campaigns_dir() / campaign_name
        recovery_dir = campaign_dir / "recovery" / "indexes" / "google_maps_prospects"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        output_missing = recovery_dir / "folders-not-in-index.usv"

    # Load all known identifiers from index for fast lookup
    index_pids = set()
    index_slugs = set()
    logger.info("Loading index identifiers...")
    for p in manager.read_all_prospects():
        if p.place_id:
            index_pids.add(p.place_id)
        if p.company_slug:
            index_slugs.add(p.company_slug)
    logger.info(f"Index loaded: {len(index_pids)} PIDs, {len(index_slugs)} Slugs.")

    missing_slugs = []
    found_in_folders = 0
    
    # We use a list to get a total count for the progress bar
    all_companies = list(Company.get_all())
    
    for company in track(all_companies, description="Checking Folders -> Index"):
        if campaign_name not in company.tags:
            continue
            
        found_in_folders += 1
        
        # Check if this company is represented in the index
        exists = (
            (company.place_id and company.place_id in index_pids) or
            (company.slug in index_slugs)
        )
        
        if not exists:
            logger.warning(f"FOLDER NOT IN INDEX: {company.slug} (Name: {company.name}, PID: {company.place_id})")
            missing_slugs.append({
                "slug": company.slug,
                "name": company.name,
                "place_id": company.place_id or ""
            })

    if missing_slugs:
        with open(output_missing, 'w', encoding='utf-8') as f:
            writer = USVDictWriter(f, fieldnames=["slug", "name", "place_id"])
            for m in missing_slugs:
                writer.writerow(m)
        console.print(f"\n[bold yellow]Attention:[/bold yellow] Found {len(missing_slugs)} folders tagged '{campaign_name}' missing from the index.")
        console.print(f"Logged missing slugs to: [cyan]{output_missing}[/cyan]")
    else:
        console.print(f"\n[bold green]Success![/bold green] All {found_in_folders} tagged folders are represented in the index.")
    
    logger.info(f"Checked {found_in_folders} tagged folders. Found {len(missing_slugs)} missing from index.")

if __name__ == "__main__":
    app()
