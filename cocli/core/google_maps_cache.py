
import csv
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from ..models.google_maps import GoogleMapsData
from .config import get_cocli_base_dir

class GoogleMapsCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "google_maps_cache.csv"
        self.data: Dict[str, GoogleMapsData] = {}
        self._load_data()

    def _load_data(self):
        if not self.cache_file.exists():
            return

        with open(self.cache_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Convert numeric and datetime fields
                for field in ['Reviews_count']:
                    if row.get(field):
                        try:
                            row[field] = int(row[field])
                        except (ValueError, TypeError):
                            row[field] = None
                for field in ['Average_rating', 'Latitude', 'Longitude']:
                    if row.get(field):
                        try:
                            row[field] = float(row[field])
                        except (ValueError, TypeError):
                            row[field] = None
                for field in ['created_at', 'updated_at']:
                    if row.get(field):
                        try:
                            row[field] = datetime.fromisoformat(row[field])
                        except (ValueError, TypeError):
                            row[field] = None

                model_data = {k: v for k, v in row.items() if k in GoogleMapsData.model_fields}
                if model_data.get("Place_ID"):
                    self.data[model_data["Place_ID"]] = GoogleMapsData(**model_data)

    def get_by_place_id(self, place_id: str) -> Optional[GoogleMapsData]:
        return self.data.get(place_id)

    def add_or_update(self, item: GoogleMapsData):
        if item.Place_ID:
            item.updated_at = datetime.utcnow()
            self.data[item.Place_ID] = item

    def save(self):
        with open(self.cache_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = GoogleMapsData.model_fields.keys()
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                writer.writerow(item.model_dump())
