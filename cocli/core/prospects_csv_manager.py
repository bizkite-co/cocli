import csv
import logging
from typing import List, Set

from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_campaign_scraped_data_dir

logger = logging.getLogger(__name__)

class ProspectsCSVManager:
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.prospects_csv_path = get_campaign_scraped_data_dir(campaign_name) / "prospects.csv"
        self._existing_place_ids: Set[str] = set()
        self._load_existing_place_ids()

    def _load_existing_place_ids(self) -> None:
        """Loads Place_IDs from an existing prospects.csv for deduplication."""
        if self.prospects_csv_path.exists():
            try:
                with open(self.prospects_csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'Place_ID' in row and row['Place_ID']:
                            self._existing_place_ids.add(row['Place_ID'])
                logger.debug(f"Loaded {len(self._existing_place_ids)} existing Place_IDs from {self.prospects_csv_path}")
            except Exception as e:
                logger.warning(f"Error reading existing prospects.csv for deduplication: {e}. Proceeding as if file is new.")
                self._existing_place_ids.clear()

    def read_all_prospects(self) -> List[GoogleMapsProspect]:
        """Reads all prospects from the CSV and returns them as a list of GoogleMapsProspect objects."""
        prospects: List[GoogleMapsProspect] = []
        if not self.prospects_csv_path.exists():
            return prospects

        try:
            with open(self.prospects_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Only include fields that are part of the GoogleMapsProspect model
                        model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
                        prospects.append(GoogleMapsProspect.model_validate(model_data))
                    except Exception as e:
                        logger.error(f"Error validating row from prospects.csv: {row}. Error: {e}")
            logger.debug(f"Read {len(prospects)} prospects from {self.prospects_csv_path}")
        except Exception as e:
            logger.error(f"Error reading prospects.csv: {e}")
        return prospects

    def append_prospect(self, prospect_data: GoogleMapsProspect) -> bool:
        """
        Appends a single GoogleMapsProspect object to the CSV, performing Place_ID deduplication.
        Returns True if the prospect was written, False if skipped (due to duplicate Place_ID or missing Place_ID).
        """
        if not prospect_data.Place_ID:
            logger.warning(f"Prospect data missing Place_ID, cannot deduplicate. Skipping: {prospect_data.Name or prospect_data.Domain}")
            return False
        
        if prospect_data.Place_ID in self._existing_place_ids:
            logger.debug(f"Skipping duplicate prospect (Place_ID: {prospect_data.Place_ID}): {prospect_data.Name}")
            return False
        
        # Determine if header needs to be written
        write_header = not self.prospects_csv_path.exists() or self.prospects_csv_path.stat().st_size == 0
        
        try:
            with open(self.prospects_csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = list(GoogleMapsProspect.model_fields.keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if write_header:
                    writer.writeheader()
                
                writer.writerow(prospect_data.model_dump(by_alias=False)) # Use by_alias=False to use field names directly
            
            self._existing_place_ids.add(prospect_data.Place_ID)
            logger.debug(f"Appended new prospect (Place_ID: {prospect_data.Place_ID}): {prospect_data.Name}")
            return True
        except Exception as e:
            logger.error(f"Error appending prospect to CSV (Place_ID: {prospect_data.Place_ID}): {e}")
            return False

    def has_place_id(self, place_id: str) -> bool:
        """Checks if a given Place_ID already exists in the manager's loaded set."""
        return place_id in self._existing_place_ids
