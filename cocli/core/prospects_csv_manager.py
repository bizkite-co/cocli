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
    Manages Google Maps prospects stored as individual files in a file-based index.
    Supports both legacy CSV (.csv) and modern USV (.usv) formats.
    Directory: data/campaigns/{campaign}/indexes/google_maps_prospects/
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        # Move from scraped_data to indexes
        scraped_dir = get_campaign_scraped_data_dir(campaign_name)
        self.index_dir = scraped_dir.parent / "indexes" / "google_maps_prospects"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # Inbox for new/untriaged prospects
        self.inbox_dir = self.index_dir / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def get_file_path(self, place_id: str) -> Path:
        """
        Returns the existing file path for a given Place_ID, or the default new path.
        Checks for .usv first, then .csv.
        """
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        
        # Try finding existing file
        for ext in [".usv", ".csv"]:
            filename = f"{safe_filename}{ext}"
            inbox_path = self.inbox_dir / filename
            root_path = self.index_dir / filename
            
            if inbox_path.exists():
                return inbox_path
            if root_path.exists():
                return root_path
            
        # Default for new files (always .usv)
        return self.inbox_dir / f"{safe_filename}.usv"

    def read_all_prospects(self) -> Iterator[GoogleMapsProspect]:
        """
        Yields prospects from the file index (both root and inbox).
        Handles both .csv and .usv files.
        """
        if not self.index_dir.exists():
            return

        import itertools
        
        # Scan root and inbox for both extensions
        root_files = list(self.index_dir.glob("*.usv")) + list(self.index_dir.glob("*.csv"))
        inbox_files = list(self.inbox_dir.glob("*.usv")) + list(self.inbox_dir.glob("*.csv"))
        
        # Remove duplicates (if both .csv and .usv exist for same place_id)
        # We prefer .usv
        seen_place_ids = set()
        
        # Sort so .usv comes before .csv
        all_files = sorted(itertools.chain(root_files, inbox_files), key=lambda p: (p.stem, p.suffix == ".csv"))
        
        for file_path in all_files:
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
                            # Only include fields that are part of the GoogleMapsProspect model
                            model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
                            yield GoogleMapsProspect.model_validate(model_data)
                        except Exception as e:
                            logger.error(f"Error validating prospect in {file_path.name}: {e}")
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")

    def append_prospect(self, prospect_data: GoogleMapsProspect) -> bool:
        """
        Writes a single GoogleMapsProspect object to its individual file in the index.
        Always writes in USV format.
        """
        if not prospect_data.place_id:
            logger.warning(f"Prospect data missing place_id, cannot save to index. Skipping: {prospect_data.name or prospect_data.domain}")
            return False
        
        # Get path (will default to .usv if new, or return existing .csv/.usv)
        file_path = self.get_file_path(prospect_data.place_id)
        
        # If it was a .csv, we should migrate it to .usv
        if file_path.suffix == ".csv":
            old_path = file_path
            file_path = file_path.with_suffix(".usv")
            logger.info(f"Migrating {old_path.name} to USV")
            # We'll delete the old one after successful write
        else:
            old_path = None
        
        try:
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
        """Checks if a given Place_ID already exists in the index (.csv or .usv)."""
        if not place_id:
            return False
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        for ext in [".usv", ".csv"]:
            if (self.index_dir / f"{safe_filename}{ext}").exists():
                return True
            if (self.inbox_dir / f"{safe_filename}{ext}").exists():
                return True
        return False


