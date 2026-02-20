import typer
import logging
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaigns_dir
from cocli.models.companies.company import Company
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.queue.factory import get_queue_manager
from cocli.utils.usv_utils import USVDictWriter
from pathlib import Path
from typing import Optional, Dict, Set
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

def get_discovery_map(campaign_name: str) -> Dict[str, Set[str]]:
    """Scans all gm-list results to map place_id -> set of search phrases."""
    discovery_map: Dict[str, Set[str]] = {}
    campaign_dir = get_campaigns_dir() / campaign_name
    results_dir = campaign_dir / "queues" / "gm-list" / "completed" / "results"
    
    if not results_dir.exists():
        return discovery_map
        
    from cocli.core.utils import UNIT_SEP
    
    # Results are in shards like results/4/40.08/-104.97/phrase.usv
    # OR results/4/40.1_-105.0/phrase.usv
    for usv_file in results_dir.rglob("*.usv"):
        phrase = usv_file.stem # The filename is the search phrase slug
        
        # Provenance sanity check: if the filename is 'google_maps', skip it 
        # (those are our new enrichment receipts, not batch results)
        if phrase == "google_maps":
            continue
            
        try:
            content = usv_file.read_text()
            for line in content.splitlines():
                parts = line.split(UNIT_SEP)
                if parts and parts[0]:
                    pid = parts[0]
                    discovery_map.setdefault(pid, set()).add(phrase)
        except Exception:
            continue
    return discovery_map

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

    # 1. Build the Discovery Map (Multi-phrase recovery)
    discovery_map = get_discovery_map(campaign_name)
    logger.info(f"Discovery Map built: {len(discovery_map)} IDs indexed.")

    # 2. Initialize Enrichment Queue
    enrichment_queue = get_queue_manager("enrichment", queue_type="enrichment", campaign_name=campaign_name, use_cloud=True)

    manager = ProspectsIndexManager(campaign_name)
    companies_dir = get_companies_dir()
    
    created_count = 0
    updated_count = 0
    tagged_count = 0
    enqueued_count = 0
    
    prospects = list(manager.read_all_prospects())
    logger.info(f"Loaded {len(prospects)} prospects from index.")

    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

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
            # Ensure name is valid for pydantic (min 3 chars)
            safe_name = prospect.name or slug
            if len(safe_name) < 3:
                safe_name = slug
                
            company_obj = Company(
                name=safe_name,
                slug=slug,
                tags=[campaign_name]
            )
            is_new = True
            # IMMEDIATELY save to establish _index.md
            if not dry_run:
                company_obj.save()
        
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
            
        if company_obj.name != prospect.name and prospect.name:
            logger.info(f"Syncing name for {slug}: {company_obj.name} -> {prospect.name}")
            company_obj.name = prospect.name
            updated = True

        # NEW: Exhaustive Sync via Field Mirroring
        # We sync everything from the prospect model to the company model if the field names match
        prospect_data = prospect.model_dump()
        for field, value in prospect_data.items():
            if value is None or value == "" or value == 0:
                continue
                
            # Handle special field name mappings (Prospect -> Company)
            target_field = field
            if field == "phone":
                target_field = "phone_number"
            if field == "zip":
                target_field = "zip_code"
            if field == "website":
                target_field = "website_url"
            
            if hasattr(company_obj, target_field):
                current_val = getattr(company_obj, target_field)
                
                # Update if current is empty or if it's a high-priority identity field
                if current_val is None or current_val == "" or current_val == 0 or field in ["place_id", "name"]:
                    # Coerce value if necessary
                    if target_field == "phone_number":
                        value = str(value)
                    
                    if current_val != value:
                        logger.info(f"Syncing {target_field} for {slug}: {value}")
                        setattr(company_obj, target_field, value)
                        updated = True

        # Merge Categories (Google Maps categories are high quality)
        new_cats = [c for c in [prospect.first_category, prospect.second_category] if c]
        for cat in new_cats:
            if cat and cat not in company_obj.categories:
                company_obj.categories.append(cat)
                updated = True

        # 4. Ensure campaign tag
        if campaign_name not in company_obj.tags:
            logger.info(f"Adding campaign tag '{campaign_name}' to {slug}")
            company_obj.tags.append(campaign_name)
            updated = True
            tagged_count += 1
            
        # 5. Recovery: Discovery Phrase & Keyword Linkage
        discovery_tags = set([prospect.discovery_phrase, prospect.keyword])
        # Add all phrases from the discovery map (gm-list results)
        if prospect.place_id in discovery_map:
            discovery_tags.update(discovery_map[prospect.place_id])
            
        for dt in discovery_tags:
            if dt and dt not in company_obj.tags:
                logger.info(f"Adding discovery tag '{dt}' to {slug}")
                company_obj.tags.append(dt)
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

        # 6. ENQUEUE FOR ENRICHMENT (The "Pipe")
        if prospect.domain and prospect.name:
            try:
                from cocli.models.campaigns.queues.enrichment import EnrichmentTask
                
                # We use the Gold Standard model which handles its own Ordinant (Paths/Shards)
                task = EnrichmentTask(
                    domain=prospect.domain,
                    company_slug=slug,
                    campaign_name=campaign_name,
                    force_refresh=False
                )
                
                enrichment_queue.push(task)
                logger.info(f"Enqueued {slug} for enrichment (Shard: {task.shard})")
                enqueued_count += 1
            except Exception as e:
                logger.error(f"Failed to enqueue {slug}: {e}")

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
    console.print(f"Companies Enqueued: {enqueued_count}")
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
