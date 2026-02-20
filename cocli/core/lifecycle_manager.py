import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Iterator
from datetime import datetime, UTC

from .paths import paths
from .utils import UNIT_SEP

logger = logging.getLogger(__name__)

class LifecycleManager:
    """
    Manages the compilation and retrieval of the campaign-level lifecycle index.
    Maps PlaceID to Scraped, Details, and Enriched timestamps.
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.campaign_path = paths.campaign(campaign_name)
        self.index_path = self.campaign_path.lifecycle

    def compile(self) -> Iterator[Any]:
        """
        Compiles the lifecycle.usv from local completed queues and company folders.
        Yields progress updates: {"phase": str, "current": int, "total": int, "label": str}
        Final yield is the total record count (int).
        """
        # place_id -> {"scraped": str, "details": str, "enriched": str}
        lifecycle_data: Dict[str, Dict[str, str]] = {}

        # 1. Scan gm-details completions
        details_dir = self.campaign_path.queue("gm-details").completed
        if details_dir.exists():
            files = list(details_dir.glob("*.json"))
            total_files = len(files)
            for i, f in enumerate(files):
                place_id = f.stem
                if place_id.startswith("ChIJ"):
                    try:
                        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                        if place_id not in lifecycle_data:
                            lifecycle_data[place_id] = {}
                        lifecycle_data[place_id]["details"] = mtime
                    except Exception as e:
                        logger.warning(f"Failed to read mtime for {f.name}: {e}")
                
                if i % 500 == 0:
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
                                        lifecycle_data[place_id] = {}
                                    
                                    scrape_date = file_date
                                    if created_at_raw and len(created_at_raw) >= 10:
                                        scrape_date = created_at_raw[:10]
                                    
                                    existing = lifecycle_data[place_id].get("scraped")
                                    if not existing or scrape_date < existing:
                                        lifecycle_data[place_id]["scraped"] = scrape_date
                except Exception as e:
                    logger.warning(f"Failed to parse result file {f.name}: {e}")
                
                if i % 100 == 0:
                    yield {"phase": "Scraped Results", "current": i, "total": total_usv, "label": f.name}

        # 3. Scan Company folders
        from .config import get_companies_dir
        companies_root = get_companies_dir()
        
        # We need to list first to get a total for the progress bar
        entries = [e for e in os.scandir(companies_root) if e.is_dir()]
        total_entries = len(entries)

        for i, entry in enumerate(entries):
            slug = entry.name
            enrichments_dir = Path(entry.path) / "enrichments"
            
            if i % 500 == 0:
                yield {"phase": "Company Folders", "current": i, "total": total_entries, "label": slug}

            if not enrichments_dir.exists():
                continue
                
            maps_receipt = enrichments_dir / "google_maps.usv"
            receipt_pid: Optional[str] = None
            if maps_receipt.exists():
                try:
                    with open(maps_receipt, "r", encoding="utf-8") as rf:
                        header = rf.readline()
                        data_line = rf.readline()
                        if data_line:
                            parts = data_line.split(UNIT_SEP)
                            if len(parts) > 0 and parts[0].startswith("ChIJ"):
                                receipt_pid = parts[0]
                                mtime = datetime.fromtimestamp(maps_receipt.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                                if receipt_pid not in lifecycle_data:
                                    lifecycle_data[receipt_pid] = {}
                                if not lifecycle_data[receipt_pid].get("details"):
                                    lifecycle_data[receipt_pid]["details"] = mtime
                except Exception:
                    pass

            website_md = enrichments_dir / "website.md"
            if website_md.exists() and receipt_pid:
                try:
                    mtime = datetime.fromtimestamp(website_md.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                    if receipt_pid not in lifecycle_data:
                        lifecycle_data[receipt_pid] = {}
                    lifecycle_data[receipt_pid]["enriched"] = mtime
                except Exception:
                    pass

        # 4. Write to USV
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        sorted_pids = sorted(lifecycle_data.keys())
        
        with open(self.index_path, "w", encoding="utf-8") as f_handle:
            header = UNIT_SEP.join(["place_id", "scraped_at", "details_at", "enriched_at"])
            f_handle.write(f"{header}\n")
            for pid in sorted_pids:
                dates = lifecycle_data[pid]
                line = UNIT_SEP.join([
                    pid, 
                    dates.get('scraped', ''), 
                    dates.get('details', ''), 
                    dates.get('enriched', '')
                ])
                f_handle.write(f"{line}\n")
                count += 1
        
        logger.info(f"Compiled lifecycle index for {self.campaign_name}: {count} records")
        yield count
