import logging
from typing import Dict
from datetime import datetime, UTC

from .paths import paths
from .utils import UNIT_SEP

logger = logging.getLogger(__name__)

class LifecycleManager:
    """
    Manages the compilation and retrieval of the campaign-level lifecycle index.
    Maps PlaceID to Scraped and Details timestamps.
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.campaign_path = paths.campaign(campaign_name)
        self.index_path = self.campaign_path.lifecycle

    def compile(self) -> int:
        """
        Compiles the lifecycle.usv from local completed queues.
        Returns the number of records indexed.
        """
        lifecycle_data: Dict[str, Dict[str, str]] = {}

        # 1. Scan gm-details completions
        details_dir = self.campaign_path.queue("gm-details").completed
        if details_dir.exists():
            for f in details_dir.glob("*.json"):
                place_id = f.stem
                if place_id.startswith("ChIJ"):
                    try:
                        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime('%Y-%m-%d')
                        if place_id not in lifecycle_data:
                            lifecycle_data[place_id] = {}
                        lifecycle_data[place_id]["details"] = mtime
                    except Exception as e:
                        logger.warning(f"Failed to read mtime for {f.name}: {e}")

        # 2. Scan gm-list results for scraped_at
        list_results_dir = self.campaign_path.queue("gm-list").completed / "results"
        if list_results_dir.exists():
            for f in list_results_dir.rglob("*.usv"):
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

        # 3. Write to USV
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
                    '' # enriched_at
                ])
                f_handle.write(f"{line}\n")
                count += 1
        
        logger.info(f"Compiled lifecycle index for {self.campaign_name}: {count} records")
        return count
