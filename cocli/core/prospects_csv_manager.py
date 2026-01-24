import csv
import logging
from pathlib import Path
from typing import Iterator

from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_campaign_scraped_data_dir

logger = logging.getLogger(__name__)

class ProspectsIndexManager:
    """
    Manages Google Maps prospects stored as individual CSV files in a file-based index.
    Directory: data/campaigns/{campaign}/indexes/google_maps_prospects/
    Each file is named {Place_ID}.csv and contains a single row with header.
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
        Returns the file path for a given Place_ID.
        Logic:
        1. If exists in inbox, return inbox path.
        2. If exists in root (processed), return root path.
        3. If new, return inbox path (default write location).
        """
        # Sanitize filename just in case, though Place_ID is usually safe
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        filename = f"{safe_filename}.csv"
        
        inbox_path = self.inbox_dir / filename
        root_path = self.index_dir / filename
        
        if inbox_path.exists():
            return inbox_path
        
        if root_path.exists():
            return root_path
            
        # Default for new files
        return inbox_path

    def read_all_prospects(self) -> Iterator[GoogleMapsProspect]:
        """
        Yields prospects from the file index (both root and inbox).
        Changed from returning a List to an Iterator for memory efficiency with large datasets.
        """
        if not self.index_dir.exists():
            return

        # Chain iterators for root and inbox
        import itertools
        
        # Scan root (excluding directories like 'inbox')
        root_files = [p for p in self.index_dir.glob("*.csv") if p.is_file()]
        inbox_files = [p for p in self.inbox_dir.glob("*.csv") if p.is_file()]
        
        for file_path in itertools.chain(root_files, inbox_files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
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
        This effectively acts as "Latest Write Wins" or "Upsert".
        """
        if not prospect_data.Place_ID:
            logger.warning(f"Prospect data missing Place_ID, cannot save to index. Skipping: {prospect_data.Name or prospect_data.Domain}")
            return False
        
        file_path = self.get_file_path(prospect_data.Place_ID)
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = list(GoogleMapsProspect.model_fields.keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(prospect_data.model_dump(by_alias=False))
            
            logger.debug(f"Saved prospect to index: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"Error writing prospect to index (Place_ID: {prospect_data.Place_ID}): {e}")
            return False

    def has_place_id(self, place_id: str) -> bool:
        """Checks if a given Place_ID already exists in the index."""
        if not place_id:
            return False
        return self.get_file_path(place_id).exists()


