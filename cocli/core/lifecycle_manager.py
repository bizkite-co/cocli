import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Iterator
from datetime import datetime, UTC

from .paths import paths
from .utils import UNIT_SEP
from ..models.lifecycle import LifecycleItem

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

        # 1. Scan gm-details completions
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
                            enriched_at=None
                        )
                    lifecycle_data[place_id].details_at = mtime
                
                if i % 1000 == 0:
                    yield {"phase": "Details Queue", "current": i, "total": total_files, "label": place_id}

        # 2. Scan gm-list results
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

        # 3. Scan Company folders
        from .config import get_companies_dir
        companies_root = get_companies_dir()
        
        entries = [e for e in os.scandir(companies_root) if e.is_dir()]
        total_entries = len(entries)

        for i, entry in enumerate(entries):
            slug = entry.name
            enrichments_dir = Path(entry.path) / "enrichments"
            
            if i % 1000 == 0:
                yield {"phase": "Company Folders", "current": i, "total": total_entries, "label": slug}

            if not enrichments_dir.exists():
                continue
                
            maps_receipt = enrichments_dir / "google_maps.usv"
            receipt_pid: Optional[str] = None
            if maps_receipt.exists():
                try:
                    with open(maps_receipt, "r", encoding="utf-8") as rf:
                        rf.readline() # skip header
                        data_line = rf.readline()
                        if data_line:
                            parts = data_line.split(UNIT_SEP)
                            if len(parts) > 0 and parts[0].startswith("ChIJ"):
                                receipt_pid = parts[0]
                                mtime = datetime.fromtimestamp(maps_receipt.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                                if receipt_pid not in lifecycle_data:
                                    lifecycle_data[receipt_pid] = LifecycleItem(
                                        place_id=receipt_pid,
                                        scraped_at=None,
                                        details_at=None,
                                        enriched_at=None
                                    )
                                if not lifecycle_data[receipt_pid].details_at:
                                    lifecycle_data[receipt_pid].details_at = mtime
                except Exception:
                    pass

            website_md = enrichments_dir / "website.md"
            if website_md.exists() and receipt_pid:
                mtime = datetime.fromtimestamp(website_md.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                if receipt_pid not in lifecycle_data:
                    lifecycle_data[receipt_pid] = LifecycleItem(
                        place_id=receipt_pid,
                        scraped_at=None,
                        details_at=None,
                        enriched_at=None
                    )
                lifecycle_data[receipt_pid].enriched_at = mtime

        # 4. Write to USV and Save Datapackage
        self.index_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        sorted_pids = sorted(lifecycle_data.keys())
        
        # Save the frictionless schema BEFORE writing data so search_service can find it if triggered
        LifecycleItem.save_datapackage(self.index_dir)

        with open(self.index_path, "w", encoding="utf-8") as f_handle:
            for pid in sorted_pids:
                f_handle.write(lifecycle_data[pid].to_usv())
                count += 1
        
        logger.info(f"Compiled lifecycle index for {self.campaign_name}: {count} records")
        yield count
