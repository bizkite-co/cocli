import os
import logging
from pathlib import Path
from typing import Dict, Any, Iterator
from datetime import datetime, UTC

from .paths import paths
from .utils import UNIT_SEP
from ..models.campaigns.indexes.lifecycle import LifecycleItem

logger = logging.getLogger(__name__)

class LifecycleManager:
    """
    Manages the compilation and retrieval of the campaign-level lifecycle index.
    Maps PlaceID to Scraped, Details, and Enriched timestamps.
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.campaign_path = paths.campaign(campaign_name)
        # lifecycle.usv is inside the lifecycle index folder
        self.index_dir = self.campaign_path.path / "indexes" / "lifecycle"
        self.index_path = self.index_dir / "lifecycle.usv"

    def compile(self) -> Iterator[Any]:
        """
        Compiles the lifecycle.usv from local completed queues and company folders.
        Yields progress updates. Final yield is the total record count.
        """
        # place_id -> LifecycleItem
        lifecycle_data: Dict[str, LifecycleItem] = {}
        
        # Helper Map: slug -> place_id (built from company folders)
        slug_to_pid: Dict[str, str] = {}
        domain_to_pid: Dict[str, str] = {}

        # 1. Build slug_to_pid and domain_to_pid maps from both company folders and checkpoint index
        from .config import get_companies_dir
        companies_root = get_companies_dir()
        
        entries = [e for e in os.scandir(companies_root) if e.is_dir()]
        for i, entry in enumerate(entries):
            slug = entry.name
            maps_receipt = Path(entry.path) / "enrichments" / "google_maps.usv"
            if maps_receipt.exists():
                try:
                    with open(maps_receipt, "r", encoding="utf-8") as rf:
                        rf.readline() # skip header
                        data_line = rf.readline()
                        if data_line:
                            parts = data_line.split(UNIT_SEP)
                            if len(parts) > 0 and parts[0].startswith("ChIJ"):
                                pid = parts[0]
                                slug_to_pid[slug] = pid
                                # domain is typically at index 21 in GoogleMapsProspect
                                if len(parts) >= 22:
                                    domain = parts[21].strip()
                                    if domain:
                                        domain_to_pid[domain] = pid

                                if pid not in lifecycle_data:
                                    lifecycle_data[pid] = LifecycleItem(
                                        place_id=pid,
                                        scraped_at=None,
                                        details_at=None,
                                        enqueued_at=None,
                                        enriched_at=None
                                    )
                except Exception:
                    pass
            
            if i % 1000 == 0:
                yield {"phase": "Building Slug Map (Folders)", "current": i, "total": len(entries), "label": slug}

        # 1b. Augmented mapping from Checkpoint Index
        from .text_utils import extract_domain
        checkpoint_path = self.campaign_path.index("google_maps_prospects").checkpoint
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as cf:
                    for line in cf:
                        parts = line.split(UNIT_SEP)
                        if len(parts) >= 31:
                            pid = parts[0].strip()
                            slug_val = parts[1].strip()
                            website = parts[20].strip()
                            domain_val = extract_domain(website) if website else None
                            
                            if pid.startswith("ChIJ"):
                                if slug_val:
                                    slug_to_pid[slug_val] = pid
                                if domain_val:
                                    domain_to_pid[domain_val] = pid
                                if pid not in lifecycle_data:
                                    lifecycle_data[pid] = LifecycleItem(
                                        place_id=pid,
                                        scraped_at=None,
                                        details_at=None,
                                        enqueued_at=None,
                                        enriched_at=None
                                    )
            except Exception as e:
                logger.warning(f"Failed to scan checkpoint for slug mapping: {e}")

        # 2. Scan gm-details completions
        details_dir = self.campaign_path.queue("gm-details").completed
        if details_dir.exists():
            files = list(details_dir.glob("*.json"))
            total_files = len(files)
            for i, f in enumerate(files):
                place_id = f.stem
                if place_id.startswith("ChIJ"):
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                    if place_id not in lifecycle_data:
                        lifecycle_data[place_id] = LifecycleItem(
                            place_id=place_id,
                            scraped_at=None,
                            details_at=None,
                            enqueued_at=None,
                            enriched_at=None
                        )
                    lifecycle_data[place_id].details_at = mtime
                
                if i % 1000 == 0:
                    yield {"phase": "Details Queue", "current": i, "total": total_files, "label": place_id}

        # 3. Scan gm-list results
        list_results_dir = self.campaign_path.queue("gm-list").completed / "results"
        if list_results_dir.exists():
            usv_files = list(list_results_dir.rglob("*.usv"))
            total_usv = len(usv_files)
            for i, f in enumerate(usv_files):
                try:
                    file_date = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                    with open(f, "r", encoding="utf-8") as handle:
                        for line in handle:
                            parts = line.split(UNIT_SEP)
                            if len(parts) >= 31:
                                place_id = parts[30].strip()
                                created_at_raw = parts[4].strip()
                                
                                if place_id.startswith("ChIJ"):
                                    if place_id not in lifecycle_data:
                                        lifecycle_data[place_id] = LifecycleItem(
                                            place_id=place_id,
                                            scraped_at=None,
                                            details_at=None,
                                            enqueued_at=None,
                                            enriched_at=None
                                        )
                                    
                                    # Prefer the created_at from the scraper result
                                    scrape_date = file_date
                                    if created_at_raw and len(created_at_raw) >= 10:
                                        scrape_date = created_at_raw[:10]
                                    
                                    existing = lifecycle_data[place_id].scraped_at
                                    if not existing or scrape_date < existing:
                                        lifecycle_data[place_id].scraped_at = scrape_date
                except Exception as e:
                    logger.warning(f"Failed to parse result file {f.name}: {e}")
                
                if i % 500 == 0:
                    yield {"phase": "Scraped Results", "current": i, "total": total_usv, "label": f.name}

        # 4. Scan Enrichment Queue (Pending)
        enqueued_count = 0
        enrichment_pending_dir = self.campaign_path.queue("enrichment").pending
        if enrichment_pending_dir.exists():
            # Pending tasks are in shard/domain/task.json
            task_files = list(enrichment_pending_dir.rglob("task.json"))
            total_tasks = len(task_files)
            for i, f in enumerate(task_files):
                # For enrichment queue, task_id is domain, parent folder is domain
                domain = f.parent.name
                if domain in domain_to_pid:
                    pid = domain_to_pid[domain]
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                    if pid in lifecycle_data:
                        lifecycle_data[pid].enqueued_at = mtime
                        enqueued_count += 1
                
                if i % 500 == 0:
                    yield {"phase": "Enrichment Queue", "current": i, "total": total_tasks, "label": domain}
        
        logger.info(f"Populated enqueued_at for {enqueued_count} records.")

        # 5. Final pass on Company folders for Enriched date and detailed check
        for i, entry in enumerate(entries):
            slug = entry.name
            if slug not in slug_to_pid:
                continue
            
            pid = slug_to_pid[slug]
            enrichments_dir = Path(entry.path) / "enrichments"
            
            website_md = enrichments_dir / "website.md"
            if website_md.exists():
                mtime = datetime.fromtimestamp(website_md.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                if pid in lifecycle_data:
                    lifecycle_data[pid].enriched_at = mtime

        # 6. Write to USV and Save Datapackage
        self.index_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        sorted_pids = sorted(lifecycle_data.keys())
        
        # Save the frictionless schema BEFORE writing data so search_service can find it if triggered
        LifecycleItem.write_datapackage(self.campaign_name)

        with open(self.index_path, "w", encoding="utf-8") as f_handle:
            for pid in sorted_pids:
                f_handle.write(lifecycle_data[pid].to_usv())
                count += 1
        
        logger.info(f"Compiled lifecycle index for {self.campaign_name}: {count} records")
        yield count
