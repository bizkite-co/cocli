import csv
import logging
from pathlib import Path
from typing import Iterator, Dict, Any, Iterable

from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_campaign_scraped_data_dir
from ..utils.usv_utils import USVDictReader, USVDictWriter

logger = logging.getLogger(__name__)

class ProspectsIndexManager:
    """
    Manages Google Maps prospects stored as individual files in a sharded index.
    Supports both legacy CSV (.csv) and modern USV (.usv) formats.
    Directory: data/campaigns/{campaign}/indexes/google_maps_prospects/
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        # Move from scraped_data to indexes
        scraped_dir = get_campaign_scraped_data_dir(campaign_name)
        self.index_dir = scraped_dir.parent / "indexes" / "google_maps_prospects"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # Inbox for legacy compatibility (new writes go to shards)
        self.inbox_dir = self.index_dir / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def get_file_path(self, place_id: str) -> Path:
        """
        Returns the existing file path for a given Place_ID, or the default new path (sharded).
        Checks for sharded .usv first, then legacy flat .usv/.csv.
        """
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        from ..core.sharding import get_place_id_shard
        shard = get_place_id_shard(place_id)
        sharded_path = self.index_dir / shard / f"{safe_filename}.usv"
        
        # 1. Prefer sharded path (Gold Standard)
        if sharded_path.exists():
            return sharded_path
            
        # 2. Check legacy locations (root and inbox)
        for ext in [".usv", ".csv"]:
            filename = f"{safe_filename}{ext}"
            inbox_path = self.inbox_dir / filename
            root_path = self.index_dir / filename
            
            if inbox_path.exists():
                return inbox_path
            if root_path.exists():
                return root_path
            
        # 3. Default for new files: ALWAYS SHARDED
        sharded_path.parent.mkdir(parents=True, exist_ok=True)
        return sharded_path

    def read_all_prospects(self) -> Iterator[GoogleMapsProspect]:
        """
        Yields prospects from the file index (shards, root, and inbox).
        Handles both .csv and .usv files.
        """
        if not self.index_dir.exists():
            return

        import itertools
        
        # Recursive scan for all USV/CSV files
        all_files = list(self.index_dir.rglob("*.usv")) + list(self.index_dir.rglob("*.csv"))
        
        # Remove duplicates (if both .csv and .usv exist for same place_id)
        seen_place_ids = set()
        
        # Sort: .usv before .csv, and sharded (more parts) before flat
        sorted_files = sorted(all_files, key=lambda p: (p.stem, p.suffix == ".csv", -len(p.parts)))
        
        for file_path in sorted_files:
            if not file_path.is_file():
                continue
                
            place_id_stem = file_path.stem
            if place_id_stem in seen_place_ids:
                continue
            seen_place_ids.add(place_id_stem)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader: Iterable[Dict[str, Any]]
                    if file_path.suffix == ".usv":
                        # Headerless USV: Provide explicit field order
                        ordered_fields = ["place_id", "company_slug", "name", "phone_1"]
                        all_fields = list(GoogleMapsProspect.model_fields.keys())
                        remaining = [f for f in all_fields if f not in ordered_fields]
                        fieldnames = ordered_fields + remaining
                        reader = USVDictReader(f, fieldnames=fieldnames)
                    else:
                        reader = csv.DictReader(f)
                        
                    for row in reader:
                        try:
                            model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
                            yield GoogleMapsProspect.model_validate(model_data)
                        except Exception as e:
                            logger.error(f"Error validating prospect in {file_path.name}: {e}")
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")

    def append_prospect(self, prospect_data: GoogleMapsProspect) -> bool:
        """
        Writes a single GoogleMapsProspect object to its sharded file in the index.
        Always writes in headerless USV format.
        """
        if not prospect_data.place_id:
            logger.warning(f"Prospect data missing place_id, cannot save to index. Skipping: {prospect_data.name or prospect_data.domain}")
            return False
        
        # Get path (will default to sharded .usv)
        file_path = self.get_file_path(prospect_data.place_id)
        
        # If it was a .csv, we migrate it to .usv
        if file_path.suffix == ".csv":
            old_path = file_path
            file_path = file_path.with_suffix(".usv")
            logger.info(f"Migrating {old_path.name} to USV")
        else:
            old_path = None
        
        try:
            # Ensure shard directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                logger.info(f"WRITING PROSPECT: {prospect_data.place_id} | processed_by: {prospect_data.processed_by}")
                f.write(prospect_data.to_usv())
            
            # Clean up old CSV if we migrated
            if old_path and old_path.exists():
                old_path.unlink()
                
            logger.debug(f"Saved prospect to index (USV): {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"Error writing prospect to index (place_id: {prospect_data.place_id}): {e}")
            return False

    def has_place_id(self, place_id: str) -> bool:
        """Checks if a given Place_ID already exists in the index (anywhere)."""
        if not place_id:
            return False
        
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        # Check shards, root, and inbox recursively
        for ext in [".usv", ".csv"]:
            if list(self.index_dir.rglob(f"{safe_filename}{ext}")):
                return True
        return False